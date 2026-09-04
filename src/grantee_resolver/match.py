"""Name + address matching from a USAspending recipient to an IRS BMF record.

A simplified port of the cascade in Nonprofit Open Data Collective's `npmatch`:
normalize -> block on state -> score name similarity + geographic agreement ->
veto rules -> tier YES / MAYBE / NO. Every match carries its score and the
matched BMF name so a human can audit it.

Rules added after hand-checking the first CDC pass (2026-09-04):

* An exact normalized name always beats a fuzzy name, however good the fuzzy
  candidate's address is. Before this, "Research Triangle Institute" (BMF city
  Durham) lost to a fuzzy neighbour with a matching ZIP.
* If the recipient's tokens are a strict subset of the BMF name's tokens, the
  BMF record is usually a *different* organization named after the recipient:
  "University of Washington School of Law Foundation", "Georgetown University
  Chapter Sigma Xi". Such a candidate is vetoed outright when the extra tokens
  include an affiliate marker (FOUNDATION, ALUMNI, CHAPTER, ...), and can score
  no higher than MAYBE otherwise. The affiliate veto also applies to fuzzy
  candidates ("University of Texas at Austin" ~ "University of Texas Foundation"). The one exception is extra governance words
  ("Board of Trustees of the Leland Stanford Junior University"), which are
  treated as the same organization.
* A fuzzy candidate that shares fewer than 60% of the shorter name's tokens is
  NO, whatever its string similarity. Jaro-Winkler's prefix bonus otherwise
  rated "University of California, Los Angeles" ~ "University Religious
  Conference" at 0.89.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

STOPWORDS = r"\b(INC|INCORPORATED|LLC|L L C|CORP|CORPORATION|CO|LTD|THE|OF|AND|AT|&)\b"
GOV_HINTS = re.compile(
    r"\b(DEPARTMENT|DEPT|STATE OF|COMMONWEALTH|COUNTY|CITY OF|CITY AND COUNTY|COMMISSION|"
    r"AGENCY|DIVISION|MINISTRY|BOARD OF HEALTH|PUBLIC HEALTH|HEALTH DIST\w*|GOVERNMENT|"
    r"TERRITOR|TOWN OF|VILLAGE OF|PARISH|BOROUGH|MUNICIPALITY|AUTHORITY|DHSS|DHHS|HHS)\b"
)

# Extra tokens on either side that name the legal body holding an institution rather
# than a different organization. "Board of Trustees of X" is X.
GOVERNANCE = {"BOARD", "TRUSTEES", "REGENTS", "DIRECTORS"}

# Extra tokens on the BMF side that mark an affiliate of the named institution
# rather than the institution itself. A candidate carrying one of these is vetoed.
AFFILIATE = {
    "FOUNDATION", "FOUNDATIONS", "ALUMNI", "ALUMNAE", "ALUMNUS", "CHAPTER", "CHAPTERS",
    "FUND", "FUNDS", "CLUB", "TEAM", "SOCIETY", "AUXILIARY", "FRIENDS", "BOOSTER", "BOOSTERS",
    "PTA", "PTO", "PARENTS", "STUDENT", "STUDENTS", "FACULTY", "FRATERNITY", "SORORITY",
    "EMPLOYEES", "RETIREES", "RETIREMENT", "GUILD", "SUPPORTERS", "VOLUNTEERS",
    "PANHELLENIC", "INTERFRATERNITY", "FACILITIES", "ENDOWMENT", "ATHLETIC", "ATHLETICS",
}

MIN_SIMILARITY = 0.80   # below this a candidate is not considered at all
MIN_OVERLAP = 0.60      # share of the shorter name's tokens that must appear in the other


def normalize(name: str) -> str:
    n = (name or "").upper()
    n = n.replace("&", " AND ")
    n = re.sub(r"[^A-Z0-9 ]+", " ", n)
    n = re.sub(STOPWORDS, " ", n)
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
    tier: str      # YES | MAYBE | NO | GOV | FOREIGN | NA
    method: str


def _none(tier: str, method: str) -> Match:
    return Match(None, None, None, None, None, None, 0, 0, tier, method)


def _geo(usasp_city: str | None, usasp_zip5: str | None, cand: dict) -> float:
    score = 0.0
    if usasp_zip5 and (cand.get("ZIP") or "")[:5] == usasp_zip5:
        score += 1.0
    if usasp_city and normalize(cand.get("CITY", "")) == normalize(usasp_city):
        score += 0.5
    return score


def _strip_governance(name: str) -> str:
    return " ".join(t for t in name.split() if t not in GOVERNANCE)


def _classify(target: str, ttoks: set[str], cn: str, ctoks: set[str]) -> tuple[str, float, set[str]]:
    """Return (kind, name_score, extra_bmf_tokens).

    kind: "exact"      normalized names identical
          "exact-gov"  identical once governance words are removed, word order kept
          "contained"  recipient tokens are a strict subset of the BMF name's
          "contains"   BMF tokens are a strict subset of the recipient's
          "fuzzy"      anything else
    """
    extra_c = ctoks - ttoks
    extra_t = ttoks - ctoks
    if cn == target:
        return "exact", 1.0, extra_c
    if extra_c <= GOVERNANCE and extra_t <= GOVERNANCE and _strip_governance(cn) == _strip_governance(target):
        return "exact-gov", 1.0, extra_c
    ns = max(JaroWinkler.normalized_similarity(target, cn), fuzz.token_sort_ratio(target, cn) / 100.0)
    if not extra_t:
        return "contained", ns, extra_c
    if not extra_c:
        return "contains", ns, extra_c
    return "fuzzy", ns, extra_c


def best_match(name: str, city: str | None, zip5: str | None, candidates: list[dict], business_categories: str = "") -> Match:
    if not name:
        return _none("NA", "no-name")
    if looks_governmental(name, business_categories):
        return _none("GOV", "government-entity")
    target = normalize(name)
    if not target:
        return _none("NA", "empty-after-normalize")
    ttoks = set(target.split())

    # Blocking: share at least one informative token (len >= 4) with the target.
    block = {t for t in ttoks if len(t) >= 4}
    best: tuple[tuple[int, float], str, float, float, dict] | None = None
    vetoed: tuple[float, str, str] | None = None   # (score, reason token, BMF name)
    for c in candidates:
        cn = normalize(c.get("NAME", ""))
        if not cn:
            continue
        ctoks = set(cn.split())
        if block and not (block & ctoks):
            continue
        kind, ns, extra_c = _classify(target, ttoks, cn, ctoks)
        exact = kind in ("exact", "exact-gov")
        if not exact:
            if ns < MIN_SIMILARITY:
                continue
            if extra_c & AFFILIATE:
                # The BMF org calls itself a foundation/chapter/fund/... and the recipient does not.
                reason = sorted(extra_c & AFFILIATE)[0]
                if vetoed is None or ns > vetoed[0]:
                    vetoed = (ns, reason, c.get("NAME", ""))
                continue
            overlap = len(ttoks & ctoks) / min(len(ttoks), len(ctoks))
            if overlap < MIN_OVERLAP:
                continue
        gs = _geo(city, zip5, c)
        rank = ({"exact": 2, "exact-gov": 1}.get(kind, 0), ns + 0.15 * gs)
        if best is None or rank > best[0]:
            best = (rank, kind, ns, gs, c)

    if best is None:
        if vetoed:
            return _none("NO", f"no-match (vetoed: {vetoed[1]} in '{vetoed[2]}')")
        return _none("NO", "no-candidate>=0.80")

    _, kind, ns, gs, c = best
    if kind in ("exact", "exact-gov"):
        tier = "YES"
        method = "exact-name" if gs == 0 else "exact-name+geo"
        if kind == "exact-gov":
            method += "-modulo-governance"
    elif kind in ("contained", "contains"):
        # One name extends the other. Could be the same org under a longer legal name,
        # or a distinct org named after it. Never better than MAYBE without a human.
        tier = "MAYBE" if ns >= 0.88 else "NO"
        method = f"name-{kind}"
    else:
        method = "name+geo"
        if ns >= 0.97 and gs >= 0.5:
            tier = "YES"
        elif ns >= 0.93 and gs >= 1.0:
            tier = "YES"            # ZIP agrees
        elif ns >= 0.88:
            tier = "MAYBE"
        else:
            tier = "NO"
    if tier == "NO":
        # Keep the closest rejected candidate's name for audit, but never its identifiers.
        return Match(None, c.get("NAME"), c.get("CITY"), None, None, None, round(ns, 3), gs, tier, f"{method} (closest rejected)")
    return Match(c.get("EIN"), c.get("NAME"), c.get("CITY"), (c.get("ZIP") or "")[:5], c.get("NTEE_CD"), c.get("REVENUE_AMT"), round(ns, 3), gs, tier, method)
