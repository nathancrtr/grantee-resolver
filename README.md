# grantee-resolver

Who actually lost the grant? This project resolves terminated federal grant recipients to
their **UEI** (via USAspending.gov) and **EIN** (via the IRS Exempt Organizations Business
Master File), and snapshots the official HHS list of terminated grants every night so that
reinstatements — which HHS records only by *removing* rows — become visible as diffs.

It is a companion dataset, not a tracker. [Grant Witness](https://grantwitness.org) already
tracks termination and reinstatement status per award for NIH, CDC, SAMHSA, AHRQ, NSF and
EPA. This project keys on their Award IDs and adds the identity layer nobody publishes:
organization identifiers, address, congressional district, NTEE category, and the
organization's reported revenue, so a lost award can be read against the size of the
organization that lost it.

**Status (2026-09-03):** first pass. CDC file resolved; match tiers are auditable but not
yet human-reviewed. Nothing here has been validated by the Grant Witness maintainers.

## Principles

- **Extraction, not judgment.** No model decides anything. Matching is deterministic
  name + address scoring, and every match carries its score, tier, and the matched IRS
  record so a reader can check it.
- **Provenance on every row.** TAGGS rows carry the PDF page they came from and the
  file's SHA-256; USAspending responses are cached verbatim; diffs are committed to git.
- **Headline views exclude routine terminations.** HHS's list mixes policy terminations
  ("Departmental Authority", "Termination for Cause") with bilateral and
  mutual-convenience closeouts, which are often ordinary. The full data is always kept;
  summaries default to the policy types.
- **No donate button.** See the project brief for why.

## Data flow

```
TAGGS PDF ──parse──▶ data/taggs/snapshots/YYYY-MM-DD.csv ──diff──▶ data/taggs/changes/YYYY-MM-DD.json
Grant Witness CSV ──▶ USAspending award API ──▶ UEI, business category, address
                                                   └──▶ IRS BMF (per state) ──▶ EIN, NTEE, revenue
                                                                        └──▶ data/resolved/{agency}.csv
```

## Usage

```sh
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/grantee taggs            # download, parse, snapshot, diff against the previous snapshot
.venv/bin/grantee gw cdc samhsa    # mirror Grant Witness tables
.venv/bin/grantee resolve cdc      # write data/resolved/cdc.csv
```

`.github/workflows/nightly.yml` runs the same three steps daily and commits the result.

## Match tiers

| Tier | Meaning |
|---|---|
| `YES` | Normalized name identical in-state; or similarity ≥ 0.97 with city match; or ≥ 0.93 with ZIP match |
| `MAYBE` | Name similarity ≥ 0.88; needs a human look |
| `NO` | No IRS record scored ≥ 0.80 in that state |
| `GOV` | Recipient looks like a government entity; not expected in the BMF |
| `NA` | No usable name or state |

## Licenses

Code: MIT. Data produced here: CC0 (see `data/LICENSE`). Grant Witness data is mirrored
without a stated upstream license, pending a conversation with its maintainers.

## Related

- Grant Witness — https://grantwitness.org (upstream status data)
- HHS TAGGS terminated grants — https://taggs.hhs.gov/Content/Data/HHS_Grants_Terminated.pdf
- Nonprofit Open Data Collective `npmatch` — the matching cascade this simplifies
- GAO-26-108615 — the DOGE "Wall of Receipts" reconciliation (already done; not repeated here)
