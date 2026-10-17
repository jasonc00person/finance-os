# Finance OS for Claude Code

A complete bookkeeping, tax, and CFO system for a solo business, where **Claude Code is the application**. Connect Monarch Money once; from then on you ask Claude to close the books, check where you stand on taxes, or decide whether you can afford something.

Built for US single-member LLCs and sole proprietors filing Schedule C (single or married filing jointly).

## What you get

- **Monarch Money sync**: every transaction for the year, categorized in Monarch, exported to CSVs.
- **Double-entry ledger** (beancount) that must reconcile to your real bank balances, or the build fails.
- **Tax P&L**: Schedule C lines, home office, business spend on personal cards, meals at 50%, SE tax, federal income tax with QBI, safe-harbor estimates, and what you actually keep after tax. Any month, quarter, half, YTD, or full year.
- **Two published pages**: a drill-down P&L (click any line to see its transactions) and a live balance sheet with your tax reserve held out of net worth.
- **Skills**: `setup`, `monthly-close`, `find-transaction`, `money-status`, `log-estimated-tax-payment`, `affordability-check`.
- **Invoice template**, mileage log, audit-notes substantiation record, tax-strategy playbook.
- Optional read-only **Sequence** MCP if you route money with getsequence.io.

## Requirements

- macOS or Linux, Python 3.10+, [Claude Code](https://claude.com/claude-code)
- A [Monarch Money](https://www.monarchmoney.com) account with your bank and card accounts connected

## Start

```bash
git clone <this repo> my-finances && cd my-finances
claude
```

Then tell Claude: **"set me up"**. The `setup` skill installs dependencies, interviews you, has you log in to Monarch (you type your own password), maps your accounts and categories into `config.toml`, runs the first close, and publishes your P&L and balance sheet.

Make your copy **private** once your data is in it: your books, ledger, and config are personal financial records.

## See it working first

The `demo/` folder has a full year of fake books:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
FINANCE_HOME=demo .venv/bin/python scripts/csv_to_beancount.py
FINANCE_HOME=demo .venv/bin/python scripts/generate_pl.py --period ytd
FINANCE_HOME=demo .venv/bin/python scripts/make_pl_page.py     # open demo/2026/pl-page.html
```

## Every month

Say **"close the books"**. Claude runs the categorization sweep, export, ledger with fresh balance checks, P&Ls, and republishes both pages, then reports revenue, profit, tax owed vs paid vs reserved, net worth, and anything that looks wrong.

## Notes

- Monarch access uses the unofficial [`monarchmoneycommunity`](https://pypi.org/project/monarchmoneycommunity/) library. Your session token is stored locally in `.mm/` (gitignored).
- Tax figures are planning estimates, not tax advice or a filed return. Federal tables for 2025 and 2026 are in `scripts/config.py`; verify and add new years as the IRS publishes them.
- Claude never enters bank credentials, moves money, or places trades. You do.
