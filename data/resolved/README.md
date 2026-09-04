# Resolved awards: methods note

**cdc.csv** has one row per award in the Grant Witness CDC table, keyed on their Award ID,
with the recipient's USAspending identifiers and, where one could be found, its IRS
record. Produced 2026-09-04 from gw-data release `2026-08-26.6` (see `cdc.meta.json`
for the source URL and SHA-256). Licence CC0 (see `../LICENSE`).

## Columns

| Group | Columns | Source |
|---|---|---|
| Award | `award_id`, `agency`, `detailed_status`, `grantee_*` | Grant Witness, verbatim |
| Recipient | `usasp_award_id`, `usasp_recipient_name`, `uei`, `parent_uei`, `parent_name`, `business_categories`, `usasp_address`, `usasp_city`, `usasp_state`, `usasp_country`, `usasp_zip5`, `usasp_county`, `usasp_congressional`, `usasp_pop_end` | USAspending award API, recipient location |
| IRS | `ein`, `bmf_name`, `bmf_city`, `bmf_zip5`, `ntee`, `bmf_revenue` | IRS Exempt Organizations BMF, one file per state |
| Match | `match_tier`, `match_name_score`, `match_geo_score`, `match_method` | this project |

`bmf_revenue` is the IRS `REVENUE_AMT` field: total revenue from the organization's most
recent Form 990, blank for organizations that do not file one (most public universities,
churches, very small organizations).

## How the IRS record is chosen

No model is involved. For each award:

1. Take the recipient name and address from USAspending (falling back to Grant Witness).
2. If the recipient's country is not the US, tier `FOREIGN` and stop.
3. If the name or USAspending business category says government, tier `GOV` and stop.
4. Normalize the name: upper-case, strip punctuation, drop INC / CORP / LLC / THE / OF /
   AND / AT and similar.
5. Consider every BMF record **in the same state** sharing at least one word of four or
   more letters with the recipient.
6. Score each candidate on name similarity (Jaro-Winkler or token-sort ratio, whichever
   is higher) and address agreement (+1.0 for same ZIP5, +0.5 for same city).
7. Apply the veto rules below, pick the best surviving candidate, assign a tier.

### Tiers

| Tier | Rows | Meaning |
|---|---|---|
| `YES` | 112 | Normalized names identical (allowing "Board of Trustees of", "Regents of"); or similarity ≥ 0.97 with city match; or ≥ 0.93 with ZIP match |
| `MAYBE` | 6 | Similarity ≥ 0.88, or one name is a word-subset of the other. Needs a human. See verdicts below |
| `NO` | 10 | No candidate survived. `ein` is blank; `bmf_name` shows the closest rejected candidate and `match_method` says why |
| `GOV` | 418 | Government entity; not looked up |
| `FOREIGN` | 32 | Recipient outside the US; not in the BMF |
| `NA` | 2 | US-associated state code with no IRS file (both Micronesia) |

### Veto rules

These came out of hand-checking the first pass (below). Each has a regression test in
`tests/test_match.py`.

- **Exact beats near.** An identical normalized name in the state always wins, whatever
  the address. The first pass ranked by name plus address, so Research Triangle Institute
  (IRS city Durham, USAspending city Research Triangle Park) lost to a fuzzy neighbour
  with the right ZIP.
- **Subsets are suspects.** If the recipient's words are a strict subset of the IRS
  name's, the IRS record is usually a *different* organization named after the recipient.
  It can score no better than `MAYBE`.
- **Affiliate words veto.** Any non-identical candidate whose extra words include
  FOUNDATION, ALUMNI, CHAPTER, FUND, CLUB, TEAM, SOCIETY, STUDENT, FACULTY, FACILITIES,
  ENDOWMENT, PANHELLENIC and similar is rejected outright. The rejected name is recorded in
  `match_method`.
- **Governance words are transparent.** "The Board of Trustees of the Leland Stanford
  Junior University" is Stanford. BOARD, TRUSTEES, REGENTS, DIRECTORS are ignored when the
  remaining words match in order.
- **Low word overlap is NO.** A candidate sharing fewer than 60% of the shorter name's
  words is rejected regardless of string similarity. Jaro-Winkler's prefix bonus otherwise
  rated "University of California, Los Angeles" ~ "University Religious Conference" at 0.89.
- **Health districts are GOV.** `HEALTH DIST` joins the government hints alongside
  DEPARTMENT, COUNTY, CITY OF, and so on.

## Hand check (2026-09-04)

The first pass produced YES 105 / MAYBE 5 / NO 21 / GOV 417 / NA 32. Every YES, MAYBE
and NO row was read against the IRS record it matched.

- **MAYBE, 5 of 5 wrong.** UCLA to a religious conference (twice), a help center to a
  legal center, a health district to a social-services agency, an intergovernmental body
  to a development association.
- **YES, 16 of 105 wrong.** All the same shape: a university or hospital matched to its
  foundation, alumni association, fraternity chapter, equestrian team, facilities
  corporation, or law-school foundation, because the old similarity function scored a
  word-subset as identical. One further ("Alliance Care 360" to "Care & Care") was a
  subset in the other direction.
- **NO, 15 of 21 should have been YES.** Exact names for UCSF, UC Davis, the Regents of
  the University of Colorado, Research Triangle Institute and others lost to fuzzy
  candidates with a better address.

After the rules above, 38 rows carry a different `ein` than the first pass. The remaining
`MAYBE` and `NO` rows were checked by hand:

| Award | Recipient | Closest IRS record | Verdict |
|---|---|---|---|
| NU38PW000029 | National Environmental Health Association | NATIONAL ENVIRONMENTAL HEALTH, Denver, EIN 84-0469910 | Same org. IRS name is truncated |
| NU58DP007617 | Stapleton Foundation for Sustainable Urban Communities | STAPLETON FOUNDATION FOR, Denver | Same org. IRS name is truncated |
| NH23IP922656 | Council of Medical Specia | COUNCIL OF MEDICAL SPECIALTY SOCIETIES | Same org. Name is truncated upstream in USAspending |
| NU65PS923721 | Health Research, Inc. | HEALTH RESEARCH INCORPORATED ELIZABETH WOOD, Menands NY, revenue $1.09B | Same org (New York State's HRI) |
| NU62PS924658 | South Side Help Center | SOUTH SIDE LEGAL CENTER, Chicago | Different org |
| NU50CK000618 | University of South Florida | USF INSTITUTE OF APPLIED ENGINEERING | Different org. USF itself does not file |
| NU50CD300862, U01CK000643 | UCLA | rejected: USC, and a dozen UCLA affiliates | Correctly NO. UCLA has no own BMF row in CA |
| NU50CK000622 | The General Hospital Corporation (Mass General) | rejected: disability trust, nurses' alumnae | Not in the MA file under this name |
| NU50CK000623 | University of Iowa | rejected: research foundation, facilities corp, police lodge | Correctly NO |
| U01IP001136 | University of Texas at Austin | rejected: UT Foundation, equestrian team | Correctly NO |
| NU2GGH002392 | Interchurch Medical Assistance | none in DC | It files in Maryland (EIN 52-2112460). Matching is in-state only |
| NU50CK000495 | International Organization for Migration | rejected: Sikh organization | Intergovernmental; not a US nonprofit |
| NU58DP007641 | Asian Media Access | rejected: a student union | Not found in MN file |
| NU62PS924789 | Alliance Care 360 | rejected: a foundation | Not found in IL file |
| NU58DP007494 | New Mexico Perinatal Collaborative | rejected: New Mexico Alive | Not found in NM file |

The four "same org" MAYBE rows are left as `MAYBE` on purpose: the rule that flagged them
is right in general, and the tier tells a reader exactly which rows a human vouched for.

## Known limits

- Candidates come from the recipient's own state only. Organizations that file from a
  different state (Interchurch Medical Assistance, above) are missed.
- The IRS `NAME` field is sometimes truncated or reorganized; the USAspending name
  occasionally is too.
- Public universities and hospitals are inconsistently present in the BMF. Their
  `bmf_revenue` is usually blank even when the EIN is found.
- `GOV` rows are never looked up, though some government-adjacent bodies do have EINs.
- Nothing here has been reviewed by the Grant Witness maintainers.
