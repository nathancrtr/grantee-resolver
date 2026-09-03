"""USAspending.gov award lookups, cached on disk.

GET /api/v2/awards/{generated_unique_award_id}/ returns the recipient's UEI, business
categories, and address. The award id is an exact key, so this step needs no matching.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

API = "https://api.usaspending.gov/api/v2/awards/{award_id}/"


def fetch_award(award_id: str, cache_dir: Path, sleep: float = 0.2) -> dict | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{award_id}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    r = requests.get(API.format(award_id=award_id), timeout=60, headers={"User-Agent": "grantee-resolver/0.1"})
    time.sleep(sleep)
    if r.status_code == 404:
        cached.write_text("null")
        return None
    r.raise_for_status()
    cached.write_text(r.text)
    return r.json()


def recipient_fields(award: dict | None) -> dict:
    if not award:
        return {}
    rec = award.get("recipient") or {}
    loc = rec.get("location") or {}
    pop = award.get("period_of_performance") or {}
    return {
        "usasp_award_id": award.get("generated_unique_award_id"),
        "usasp_recipient_name": rec.get("recipient_name"),
        "uei": rec.get("recipient_uei"),
        "parent_uei": rec.get("parent_recipient_uei"),
        "parent_name": rec.get("parent_recipient_name"),
        "recipient_hash": rec.get("recipient_hash"),
        "business_categories": "|".join(rec.get("business_categories") or []),
        "usasp_city": loc.get("city_name"),
        "usasp_state": loc.get("state_code"),
        "usasp_zip5": loc.get("zip5"),
        "usasp_county": loc.get("county_name"),
        "usasp_congressional": loc.get("congressional_code"),
        "usasp_address": loc.get("address_line1"),
        "usasp_pop_end": pop.get("end_date"),
        "usasp_total_obligation": award.get("total_obligation"),
    }
