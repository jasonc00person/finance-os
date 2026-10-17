---
name: find-transaction
description: Locate a specific transaction in Monarch, judge whether it's categorized correctly, and fix it in both Monarch and the repo. Use when the owner asks to find a charge or deposit, check whether something is categorized right, recategorize or rename a row, explain an unexpected balance or net-worth move, or investigate a transaction that looks wrong or duplicated.
---

# Find and verify a transaction

Three steps every time: **locate it, judge it, fix it in both places.** The third is the one that gets skipped and brings the same question back next month.

## 1. Locate

Always query live, from the project root:

```bash
.venv/bin/python scripts/monarch.py transactions --start 2026-01-01 --end 2026-12-31 --limit 5000
```

- **The API silently truncates at `limit`.** Compare `totalCount` to the rows returned before claiming you searched everything.
- **Search by amount across the whole account, not a date window.** Feeds can date the same row weeks apart from the bank.
- **Generic descriptors** ("Online Transfer / Payment: Debit") strip payee identity. Identify by amount against the recurring bills, or by elimination.
- **Outbound ACH/wire sends** often show the sender (the business) as merchant. Read `plaidName` / statement text for the real payee.
- Check `<year>/audit-notes.md` before asking the owner about a flagged row. If it's resolved there, it's not a question anymore.

## 2. Judge

**The owner's hand-set categories are authoritative.** Overrule one only when it's clearly wrong under these conventions or the tax rules. Never bulk-recategorize.

- **P2P rows (Zelle, Venmo, Cash App, Apple Cash) are categorized by what the money bought**, never by the rail.
- **Family gifts and owner money in stay Transfer**, never an income category.
- **IRS payments out of the tax bucket are `Taxes`.** Flows into the bucket are Transfer. Business taxes (state LLC fees, franchise tax) on a business account are deductible as Taxes & Licenses via `business_tax_markers`.
- **A Business-group category on a personal account is a deduction.** A personal charge sitting in a business category is an over-deduction: recategorize it.
- **Display-vs-tax:** when a category is chosen for how it reads in Monarch, keep it there and override the tax treatment in `config.toml` (`force_transfer_merchants`, `[ledger] overrides`).

Before calling something a problem, read `config.toml` ([categories], [rules], [ledger]). Some rows that look wrong in Monarch are already overridden and have zero tax effect: say so instead of proposing a no-op fix.

## 3. Fix, in both places

```bash
.venv/bin/python scripts/monarch.py categories                       # ids
.venv/bin/python scripts/monarch.py update <tx_id> --category <id>   # also --notes, --reviewed, --hide
.venv/bin/python scripts/monarch.py raw update_transaction '{"transaction_id":"<id>","merchant_name":"New Name"}'
```

- **Sweep for siblings.** A miscategorized row almost always has twins (same merchant other months, same descriptor on another card). Fix the set.
- **Fix the rule too.** If a Monarch rule caused it, the next charge comes back wrong. Fix it in Monarch's Rules UI.
- **Verify live.** Re-query and print the new category. Don't report a fix you haven't seen come back.
- **If it changes the tax layer**, rerun export → `csv_to_beancount.py` → `generate_pl.py --period ytd`.
- **If the owner confirms a business purpose**, append a dated row to `<year>/audit-notes.md` so it's never re-asked.

## Anomalies worth flagging unprompted

- Same-day same-amount pairs on one account (possible duplicate; confirmed dupes go in `[ledger] known_dupes`).
- A card whose full-balance payments always equal the books plus the same constant: a mis-anchored balance assertion, not a missing charge.
- A burst of near-identical charges from one vendor (auto-recharge or a leaked API key).
- A recurring bill that didn't appear this month.
