"""Surface crops in the model's known blind spot: box_height in the 130-165px
range, where seated-adult and seated-child genuinely overlap in this
dataset (medians ~152 vs ~132 — see README.md). This is exactly the range
that produced a real false positive on live footage: a seated child near a
table scored ADULT 99% because her box_height (145-160px) matched the
seated-adult pattern the model learned, and her keypoints were noisy enough
(occlusion from the table) that build_ratio didn't correct it.

Unlike find_seated_adults.py (which looks for probable ADULTS to label),
this doesn't guess a class — it just flags "the model is likely to be
wrong here regardless of which class it is," so you see whichever crops
actually matter, from either class.

Writes data/ambiguous_candidates.txt — feed it to 2_label_tool.py the same
way:

    python find_ambiguous_cases.py --dir data/
    python 2_label_tool.py --dir data/ --priority data/ambiguous_candidates.txt

Run:
    python find_ambiguous_cases.py --dir data/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

MIN_BOX_HEIGHT = 130
MAX_BOX_HEIGHT = 165
MAX_CANDIDATES = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find crops in the model's ambiguous box_height range.")
    parser.add_argument("--dir", default="data", help="Dataset directory containing features.csv (default: data/)")
    parser.add_argument("--min-height", type=float, default=MIN_BOX_HEIGHT)
    parser.add_argument("--max-height", type=float, default=MAX_BOX_HEIGHT)
    parser.add_argument("--max", type=int, default=MAX_CANDIDATES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    features_csv = Path(args.dir) / "features.csv"
    out_path = Path(args.dir) / "ambiguous_candidates.txt"

    if not features_csv.exists():
        print(f"{features_csv} not found — run 1_collect_features.py first.")
        return

    df = pd.read_csv(features_csv, keep_default_na=False, dtype={"label": str})
    df["box_height"] = pd.to_numeric(df["box_height"], errors="coerce")

    candidates = df[
        (df["label"] == "") & (df["box_height"] >= args.min_height) & (df["box_height"] <= args.max_height)
    ]
    candidates = candidates.sample(n=min(len(candidates), args.max), random_state=42)  # random, not sorted — either class could show up

    if candidates.empty:
        print("No candidates found in this range — try widening --min-height/--max-height.")
        return

    filenames = [Path(p).name for p in candidates["crop_path"]]
    out_path.write_text("\n".join(filenames), encoding="utf-8")

    print(f"Found {len(filenames)} candidate(s) with box_height in [{args.min_height}, {args.max_height}]px.")
    print(f"Written to {out_path}")
    print(f"\nNext: python 2_label_tool.py --dir {args.dir} --priority {out_path}")


if __name__ == "__main__":
    main()
