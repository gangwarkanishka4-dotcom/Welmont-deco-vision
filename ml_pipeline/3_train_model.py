"""Step 3: train a classical adult/child classifier on the features labeled
by 2_label_tool.py.

Why a small RandomForest instead of a CNN: the feature set (shoulder_width,
head_width, build_ratio, leg_to_upper_ratio, box_height, ...) is already the
hand-engineered, anthropometrically-justified signal the rule-based
classifier uses — a few hundred labeled rows is a realistic amount of data
for a model on ~6 numeric features, but nowhere near enough to train a CNN
from scratch. This also keeps inference CPU-cheap (a forest over 6 numbers,
not a neural net forward pass) and the model directly inspectable (feature
importances), which matters for trusting it in a supervision system.

Run:
    python 3_train_model.py --dir data/

Then:
    - Read the classification report below. See README.md in this folder
      for how to interpret precision/recall/class balance before trusting
      this model on real classroom footage.
    - If it looks good: apply integration_snippet.py to your main script.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

# Must match FEATURE_COLUMNS in 1_collect_features.py and the feature
# computation in integration_snippet.py — train/serve parity.
NUMERIC_FEATURE_COLUMNS = [
    "shoulder_width", "head_width", "build_ratio", "leg_to_upper_ratio", "box_height", "detector_confidence",
]
MIN_LABELED_PER_CLASS = 30  # a soft floor — see README.md; more is always better


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the adult/child classifier on labeled features.")
    parser.add_argument("--dir", default="data", help="Dataset directory containing features.csv (default: data/)")
    return parser.parse_args()


def load_dataset(features_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(features_csv, keep_default_na=False, dtype={"label": str})
    df = df[df["label"].isin(["adult", "child"])].copy()

    # Missing values (build_ratio/leg_to_upper_ratio are blank whenever that
    # signal wasn't available for a given crop) become 0 rather than being
    # dropped — losing an entire row over one missing signal wastes a
    # labeled example the other features can still use.
    for col in NUMERIC_FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def main() -> None:
    args = parse_args()
    data_dir = Path(args.dir)
    features_csv = data_dir / "features.csv"
    model_output = data_dir / "adult_child_model.joblib"

    if not features_csv.exists():
        print(f"{features_csv} not found — run 1_collect_features.py then 2_label_tool.py first.")
        return

    df = load_dataset(features_csv)
    counts = df["label"].value_counts()
    n_adult, n_child = counts.get("adult", 0), counts.get("child", 0)
    print(f"Labeled dataset: adult={n_adult}  child={n_child}  total={len(df)}")

    if n_adult < MIN_LABELED_PER_CLASS or n_child < MIN_LABELED_PER_CLASS:
        print(
            f"\nAt least {MIN_LABELED_PER_CLASS} of each class is a reasonable floor to even try training — "
            f"you have adult={n_adult}, child={n_child}. Label more with 2_label_tool.py before continuing."
        )
        return

    X = df[NUMERIC_FEATURE_COLUMNS]
    y = (df["label"] == "adult").astype(int)  # 1 = adult, 0 = child — predict_proba()[:, 1] = P(adult)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    # class_weight="balanced" matters here: real classroom footage is
    # overwhelmingly children, so an unweighted model can get high overall
    # accuracy while barely ever predicting "adult" — exactly the failure
    # mode this system can't afford (a missed adult looks like an empty room).
    model = RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced", random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print("\n" + classification_report(y_test, y_pred, target_names=["child", "adult"]))
    print("Confusion matrix (rows=actual, cols=predicted, order=[child, adult]):")
    print(confusion_matrix(y_test, y_pred))

    print("\nFeature importances:")
    for name, importance in sorted(zip(NUMERIC_FEATURE_COLUMNS, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {name:22s} {importance:.3f}")

    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_columns": NUMERIC_FEATURE_COLUMNS}, model_output)
    print(f"\nSaved {model_output}")

    # Also export to ONNX for the live backend to load via onnxruntime — the
    # backend's own venv can't import scikit-learn/scipy directly (an
    # Application Control policy blocks scipy's compiled extensions there),
    # but onnxruntime is already a pinned backend dependency and works fine.
    onnx_output = model_output.with_suffix(".onnx")
    onnx_model = convert_sklearn(
        model,
        initial_types=[("input", FloatTensorType([None, len(NUMERIC_FEATURE_COLUMNS)]))],
        options={id(model): {"zipmap": False}},  # plain probability array, not a list of dicts
        target_opset=17,  # onnxruntime==1.20.1 (pinned in backend/requirements.txt) supports up to opset 21;
                          # 17 leaves headroom without relying on newly-added, less-tested ops.
    )
    onnx_output.write_bytes(onnx_model.SerializeToString())
    print(f"Saved {onnx_output} (for the live backend — see integration_snippet.py)")
    print("See README.md in this folder for how to read the report above before trusting this model.")


if __name__ == "__main__":
    main()
