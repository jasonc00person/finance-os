---
name: money-status
description: Answer "where do I stand" money questions from live data — tax owed vs paid vs the tax bucket, retirement contribution progress and room, how much went into investing this month, whether the tax skim % is still right, net worth, and what's actually spendable. Use when the owner asks how far behind they are on taxes, what they owe, how much they've contributed, whether they're on track, or what their net worth or liquid cash is.
---

# Money status

**Never answer from the repo CSVs or a stored P&L alone** — they're as-of the last export. Query live.

## Sources

1. Live balances: `.venv/bin/python scripts/monarch.py accounts`
2. Live transactions: `.venv/bin/python scripts/monarch.py transactions --start <d> --end <d> --limit 5000` (check `totalCount`).
3. Accrued tax: `.venv/bin/python scripts/monarch_export.py` then `.venv/bin/python scripts/generate_pl.py --period ytd`; read TAX LIABILITY and AFTER-TAX OWNER EARNINGS. It's a projection; name its cutoff date.
4. Estimates paid: `[tax.years.<year>] estimates_paid` in `config.toml`, cross-checked against `<year>/q*-estimated-tax-payment-confirmation.md`.

## "How far behind am I on taxes?"

Five lines, in order:

1. **Tax accrued YTD** (P&L `TAX ACCRUED THIS PERIOD`, with cutoff date).
2. **Paid toward this tax year** (a January payment is usually last year's Q4; an April balance payment settles last year. Neither counts).
3. **In the bucket** (live balance of the `reserved` account).
4. **Gap** = accrued − paid − bucket. Say plainly if short and by how much.
5. **April exposure** = projected full-year tax − four estimates at the current pace.

Then the penalty check: safe harbor is 100% of last year's total tax (110% if last year's AGI was over $150K), paid in four installments. At or above it, no underpayment penalty regardless of the April balance. Say both: penalty status, and that the cash still has to exist in April.

## "How much have I contributed this month?"

Sum positive `Transfer` rows on the investing or retirement account for the month (exclude dividends, interest, and Buy rows inside the account). Pair a retirement number with room left against the year's limit (2026: $24,500 employee deferral, plus employer profit-sharing up to 20% of net SE earnings, total $72,000 — verify current limits).

## "Should I change the skim?"

Compare the skim % of topline against **effective tax rate on net profit × profit margin** (different denominators; never compare the skim to the effective rate directly). Use margin since the skim started. Costs are near-fixed, so incremental revenue needs roughly the effective rate itself. Report the accrued-basis gap, not just whether the next payment clears.

## Facts to apply

- Pre-tax 401(k) deferrals do not reduce SE tax for a sole proprietor; they also shrink the QBI base, so the real saving is below the bracket rate.
- In a Solo 401(k)'s first year, a sole proprietor can fund the prior year's deferrals up to the filing deadline (SECURE 2.0 §317). Verify for their plan.
- The tax bucket is never spendable and never in net worth.
- Watch the QBI threshold in `scripts/config.py` (2026: $201,750 single / $403,500 joint) — crossing it starts phasing out the 20% deduction.

## Output

Numbers first, no preamble. State the as-of date of anything not live. If they're short, say the amount and stop.
