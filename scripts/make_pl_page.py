#!/usr/bin/env python3
"""Build the drill-down P&L page from the ledger.

Usage (from the project root): .venv/bin/python scripts/make_pl_page.py [--year 2026]
Writes <year>/pl-page.html (business view only). Publish it as an Artifact after each
close, to the URL saved in config.toml [artifacts] pl_page_url.
"""
import argparse, json
from beancount import loader
from beancount.core import data

from config import ROOT, TEMPLATES, camel, cfg, default_year
from generate_pl import compute_pl, home_office_pct, periods


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=default_year())
    year = ap.parse_args().year

    # Ledger leaves are CamelCased config names; map them back to the readable name.
    names = [x['line'] for x in cfg().get('revenue', [])] + list(cfg()['categories'].get('deductible', {})) \
        + cfg()['categories'].get('non_deductible', []) + cfg()['categories'].get('refunds', ['Refunds'])
    pretty = {camel(n): n for n in names}
    pretty.update(Other='Other income', Uncategorized='Uncategorized')

    entries, errors, _ = loader.load_file(str(ROOT / str(year) / 'ledger.beancount'))
    assert not errors, errors[:3]
    inc, exp = [], []
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        for p in e.postings:
            row = dict(d=e.date.isoformat(), n=(e.narration or e.payee or '')[:60], a=float(p.units.number))
            leaf = p.account.rsplit(':', 1)[1]
            if p.account.startswith('Income:Business:'):
                row['a'] = -row['a']
                row['c'] = pretty.get(leaf, leaf)
                inc.append(row)
            elif p.account.startswith('Expenses:Biz:'):
                row['c'] = pretty.get(leaf, leaf)
                exp.append(row)
    last = max(r['d'] for r in inc + exp)

    # Tax-view section: Schedule C deductions paid outside the business accounts (home
    # office, personal-card business spend), from the same engine as the tax P&L.
    start, end, _ = periods(year)['full']
    t = compute_pl(year, start, end)
    ho_cat = f'Home office ({home_office_pct()*100:.2f}% of rent+utilities)'
    taxonly = [dict(d=dt, n=n[:60], a=round(a, 2), c=ho_cat) for dt, n, a in t['ho_rows']] + \
              [dict(d=dt, n=n[:60], a=round(a, 2), c=f'{b} — personal card') for dt, n, a, b in t['pcard']]

    payload = json.dumps(dict(year=year, asof=last, income=inc, expense=exp, taxonly=taxonly), separators=(',', ':'))
    html = (TEMPLATES / 'pl-page.template.html').read_text() \
        .replace('__BUSINESS_NAME__', cfg()['business']['name']).replace('/*__DATA__*/', payload)
    out = ROOT / str(year) / 'pl-page.html'
    out.write_text(html)
    print(f'{out}  ({len(inc)} income rows, {len(exp)} expense rows, through {last})')


if __name__ == '__main__':
    main()
