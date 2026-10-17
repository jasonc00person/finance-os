#!/usr/bin/env python
"""Monarch -> year CSVs. The single transaction source for the books.

Pulls every transaction for a year from Monarch (paginated, count-verified) and writes
<year>/transactions-business.csv + <year>/transactions-personal.csv, which
generate_pl.py and csv_to_beancount.py consume. Monarch categories are the
categorization source of truth; config.toml maps them to tax treatment.

    .venv/bin/python scripts/monarch_export.py              # current year (config business.year)
    .venv/bin/python scripts/monarch_export.py --year 2025

Run from the project root (the Monarch session in .mm/ resolves against the CWD).
Years listed in business.frozen_years (filed returns) are never overwritten
without --force-frozen.
"""

import argparse
import asyncio
import csv
import sys

from monarchmoney import MonarchMoney

from config import ROOT, cfg, default_year, frozen_years, match_account

COLUMNS = ["Date", "Description", "Statement description", "Type", "Category", "Group",
           "Amount", "Account", "Tags", "Notes"]


def row_type(cat_name, group_type, C):
    if cat_name in C['transfer'] or group_type == "transfer":
        return "Transfer"
    if cat_name in C['income'] or group_type == "income":
        return "Income"
    return "Expense"


async def fetch_all(mm, year):
    out, offset = [], 0
    while True:
        d = await mm.get_transactions(limit=1000, offset=offset,
                                      start_date=f"{year}-01-01", end_date=f"{year}-12-31")
        chunk = d["allTransactions"]["results"]
        total = d["allTransactions"]["totalCount"]
        out.extend(chunk)
        offset += len(chunk)
        if offset >= total or not chunk:
            break
    assert len(out) == total, f"pagination bug: fetched {len(out)} of {total}"
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=default_year())
    ap.add_argument("--force-frozen", action="store_true",
                    help="allow overwriting a frozen (as-filed) year's CSVs")
    args = ap.parse_args()
    if args.year in frozen_years() and not args.force_frozen:
        sys.exit(f"{args.year} CSVs are the frozen as-filed record; refusing to overwrite "
                 f"(pass --force-frozen only if you really mean it).")
    C = cfg()['categories']
    force_transfer = {m.lower() for m in cfg().get('rules', {}).get('force_transfer_merchants', [])}

    mm = MonarchMoney()
    try:
        mm.load_session()
    except FileNotFoundError:
        sys.exit("No Monarch session. Run `.venv/bin/python scripts/monarch.py auth` first.")
    mm.set_timeout(60)

    cats = await mm.get_transaction_categories()
    group_type = {c["name"]: (c.get("group") or {}).get("type") for c in cats["categories"]}
    group_name = {c["name"]: (c.get("group") or {}).get("name") for c in cats["categories"]}

    txs = await fetch_all(mm, args.year)
    rows = {"business": [], "personal": []}
    skipped, hidden = {}, []
    for t in txs:
        name = t["account"]["displayName"]
        a = match_account(name)
        if a is None or a.get('export') is False:
            skipped[name] = skipped.get(name, 0) + 1
            continue
        cat = (t.get("category") or {}).get("name") or "Uncategorized"
        merchant = ((t.get("merchant") or {}).get("name") or "").strip() or "Unknown"
        stmt = (t.get("plaidName") or "").strip().replace(" -> ", " - ") or merchant
        typ = row_type(cat, group_type.get(cat), C)
        if merchant.lower() in force_transfer:  # display-vs-tax: Monarch category kept for display only
            typ = "Transfer"
        if t.get("hideFromReports"):  # still exported: balance assertions need every real row
            hidden.append(f'{t["date"]}  {t["amount"]:>10.2f}  {merchant}  ({a["label"]})')
        rows[a['side']].append({
            "Date": t["date"],
            "Description": merchant,
            "Statement description": stmt,
            "Type": typ,
            "Category": cat,
            "Group": group_name.get(cat) or "",
            "Amount": f'{t["amount"]:.2f}',
            "Account": a['label'],
            "Tags": ",".join(x["name"] for x in (t.get("tags") or [])),
            "Notes": (t.get("notes") or "").replace("\n", " ")[:200],
        })

    (ROOT / str(args.year)).mkdir(exist_ok=True)
    for side, rs in rows.items():
        rs.sort(key=lambda r: r["Date"], reverse=True)
        path = ROOT / f"{args.year}/transactions-{side}.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rs)
        print(f"{path}: {len(rs)} rows")
    if skipped:
        print("skipped accounts (export=false or not in config.toml [[accounts]]):")
        for n, k in sorted(skipped.items()):
            print(f"  {k:4}  {n}")
    if hidden:
        print(f"WARNING: {len(hidden)} exported row(s) are hidden from reports in Monarch (review):")
        for h in hidden:
            print(f"  {h}")

asyncio.run(main())
