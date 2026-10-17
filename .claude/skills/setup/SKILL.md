---
name: setup
description: First-run onboarding for this finance system — interview the owner, connect Monarch, map every account and category into config.toml, run the first export, ledger and P&L, and publish the P&L and balance-sheet pages. Use when the owner says set up, get started, onboard me, connect Monarch, or when config.toml still says "Your Business LLC".
---

# Setup

Goal: from a fresh copy to a reconciled YTD P&L and both pages published, in one session. Do the work; ask only what only the owner knows.

## 1. Environment

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Python 3.10+. If `python3` is older, install a current one (`brew install python`) first.

## 2. Interview (one message, all at once)

Ask for: business legal name, owner name, entity type and state, filing status (single or married filing jointly), last year's total federal tax (Form 1040 line 24, for safe harbor), estimated payments already made this year (date + amount), pre-tax retirement contributions funded this year, whether they skim a % of revenue into a tax account (and which account), home office square footage vs home square footage (or none), revenue sources (platforms that pay them), and any business expenses they pay on personal cards (vendors, and business-use % for phone/internet).

Write the answers into `config.toml` ([business], [tax], [tax.years.<year>], [home_office], [personal_card], [[revenue]]) and into `business-profile.md`.

## 3. Connect Monarch

The owner runs the login themselves (it prompts for email, password, MFA). Never type their credentials.

```bash
.venv/bin/python scripts/monarch.py auth
```

Session lands in `.mm/` (gitignored). On any later 401, rerun auth.

## 4. Map accounts

```bash
.venv/bin/python scripts/monarch.py accounts
```

Replace the placeholder `[[accounts]]` in `config.toml` with one entry per real account. Use the `(...1234)` mask as `match` wherever Monarch shows one (rename-proof). Decide with the owner: business vs personal side, and the balance-sheet bucket. The account that holds tax money is `balance_sheet = "reserved"` with a ledger name under `Assets:TaxBucket:`. Brokerage/retirement accounts are `export = false` plus an `[ledger.untracked]` keyword so transfers into them get a running balance.

## 5. Map categories

```bash
.venv/bin/python scripts/monarch.py categories
```

Every category used on a business account must be in `[categories.deductible]` or `non_deductible`, else it lands in the P&L REVIEW block. Custom categories the owner created need a line. Note which Monarch group holds business categories (`business_group`).

## 6. First export, ledger, P&L

```bash
.venv/bin/python scripts/monarch_export.py
.venv/bin/python scripts/csv_to_beancount.py
.venv/bin/python scripts/generate_pl.py --period ytd
```

Gates: `bean-check: PASS`, tie-out lines match, P&L `Difference (should be ~0)` reads 0.00. Then work the REVIEW block and "Other Revenue" line with the owner until both are empty: add `[[revenue]]` keywords, recategorize in Monarch, or extend the category maps, then rerun from export.

Clearing residual: transfers between two exported accounts cancel. A big residual means a transfer goes to an account not in config: add it, or add an `[ledger.untracked]` keyword.

Opening balances: accounts that existed before Jan 1 need `pad` + `balance` lines in `<year>/ledger-assertions.beancount` (see the monthly-close skill). Add them now from today's `monarch.py accounts` balances.

## 7. Publish the pages

```bash
.venv/bin/python scripts/make_pl_page.py
.venv/bin/python scripts/make_balance_sheet.py
```

Publish `<year>/pl-page.html` and `<year>/balance-sheet.html` with the Artifact tool, then save both URLs in `config.toml` [artifacts] so every later close updates the same pages.

## 8. Fill the playbook

Copy `year-template/` files into `<year>/` if not there (`tax-strategy.md`, `audit-notes.md`, `mileage-log.md`). Fill `tax-strategy.md` with the owner's real numbers: Solo 401(k) room, S-corp trigger, QBI headroom. Then `git add -A && git commit`.

Report: YTD revenue, expenses, net profit, tax accrued vs paid vs bucket, net worth, and the two page links.
