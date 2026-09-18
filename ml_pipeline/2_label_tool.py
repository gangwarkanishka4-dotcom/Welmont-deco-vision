"""Step 2: label the crops collected by 1_collect_features.py.

Unlike a folder-sorting labeler, this writes the label directly into
features.csv's "label" column (each row already carries its own feature
vector, computed once in step 1 — no need to recompute anything here, just
attach a human judgment to each row).

Shows each crop in a window; press a key to label it:
    a  -> adult
    c  -> child
    s  -> skip (not usable, or you're unsure — leaves it unlabeled for later)
    d  -> discard (same as skip, but marks it "discard" so it's not re-shown
          next run either — use for genuinely unusable crops: blurry, cut
          off, not a person)
    u  -> undo the previous decision (restores whatever it was before)
    q  -> quit and save whenever you want (progress is saved after every
          label — just re-run to resume where you left off)

Run:
    python 2_label_tool.py --dir data/

To go back and fix crops you already labeled (instead of labeling new
ones), add --review:

    python 2_label_tool.py --dir data/ --review

--review shows every already-labeled crop (adult/child/discard) one at a
time with its current label displayed, so you can catch mistakes. The same
a/c/d/s/u/q keys apply — "s" here just means "leave this one as it is."
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import pandas as pd

DISPLAY_SCALE = 3  # crops are small; scale up so they're actually visible

WINDOW_NAME = "Label crop — [a]dult  [c]hild  [s]kip  [d]iscard  [u]ndo  [q]uit"

LABEL_KEYS = {ord("a"): "adult", ord("c"): "child", ord("d"): "discard"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Label (or re-check) crops collected by 1_collect_features.py.")
    parser.add_argument("--dir", default="data", help="Dataset directory containing features.csv (default: data/)")
    parser.add_argument(
        "--review", action="store_true",
        help="Re-check already-labeled crops (adult/child/discard) instead of labeling new ones — "
        "use this to find and fix mistakes.",
    )
    parser.add_argument(
        "--priority", default=None,
        help="Path to a text file of crop filenames (one per line, e.g. from find_seated_adults.py) — "
        "those are shown first, before the rest of the unlabeled pool.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    features_csv = Path(args.dir) / "features.csv"

    if not features_csv.exists():
        print(f"{features_csv} not found — run 1_collect_features.py first.")
        return

    df = pd.read_csv(features_csv, keep_default_na=False, dtype={"label": str})

    if args.review:
        target_idx = df.index[df["label"] != ""].tolist()
        if not target_idx:
            print("Nothing labeled yet to review — label some crops first (run without --review).")
            return
        print(f"Reviewing {len(target_idx)} already-labeled row(s). Press a/c/d to change a label, s to leave it.")
    else:
        target_idx = df.index[df["label"] == ""].tolist()
        already_done = len(df) - len(target_idx)
        if not target_idx:
            print(f"Nothing left to label. {already_done}/{len(df)} rows already labeled.")
            return

        if args.priority:
            priority_names = [
                line.strip() for line in Path(args.priority).read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            priority_rank = {name: i for i, name in enumerate(priority_names)}
            basenames = {idx: Path(df.at[idx, "crop_path"]).name for idx in target_idx}
            in_priority = [idx for idx in target_idx if basenames[idx] in priority_rank]
            rest = [idx for idx in target_idx if basenames[idx] not in priority_rank]
            in_priority.sort(key=lambda idx: priority_rank[basenames[idx]])
            target_idx = in_priority + rest
            print(f"{len(in_priority)} priority row(s) from {args.priority}, shown first.")

        print(f"{len(target_idx)} row(s) left to label ({already_done}/{len(df)} already done).")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    history: list[tuple[int, str]] = []  # (row_idx, label_before_this_edit), for undo
    corrections = 0
    pos = 0
    while pos < len(target_idx):
        row_idx = target_idx[pos]
        crop_path = df.at[row_idx, "crop_path"]
        current_label = df.at[row_idx, "label"]

        image = cv2.imread(crop_path)
        if image is None:
            print(f"  missing crop file, skipping: {crop_path}")
            pos += 1
            continue

        h, w = image.shape[:2]
        display = cv2.resize(image, (w * DISPLAY_SCALE, h * DISPLAY_SCALE), interpolation=cv2.INTER_NEAREST)
        cv2.putText(
            display, f"{pos + 1}/{len(target_idx)}  row={row_idx}  current: {current_label or '(none)'}", (8, 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
        )
        cv2.imshow(WINDOW_NAME, display)
        key = cv2.waitKey(0) & 0xFF

        if key == ord("q"):
            break
        elif key in LABEL_KEYS:
            new_label = LABEL_KEYS[key]
            if new_label == current_label:
                pos += 1  # already this label — nothing to record, just move on
                continue
            history.append((row_idx, current_label))
            df.at[row_idx, "label"] = new_label
            if args.review:
                corrections += 1
        elif key == ord("s"):
            # Review mode: leave the current label as-is. Normal mode: leave
            # blank — unlike "d", this row is shown again next run.
            pos += 1
            continue
        elif key == ord("u"):
            if history:
                prev_idx, prev_label = history.pop()
                df.at[prev_idx, "label"] = prev_label
                if args.review and prev_label != "":
                    corrections -= 1
                pos = target_idx.index(prev_idx)
                continue
            else:
                continue
        else:
            continue  # any other key: redraw the same crop

        df.to_csv(features_csv, index=False)  # save after every change — safe to Ctrl+C or quit anytime
        pos += 1

    cv2.destroyAllWindows()
    counts = df["label"].value_counts()
    if args.review:
        print(f"\nReview session done. {corrections} label(s) corrected.")
    print(
        f"adult={counts.get('adult', 0)} child={counts.get('child', 0)} "
        f"discarded={counts.get('discard', 0)} unlabeled={counts.get('', 0)}"
    )
    print("Re-run this script any time to keep labeling where you left off.")


if __name__ == "__main__":
    main()
