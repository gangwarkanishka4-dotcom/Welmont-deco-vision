"""Interactive labeler for the crops extracted by scripts/extract_crops.py.

Shows each unlabeled crop in a window; press a key to sort it:
    a  -> adult
    c  -> child
    d  -> discard (not a usable crop — blurry, cut off, not a person, etc.)
    u  -> undo the previous decision (moves it back to unlabeled)
    q  -> quit (progress is saved as you go — just re-run to resume)

Run from backend/:
    python -m scripts.label_crops
"""
from __future__ import annotations

from pathlib import Path

import cv2

UNLABELED_DIR = Path("../training_data/unlabeled")
ADULT_DIR = Path("../training_data/adult")
CHILD_DIR = Path("../training_data/child")
DISCARD_DIR = Path("../training_data/discarded")

WINDOW_NAME = "Label crop — [a]dult  [c]hild  [d]iscard  [u]ndo  [q]uit"
DISPLAY_SCALE = 3  # crops are small; scale up so they're actually visible


def main() -> None:
    for d in (ADULT_DIR, CHILD_DIR, DISCARD_DIR):
        d.mkdir(parents=True, exist_ok=True)

    remaining = sorted(UNLABELED_DIR.glob("*.jpg"))
    if not remaining:
        print(f"No crops found in {UNLABELED_DIR} — run scripts.extract_crops first.")
        return

    already_done = len(list(ADULT_DIR.glob("*.jpg"))) + len(list(CHILD_DIR.glob("*.jpg"))) + len(list(DISCARD_DIR.glob("*.jpg")))
    print(f"{len(remaining)} crop(s) left to label ({already_done} already done in a previous session).")

    last_moved: tuple[Path, Path] | None = None  # (current_path, original_unlabeled_path) for undo
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    i = 0
    while i < len(remaining):
        path = remaining[i]
        if not path.exists():  # already moved by undo bookkeeping below
            i += 1
            continue

        image = cv2.imread(str(path))
        if image is None:
            i += 1
            continue

        h, w = image.shape[:2]
        display = cv2.resize(image, (w * DISPLAY_SCALE, h * DISPLAY_SCALE), interpolation=cv2.INTER_NEAREST)
        cv2.putText(display, f"{i + 1}/{len(remaining)}  {path.name}", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imshow(WINDOW_NAME, display)
        key = cv2.waitKey(0) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("a"):
            dest = ADULT_DIR / path.name
            path.rename(dest)
            last_moved = (dest, path)
            i += 1
        elif key == ord("c"):
            dest = CHILD_DIR / path.name
            path.rename(dest)
            last_moved = (dest, path)
            i += 1
        elif key == ord("d"):
            dest = DISCARD_DIR / path.name
            path.rename(dest)
            last_moved = (dest, path)
            i += 1
        elif key == ord("u"):
            if last_moved is not None:
                current_path, original_path = last_moved
                if current_path.exists():
                    current_path.rename(original_path)
                    print(f"Undid: {original_path.name}")
                last_moved = None
                i = max(0, i - 1)
        # any other key: redraw the same crop (ignored)

    cv2.destroyAllWindows()
    print(
        f"\nSession done. adult={len(list(ADULT_DIR.glob('*.jpg')))} "
        f"child={len(list(CHILD_DIR.glob('*.jpg')))} discarded={len(list(DISCARD_DIR.glob('*.jpg')))} "
        f"remaining={len(list(UNLABELED_DIR.glob('*.jpg')))}"
    )
    print("Re-run this script any time to keep labeling where you left off.")


if __name__ == "__main__":
    main()
