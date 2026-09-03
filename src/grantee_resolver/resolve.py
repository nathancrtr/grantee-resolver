"""Resolve a Grant Witness agency table to UEI (USAspending) and EIN (IRS BMF)."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from . import bmf, grantwitness, match, usaspending

OUT_COLUMNS = [
    "award_id", "agency", "detailed_status", "grantee_organization", "grantee_state", "grantee_city",
    "grantee_org_type", "usasp_award_id", "usasp_recipient_name", "uei", "parent_uei", "parent_name",
    "business_categories", "usasp_address", "usasp_city", "usasp_state", "usasp_zip5", "usasp_county",
    "usasp_congressional", "usasp_pop_end", "ein", "bmf_name", "bmf_city", "bmf_zip5", "ntee", "bmf_revenue",
    "match_tier", "match_name_score", "match_geo_score", "match_method",
]


def resolve(agency: str, gw_path: Path, cache_dir: Path, out_path: Path, limit: int | None = None) -> dict:
    rows = grantwitness.load(gw_path)
    if limit:
        rows = rows[:limit]
    bmf_by_state: dict[str, list[dict]] = {}
    out: list[dict] = []
    tiers: dict[str, int] = defaultdict(int)
    for r in rows:
        award_id = grantwitness.usaspending_award_id(r)
        aw = usaspending.fetch_award(award_id, cache_dir / "usaspending") if award_id else None
        rf = usaspending.recipient_fields(aw)
        name = rf.get("usasp_recipient_name") or r.get("Grantee Organization")
        st = rf.get("usasp_state") or r.get("Grantee State")
        m = match.Match(None, None, None, None, None, None, 0, 0, "NA", "no-state")
        if st and len(st) == 2 and st != "N/A":
            if st not in bmf_by_state:
                try:
                    bmf_by_state[st] = bmf.load_state(st, cache_dir / "bmf")
                except Exception:
                    bmf_by_state[st] = []
            m = match.best_match(name, rf.get("usasp_city"), rf.get("usasp_zip5"), bmf_by_state[st], rf.get("business_categories", ""))
        tiers[m.tier] += 1
        out.append({
            "award_id": r.get("Award ID"), "agency": agency, "detailed_status": r.get("Detailed Status"),
            "grantee_organization": r.get("Grantee Organization"), "grantee_state": r.get("Grantee State"),
            "grantee_city": r.get("Grantee City"), "grantee_org_type": r.get("Grantee Organization Type"),
            **{k: rf.get(k) for k in ("usasp_award_id", "usasp_recipient_name", "uei", "parent_uei", "parent_name", "business_categories", "usasp_address", "usasp_city", "usasp_state", "usasp_zip5", "usasp_county", "usasp_congressional", "usasp_pop_end")},
            "ein": m.ein, "bmf_name": m.bmf_name, "bmf_city": m.bmf_city, "bmf_zip5": m.bmf_zip5, "ntee": m.ntee, "bmf_revenue": m.revenue,
            "match_tier": m.tier, "match_name_score": m.name_score, "match_geo_score": m.geo_score, "match_method": m.method,
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(out)
    stats = {
        "agency": agency,
        "rows": len(out),
        "uei_found": sum(1 for o in out if o["uei"]),
        "tiers": dict(tiers),
        "grant_witness_source": grantwitness.source(gw_path),
    }
    # The upstream CSV is not committed, so record which snapshot produced this output.
    out_path.with_suffix(".meta.json").write_text(json.dumps(stats, indent=1) + "\n")
    return stats
