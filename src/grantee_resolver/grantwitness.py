"""Fetch Grant Witness per-agency tables.

Grant Witness (https://grantwitness.org) publishes weekly CSVs. No license is stated
upstream; we mirror only for reproducibility and key our outputs on their Award ID.
"""
from __future__ import annotations

import csv
from pathlib import Path

import requests

AGENCIES = ["nih", "cdc", "samhsa", "ahrq", "nsf", "epa"]
BASE = "https://data.grant-witness.us/{agency}/dl-table.csv"


def fetch(agency: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    r = requests.get(BASE.format(agency=agency), timeout=120)
    r.raise_for_status()
    path = dest_dir / f"{agency}.csv"
    path.write_bytes(r.content)
    return path


def load(path: Path) -> list[dict]:
    csv.field_size_limit(10**9)
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def usaspending_award_id(row: dict) -> str | None:
    """Grant Witness links each award to USAspending; the generated award id is the last path segment."""
    url = (row.get("USAspending") or "").rstrip("/")
    if "/award/" not in url:
        return None
    return url.rsplit("/", 1)[-1]
