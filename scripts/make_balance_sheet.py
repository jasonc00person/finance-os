#!/usr/bin/env python3
"""Build the balance-sheet page from LIVE Monarch balances.

Usage (from the project root): .venv/bin/python scripts/make_balance_sheet.py [--year 2026]
Writes <year>/balance-sheet.html. Every figure is the live Monarch balance, mapped by
config.toml [[accounts]] balance_sheet = liquid | invest | liability | reserved | skip.
The tax reserve is shown separately and never counted in net worth.
Pass --from-json <file> (a saved `monarch.py accounts`-style dump) to build offline.
"""
import argparse, asyncio, json, re, sys
from datetime import date

from config import ROOT, TEMPLATES, cfg, default_year, match_account


async def fetch():
    from monarchmoney import MonarchMoney
    mm = MonarchMoney()
    try:
        mm.load_session()
    except FileNotFoundError:
        sys.exit('No Monarch session. Run `.venv/bin/python scripts/monarch.py auth` first.')
    mm.set_timeout(60)
    return [dict(name=a['displayName'], balance=a.get('displayBalance'))
            for a in (await mm.get_accounts())['accounts']]


def pl_tax(year):
    """Tax figures from the latest <year>/ytd-profit-and-loss.txt, or None."""
    try:
        txt = (ROOT / str(year) / 'ytd-profit-and-loss.txt').read_text()
    except FileNotFoundError:
        return None
    span = re.search(r'(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})', txt)
    unpaid = re.search(r'Accrued, not yet paid \(hold in bucket\)\s+\$\s*(-?[\d,]+\.\d{2})', txt)
    sh_q = re.search(r'Prior-year safe harbor \(per quarter\)\s+\$\s*(-?[\d,]+\.\d{2})', txt)
    if not (span and unpaid) or span.group(1) != f'{year}-01-01':
        return None
    num = lambda m: float(m.group(1).replace(',', '')) if m else None
    return dict(through=span.group(2), unpaid=num(unpaid), safe_harbor_q=num(sh_q))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=default_year())
    ap.add_argument('--from-json')
    a = ap.parse_args()

    accounts = json.load(open(a.from_json)) if a.from_json else asyncio.run(fetch())
    assets, liabilities = [], []
    reserved = 0.0
    for acct in accounts:
        name, bal = acct['name'], float(acct.get('balance') or 0)
        hit = match_account(name)
        bucket = (hit or {}).get('balance_sheet', 'skip')
        if hit is None:
            if abs(bal) > 1:
                print(f'  ! unmapped account with balance, not shown: {name} = {bal}', file=sys.stderr)
            continue
        label = hit.get('display') or hit['label']
        if bucket == 'reserved':
            reserved += bal
        elif bucket == 'liability':
            # Monarch shows amounts owed as positive; a card carrying a credit stays negative.
            if abs(bal) > 0.004:
                liabilities.append((label if bal > 0 else f'{label} (credit balance)', bal))
        elif bucket in ('liquid', 'invest') and abs(bal) > 0.004:
            assets.append((label, bal, bucket))

    liquid = sum(v for _, v, k in assets if k == 'liquid')
    invest = sum(v for _, v, k in assets if k == 'invest')
    total_liab = sum(v for _, v in liabilities)
    payload = json.dumps(dict(
        asof=str(date.today()), assets=[[n, v, k] for n, v, k in assets],
        liabilities=[[n, v] for n, v in liabilities], liquid=liquid, invest=invest,
        total_assets=liquid + invest, total_liab=total_liab, net_worth=liquid + invest - total_liab,
        reserved=reserved, tax=pl_tax(a.year), skim=cfg().get('tax', {}).get('skim_rate'),
    ), separators=(',', ':'))
    html = (TEMPLATES / 'balance-sheet.template.html').read_text() \
        .replace('__BUSINESS_NAME__', cfg()['business']['name']).replace('/*__DATA__*/', payload)
    out = ROOT / str(a.year) / 'balance-sheet.html'
    out.write_text(html)
    print(f'{out}  net worth ${liquid + invest - total_liab:,.2f} (+${reserved:,.2f} reserved), live as of {date.today()}')


if __name__ == '__main__':
    main()
