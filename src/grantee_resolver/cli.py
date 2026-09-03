from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from . import grantwitness, resolve, taggs

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def cmd_taggs(args):
    pdf, sha = taggs.download(DATA / "cache" / "HHS_Grants_Terminated.pdf")
    rows = taggs.parse(pdf)
    snap_dir = DATA / "taggs" / "snapshots"
    prev_files = sorted(snap_dir.glob("*.csv"))
    today = date.today()
    path = taggs.write_snapshot(rows, snap_dir, today)
    result = {"date": today.isoformat(), "rows": len(rows), "sha256": sha, "snapshot": str(path.relative_to(ROOT))}
    prev = [p for p in prev_files if p != path]
    if prev:
        d = taggs.diff(taggs.load_snapshot(prev[-1]), taggs.load_snapshot(path))
        d["against"] = prev[-1].name
        d["sha256"] = sha
        dpath = taggs.write_diff(d, DATA / "taggs" / "changes", today)
        result.update(added=len(d["added"]), removed=len(d["removed"]), changed=len(d["changed"]), diff=str(dpath.relative_to(ROOT)))
    print(json.dumps(result, indent=1))


def cmd_gw(args):
    for a in args.agencies:
        p = grantwitness.fetch(a, DATA / "grantwitness")
        print(a, p)


def cmd_resolve(args):
    gw_path = DATA / "grantwitness" / f"{args.agency}.csv"
    if not gw_path.exists():
        grantwitness.fetch(args.agency, DATA / "grantwitness")
    stats = resolve.resolve(args.agency, gw_path, DATA / "cache", DATA / "resolved" / f"{args.agency}.csv", args.limit)
    print(json.dumps(stats, indent=1))


def main():
    ap = argparse.ArgumentParser(prog="grantee")
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("taggs", help="snapshot + diff the HHS terminated-grants PDF"); s.set_defaults(fn=cmd_taggs)
    s = sub.add_parser("gw", help="fetch Grant Witness tables"); s.add_argument("agencies", nargs="*", default=["cdc"]); s.set_defaults(fn=cmd_gw)
    s = sub.add_parser("resolve", help="resolve a Grant Witness table to UEI/EIN"); s.add_argument("agency"); s.add_argument("--limit", type=int); s.set_defaults(fn=cmd_resolve)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
