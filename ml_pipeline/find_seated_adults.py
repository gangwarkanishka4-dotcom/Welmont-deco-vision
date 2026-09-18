"""Surface likely seated/bent-over ADULT candidates from the unlabeled pool,
so you're not hunting through thousands of standing-child crops to find the
specific pose the model struggles with (see review_errors.py's findings —
box_height and shoulder_width both lose signal when someone's sitting).

There's no ground truth to filter on directly, so this uses a proxy from
what's already labeled: leg_extended=False (bent knee — sitting/crouching,
already computed by 1_collect_features.py) combined with a taller box_height
than a seated child would produce. In this dataset, seated adults have a
median box_height around 152px vs. ~132px for seated children — real
overlap, so this is a candidate list to label from, not a guarantee every
crop in it is actually an adult.

Writes data/seated_candidates.txt (one crop filename per line, highest
box_height first). Feed it to 2_label_tool.py with --priority so those
crops are shown before the rest of the unlabeled pool:

    python find_seated_adults.py --dir data/
    python 2_label_tool.py --dir data/ --priority data/seated_candidates.txt

Run:
    python find_seated_adults.py --dir data/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

MIN_BOX_HEIGHT = 150  # near the seated-adult median in this dataset; see docstring
MAX_CANDIDATES = 500  # a labeling session's worth — re-run after using these up


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find likely seated-adult crops in the unlabeled pool.")
    parser.add_argument("--dir", default="data", help="Dataset directory containing features.csv (default: data/)")
    parser.add_argument("--min-height", type=float, default=MIN_BOX_HEIGHT)
    parser.add_argument("--max", type=int, default=MAX_CANDIDATES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    features_csv = Path(args.dir) / "features.csv"
    out_path = Path(args.dir) / "seated_candidates.txt"

    if not features_csv.exists():
        print(f"{features_csv} not found — run 1_collect_features.py first.")
        return

    df = pd.read_csv(features_csv, keep_default_na=False, dtype={"label": str, "leg_extended": str})
    df["box_height"] = pd.to_numeric(df["box_height"], errors="coerce")

    candidates = df[(df["label"] == "") & (df["leg_extended"] == "False") & (df["box_height"] >= args.min_height)]
    candidates = candidates.sort_values("box_height", ascending=False).head(args.max)

    if candidates.empty:
        print("No candidates found — try lowering --min-height, or you've already labeled through this pool.")
        return

    filenames = [Path(p).name for p in candidates["crop_path"]]
    out_path.write_text("\n".join(filenames), encoding="utf-8")

    print(f"Found {len(filenames)} likely seated-adult candidate(s) (box_height >= {args.min_height}).")
    print(f"Written to {out_path}")
    print(f"\nNext: python 2_label_tool.py --dir {args.dir} --priority {out_path}")


if __name__ == "__main__":
    main()
