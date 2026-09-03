# grantee-resolver

Resolves terminated federal grant recipients to their **UEI** (from USAspending.gov) and
**EIN** (from the IRS Exempt Organizations Business Master File). Also snapshots the
official HHS list of terminated grants every night. HHS records a reinstatement only by
removing the row from that list, so diffing snapshots is the only way to see one.

This is a companion dataset to [Grant Witness](https://grantwitness.org), which already
tracks termination and reinstatement status per award for NIH, CDC, SAMHSA, AHRQ, NSF and
EPA. This project keys on their Award IDs and adds organization identifiers, address,
congressional district, NTEE category, and reported revenue, so a lost award can be
compared to the size of the organization that lost it.

**Status (2026-09-03):** first pass. CDC file resolved; match tiers are auditable but not
yet human-reviewed. Nothing here has been validated by the Grant Witness maintainers.

## Principles

- No model decides anything. Matching is deterministic name and address scoring, and
  every match carries its score, tier, and the matched IRS record so a reader can check it.
- Every row has provenance. TAGGS rows carry the PDF page they came from and the file's
  SHA-256. USAspending responses are cached verbatim. Diffs are committed to git.
- Summaries exclude routine terminations by default. HHS's list mixes policy terminations
  ("Departmental Authority", "Termination for Cause") with bilateral and
  mutual-convenience closeouts, which are often ordinary. The full data is always kept.
- No donate button. See the project brief for why.

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
.venv/bin/grantee gw cdc samhsa    # fetch Grant Witness tables
.venv/bin/grantee resolve cdc      # write data/resolved/cdc.csv
```

`.github/workflows/nightly.yml` runs the same three steps daily and commits the result.

## Grant Witness input

The Grant Witness CSVs are fetched at run time, not committed. The Grant Witness team
archives them at [signaltrack/gw-data](https://github.com/signaltrack/gw-data), which cuts
a dated release per pull, and `grantee gw` reads from a release tag pinned in
`grantwitness.py`. So a run is reproducible and the input is citable, and this repo does
not carry a second copy of a 25 MB file someone else already archives.

Every fetch writes `data/grantwitness/{agency}.source.json` with the URL, release tag,
SHA-256 of the bytes, and when that content was first seen. Each resolve writes `data/resolved/{agency}.meta.json`
carrying that record alongside the run's tier counts. Those sidecars are committed; the
CSVs are not.

Bump `PINNED_RELEASE` to take new upstream data. Until you do, nightly runs reproduce the
same resolved output and commit nothing, so the data moves only when you move the pin.
Pass `--live` to pull from grantwitness.org instead, or `--tag` for a one-off release.

## Match tiers

| Tier | Meaning |
|---|---|
| `YES` | Normalized name identical in-state; or similarity ≥ 0.97 with city match; or ≥ 0.93 with ZIP match |
| `MAYBE` | Name similarity ≥ 0.88; needs a human look |
| `NO` | No IRS record scored ≥ 0.80 in that state |
| `GOV` | Recipient looks like a government entity; not expected in the BMF |
| `NA` | No usable name or state |

## Licenses

Code: MIT. Data produced here: CC0 (see `data/LICENSE`).

Grant Witness states no license on its site, but the team's own archive repo declares the
data CC0-1.0 in its Zenodo deposit metadata, and their FAQ answers "Can I use this data in
my own reporting?" with "Emphatically yes." This project relies on that, cites their
release tag, and does not redistribute their CSVs. Confirming CC0 with the maintainers
directly is still worth doing.

## Related

- [Grant Witness](https://grantwitness.org), the upstream status data
- [signaltrack/gw-data](https://github.com/signaltrack/gw-data), their archive of it
- [HHS TAGGS terminated grants PDF](https://taggs.hhs.gov/Content/Data/HHS_Grants_Terminated.pdf)
- Nonprofit Open Data Collective `npmatch`, the matching cascade this simplifies
- GAO-26-108615, the DOGE "Wall of Receipts" reconciliation (already done; not repeated here)
