"""Fetch Grant Witness per-agency tables.

Grant Witness (https://grantwitness.org) publishes weekly CSVs. The team also archives
them at https://github.com/signaltrack/gw-data, which cuts a dated release per pull and
deposits to Zenodo; that repo's `.zenodo.json` declares the data CC0-1.0.

We fetch from a pinned release tag by default, so a run is reproducible and cites a
fixed upstream snapshot. Pass live=True for same-day freshness at the cost of that.
The CSVs themselves are not committed here (see .gitignore); each fetch writes a
`{agency}.source.json` sidecar recording where the bytes came from, and that is.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

AGENCIES = ["nih", "cdc", "samhsa", "ahrq", "nsf", "epa"]

# Pinned release of github.com/signaltrack/gw-data. Bump deliberately; the resolved
# outputs record which tag produced them.
PINNED_RELEASE = "2026-08-26.6"
ARCHIVE = "https://raw.githubusercontent.com/signaltrack/gw-data/{tag}/data/{agency}.csv"
LIVE = "https://data.grant-witness.us/{agency}/dl-table.csv"


def source_path(csv_path: Path) -> Path:
    """Sidecar recording the provenance of a fetched CSV."""
    return csv_path.with_suffix(".source.json")


def fetch(agency: str, dest_dir: Path, live: bool = False, tag: str = PINNED_RELEASE) -> Path:
    """Download one agency table and write a provenance sidecar beside it."""
    url = LIVE.format(agency=agency) if live else ARCHIVE.format(tag=tag, agency=agency)
    dest_dir.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=120, headers={"User-Agent": "grantee-resolver/0.1"})
    r.raise_for_status()
    path = dest_dir / f"{agency}.csv"
    path.write_bytes(r.content)
    source_path(path).write_text(json.dumps({
        "agency": agency,
        "url": url,
        "release": None if live else tag,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "bytes": len(r.content),
    }, indent=1) + "\n")
    return path


def source(csv_path: Path) -> dict:
    """Read the provenance sidecar for a fetched CSV, or {} if it is missing."""
    p = source_path(csv_path)
    return json.loads(p.read_text()) if p.exists() else {}


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
