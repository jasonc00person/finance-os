---
name: monthly-close
description: Run the full monthly books close end to end — Monarch categorization sweep, CSV export, ledger rebuild with fresh balance assertions, P&L generation, and republish of the P&L and balance-sheet pages — then report the month with anything weird flagged. Use when the owner says to close the books, close out a month, run the monthly close, or asks for the month's numbers with miscategorized or odd transactions flagged.
---

# Monthly close

Five steps, in order. Each has a gate that must pass before moving on. Run everything from the project root (the Monarch session resolves `.mm/` against the working directory).

Closing a month after the fact is normal: pass `--end` to stop the YTD at the real month boundary.

## Step 1 — Categorization sweep in Monarch

Monarch is the source of truth, so this happens before any export. **Never bulk-overwrite categories the owner set by hand.**

1. `.venv/bin/python scripts/monarch.py transactions --start <month-start> --end <month-end> --limit 5000`. Compare `totalCount` to the rows returned.
2. Categorize anything Uncategorized or `needsReview`, per the conventions in the `find-transaction` skill.
3. Generic bank descriptors ("Online Transfer", "Debit", Zelle/Venmo): identify by amount pattern against recurring bills, then rename the merchant so it joins its recurring stream.
4. Personal-card rows that landed in a Business-group category: confirm each is real business spend (Monarch auto-categorizes unfamiliar merchants, e.g. a dating app in Software). A wrong one is an over-deduction.
5. If the owner uses Amazon/retail sync in Monarch, ask them to run it first: it splits orders into items and often surfaces business gear sitting in Shopping.

Gate: zero Uncategorized rows in the month.

## Step 2 — Export

```bash
.venv/bin/python scripts/monarch_export.py
```

Gates: the paginated count check passes, and no `WARNING: ... hidden from reports` block (unhide or confirm each). Unmapped accounts print under "skipped": add real ones to `config.toml`.

## Step 3 — Ledger, with fresh balance assertions

Pull live balances (`.venv/bin/python scripts/monarch.py accounts`) and append a dated block to `<year>/ledger-assertions.beancount`:

```
; ---- Oct 1 close (live balances pulled 10/01) ----
2026-10-01 balance Assets:Biz:Checking        4570.41 USD
2026-10-01 balance Liabilities:Biz:CreditCard  -232.19 USD
```

A balance assertion checks the START of its date, so date it the day after the last posted row. Liabilities are negative. Accounts that existed before Jan 1 get a one-time `2026-01-01 pad <account> Equity:OpeningBalances` above their first assertion. Rules that prevent silent corruption:

- **Card balances that exclude pending charges** (Amex does this; the feed includes pending rows): never assert to a same-day balance. Date it the day before the first pending row, or add pending rows back.
- **In-transit transfers** at the export boundary leave a nonzero `Assets:Transfers:Clearing` residual for 1-3 days. Decompose it into boundary-dated legs and write that in a `; NOT asserted:` note. Never assert an account whose counter-leg hasn't landed.
- **Investment accounts** carry flows at cost. Mark to market with a `pad <account> Income:Personal:InvestmentGains` the day before a live-value assertion.

```bash
.venv/bin/python scripts/csv_to_beancount.py
```

Gates: `bean-check: PASS`, all three TIE-OUT lines match to the cent, CLEARING residual 0.00 or fully decomposed. Flows Monarch can't see (IRS payments from an unconnected account, brokerage-internal moves) go in `<year>/ledger-manual.beancount`. **Never hand-edit `ledger.beancount`.**

## Step 4 — P&Ls

```bash
.venv/bin/python scripts/generate_pl.py --period ytd --end 2026-09-30
.venv/bin/python scripts/generate_pl.py --period sep
.venv/bin/python scripts/generate_pl.py --period q3      # when a quarter just closed
```

Gates: `Difference (should be ~0)` reads 0.00, and no `REVIEW — UNMAPPED CATEGORIES` block. REVIEW rows are held out of deductions but still count toward the Difference, so 0.00 does not clear them: recategorize in Monarch or map the category in `config.toml`, then rerun from Step 2.

## Step 5 — Pages

```bash
.venv/bin/python scripts/make_pl_page.py
.venv/bin/python scripts/make_balance_sheet.py
```

Republish both with the Artifact tool, **passing the URLs from `config.toml` [artifacts]** as `url`. Omitting it mints a new page and the owner loses the pinned one.

## The close report

Numbers first, then flags.

- Revenue, expenses, net profit for the month and YTD.
- Personal spending in two lines: **lifestyle spend** (ex-tax) and **tax set-aside**. Never merge them.
- **After-tax owner earnings** from the P&L's AFTER-TAX block (net profit minus tax accrued). The number they keep.
- **Tax position**: accrued vs paid vs bucket, and the projected April balance.
- **Net worth**, tax bucket reported separately as reserved cash.
- **Flags**: miscategorized, duplicated, missing from a recurring series, or anomalous, with evidence and a proposed fix. Apply the mechanical ones; ask about judgment calls.

Record anything the owner confirms in `<year>/audit-notes.md`.

## Quarterly CFO review (Jan / Apr / Jul / Oct closes)

Revenue trend and concentration (share from the top source), spend vs value produced, retirement contribution room, the S-corp trigger, whether the tax skim % still covers accrued tax, and the next estimate due date (Apr 15, Jun 15, Sep 15, Jan 15). December close: size any employer profit-sharing contribution against the year's tax gap.
