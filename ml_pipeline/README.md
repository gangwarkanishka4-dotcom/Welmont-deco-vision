# ml_pipeline

A classical (RandomForest, not CNN) adult/child classifier trained on the
same hand-engineered features the main backend's heuristic classifier
already uses — shoulder width, ear-to-ear head width, their ratio, leg
extension, box height. This folder is self-contained for steps 1-3 (only
`ultralytics`, `opencv-python`, `pandas`, `scikit-learn`, `joblib`) so it can
be copied to another machine and run independently of the backend package.
Step 4 (`integration_snippet.py`) is the one exception — it's the bridge
back into the backend and imports from `app.cv.*`.

## Setup (Apple Silicon Mac)

```
python3 -m venv .venv
source .venv/bin/activate
pip install ultralytics opencv-python pandas scikit-learn joblib
```

`ultralytics` will auto-download `yolov8n-pose.pt` on first run if it isn't
already present in this folder. No CUDA/MPS setup is required for this
pipeline — the pose model runs fine on CPU for offline feature extraction,
and the RandomForest trains in seconds regardless of hardware.

## Steps

1. Run against each clip you have — story-time, desk work, kids at tables,
   whatever mix of standing and seated poses you've got. All runs with the
   same `--out` accumulate into one `features.csv` instead of overwriting it:
   ```
   python 1_collect_features.py --source story_time.mp4 --out data/
   python 1_collect_features.py --source desk_work.mp4 --out data/
   ```
   Writes crops to `data/crops/` and one row per detected person to
   `data/features.csv`, with an empty `label` column.

2. ```
   python 2_label_tool.py --dir data/
   ```
   A window shows each crop one at a time:
   - `a` — adult
   - `c` — child
   - `s` — skip (unsure — leaves it unlabeled, shown again next run)
   - `d` — discard (genuinely unusable crop — blurry, cut off, not a person —
     won't be re-shown)
   - `u` — undo the previous decision
   - `q` — quit and save whenever you want

   Saves after every keypress — safe to quit and resume anytime. Aim for at
   least a couple hundred labeled crops, with both classes and both standing
   and seated poses represented.

3. ```
   python 3_train_model.py --dir data/
   ```
   Trains on the rows you've labeled and prints a report like:
   ```
                 precision    recall  f1-score
   child           0.91        0.88      0.89
   adult           0.87        0.92      0.90
   ```
   That table is how you judge whether it's ready — see below for how to
   read it. Saves `data/adult_child_model.joblib`.

4. If the report looks solid, apply `integration_snippet.py` (see its
   header — it shows the exact `factory.py` diff, not applied
   automatically) to swap the rule-based scoring for this model's
   `predict_proba()`.

## Reading the classification report

`3_train_model.py` prints a `classification_report` and confusion matrix on
a held-out 25% test split. Two numbers matter most for this system:

- **Adult recall** (row "adult", column "recall") — of the real adults in
  the test set, what fraction did the model catch? This is the one that
  can't be low: a missed adult makes a supervised room look empty, which is
  exactly the failure this system exists to prevent. If adult recall is
  noticeably lower than child recall, that's usually the seated-adult
  problem again — `box_height` and `leg_to_upper_ratio` both lose their
  signal when someone's sitting, which is exactly why the heuristic
  classifier struggled here too. The fix is more labeled *seated*-adult
  examples specifically, not a different model or more data in general.
- **Adult precision** — of everything the model called "adult", how much
  actually was? Lower precision here is the safer direction to err in than
  low recall (a child briefly flagged as adult self-corrects on the next
  frame via `RollingClassificationHistory`'s smoothing; a missed adult
  during their only frame in view does not).

The confusion matrix shows the same thing spatially — watch the
top-right cell (actual child, predicted adult) and bottom-left cell (actual
adult, predicted child) specifically, not just overall accuracy. Overall
accuracy is misleading on this data: classroom footage is mostly children,
so a model that always predicts "child" can still score high accuracy while
being useless — this is why `3_train_model.py` uses
`class_weight="balanced"` and why the per-class numbers, not the aggregate,
are what to check.

**On data volume**: `MIN_LABELED_PER_CLASS = 30` in `3_train_model.py` is a
floor to even attempt training, not a target — it's enough rows for the
model to fit without erroring, not enough to trust blindly. Precision/recall
computed from a 25%-of-~60-rows test split (i.e. ~15 examples) can swing a
lot on a single relabeled crop. Treat early reports as directional. Before
relying on this in place of the heuristic classifier:

- Label a few hundred examples per class, not a few dozen.
- Make sure both classes span different camera angles, distances, lighting,
  and — for children — different poses (standing, sitting, mid-motion), not
  just one clip's worth of near-identical frames.
- Re-run `1_collect_features.py` against new footage periodically and add
  to the labeled set rather than training once and freezing it — a preschool
  classroom's camera angles and lighting are more consistent than most
  scenes, which helps, but new furniture, seasonal clothing, or a repositioned
  camera can all shift the input distribution.

## Feature importances

`3_train_model.py` also prints which features the trained forest actually
relied on. If `build_ratio` (shoulder-to-head-width ratio) dominates, that
matches what the heuristic classifier's own weighting already assumed
(`POSE_WEIGHT = 0.30` there) — a useful sanity check that the model learned
something real rather than an artifact of this particular footage.
