"""Find the specific crops the trained model gets wrong, so you can look at
them instead of guessing what to label more of.

Re-runs the exact same train/test split 3_train_model.py used (same
random_state=42), so the "test set" here is identical to the one the
printed classification report was computed on. Copies every misclassified
crop into data/review_errors/, renamed to show what happened, e.g.:

    actual-adult_predicted-child_ALT-20260907-00326E_f180_0.jpg

Browse that folder directly (File Explorer, or `start data\\review_errors`)
— no interactive tool needed. If a crop in there is actually mislabeled
(you labeled a child as adult by mistake), fix it with:

    python 2_label_tool.py --dir data/ --review

If the crop's label was correct and the model just got it wrong, it's a
real example of the model's weak spot — that tells you what kind of new
crops (via 1_collect_features.py) or relabeling to prioritize next.

Run:
    python review_errors.py --dir data/
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split

# Must match 3_train_model.py exactly, so this reproduces the same split.
NUMERIC_FEATURE_COLUMNS = [
    "shoulder_width", "head_width", "build_ratio", "leg_to_upper_ratio", "box_height", "detector_confidence",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy out the model's misclassified test-set crops for review.")
    parser.add_argument("--dir", default="data", help="Dataset directory (default: data/)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.dir)
    features_csv = data_dir / "features.csv"
    model_path = data_dir / "adult_child_model.joblib"
    review_dir = data_dir / "review_errors"

    if not features_csv.exists() or not model_path.exists():
        print(f"Need both {features_csv} and {model_path} — run 1/2/3 first.")
        return

    bundle = joblib.load(model_path)
    clf = bundle["model"]
    feature_columns = bundle["feature_columns"]

    df = pd.read_csv(features_csv, keep_default_na=False, dtype={"label": str})
    df = df[df["label"].isin(["adult", "child"])].copy()
    for col in NUMERIC_FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    X = df[NUMERIC_FEATURE_COLUMNS]
    y = (df["label"] == "adult").astype(int)

    # Same split call, same random_state, as 3_train_model.py — this
    # reproduces exactly which rows ended up in the held-out test set.
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    X_test_ordered = X_test[feature_columns]
    predictions = clf.predict(X_test_ordered)

    wrong_mask = predictions != y_test.values
    wrong_rows = df.loc[X_test.index[wrong_mask]]
    wrong_preds = predictions[wrong_mask]

    if review_dir.exists():
        shutil.rmtree(review_dir)  # stale copies from a previous model version
    review_dir.mkdir(parents=True)

    missed_adults = missed_children = 0
    for (row_idx, row), predicted in zip(wrong_rows.iterrows(), wrong_preds):
        actual = row["label"]
        predicted_label = "adult" if predicted == 1 else "child"
        if actual == "adult":
            missed_adults += 1
        else:
            missed_children += 1

        src = Path(row["crop_path"])
        if not src.exists():
            continue
        dest_name = f"actual-{actual}_predicted-{predicted_label}_{src.name}"
        shutil.copy2(src, review_dir / dest_name)

    total_wrong = missed_adults + missed_children
    print(f"Test set: {len(X_test)} row(s), {total_wrong} misclassified ({total_wrong / len(X_test):.0%}).")
    print(f"  Real adults called child: {missed_adults}  <- the ones that matter most")
    print(f"  Real children called adult: {missed_children}")
    print(f"\nCopied {total_wrong} crop(s) to {review_dir}/")
    print("Filenames start with 'actual-adult_predicted-child_...' or 'actual-child_predicted-adult_...'")
    print(f"Open the folder: start {review_dir}")


if __name__ == "__main__":
    main()
