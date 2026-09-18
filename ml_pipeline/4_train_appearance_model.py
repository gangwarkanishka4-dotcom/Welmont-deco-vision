"""Step 4 (alternative to 3_train_model.py): train an adult/child classifier
on what a person actually LOOKS LIKE (clothing, build, hair, posture in the
image) rather than on hand-measured pose geometry.

Why this exists: 3_train_model.py's RandomForest leans hardest on box_height
(37-39% feature importance) — the pixel height of the detection box. That
number conflates a person's real height with their distance from the
camera and this classroom's fisheye distortion, which is exactly why real
failures kept tracing back to it: a seated adult with a short box, a
standing child near the lens with an inflated one. No amount of relabeling
fixes a feature that's fundamentally ambiguous.

This trains on the crop images directly instead: a MobileNetV2 pretrained
on ImageNet (frozen — 5-6k crops isn't enough to fine-tune a CNN from
scratch, but it's enough to train a classifier on top of features that
already know how to see clothing, texture, and body proportions), with a
small trainable head on top. Uses the exact same labeled crops as
3_train_model.py (data/features.csv + data/crops/) — no separate
labeling pass needed.

Run:
    python 4_train_appearance_model.py --dir data/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from torchvision import models, transforms

IMG_SIZE = 160
BATCH_SIZE = 64
HEAD_EPOCHS = 60
MIN_LABELED_PER_CLASS = 30

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an appearance-based (image) adult/child classifier.")
    parser.add_argument("--dir", default="data", help="Dataset directory (default: data/)")
    return parser.parse_args()


def build_backbone() -> nn.Module:
    weights = models.MobileNet_V2_Weights.IMAGENET1K_V1
    backbone = models.mobilenet_v2(weights=weights)
    backbone.classifier = nn.Identity()  # -> 1280-dim pooled feature per image
    for p in backbone.parameters():
        p.requires_grad = False
    backbone.eval()
    return backbone


def load_crops(df: pd.DataFrame, transform) -> torch.Tensor:
    tensors = []
    for path in df["crop_path"]:
        img = Image.open(path).convert("RGB")
        tensors.append(transform(img))
    return torch.stack(tensors)


class AppearanceModel(nn.Module):
    """Backbone + head combined into one module, so the ONNX export is a
    single self-contained graph (crop in, adult probability out) —
    inference doesn't need to know embeddings were involved at all."""

    def __init__(self, backbone: nn.Module, head: nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        self.head = head

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone(x)
        logits = self.head(features)
        return torch.softmax(logits, dim=1)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.dir)
    features_csv = data_dir / "features.csv"
    model_output = data_dir / "adult_child_appearance_model.onnx"

    if not features_csv.exists():
        print(f"{features_csv} not found — run 1_collect_features.py then 2_label_tool.py first.")
        return

    df = pd.read_csv(features_csv, keep_default_na=False, dtype={"label": str})
    df = df[df["label"].isin(["adult", "child"])].copy()
    df = df[df["crop_path"].apply(lambda p: Path(p).exists())]  # skip any moved/deleted crop files

    counts = df["label"].value_counts()
    n_adult, n_child = counts.get("adult", 0), counts.get("child", 0)
    print(f"Labeled dataset: adult={n_adult}  child={n_child}  total={len(df)}")
    if n_adult < MIN_LABELED_PER_CLASS or n_child < MIN_LABELED_PER_CLASS:
        print(f"Need at least {MIN_LABELED_PER_CLASS} of each class — label more with 2_label_tool.py first.")
        return

    y = (df["label"] == "adult").astype(int).values
    train_df, test_df, y_train, y_test = train_test_split(
        df, y, test_size=0.25, random_state=42, stratify=y
    )

    transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])

    print("Loading pretrained MobileNetV2 (frozen) and extracting embeddings for every crop...")
    print("(one-time cost — after this, training the head itself is fast)")
    backbone = build_backbone()

    def embed(frame_df: pd.DataFrame) -> torch.Tensor:
        embeddings = []
        with torch.no_grad():
            for start in range(0, len(frame_df), BATCH_SIZE):
                batch_df = frame_df.iloc[start:start + BATCH_SIZE]
                batch = load_crops(batch_df, transform)
                embeddings.append(backbone(batch))
        return torch.cat(embeddings)

    X_train = embed(train_df)
    X_test = embed(test_df)
    y_train_t = torch.tensor(y_train, dtype=torch.long)
    y_test_t = torch.tensor(y_test, dtype=torch.long)
    print(f"Embedded {len(X_train)} train + {len(X_test)} test crop(s), {X_train.shape[1]}-dim each.")

    # class-weighted loss — same reasoning as 3_train_model.py's class_weight="balanced":
    # real footage skews heavily toward children, an unweighted head would just predict
    # "child" most of the time and still look accurate on paper.
    class_counts = torch.bincount(y_train_t, minlength=2).float()
    class_weights = (class_counts.sum() / (2.0 * class_counts)).clamp(max=10.0)

    head = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(X_train.shape[1], 2),
    )
    optimizer = torch.optim.Adam(head.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss(weight=class_weights)

    print(f"\nTraining classifier head for {HEAD_EPOCHS} epochs on cached embeddings...")
    head.train()
    for epoch in range(HEAD_EPOCHS):
        optimizer.zero_grad()
        logits = head(X_train)
        loss = loss_fn(logits, y_train_t)
        loss.backward()
        optimizer.step()
        if (epoch + 1) % 10 == 0:
            print(f"  epoch {epoch + 1}/{HEAD_EPOCHS}  loss={loss.item():.4f}")

    head.eval()
    with torch.no_grad():
        test_logits = head(X_test)
        y_pred = test_logits.argmax(dim=1).numpy()

    print("\n" + classification_report(y_test, y_pred, target_names=["child", "adult"]))
    print("Confusion matrix (rows=actual, cols=predicted, order=[child, adult]):")
    print(confusion_matrix(y_test, y_pred))

    combined = AppearanceModel(backbone, head)
    combined.eval()
    dummy_input = torch.zeros(1, 3, IMG_SIZE, IMG_SIZE)
    model_output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        combined, dummy_input, str(model_output),
        input_names=["image"], output_names=["probabilities"],
        dynamic_axes={"image": {0: "batch"}, "probabilities": {0: "batch"}},
        opset_version=17,
        dynamo=False,  # the newer dynamo-based exporter needs onnxscript and has version quirks;
                        # this is the older, more stable TorchScript-based export path.
    )
    print(f"\nSaved {model_output}")
    print("This is a self-contained image classifier: feed it a 160x160 RGB crop, get back [P(child), P(adult)].")
    print("Unlike 3_train_model.py's output, it needs no pose keypoints at all — just the detection box crop.")


if __name__ == "__main__":
    main()
