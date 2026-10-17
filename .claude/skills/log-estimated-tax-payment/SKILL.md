---
name: log-estimated-tax-payment
description: Size a quarterly estimated tax payment before it's made and record it after — verify against safe harbor, write the confirmation file, wire it into the books, and state the next due date. Use when the owner needs to pay quarterly taxes, just paid an estimate, asks how much to pay this quarter, or asks when estimates are due.
---

# Estimated tax payments

Due dates: **Apr 15, Jun 15, Sep 15, Jan 15** (next business day if a weekend). Surface the next one at every close.

## Sizing

Floor = **prior-year safe harbor**: 100% of last year's total tax (Form 1040 line 24) ÷ 4, or 110% if last year's AGI was over $150K ($75K married filing separately). That figure lives in `config.toml` `prior_year_total_tax`; always take it from the filed return, never from a P&L estimate.

Sanity-check against reality with the `money-status` skill: if projected tax is far above four safe-harbor payments, say plainly that the floor is penalty-free but leaves a big April balance, and give the number. Add state estimates if `state_rate` > 0 (state rules differ; verify).

## Paying

**The owner pays.** Never enter bank details or credentials into IRS Direct Pay / the IRS Online Account for them. Pay from the tax bucket account.

## Recording

1. **Confirmation file:** `<year>/q<N>-estimated-tax-payment-confirmation.md` from `year-template/q-estimated-tax-payment-confirmation.md`. Capture the EFT/confirmation number verbatim; it's what the IRS asks for.
2. **Books:**
   - Paid from an account Monarch exports: it arrives via the export. Make sure it routes to `Equity:Draws:FederalTax` (the `USATAXPYMT` / `IRS TREAS` overrides catch most; else add a `date_amount_overrides` entry). Do **not** also add a manual entry.
   - Paid from an account Monarch doesn't export: add an entry to `<year>/ledger-manual.beancount`.
3. **P&L paid list:** append `["YYYY-MM-DD", amount]` to `[tax.years.<year>] estimates_paid` in `config.toml`. Only payments for that tax year.
4. **Monarch:** categorize the row `Taxes`.
5. State the next due date.

Federal estimates are personal obligations, never a Schedule C expense. Business-level taxes (state LLC fees, franchise tax) are deductible.
