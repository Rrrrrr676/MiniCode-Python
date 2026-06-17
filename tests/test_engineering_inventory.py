from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_material_inventory_tracks_current_product_app_entries() -> None:
    inventory = json.loads(
        (ROOT / "docs" / "engineering" / "material-inventory.json").read_text(
            encoding="utf-8"
        )
    )

    app = inventory["currentProductApp"]
    assert app["logicalBoundary"] == "product/app/minicode_frontline"
    assert app["currentSourceRoot"] == "minicode"

    entries = {entry["name"]: entry for entry in app["entrySurfaces"]}
    assert entries["interactive-cli"]["path"] == "minicode/main.py"
    assert entries["headless-runner"]["path"] == "minicode/headless.py"
    assert entries["product-surfaces"]["path"] == "minicode/product_surfaces.py"


def test_material_inventory_covers_known_material_roots() -> None:
    inventory = json.loads(
        (ROOT / "docs" / "engineering" / "material-inventory.json").read_text(
            encoding="utf-8"
        )
    )

    material_paths = {item["path"] for item in inventory["materials"]}
    assert {
        "py-src",
        "ts-src",
        "MiniCode-fork",
        "MiniCode-main-work",
        "claude-code-src",
        "superpowers-zh",
        ".dead-modules-backup",
        "paper_experiments",
        "outputs",
    }.issubset(material_paths)
