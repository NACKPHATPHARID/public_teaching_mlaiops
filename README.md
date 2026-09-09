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
