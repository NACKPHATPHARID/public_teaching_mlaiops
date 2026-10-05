# ITCS355 Lab 1 — Reproducible Training

> **Course materials live in [`course/`](course/README.md)** — syllabus, slides, the faculty
> specification, all five lab handouts, and the project brief. Every document is Markdown and
> renders on GitHub, diagrams included. New to the repo? Start with the
> [portability reference](course/reference/cloud-portability-reference.md).
> Keep this block when you edit the rest of this file; it is not part of the Lab 1 deliverable.

Predicting machine failure within 7 days from sensor readings. The model is not the point;
whether a stranger can reproduce it is.

> **This README is graded.** A grader with Docker and nothing else from your setup runs one
> command and compares the result against the claim below. Edit every `<...>` and delete the
> instruction blocks marked **REPLACE** before submitting.

---

## Reproduce

```bash
make reproduce
```

expected test_roc_auc: 0.848 ± 0.02

Runtime: about 40 seconds on 4 cores. No cloud account or credentials needed for this command —
that is deliberate, and it is why a grader can run it.

---

## The problem

240 machines, 25 readings each, 6 sensor features, binary target `failed_within_7d` with a
positive rate near 12%.

Machines have persistent characteristics — a hot-running machine reads hot in every row. So the
train/validation/test split is **grouped by `machine_id`**: every reading from one machine lands
in exactly one partition. Splitting row-wise instead lets the model memorise the machine and
reports a validation score that will never survive production. `tests/test_data.py` asserts this
property holds, and Lab 4 turns it into a CI gate.

Bringing your own dataset is allowed. Replace `scripts/make_dataset.py`, update the schema in
`src/data.py`, and keep every test passing.

---

## Layout

```
src/          Layer 1 — provider-neutral. No SDKs, no bucket names, no absolute paths.
cloudlayer/   Layer 3 — the only place a provider SDK may be imported.
scripts/      Dataset generation, cloud check, portability audit, metric verification.
tests/        Data contract tests and split property tests.
```

`src/config.py` is the single point of environment knowledge. Everything else reads from it.
`make portability-audit` enforces the rule; it fails the build if a provider string appears in
`src/` or `tests/`.

---

## Setup

```bash
cp cloud.env.example cloud.env      # fill in, never commit
make setup
make cloud-check                    # eight slots, all PASS
make data                           # generate the dataset
make test                           # 10 tests, all passing
```

Post your `make cloud-check` output in the course channel before Session 1.

---

## What you must finish

Four `TODO` markers are left in the repo deliberately. Each is a graded decision, not busywork.

| Where | What |
|---|---|
| `requirements.txt` | Regenerate with `pip-compile --generate-hashes` |
| `Dockerfile` | Pin the base image by digest; add `--require-hashes` |
| `cloudlayer/<your provider>.py` | Implement `upload`, `download`, `push_image` |
| This README | The reproducibility trade-off question below |

Then:

```bash
make image-push        # image reaches your registry, digest-pinned
dvc init && dvc remote add -d storage ${BLOB_URI}/dvc
dvc add data/raw && dvc push
```

Run five or more tracked runs varying something meaningful — not five identical runs with
different seeds.

---

## Reproducibility trade-off


I would drop digest pin first. If I drop seed control, I can't compare runs
fairly anymore but my test still builds and runs. Changing only the seed moved
test_roc_auc by 0.009 (0.848 to 0.839), which is small. If I drop hashed
dependencies, a package could get quietly swapped for a bad one, but
--require-hashes makes that fail loudly instead of hiding. Dropping the digest pin
is the worst, because it fails silently. During this lab, installing scikit-learn
without a pin quietly gave me version 1.9.0 instead of the pinned 1.8.0, with just
a warning, not an error.


Three things pin your build: hashed dependencies, a digest-pinned base image, and controlled
seeds. Under real time pressure you would keep some and drop others.

Which would you drop first, and what specifically breaks when you do? There is a defensible
answer, and we compare answers in Session 2. An answer that refuses to choose scores zero.

---

## Drill 1
My data fingerprint is 422cccb9136e8140, and it stayed the same across all 5 runs, showing the data itself didn't change. Across those 5 runs I changed the tree settings (n_estimators and max_depth), which moved my test score between 0.842 and 0.853, and I also changed only the seed once, which moved the score from 0.848 down to 0.839 — a similar-sized change, because the seed controls how the data gets split, not just how the model trains. Based on this real spread (0.839 to 0.853), I set my tolerance to ±0.02. For the trade-off question, I would drop the digest pin first, because it fails quietly during this lab, my scikit-learn version quietly changed from 1.8.0 to 1.9.0 with only a warning and no error, which is exactly the kind of hidden break a moving base image tag causes.

---

## Notes for the grader

Tolerance (+/-0.02) is based on 5 tracked runs varying n_estimators, max_depth, and
seed; see MLflow run history for the raw spread (0.8390-0.8533 on test_roc_auc).
cloudlayer/gcp.py uses the gcloud and docker CLIs instead of the google-cloud-storage
SDK, to avoid adding an unpinned dependency mid-lab. Tested on WSL2 Ubuntu 24.04 with
Docker Desktop; docker buildx build --platform linux/amd64 is used explicitly even
though the dev machine is already amd64.

---

## Checklist before you submit

- [CHECK ] `make reproduce` works from a fresh clone, on a machine that is not yours
- [CHECK ] `make verify` passes against your claim line
- [CHECK ] `make test` — all tests pass
- [ CHECK] `make portability-audit` — clean
- [ CHECK] Image builds for `linux/amd64` and is pushed, digest-pinned
- [CHECK ] `dvc push` completed; a grader can `dvc pull`
- [ CHECK] Five or more tracked runs with params, metrics, data fingerprint, and commit SHA
- [CHECK ] Every **REPLACE** block above is gone (the course-materials block at the top stays)
- [CHECK ] `git log -p | grep -i -E "secret|password|AKIA|BEGIN PRIVATE"` returns nothing

That last check is not optional. A credential in Git history is an automatic deduction in this
course, and rotating it is your responsibility, not the grader's.

## Lab 4: what each data contract test guards against

Schema test: a vendor firmware update renames or drops a sensor column, or an export
writes "N/A" so a numeric column turns into text. Without this the model scores on
missing or garbage inputs and nothing errors.

Null test: a gateway outage leaves temp_c blank for a whole shift.

Range test: one production line starts reporting Fahrenheit, so 78 C arrives as 172.
The ceiling is 140, so this fails the build instead of flooding the alert queue.

Target test: a broken label join makes every row 0 and a retrain learns to never flag
anything.

Unique ID test: a replayed batch loads the same readings twice, which inflates the
data and can put one machine's rows on both sides of a split.

Leakage test: someone switches to a row-level random split, validation AUC jumps, and
the score falls apart on machines the model has never seen.

Latency budget: 50 ms for one prediction in the test. Lab 3 measured 7.9 ms at
n_jobs=1, so this is about 6x headroom for a slow CI runner, and 20% of the 250 ms p95
target in loadtest/k6.js. The test sets n_jobs=1 because serving does.

## Lab 4: blocked bad commit

I opened a pull request that makes make_dataset.py write temp_c in Fahrenheit, the
"one line switches units" incident. CI failed at the Data contract tests step with
test_features_within_plausible_ranges: "temp_c above plausible ceiling: 240.215" (limit
140). Model behaviour tests, service tests and the image build did not run, so nothing
shipped. The pull request was closed without merging.

Run: https://github.com/NACKPHATPHARID/public_teaching_mlaiops/actions/runs/37325707384

The schema test passed on this change, since the column and its type were still correct.
Only the range test caught it, which is why both exist.

## Lab 4: drift threshold, SLO, and evidence

**Drift threshold.** Each feature has its own PSI limit, set in `monitoring/drift_job.py` from `monitoring/calibrate.py`. That script scores 300 clean windows of 3000 rows (whole machines at a time, since that is how real traffic arrives) and the limit is 1.5 times the clean p99, with a floor of 0.10. The limits are 0.10 for ambient_humidity, hours_since_service, pressure_kpa and vibration_mm_s, 0.14 for temp_c and 0.25 for load_pct. I did not use the common 0.25 for everything, because on clean data load_pct alone goes above 0.25 in about one window in a hundred at 1000 rows. A window needs at least 300 rows or the job does not judge. On clean staging traffic the highest PSI was 0.008. With temp_c shifted by 6 it was 0.393.

**Alerting.** Cloud Scheduler runs the drift job every 15 minutes. The job writes `drift.breached_features`, and one alert policy emails me when it is above 0. Detection time in the injection exercise was 16 min 52 s from injection start to incident (14 min 16 s to the job, 2 min 36 s through the alert). Post-mortem: `reports/lab4-postmortem.md`.

**SLO** (`monitoring/slo.yaml`). Availability 99.5% over 30 days, which leaves about 3.6 hours of failures a month. That is tight enough that an outage is felt and loose enough that one bad deploy plus a rollback fits inside the budget. When the budget is spent: freeze deploys, roll back to the model-v2 tag, then investigate. Latency p95 under 250 ms over 7 days, the same target as `loadtest/k6.js`. Freshness 30 days.

**Evidence** is in `reports/lab4/`: the blocked bad commit (`task3-failed-run.txt`, test_features_within_plausible_ranges, temp_c above its ceiling), the staging smoke test, the injection timeline and the drift job logs before and after, and the injection modes comparison. Dashboard and alert are committed as code in `infra/gcp/`.
