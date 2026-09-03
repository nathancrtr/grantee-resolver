"""Name + address matching from a USAspending recipient to an IRS BMF record.

A simplified port of the cascade in Nonprofit Open Data Collective's `npmatch`:
normalize -> block on state -> score name similarity + geographic agreement ->
veto rules -> tier YES / MAYBE / NO. Every match carries its score and the
matched BMF name so a human can audit it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

SUFFIXES = r"\b(INC|INCORPORATED|LLC|L L C|CORP|CORPORATION|CO|LTD|THE|OF|AND|&)\b"
GOV_HINTS = re.compile(
    r"\b(DEPARTMENT|DEPT|STATE OF|COMMONWEALTH|COUNTY|CITY OF|CITY AND COUNTY|COMMISSION|"
    r"AGENCY|DIVISION|MINISTRY|BOARD OF HEALTH|PUBLIC HEALTH|HEALTH DISTRICT|GOVERNMENT|"
    r"TERRITOR|TOWN OF|VILLAGE OF|PARISH|BOROUGH|MUNICIPALITY|AUTHORITY|DHSS|DHHS|HHS)\b"
)


def normalize(name: str) -> str:
    n = (name or "").upper()
    n = n.replace("&", " AND ")
    n = re.sub(r"[^A-Z0-9 ]+", " ", n)
    n = re.sub(SUFFIXES, " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def looks_governmental(name: str, business_categories: str) -> bool:
    bc = (business_categories or "").lower()
    if "government" in bc and "nonprofit" not in bc:
        return True
    return bool(GOV_HINTS.search((name or "").upper()))


@dataclass
class Match:
    ein: str | None
    bmf_name: str | None
    bmf_city: str | None
    bmf_zip5: str | None
    ntee: str | None
    revenue: str | None
    name_score: float
    geo_score: float
    tier: str      # YES | MAYBE | NO | GOV | NA
    method: str


def _geo(usasp_city: str | None, usasp_zip5: str | None, cand: dict) -> float:
    score = 0.0
    if usasp_zip5 and (cand.get("ZIP") or "")[:5] == usasp_zip5:
        score += 1.0
    if usasp_city and normalize(cand.get("CITY", "")) == normalize(usasp_city):
        score += 0.5
    return score


def best_match(name: str, city: str | None, zip5: str | None, candidates: list[dict], business_categories: str = "") -> Match:
    if not name:
        return Match(None, None, None, None, None, None, 0, 0, "NA", "no-name")
    if looks_governmental(name, business_categories):
        return Match(None, None, None, None, None, None, 0, 0, "GOV", "government-entity")
    target = normalize(name)
    if not target:
        return Match(None, None, None, None, None, None, 0, 0, "NA", "empty-after-normalize")

    # Blocking: share at least one informative token (len >= 4) with the target.
    tokens = {t for t in target.split() if len(t) >= 4}
    best: tuple[float, float, dict] | None = None
    for c in candidates:
        cn = normalize(c.get("NAME", ""))
        if not cn:
            continue
        ctoks = set(cn.split())
        if tokens and not (tokens & ctoks):
            continue
        ns = max(JaroWinkler.normalized_similarity(target, cn), fuzz.token_set_ratio(target, cn) / 100.0)
        if ns < 0.80:
            continue
        gs = _geo(city, zip5, c)
        total = ns + 0.15 * gs
        if best is None or total > best[0]:
            best = (total, ns, c)
    if best is None:
        return Match(None, None, None, None, None, None, 0, 0, "NO", "no-candidate>=0.80")
    total, ns, c = best
    gs = _geo(city, zip5, c)
    method = "name+geo"
    if ns >= 0.995:
        tier = "YES"            # normalized names identical within the state; address may have moved
        method = "exact-name" if gs == 0 else "exact-name+geo"
    elif ns >= 0.97 and gs >= 0.5:
        tier = "YES"
    elif ns >= 0.93 and gs >= 1.0:
        tier = "YES"            # ZIP agrees
    elif ns >= 0.88:
        tier = "MAYBE"
    else:
        tier = "NO"
    return Match(c.get("EIN"), c.get("NAME"), c.get("CITY"), (c.get("ZIP") or "")[:5], c.get("NTEE_CD"), c.get("REVENUE_AMT"), round(ns, 3), gs, tier, method)
