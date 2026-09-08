"""Trains a binary adult/child classifier on the labeled crops produced by
scripts/extract_crops.py + scripts/label_crops.py, and exports it in the
exact format app/cv/classifier/ml_classifier.py already expects: a
torch.save'd module (224x224 RGB input, ImageNet normalization) whose
output is a single logit — sigmoid(output) = P(adult).

Needs training_data/adult/ and training_data/child/ to both have a
meaningful number of crops (a few hundred each is a reasonable starting
point — more always helps, but don't block on a huge dataset before trying
this; see how much MLAgeClassifier's fusion with the heuristic fallback
helps even with a modest first model).

Run from backend/:
    python -m scripts.train_classifier

Then, to use it:
    cp models/age_classifier.pt ../models/   # if not already there
    # set AGE_MODEL=models/age_classifier.pt in .env, restart the backend
"""
from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, random_split
from torchvision import models, transforms
from torchvision.datasets import ImageFolder

DATA_DIR = Path("../training_data")
OUTPUT_PATH = Path("../models/age_classifier.pt")
INPUT_SIZE = 224
BATCH_SIZE = 16
EPOCHS = 15
LEARNING_RATE = 1e-4
VAL_FRACTION = 0.2


def build_model() -> nn.Module:
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.last_channel, 1)  # single logit: P(adult) = sigmoid(output)
    return model


def main() -> None:
    if not (DATA_DIR / "adult").exists() or not (DATA_DIR / "child").exists():
        print(f"Expected {DATA_DIR}/adult/ and {DATA_DIR}/child/ — run scripts.extract_crops "
              f"then scripts.label_crops first.")
        return

    train_transform = transforms.Compose([
        transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    eval_transform = transforms.Compose([
        transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    full_dataset = ImageFolder(str(DATA_DIR), transform=train_transform)
    print(f"Classes found: {full_dataset.class_to_idx} "
          f"(adult={len(list((DATA_DIR / 'adult').glob('*.jpg')))}, "
          f"child={len(list((DATA_DIR / 'child').glob('*.jpg')))})")

    # ImageFolder assigns indices alphabetically ("adult"=0, "child"=1) —
    # remap so the loss target is always 1.0 for adult, 0.0 for child,
    # regardless of that alphabetical accident, matching MLAgeClassifier's
    # sigmoid(output) = P(adult) contract.
    adult_index = full_dataset.class_to_idx["adult"]

    val_size = int(len(full_dataset) * VAL_FRACTION)
    train_size = len(full_dataset) - val_size
    train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])
    val_dataset.dataset.transform = eval_transform  # val split shouldn't get the training augmentation

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.BCEWithLogitsLoss()

    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_loss = 0.0
        for images, labels in train_loader:
            images = images.to(device)
            targets = (labels == adult_index).float().unsqueeze(1).to(device)

            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * images.size(0)

        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images = images.to(device)
                targets = (labels == adult_index).float().unsqueeze(1).to(device)
                predictions = (torch.sigmoid(model(images)) >= 0.5).float()
                correct += (predictions == targets).sum().item()
                total += targets.size(0)

        val_accuracy = correct / total if total else 0.0
        print(f"Epoch {epoch}/{EPOCHS}  train_loss={train_loss / train_size:.4f}  val_accuracy={val_accuracy:.3f}")

    model.eval()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model, OUTPUT_PATH)
    print(f"\nSaved {OUTPUT_PATH}")
    print("Set AGE_MODEL=models/age_classifier.pt in .env and restart the backend to use it.")


if __name__ == "__main__":
    main()
