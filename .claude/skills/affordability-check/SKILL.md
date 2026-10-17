---
name: affordability-check
description: Give a CFO verdict on a purchase or discretionary spend, priced against the live books. Use when the owner asks whether they should buy something, whether they can afford it, how much car or house they could afford at some income, whether a trip or gift is reasonable, or whether to pay something off early versus invest.
---

# Affordability check

They want a verdict, not a framework. Lead with yes or no and the number that decides it, then the two or three figures behind it.

## The four numbers

Pull live:

1. **After-tax monthly earnings**: AFTER-TAX OWNER EARNINGS "Average per month" from `.venv/bin/python scripts/generate_pl.py --period ytd`.
2. **Personal burn**: monthly lifestyle spend from the personal CSV (ex-tax, ex-transfers); confirm against recent months for recurring purchases.
3. **Tax bucket status**: bucket vs accrued-but-unpaid tax. If short, discretionary spend competes with an April bill. Say so.
4. **Spendable cash**: liquid accounts only. The tax bucket is never spendable.

## By size

- **Small, one-off:** if the bucket is funded and burn is covered, say yes in one line and stop.
- **Recurring or financed:** convert to monthly, test against after-tax earnings minus burn, and name what it displaces (retirement room, a debt paydown, the tax bucket). That trade is the answer.
- **Large or aspirational:** answer the hypothetical honestly, then anchor it to the owner's own gates in `business-profile.md`. A hypothetical income is never the basis for a present-tense yes.

Debt vs invest: compare the loan APR to the risk-free yield and to the after-tax value of unused retirement room. Pay down high-APR debt after retirement room is used, unless the owner set a different order in `business-profile.md`.

## Don'ts

- No personalized investment advice (not a licensed advisor); no trades, transfers, or purchases.
- Don't moralize about discretionary spending. State what it costs against their stated priorities.
