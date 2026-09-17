"""Lab 2 — budgeted hyperparameter study on managed compute.

Run:  make tune                          (12 trials, spot, 150 THB budget)
      make seeds CONFIG='{"n_estimators":300,...}'   (seed variance for your chosen config)

How it works — one Vertex custom job per trial:

    this script (your laptop)                        managed job (Vertex, spot)
    ─────────────────────────                        ──────────────────────────
    pick next configs from SEARCH_SPACE
    adapter.submit_training(image, args) ───────────▶ dvc pull && python -m src.train --no-track ...
    adapter.wait_training(job_id)                     writes metrics.json + model.joblib
                                          ◀─────────── under /gcs/<bucket>/... (auto-mounted)
    adapter.download_key(...) the results
    log params/metrics/cost/lineage to MLflow  ← runs on YOUR disk. cloud.env.example says it
    save checkpoint after every trial            itself: "self-hosted MLflow... use sqlite
                                                  locally" — a job's disk is destroyed when it
                                                  ends, so tracking never happens inside one.
    an interruption (Ctrl+C, spot preemption, laptop sleep) costs at most the trial in
    flight — finished trials are already in mlflow.db and the checkpoint file.

The budget is enforced, not advisory. The study stops when projected spend would exceed
it, and reports what it did not get to.

`--instance local` runs the trial as a local subprocess at zero cost, for debugging the
orchestration logic only — a study whose cost column is all zeros has not run on managed
compute (this is called out by name in the grading notes).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import yaml

from src import config, costs, data, seeds
from src.train import git_commit

# Three hyperparameters, each changing the forest in a genuinely different way, at 2-3
# settings each = 12 trials (2 x 3 x 2), satisfying "at least 12 trials, varying at least
# three hyperparameters" as a full factorial rather than a truncated bigger grid (which
# would silently under-vary whichever key sorts last).
#   n_estimators       ensemble size: mainly a cost/variance knob, cheap to include as a
#                       real axis rather than holding it fixed
#   max_depth           capacity: how complex any one tree may get     (underfit <-> overfit)
#   min_samples_leaf    smoothing: evidence required before a leaf decides
SEARCH_SPACE: dict[str, list] = {
    "n_estimators": [100, 300],
    "max_depth": [4, 8, 12],
    "min_samples_leaf": [1, 5],
}

RETRYABLE_WORDS = ("preempt", "spot", "stockout", "resource", "capacity", "zone_resource",
                   "cancelled")
MAX_ATTEMPTS = 3


# --- study design ------------------------------------------------------------------------------
def grid(space: dict[str, list]) -> list[dict]:
    keys = list(space)
    return [dict(zip(keys, values)) for values in itertools.product(*(space[k] for k in keys))]


def trial_key(params: dict) -> str:
    return hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]


def data_version(raw_path: Path) -> str:
    """The DVC hash for data/raw, from the committed pointer file `data/raw.dvc`."""
    dvc_file = raw_path.parents[1] / "raw.dvc"          # data/raw.dvc, sibling of data/raw/
    if dvc_file.exists():
        outs = yaml.safe_load(dvc_file.read_text())["outs"]
        return outs[0]["md5"]
    return data.data_fingerprint(raw_path)               # fallback if DVC isn't set up yet


# --- args / checkpoint --------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 Lab 2 — budgeted study")
    p.add_argument("--trials", type=int, default=12, help="minimum 12 for the lab")
    p.add_argument("--budget-thb", type=float, default=150.0)
    p.add_argument("--instance", default="n1-standard-4", help="key into src/costs.py PRICE_TABLE")
    p.add_argument("--spot", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--seeds", default=None,
                   help="with --config: comma list of seeds for a variance study")
    p.add_argument("--config", default=None, help="JSON hyperparameters for a seed-variance study")
    p.add_argument("--experiment", default="itcs355-lab2")
    p.add_argument("--image-file", type=Path, default=Path("reports/lab2-image.json"))
    p.add_argument("--checkpoint", type=Path, default=Path("reports/tune_checkpoint.json"),
                   help="Resume file. An interruption should cost minutes, not the run.")
    p.add_argument("--allow-dirty", action="store_true",
                   help="Skip the uncommitted-changes check (lineage will be wrong — debug only)")
    return p.parse_args()


def load_checkpoint(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"trials": {}, "spent_thb": 0.0}


def save_checkpoint(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)                                     # atomic — never a half-written file


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def build_trials(args: argparse.Namespace) -> tuple[str, list[dict]]:
    if args.config:
        fixed = json.loads(args.config)
        seed_list = [int(s) for s in (args.seeds or "11,22,33,44,55").split(",")]
        return "seed-variance", [{**fixed, "seed": s} for s in seed_list]
    combos = grid(SEARCH_SPACE)[: args.trials]
    return "grid", [{**c, "seed": args.seed} for c in combos]


def run_local(module: str, hyperparams: dict, out_dir: Path) -> dict:
    """--instance local debug path: same command shape, no cloud job, zero cost."""
    cli = [sys.executable, "-m", module, "--no-track",
           "--metrics-out", str(out_dir / "metrics.json"), "--model-out", str(out_dir / "model")]
    for k, v in hyperparams.items():
        if isinstance(v, bool):
            if v:
                cli.append(f"--{k.replace('_', '-')}")
        else:
            cli += [f"--{k.replace('_', '-')}", str(v)]
    started = time.perf_counter()
    subprocess.run(cli, check=True, stdout=subprocess.DEVNULL, cwd=config.REPO_ROOT)
    return {"job_id": "local", "state": "LOCAL", "succeeded": True,
            "duration_s": time.perf_counter() - started, "queued_s": 0.0, "error": ""}


def record(key: str, params: dict, result: dict, out_dir: Path, rate: float, lineage: dict,
          args: argparse.Namespace, study: str, attempts: int) -> float:
    metrics = json.loads((out_dir / "metrics.json").read_text())
    model = joblib.load(out_dir / "model" / "model.joblib")
    cost = result["duration_s"] / 3600.0 * rate

    hyper = {k: v for k, v in params.items() if k != "seed"}
    with mlflow.start_run(run_name=f"{study}-{key}") as run:
        mlflow.log_params({**hyper, "seed": params["seed"], "instance": args.instance,
                           "spot": args.spot})
        mlflow.log_metrics({
            "val_roc_auc": metrics["val_roc_auc"], "val_pr_auc": metrics["val_pr_auc"],
            "test_roc_auc": metrics["test_roc_auc"], "test_pr_auc": metrics["test_pr_auc"],
            "duration_s": round(result["duration_s"], 1),      # billed wall clock
            "queued_s": round(result["queued_s"], 1),
            "cost_thb": round(cost, 4),
        })
        mlflow.set_tags({**lineage, "training_job_id": result["job_id"], "trial_key": key,
                         "study": study, "attempts": attempts, "output_key": f"lab2/trials/{key}",
                         "lab": "2"})
        mlflow.sklearn.log_model(model, name="model",
                                 skops_trusted_types=["sklearn.tree._tree.Tree"])
        run_id = run.info.run_id
    log(f"  logged run {run_id[:8]}  val_roc_auc={metrics['val_roc_auc']:.4f} "
        f"test_roc_auc={metrics['test_roc_auc']:.4f}  billed={result['duration_s']:.0f}s "
        f"cost={cost:.4f} THB")
    return cost


def main() -> None:
    args = parse_args()
    cfg = config.load(strict=False)
    remote = args.instance != "local"
    study, trials = build_trials(args)

    if remote and not args.allow_dirty:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "src", "cloudlayer", "Dockerfile",
             "requirements.txt", ".dvc", "data/raw.dvc"],
            capture_output=True, text=True).stdout.strip()
        if dirty:
            sys.exit("Uncommitted changes in code/data that go into the image or lineage:\n" +
                     dirty + "\nCommit, then `make image-lab2`, then run again.")

    commit = git_commit()
    image_ref = "local"
    if remote:
        if not args.image_file.exists():
            sys.exit(f"{args.image_file} missing. Run `make image-lab2` first.")
        image = json.loads(args.image_file.read_text())
        if image["git_commit"] != commit:
            sys.exit(f"Image was built from {image['git_commit'][:8]} but HEAD is {commit[:8]}.\n"
                     "Run `make image-lab2` so the image matches the code you are logging.")
        image_ref = image["image_uri"]

    rate = 0.0 if not remote else costs.hourly_rate(cfg.provider, args.instance, spot=args.spot)
    lineage = {"git_commit": commit, "data_version": data_version(cfg.raw_path),
               "image_digest": image_ref.split("@", 1)[-1] if "@" in image_ref else image_ref}

    adapter = None
    if remote:
        from cloudlayer.factory import get_adapter
        adapter = get_adapter(cfg)

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    mlflow.set_experiment(args.experiment)

    state = load_checkpoint(args.checkpoint)
    state.setdefault("trials", {})
    log(f"study={study} trials={len(trials)} instance={args.instance} spot={args.spot} "
        f"rate={rate:.3f} THB/h budget={args.budget_thb} spent_so_far={state['spent_thb']:.4f}")

    pending = [t for t in trials if state["trials"].get(trial_key(t), {}).get("status") != "done"]
    for t in trials:
        if t not in pending:
            log(f"trial {trial_key(t)}: already done, skipping (resumed from checkpoint)")

    est_trial_cost = max((s.get("cost_thb", 0.0) for s in state["trials"].values()), default=0.0) \
        or rate * 0.1                                     # first guess: ~6 billed minutes
    skipped: list[dict] = []

    for params in list(pending):
        if state["spent_thb"] + est_trial_cost > args.budget_thb:
            skipped.append(params)
            continue

        key = trial_key(params)
        entry = state["trials"].setdefault(key, {"params": params, "attempts": []})

        for attempt in range(MAX_ATTEMPTS):
            if entry.get("status") == "submitted" and entry.get("job_id"):
                job_id = entry["job_id"]
                log(f"trial {key}: re-attaching to job {job_id} (resumed)")
            elif remote:
                job_id = adapter.submit_training(image_ref, {
                    "module": "src.train",
                    "hyperparams": {**params, "no_track": True},
                    "output_key": f"lab2/trials/{key}",
                    "instance": args.instance,
                    "spot": args.spot,
                    "labels": {"trial": key, "study": study},
                    "env": {"GIT_COMMIT": commit},
                    "display_name": f"itcs355-lab2-{study}-{key}",
                })
                entry.update(status="submitted", job_id=job_id)
                save_checkpoint(args.checkpoint, state)
                log(f"trial {key}: submitted {job_id}  {params}")
            else:
                job_id = "local"

            with tempfile.TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                if remote:
                    result = adapter.wait_training(job_id)
                else:
                    result = run_local("src.train", params, out_dir)

                entry["attempts"].append({"job_id": job_id, "state": result["state"],
                                          "duration_s": result["duration_s"],
                                          "error": result["error"][:300]})
                state["spent_thb"] += result["duration_s"] / 3600.0 * rate  # meter runs either way

                if not result["succeeded"]:
                    retryable = any(w in result["error"].lower() for w in RETRYABLE_WORDS)
                    if retryable and attempt < MAX_ATTEMPTS - 1:
                        log(f"trial {key}: INTERRUPTED ({result['error'][:120]}) — resubmitting, "
                            f"completed trials are kept")
                        entry.update(status="interrupted", job_id=None)
                        save_checkpoint(args.checkpoint, state)
                        continue
                    entry.update(status="failed")
                    save_checkpoint(args.checkpoint, state)
                    sys.exit(f"trial {key}: job {job_id} {result['state']}\n{result['error']}\n"
                             f"{result.get('console_url', '')}\n"
                             "Not an interruption — fix the cause, then run again (it resumes).")

                if remote:
                    adapter.download_key(f"lab2/trials/{key}/metrics.json",
                                         str(out_dir / "metrics.json"))
                    adapter.download_key(f"lab2/trials/{key}/model/model.joblib",
                                         str(out_dir / "model" / "model.joblib"))

                cost = record(key, params, result, out_dir, rate, lineage, args, study,
                             len(entry["attempts"]))
                state["spent_thb"] += cost
                est_trial_cost = max(est_trial_cost, cost)
                entry.update(status="done", cost_thb=round(cost, 4))
                save_checkpoint(args.checkpoint, state)
                log(f"trial {key}: done   cumulative spend {state['spent_thb']:.4f} THB")
                break

    log(f"spent {state['spent_thb']:.4f} of {args.budget_thb} THB (estimate — confirm in Billing)")
    if skipped:
        log(f"BUDGET EXHAUSTED — {len(skipped)} configurations not run:")
        for s in skipped:
            print(f"  {s}")
        print("Report this in your README. Which trials you could not afford is a finding, "
              "not an embarrassment.")


if __name__ == "__main__":
    main()
