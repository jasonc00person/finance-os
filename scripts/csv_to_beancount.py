#!/usr/bin/env python3
"""Build a double-entry beancount ledger from the year's CSVs (monarch_export.py output).

Usage (from the project root): .venv/bin/python scripts/csv_to_beancount.py [--year 2026]

Writes <year>/ledger.beancount (fully generated, never hand-edit) and prints a tie-out
report against raw CSV sums. Hand-maintained inputs:
  * <year>/ledger-manual.beancount      flows Monarch can't see (IRS payments from an
                                        untracked account, brokerage-internal journals)
  * <year>/ledger-assertions.beancount  dated real-world balances; bean-check FAILS if
                                        the books drift from them. Add fresh ones every close.

Routing:
  * Business Income rows -> Income:Business:<revenue line> (config [[revenue]]);
    revenue_exclude matches (gifts, owner money in) -> Equity:OwnerContributions.
  * Expense rows -> Expenses:Biz:<Category> / Expenses:Per:<Category>.
  * Transfers between two TRACKED accounts -> Assets:Transfers:Clearing; both legs post
    there and cancel, so a nonzero Clearing balance = in-transit or one-sided flows.
  * Transfers to UNTRACKED destinations ([ledger.untracked] keywords) post directly so
    those accounts carry running balances.
  * [ledger] overrides / date_amount_overrides beat everything else.
"""
import argparse, csv, re, subprocess, sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from config import ROOT, camel, cfg, default_year

CLEARING = 'Assets:Transfers:Clearing'
ALWAYS_OPEN = {'Equity:Draws:FederalTax', 'Equity:OpeningBalances', 'Equity:OwnerContributions', CLEARING}


def cat_account(row, biz):
    return f"Expenses:{'Biz' if biz else 'Per'}:{camel(row['Category'])}"


def route(row, biz, L):
    """Return the counterparty account for a CSV row."""
    desc, sd, typ = row['Description'], row['Statement description'], row['Type']
    blob = desc + ' | ' + sd
    for sub, acct in L['overrides']:
        if sub.lower() in blob.lower():
            return acct
    hit = L['date_amount'].get((row['Date'], Decimal(row['Amount'].replace(',', ''))))
    if hit:
        return hit
    if typ == 'Income' and biz:
        if any(x.lower() in blob.lower() for x in cfg().get('revenue_exclude', [])):
            return 'Equity:OwnerContributions'
        for x in cfg().get('revenue', []):
            if x['keyword'].lower() in blob.lower():
                return f"Income:Business:{camel(x['line'])}"
        return 'Income:Business:Other'
    # Sequence "SEQ <rule>: <src> - <dst>" routing text marks an internal move
    # regardless of Type (harmless if you don't use Sequence).
    m = re.search(r'SEQ[^:]*:\s*(.+?)\s+-\s+(.+?)(?:;|$)', sd)
    if m:
        amt = Decimal(row['Amount'].replace(',', ''))
        counter = (m.group(2) if amt < 0 else m.group(1)).lower()
        for kw, acct in L['untracked'].items():
            if kw.lower() in counter:
                return acct
        return CLEARING
    if typ == 'Expense':
        return cat_account(row, biz)
    if typ == 'Income':  # personal income (interest, rewards, paychecks)
        return f"Income:Personal:{camel(row['Category'])}"
    for kw, acct in L['untracked'].items():
        if kw.lower() in blob.lower():
            return acct
    return CLEARING


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=default_year())
    year = ap.parse_args().year
    Lc = cfg().get('ledger', {})
    L = dict(overrides=Lc.get('overrides', []), untracked=Lc.get('untracked', {}),
             date_amount={(d, Decimal(str(a))): acct for d, a, acct in Lc.get('date_amount_overrides', [])})
    known_dupes = {(d, s, Decimal(str(a))): int(keep) for d, s, a, keep in Lc.get('known_dupes', [])}
    acct_by_label = {a['label']: a['ledger'] for a in cfg()['accounts'] if a.get('export') is not False}

    rows = []
    for name, biz in [('transactions-business.csv', True), ('transactions-personal.csv', False)]:
        p = ROOT / str(year) / name
        if not p.exists():
            sys.exit(f'{p} missing. Run scripts/monarch_export.py first.')
        with open(p, newline='', encoding='utf-8-sig') as f:
            rows += [(r, biz) for r in csv.DictReader(f) if r['Date'].startswith(str(year))]
    rows.sort(key=lambda x: x[0]['Date'])

    accounts_used, lines, routed, dropped = set(), [], [], []
    dupe_seen = defaultdict(int)
    for r, biz in rows:
        amt = Decimal(r['Amount'].replace(',', ''))
        dk = next((k for k in known_dupes if r['Date'] == k[0] and amt == k[2]
                   and (k[1] in r['Description'] or k[1] in r['Statement description'])), None)
        if dk:
            dupe_seen[dk] += 1
            if dupe_seen[dk] > known_dupes[dk]:
                dropped.append((biz, r['Type'], amt))
                continue
        acct = acct_by_label.get(r['Account'])
        if not acct:
            sys.exit(f"Account '{r['Account']}' has no ledger account in config.toml [[accounts]].")
        other = route(r, biz, L)
        accounts_used.update([acct, other])
        routed.append((biz, r['Type'], amt, other, (r['Date'], amt) in L['date_amount']))
        payee = r['Description'].replace('"', "'").strip()[:80]
        lines.append(f'{r["Date"]} * "{payee}"\n  {acct}  {amt} USD\n  {other}\n')

    manual = (ROOT / str(year) / 'ledger-manual.beancount')
    asserts = (ROOT / str(year) / 'ledger-assertions.beancount')
    manual_txt = manual.read_text() if manual.exists() else ''
    assert_txt = asserts.read_text() if asserts.exists() else ''
    # Accounts referenced only in the hand-maintained files need open directives too.
    for txt in (manual_txt, assert_txt):
        for line in txt.splitlines():
            if line.strip().startswith(';'):
                continue
            accounts_used.update(re.findall(r'\b((?:Assets|Liabilities|Equity|Income|Expenses)(?::[A-Z][A-Za-z0-9-]*)+)', line))

    out = ROOT / str(year) / 'ledger.beancount'
    with open(out, 'w') as f:
        f.write(f'; Generated by csv_to_beancount.py from {year} monarch_export CSVs — do not hand-edit.\n')
        f.write(f'; Manual entries: {year}/ledger-manual.beancount. Balance assertions: {year}/ledger-assertions.beancount.\n')
        f.write(f'option "title" "{cfg()["business"]["name"]} + personal, {year}"\noption "operating_currency" "USD"\n\n')
        for a in sorted(accounts_used | ALWAYS_OPEN):
            f.write(f'{year}-01-01 open {a} USD\n')
        f.write('\n')
        f.writelines(lines)
        f.write('\n; ---- Manual entries (ledger-manual.beancount) ----\n')
        f.write(manual_txt)
        f.write('\n; ---- Balance assertions (ledger-assertions.beancount) ----\n')
        f.write(assert_txt)

    # ---- Verify: bean-check + tie-out against raw CSV sums ----
    bc = Path(sys.executable).parent / 'bean-check'   # installed next to the venv's python
    chk = subprocess.run([str(bc) if bc.exists() else 'bean-check', str(out)], capture_output=True, text=True)
    print(f'bean-check: {"PASS" if chk.returncode == 0 else "FAIL"}')
    if chk.returncode:
        print(chk.stderr[:3000]); sys.exit(1)

    from beancount import loader
    from beancount.core import data
    entries, errors, _ = loader.load_file(str(out))
    bal = defaultdict(Decimal)
    for e in entries:
        if isinstance(e, data.Transaction):
            for p in e.postings:
                bal[p.account] += p.units.number
    tot = lambda prefix: sum(v for k, v in bal.items() if k.startswith(prefix))

    D = lambda r: Decimal(r['Amount'].replace(',', ''))
    csv_biz_inc = sum(D(r) for r, b in rows if b and r['Type'] == 'Income')
    csv_biz_exp = sum(D(r) for r, b in rows if b and r['Type'] == 'Expense')
    csv_per_exp = sum(D(r) for r, b in rows if not b and r['Type'] == 'Expense')
    for b, t, a in dropped:
        if t == 'Expense' and b:
            csv_biz_exp -= a
        elif t == 'Expense':
            csv_per_exp -= a
        elif t == 'Income' and b:
            csv_biz_inc -= a
    if dropped:
        print(f'known dupes dropped: {len(dropped)} row(s)')

    def adj(prefix, biz_flag):
        """Rows of another Type routed INTO prefix, minus rows of prefix's Type routed
        elsewhere. Cross-CSV rows count only via a date_amount_override, so any other
        misroute still shows up as a tie-out mismatch."""
        typ = 'Income' if prefix.startswith('Income') else 'Expense'
        sgn = 1 if typ == 'Income' else -1
        gained = sum(sgn * a for b, t, a, o, dao in routed
                     if o.startswith(prefix) and ((b == biz_flag and t != typ) or (b != biz_flag and dao)))
        lost = sum(sgn * a for b, t, a, o, dao in routed if b == biz_flag and not o.startswith(prefix) and t == typ)
        return gained - lost

    n_manual = len(re.findall(r'(?m)^\d{4}-\d{2}-\d{2} [*!]', manual_txt))
    man_per_exp = sum(p.units.number for e in entries
                      if isinstance(e, data.Transaction) and 'manual' in (e.tags or set())
                      for p in e.postings if p.account.startswith('Expenses:Per'))
    print(f'transactions: {len(rows)} imported + {n_manual} manual')
    print('\nTIE-OUT (ledger vs raw CSV, adjusted for re-routed rows + #manual expenses)')
    print(f'  Income:Business   {-tot("Income:Business"):>12,.2f}  vs {csv_biz_inc + adj("Income:Business", True):>12,.2f}  (adj {adj("Income:Business", True):+,.2f})')
    print(f'  Expenses:Biz      {tot("Expenses:Biz"):>12,.2f}  vs {-csv_biz_exp + adj("Expenses:Biz", True):>12,.2f}  (adj {adj("Expenses:Biz", True):+,.2f})')
    print(f'  Expenses:Per      {tot("Expenses:Per"):>12,.2f}  vs {-csv_per_exp + adj("Expenses:Per", False) + man_per_exp:>12,.2f}  (adj {adj("Expenses:Per", False):+,.2f}, manual {man_per_exp:+,.2f})')
    print(f'\nCLEARING residual (in-transit + unexplained): {bal[CLEARING]:,.2f}')
    ext = sorted(set(L['untracked'].values()))
    if ext:
        print(f'\nUNTRACKED ACCOUNT FLOWS {year} (change since Jan 1)')
        for a in ext:
            print(f'  {a:<34} {bal[a]:>12,.2f}')
    print(f'\nTRACKED ACCOUNT NET CHANGE {year}')
    for a in sorted(k for k in bal if k.startswith(('Assets:Biz', 'Assets:Per', 'Assets:TaxBucket', 'Liabilities'))):
        print(f'  {a:<34} {bal[a]:>12,.2f}')
    print(f'  {"Equity:OwnerContributions":<34} {-bal["Equity:OwnerContributions"]:>12,.2f}')


if __name__ == '__main__':
    main()
