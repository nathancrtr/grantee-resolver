"""IRS Exempt Organizations Business Master File, per state.

https://www.irs.gov/pub/irs-soi/eo_{st}.csv  (EIN, NAME, STREET, CITY, STATE, ZIP, NTEE_CD, REVENUE_AMT, ...)
"""
from __future__ import annotations

import csv
from pathlib import Path

import requests

URL = "https://www.irs.gov/pub/irs-soi/eo_{st}.csv"


def fetch_state(st: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"eo_{st.lower()}.csv"
    if not path.exists():
        r = requests.get(URL.format(st=st.lower()), timeout=300)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def load_state(st: str, cache_dir: Path) -> list[dict]:
    path = fetch_state(st, cache_dir)
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))
