"""Parse the HHS TAGGS "Grants Terminated" PDF into rows, and diff snapshots.

Source: https://taggs.hhs.gov/Content/Data/HHS_Grants_Terminated.pdf
HHS removes reinstated awards from this list rather than marking them, so the
only way to observe a reinstatement here is to snapshot the file and diff it.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import pdfplumber
import requests

TAGGS_URL = "https://taggs.hhs.gov/Content/Data/HHS_Grants_Terminated.pdf"
COLUMNS = [
    "opdiv", "fain", "obligation_doc", "recipient", "state", "country",
    "action_date", "obligated", "expended", "paid", "unliquidated", "title",
    "termination_type", "for_cause",
]
# Termination types HHS uses. "Bilateral" and "Mutual Convenience" are frequently
# routine (e.g. a PI relinquishes an award when moving institutions), so headline
# views should default to POLICY_TYPES.
POLICY_TYPES = {"Departmental Authority", "Termination for Cause"}


def download(dest: Path) -> tuple[Path, str]:
    """Download the PDF; return (path, sha256)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(TAGGS_URL, timeout=120, headers={"User-Agent": "grantee-resolver/0.1"})
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest, hashlib.sha256(r.content).hexdigest()


def money(s: str) -> float | None:
    s = (s or "").replace("$", "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse(pdf_path: Path) -> list[dict]:
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for raw in table:
                    if not raw or len(raw) < 13:
                        continue
                    if raw[0] is None or raw[0].startswith("OPDIV"):
                        continue
                    cells = [(c or "").replace("\n", " ").strip() for c in raw]
                    cells = (cells + [""] * len(COLUMNS))[: len(COLUMNS)]
                    row = dict(zip(COLUMNS, cells))
                    row["source_page"] = page_no  # provenance: page of the PDF this row came from
                    rows.append(row)
    return rows


def row_key(r: dict) -> str:
    return f"{r['opdiv']}|{r['fain']}|{r['obligation_doc']}"


def write_snapshot(rows: list[dict], out_dir: Path, day: date | None = None) -> Path:
    day = day or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day.isoformat()}.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS + ["source_page"])
        w.writeheader()
        w.writerows(rows)
    return path


def load_snapshot(path: Path) -> dict[str, dict]:
    with path.open(newline="") as f:
        return {row_key(r): r for r in csv.DictReader(f)}


def diff(prev: dict[str, dict], curr: dict[str, dict]) -> dict:
    """Rows added (new terminations) and removed (likely reinstated or corrected)."""
    added = [curr[k] for k in curr.keys() - prev.keys()]
    removed = [prev[k] for k in prev.keys() - curr.keys()]
    changed = []
    for k in curr.keys() & prev.keys():
        a, b = prev[k], curr[k]
        fields = [c for c in COLUMNS if a.get(c) != b.get(c)]
        if fields:
            changed.append({"key": k, "fields": fields, "before": {c: a[c] for c in fields}, "after": {c: b[c] for c in fields}})
    return {"added": added, "removed": removed, "changed": changed}


def write_diff(d: dict, out_dir: Path, day: date | None = None) -> Path:
    day = day or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day.isoformat()}.json"
    path.write_text(json.dumps(d, indent=1))
    return path
