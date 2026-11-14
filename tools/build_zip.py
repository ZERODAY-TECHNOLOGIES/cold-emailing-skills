#!/usr/bin/env python3
"""Construiește dist/cold-emailing.zip pentru încărcare în Claude Desktop / claude.ai (Settings > Skills)."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "cold-emailing"
OUT = ROOT / "dist" / "cold-emailing.zip"


def main():
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_dir() or "__pycache__" in f.parts or f.suffix == ".pyc" or f.name == ".DS_Store":
                continue
            z.write(f, Path("cold-emailing") / f.relative_to(SKILL))
    print(f"OK: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
