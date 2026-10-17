#!/usr/bin/env python3
"""Profit & Loss generator (canonical tax view, period-parameterized).

Usage (run from the project root):
    .venv/bin/python scripts/generate_pl.py                      # current-year YTD
    .venv/bin/python scripts/generate_pl.py --period q1          # q1|q2|q3|q4
    .venv/bin/python scripts/generate_pl.py --period h1          # h1|h2
    .venv/bin/python scripts/generate_pl.py --period sep         # a single month
    .venv/bin/python scripts/generate_pl.py --period full        # full year
    .venv/bin/python scripts/generate_pl.py --period ytd --end 2026-08-31   # close a month after the fact

Reads  {year}/transactions-business.csv + {year}/transactions-personal.csv (monarch_export.py)
Writes {year}/{period}-profit-and-loss.txt ('full' -> profit-and-loss.txt).
All mappings live in config.toml.

Methodology:
  * Business-account expenses deduct per [categories.deductible] (line, fraction).
    Categories in non_deductible are tracked, not deducted. Anything else lands in a
    REVIEW block and is NOT deducted until mapped (fail closed).
  * Home office = home_office.pct of personal rows in home_office.categories
    (credits in those categories, e.g. roommate reimbursements, net the pool).
  * Business spend on personal cards: personal_card one-offs, partial-use vendors,
    SaaS vendors, then any personal row whose Monarch category sits in the business
    group. Credits net against the same vendor; periods sum to YTD.
"""
import argparse
import calendar
import csv
import re
from collections import defaultdict
from datetime import date, timedelta

from config import ROOT, cfg, default_year, frozen_years, tax_year

TODAY = date.today()
MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
SEQ_MOVE = re.compile(r'SEQ[^:]*:\s*.+\s+-\s+')   # Sequence "<src> - <dst>" text = internal move
# Internal categories the rules below assign; mapped here, not in config.
INTERNAL = {'Taxes & Licenses': ('Taxes & Licenses', 1.0), 'Contract Labor (rule)': ('Contract Labor', 1.0)}


def home_office_pct():
    return float(cfg().get('home_office', {}).get('pct', 0.0))


def data_end(year):
    """Latest transaction date across the year's CSVs — actual data coverage."""
    latest = ''
    for name in ('transactions-business.csv', 'transactions-personal.csv'):
        p = ROOT / f'{year}/{name}'
        if p.exists():
            for r in csv.DictReader(open(p)):
                if r['Date'].startswith(str(year)) and r['Date'] > latest:
                    latest = r['Date']
    return latest


def periods(year):
    y = str(year)
    q = {
        'q1': (f'{y}-01-01', f'{y}-03-31', 'Q1 (Jan–Mar)'),
        'q2': (f'{y}-04-01', f'{y}-06-30', 'Q2 (Apr–Jun)'),
        'q3': (f'{y}-07-01', f'{y}-09-30', 'Q3 (Jul–Sep)'),
        'q4': (f'{y}-10-01', f'{y}-12-31', 'Q4 (Oct–Dec)'),
    }
    q['h1'] = (q['q1'][0], q['q2'][1], 'H1 (Jan–Jun)')
    q['h2'] = (q['q3'][0], q['q4'][1], 'H2 (Jul–Dec)')
    q['full'] = (f'{y}-01-01', f'{y}-12-31', f'Full Year {y}')
    for i, m in enumerate(MONTHS, 1):
        last = calendar.monthrange(int(y), i)[1]
        q[m] = (f'{y}-{i:02d}-01', f'{y}-{i:02d}-{last}', f'{calendar.month_name[i]} {y}')
    # Current-year YTD ends at the last transaction in the CSVs, not the run date —
    # stamping today over a stale export mislabels the period and skews annualization.
    cutoff = min(filter(None, [TODAY.isoformat(), data_end(year)])) if int(y) == TODAY.year else f'{y}-12-31'
    q['ytd'] = (f'{y}-01-01', cutoff, f'YTD (Jan 1 – {cutoff})')
    return q


def load(path, start, end):
    if not path.exists():
        return []
    return [r for r in csv.DictReader(open(path)) if start <= r['Date'] <= end]


def compute_pl(year, start, end):
    """Return a dict of all P&L figures for [start, end]."""
    C, R = cfg()['categories'], cfg().get('rules', {})
    deductible = {**{k: tuple(v) for k, v in C.get('deductible', {}).items()}, **INTERNAL}
    non_ded = set(C.get('non_deductible', [])) | {"Owner's draw"}
    refunds = set(C.get('refunds', ['Refunds']))
    biz = load(ROOT / f'{year}/transactions-business.csv', start, end)
    inc = [r for r in biz if r['Type'] == 'Income']
    exp = [r for r in biz if r['Type'] == 'Expense' and not SEQ_MOVE.search(r['Statement description'])]

    blob = lambda r: (r['Description'] + '; ' + r['Statement description']).lower()
    tax_markers = [m.lower() for m in R.get('business_tax_markers', [])]
    for r in biz:
        if any(r['Date'] == d and s.lower() in blob(r) for d, s in R.get('personal_oneoffs', [])):
            r['Category'] = "Owner's draw"            # personal spend paid from a business account
        elif r['Category'] == 'Taxes' and any(m in blob(r) for m in tax_markers):
            r['Category'] = 'Taxes & Licenses'        # entity tax/fee, not income tax

    # Contractor payments that arrive typed as transfers (e.g. Mercury/ACH sends) or
    # with junk categories: force to Contract Labor by statement-text marker.
    markers = [m.lower() for m in R.get('contractor_markers', [])]
    for r in biz:
        if markers and any(m in blob(r) for m in markers):
            if r['Type'] == 'Transfer' and float(r['Amount']) < 0:
                exp.append({**r, 'Category': 'Contract Labor (rule)'})
            elif r['Type'] == 'Expense':
                r['Category'] = 'Contract Labor (rule)'

    # Revenue
    rev_map = [(x['keyword'].upper(), x['line']) for x in cfg().get('revenue', [])]
    rev_excl = [x.lower() for x in cfg().get('revenue_exclude', [])]
    date_ov = {(d, round(float(a), 2)): line for d, a, line in cfg().get('revenue_date_overrides', [])}
    sources = defaultdict(float)
    for r in inc:
        d = r['Description'].upper() + ' ' + r['Statement description'].upper()
        if any(x in d.lower() for x in rev_excl):
            continue
        ov = date_ov.get((r['Date'], round(float(r['Amount']), 2)))
        if ov:
            sources[ov] += float(r['Amount'])
            continue
        for kw, label in rev_map:
            if kw in d:
                sources[label] += float(r['Amount'])
                break
        else:
            sources['Other Revenue'] += float(r['Amount'])
    gross = sum(sources.values())
    refund_total = sum(-float(r['Amount']) for r in exp if r['Category'] in refunds)
    net_rev = gross - refund_total

    # Business expenses
    pl, nd = defaultdict(float), defaultdict(float)
    review = []   # unmapped-category rows: not deducted until mapped (fail closed)
    for r in exp:
        cat, raw = r['Category'], float(r['Amount'])
        if cat in refunds:
            continue
        if raw > 0:                       # credit/refund reduces expenses
            pl['Credits & Refunds Received'] -= raw
            continue
        amt = abs(raw)
        if cat in deductible:
            line, frac = deductible[cat]
            pl[line] += amt * frac
            if frac < 1.0:
                nd[f'{cat} (non-deductible portion)'] += amt * (1 - frac)
        elif cat in non_ded:
            nd[cat] += amt
        else:
            nd[f'UNMAPPED: {cat} (review)'] += amt
            review.append((r['Date'], raw, r['Description'], cat))

    # Home office: pct of personal rows in the home-office categories
    HO = cfg().get('home_office', {})
    pct = home_office_pct()
    pers = load(ROOT / f'{year}/transactions-personal.csv', start, end)
    ho, ho_rows = defaultdict(float), []
    if pct:
        for r in pers:
            if r['Type'] == 'Expense' and r['Category'] in HO.get('categories', []):
                a = -float(r['Amount'])           # charges positive, credits negative
                ho[r['Category']] += a
                ho_rows.append((r['Date'], f'{r["Category"]} — {r["Description"][:40]}', a * pct))
    ho_basis = sum(ho.values())
    ho_ded = max(0.0, ho_basis * pct)
    if ho_ded:
        pl[f'Home Office ({pct*100:.2f}% of rent+utilities)'] += ho_ded

    # Business expenses on personal cards (programmatic; no hardcoded amounts).
    PC = cfg().get('personal_card', {})
    group = C.get('business_group', 'Business')
    group_excl = set(PC.get('exclude_group_categories', []))
    pers_cum = load(ROOT / f'{year}/transactions-personal.csv', f'{year}-01-01', end)

    def pcard_match(r):
        dl = (r['Description'] + ' ' + r['Statement description']).lower()
        for dt, sub, f, b in PC.get('oneoffs', []):
            if r['Date'] == dt and sub.lower() in dl:
                return f'{dt}:{sub}', float(f), b
        for vend, (f, b) in PC.get('partial', {}).items():
            if vend.lower() in dl:
                return vend, float(f), b
        for vend, b in PC.get('saas', {}).items():
            if vend.lower() in dl:
                return vend, 1.0, b
        if r.get('Group') == group and r['Category'] not in group_excl:
            line, frac = deductible.get(r['Category'], ('Other Business Expenses', 1.0))
            return f'business-group:{line}:{frac}', frac, line
        return None

    def vendor_groups(rows):
        groups = {}
        for r in rows:
            if r['Type'] != 'Expense':
                continue
            m = pcard_match(r)
            if m:
                key, frac, bucket = m
                g = groups.setdefault(key, dict(net=0.0, frac=frac, bucket=bucket, rows=[]))
                g['net'] += -float(r['Amount'])
                g['rows'].append(r)
        return groups
    vend_groups = vendor_groups(pers_cum)
    prior_groups = vendor_groups([r for r in pers_cum if r['Date'] < start])
    pcard = []
    for key, g in vend_groups.items():
        # Period deduction = cumulative through `end` minus cumulative before `start`
        # (both from Jan 1), so periods sum to YTD and a refund never deducts below zero.
        before = max(0.0, prior_groups[key]['net'] * g['frac']) if key in prior_groups else 0.0
        end_ded = max(0.0, g['net'] * g['frac'])
        if not end_ded and not before:
            continue
        rows_in = [r for r in g['rows'] if r['Date'] >= start]
        if not rows_in:
            continue
        if abs((end_ded - before) - sum(-float(r['Amount']) * g['frac'] for r in rows_in)) >= 0.005:
            pcard.append((max(r['Date'] for r in rows_in),
                          f"{rows_in[0]['Description'][:20]} net vs prior periods", end_ded - before, g['bucket']))
            pl[g['bucket']] += end_ded - before
            continue
        for r in rows_in:
            ded = -float(r['Amount']) * g['frac']
            label = r['Description'] if g['frac'] == 1.0 else f"{r['Description'][:24]} ({int(g['frac']*100)}% biz)"
            pcard.append((r['Date'], label, ded, g['bucket']))
            pl[g['bucket']] += ded
    pcard_total = sum(x[2] for x in pcard)

    total_exp = sum(pl.values())
    net_profit = net_rev - total_exp

    # Monthly
    mi, me = defaultdict(float), defaultdict(float)
    for r in inc:
        if not any(x in (r['Description'] + ' ' + r['Statement description']).lower() for x in rev_excl):
            mi[r['Date'][:7]] += float(r['Amount'])
    for r in exp:
        cat, raw = r['Category'], float(r['Amount'])
        if cat in refunds:
            mi[r['Date'][:7]] += raw
        elif raw > 0:
            me[r['Date'][:7]] -= raw
        elif cat in deductible:
            me[r['Date'][:7]] += abs(raw) * deductible[cat][1]

    vendors = defaultdict(float)
    for r in exp:
        if r['Category'] in non_ded or r['Category'] in refunds:
            continue
        if float(r['Amount']) < 0:
            vendors[r['Description']] += -float(r['Amount'])

    return dict(sources=sources, gross=gross, refund_total=refund_total, net_rev=net_rev,
                pl=pl, nd=nd, total_exp=total_exp, net_profit=net_profit,
                ho=ho, ho_basis=ho_basis, ho_ded=ho_ded, ho_rows=ho_rows,
                pcard=pcard, pcard_total=pcard_total,
                mi=mi, me=me, vendors=vendors, review=review,
                biz_exp_raw=abs(sum(float(r['Amount']) for r in exp if float(r['Amount']) < 0)))


def income_tax(taxable, brackets):
    tax, lo = 0.0, 0.0
    for hi, rate in brackets:
        if taxable <= lo:
            break
        tax += (min(taxable, hi) - lo) * rate
        lo = hi
    return tax


def tax_calc(annual_net, t):
    """Federal SE + income tax on Schedule C profit (plus other_income), plus a flat
    state estimate. Approximation for planning, not a return."""
    se_base = max(0.0, annual_net) * 0.9235
    se_tax = min(se_base, t['ss_wage_base']) * 0.124 + se_base * 0.029
    se_ded = se_tax / 2
    addl_medicare = max(0, se_base - t['addl_medicare']) * 0.009   # Form 8959
    rc = t['retirement_contrib']   # full-year amount, never annualized; no SE-tax effect
    agi = annual_net + t['other_income'] - se_ded - rc
    taxable_pre_qbi = max(0, agi - t['std_ded'])
    qbi = 0.20 * max(0.0, annual_net - se_ded - rc)
    # Above the threshold the W-2 wage/UBIA limit phases in; with no W-2 wages the
    # deduction shrinks linearly to zero across the phase-in range. Assumes non-SSTB.
    over = taxable_pre_qbi - t['qbi_threshold']
    if over > 0:
        qbi *= max(0.0, 1 - over / t['qbi_phase_in'])
    qbi = max(0, min(qbi, 0.20 * taxable_pre_qbi))
    taxable = max(0, taxable_pre_qbi - qbi)
    it = income_tax(taxable, t['brackets']) - income_tax(max(0, t['other_income'] - t['std_ded']), t['brackets'])
    state = max(0.0, annual_net) * t['state_rate']
    return dict(se_tax=se_tax, se_ded=se_ded, qbi=qbi, agi=agi, taxable=taxable,
                income_tax=it, state=state, total=se_tax + it + addl_medicare + state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=default_year())
    ap.add_argument('--period', default='ytd',
                    choices=['q1', 'q2', 'q3', 'q4', 'h1', 'h2', 'ytd', 'full'] + MONTHS)
    ap.add_argument('--end', help='YTD cutoff (YYYY-MM-DD) when closing a month after the fact')
    ap.add_argument('--force-frozen', action='store_true',
                    help="allow overwriting a frozen (as-filed) year's P&L file")
    args = ap.parse_args()
    year, pkey = args.year, args.period
    start, end, label = periods(year)[pkey]
    if args.end and pkey == 'ytd':
        end, label = args.end, f'YTD (Jan 1 – {args.end})'
    cfg_t = tax_year(year)
    pct = home_office_pct()
    name = cfg()['business']['name']

    d = compute_pl(year, start, end)
    span_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    frac = span_days / 365
    is_partial = pkey != 'full'

    W = 68
    out = []
    def p(s=''): out.append(s)

    p('=' * W)
    p(f'   {name.upper()}')
    p('   PROFIT & LOSS STATEMENT')
    p(f'   {label}  —  {start} to {end}')
    p('=' * W)

    p('')
    p('  REVENUE')
    p('  ' + '-' * (W - 4))
    for k, v in sorted(d['sources'].items(), key=lambda x: -x[1]):
        p(f'    {k:<42} ${v:>11,.2f}')
    p(f'  {"GROSS REVENUE":<44} ${d["gross"]:>11,.2f}')
    if d['refund_total']:
        p(f'    {"Client Refunds & Returns":<42} $({d["refund_total"]:>9,.2f})')
        p('  ' + '-' * (W - 4))
        p(f'  {"NET REVENUE":<44} ${d["net_rev"]:>11,.2f}')

    p('')
    p('  OPERATING EXPENSES (deductible)')
    p('  ' + '-' * (W - 4))
    for k, v in sorted(d['pl'].items(), key=lambda x: -x[1]):
        p(f'    {k:<42} ${v:>11,.2f}')
    p('  ' + '-' * (W - 4))
    p(f'  {"TOTAL DEDUCTIBLE EXPENSES":<44} ${d["total_exp"]:>11,.2f}')

    p('')
    p('  ' + '=' * (W - 4))
    p(f'  {"NET PROFIT":<44} ${d["net_profit"]:>11,.2f}')
    p('  ' + '=' * (W - 4))
    if d['net_rev']:
        p(f'  {"Profit Margin":<44} {d["net_profit"]/d["net_rev"]*100:>11.1f}%')

    if d['ho_ded']:
        p('')
        p('')
        p(f'  HOME OFFICE DEDUCTION ({pct*100:.2f}% business-use share)')
        p('  ' + '-' * (W - 4))
        for k, v in sorted(d['ho'].items(), key=lambda x: -x[1]):
            p(f'    {k:<24} ${v:>10,.2f} x {pct*100:.2f}% = ${v*pct:>9,.2f}')
        p('  ' + '-' * (W - 4))
        p(f'  {"HOME OFFICE DEDUCTION":<44} ${d["ho_ded"]:>11,.2f}')

    if d['pcard']:
        p('')
        p('')
        p('  BUSINESS EXPENSES PAID ON PERSONAL CARDS')
        p('  ' + '-' * (W - 4))
        for dt, desc, amt, bucket in sorted(d['pcard']):
            p(f'    {dt}  {desc[:30]:<30} ${amt:>8,.2f}')
        p('  ' + '-' * (W - 4))
        p(f'  {"TOTAL PERSONAL-CARD BUSINESS EXPENSES":<44} ${d["pcard_total"]:>11,.2f}')

    p('')
    p('')
    p('  MONTHLY SUMMARY')
    p('  ' + '-' * (W - 4))
    p(f'  {"Month":<10} {"Revenue":>12} {"Expenses":>12} {"Net":>12} {"Margin":>8}')
    p(f'  {"-"*10} {"-"*12} {"-"*12} {"-"*12} {"-"*8}')
    for m in sorted(set(d['mi']) | set(d['me'])):
        rev, ex = d['mi'].get(m, 0), d['me'].get(m, 0)
        net = rev - ex
        p(f'  {m:<10} ${rev:>10,.0f} ${ex:>10,.0f} ${net:>10,.0f} {(net / rev * 100) if rev > 0 else 0:>6.1f}%')

    p('')
    p('')
    state_lbl = f' + {cfg_t["state_rate"]*100:.1f}% state est.' if cfg_t['state_rate'] else ''
    if pkey in MONTHS:
        # A month annualized on its own (x12) overstates the year, so a month's tax is
        # the change in YTD accrued tax across it.
        ystart = f'{year}-01-01'
        def ytd_accrued(e):
            fr = ((date.fromisoformat(e) - date.fromisoformat(ystart)).days + 1) / 365
            an = compute_pl(year, ystart, e)['net_profit'] / fr
            tt = tax_calc(an, cfg_t)
            return tt['total'] * fr, tt, an
        acc_now, t, annual_net = ytd_accrued(end)
        prev_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        acc_prev = ytd_accrued(prev_end)[0] if prev_end >= ystart else 0.0
        owed = acc_now - acc_prev
        p('  TAX LIABILITY — ' + label.upper())
        p('  ' + '-' * (W - 4))
        p(f'    {"Net profit this month":<42} ${d["net_profit"]:>11,.2f}')
        p(f'    {f"YTD net profit annualized (thru {end})":<42} ${annual_net:>11,.2f}')
        p(f'    {f"Projected TOTAL {year} tax":<42} ${t["total"]:>11,.2f}')
        p(f'    {f"YTD tax accrued thru {end}":<42} ${acc_now:>11,.2f}')
        p(f'    {f"YTD tax accrued thru {prev_end}":<42} ${acc_prev:>11,.2f}')
        p('  ' + '-' * (W - 4))
        p(f'  {"TAX ACCRUED THIS MONTH (the difference)":<44} ${owed:>11,.2f}')
        if d['net_profit']:
            p(f'    {"Effective rate on this month":<42} {owed / d["net_profit"] * 100:>11.1f}%')
    elif is_partial:
        annual_net = d['net_profit'] / frac
        t = tax_calc(annual_net, cfg_t)
        owed = t['total'] * frac
        p('  TAX LIABILITY — ' + label.upper() + state_lbl.upper())
        p('  ' + '-' * (W - 4))
        p(f'    {"Net profit this period":<42} ${d["net_profit"]:>11,.2f}')
        p(f'    {"Annualized net profit":<42} ${annual_net:>11,.2f}')
        if cfg_t['retirement_contrib']:
            p(f'    {"Pre-tax retirement contributions (funded)":<42} ${cfg_t["retirement_contrib"]:>11,.2f}')
        p(f'    {"Projected SE tax (annual)":<42} ${t["se_tax"]:>11,.2f}')
        p(f'    {"Projected federal income tax (annual)":<42} ${t["income_tax"]:>11,.2f}')
        if t['state']:
            p(f'    {"Projected state tax (annual, flat est.)":<42} ${t["state"]:>11,.2f}')
        p(f'    {"QBI deduction (annual)":<42} ${t["qbi"]:>11,.2f}')
        p(f'    {f"Projected TOTAL {year} tax":<42} ${t["total"]:>11,.2f}')
        p(f'    {"Effective rate on net profit":<42} {t["total"] / annual_net * 100 if annual_net else 0:>11.1f}%')
        p('  ' + '-' * (W - 4))
        p(f'  {"TAX ACCRUED THIS PERIOD (owed so far)":<44} ${owed:>11,.2f}')
        if cfg_t['prior_year_total_tax']:
            p('')
            p(f'    {"Prior-year safe harbor (per quarter)":<42} ${cfg_t["prior_year_total_tax"] / 4:>11,.2f}')
            p(f'    {f"  (100% of {year-1} total tax / 4)":<42}')
    else:
        t = tax_calc(d['net_profit'], cfg_t)
        p(f'  TAX LIABILITY — FULL YEAR {year}')
        p('  ' + '-' * (W - 4))
        if cfg_t['retirement_contrib']:
            p(f'    {"Pre-tax retirement contributions (funded)":<42} ${cfg_t["retirement_contrib"]:>11,.2f}')
        p(f'    {"Self-Employment Tax (15.3%)":<42} ${t["se_tax"]:>11,.2f}')
        p(f'    {"Federal Income Tax":<42} ${t["income_tax"]:>11,.2f}')
        if t['state']:
            p(f'    {"State tax (flat est.)":<42} ${t["state"]:>11,.2f}')
        p(f'    {"QBI Deduction (20%, w/ limit)":<42} ${t["qbi"]:>11,.2f}')
        p(f'    {"Taxable Income":<42} ${t["taxable"]:>11,.2f}')
        p('  ' + '-' * (W - 4))
        p(f'  {f"TOTAL {year} TAX":<44} ${t["total"]:>11,.2f}')
        if d['net_rev']:
            p(f'  {"Effective Tax Rate (on net revenue)":<44} {t["total"]/d["net_rev"]*100:>11.1f}%')

    # What's left after tax. Estimates are owner draws, not expenses, so they never hit
    # the P&L above — net profit is the taxable number, this is the one the owner keeps.
    tax_period = owed if is_partial else t['total']
    paid = sum(a for dt, a in cfg_t['estimates_paid'] if start <= dt <= end)
    months = span_days / 30.44
    p('')
    p('')
    p(f'  AFTER-TAX OWNER EARNINGS — {label.upper()}')
    p('  ' + '-' * (W - 4))
    p(f'    {"Net profit this period":<42} ${d["net_profit"]:>11,.2f}')
    p(f'    {"Less: tax accrued this period":<42} $-{tax_period:>10,.2f}')
    p('  ' + '-' * (W - 4))
    p(f'  {"WHAT YOU KEEP (after-tax)":<44} ${d["net_profit"] - tax_period:>11,.2f}')
    if months >= 1:
        p(f'    {"Average per month":<42} ${(d["net_profit"] - tax_period) / months:>11,.2f}')
    p('')
    p(f'    {"Estimates paid in this period":<42} ${paid:>11,.2f}')
    p(f'    {"Accrued, not yet paid (hold in bucket)":<42} ${tax_period - paid:>11,.2f}')

    p('')
    p('')
    p('  TOP 10 VENDORS BY SPEND')
    p('  ' + '-' * (W - 4))
    for k, v in sorted(d['vendors'].items(), key=lambda x: -x[1])[:10]:
        p(f'    {k[:42]:<42} ${v:>11,.2f}')

    if d['nd']:
        p('')
        p('')
        p('  NON-DEDUCTIBLE (excluded from expenses above)')
        p('  ' + '-' * (W - 4))
        for k, v in sorted(d['nd'].items(), key=lambda x: -x[1]):
            p(f'    {k:<42} ${v:>11,.2f}')
        p(f'  {"TOTAL NON-DEDUCTIBLE":<44} ${sum(d["nd"].values()):>11,.2f}')

    if d['review']:
        p('')
        p('')
        p('  REVIEW — UNMAPPED CATEGORIES (not deducted; map or recategorize)')
        p('  ' + '-' * (W - 4))
        for dt, raw, desc, cat in sorted(d['review']):
            p(f'    REVIEW {dt}  ${raw:>10,.2f}  {desc[:26]:<26} [{cat}]')

    p('')
    p('')
    p('  VERIFICATION (business CSV reconciliation)')
    p('  ' + '-' * (W - 4))
    biz_ded = d['total_exp'] - d['ho_ded'] - d['pcard_total']
    credits = -d['pl'].get('Credits & Refunds Received', 0)
    accounted = biz_ded + credits + sum(d['nd'].values()) + d['refund_total']
    p(f'    {"Business CSV expenses (raw)":<42} ${d["biz_exp_raw"]:>11,.2f}')
    p(f'    {"Deductible, net of credits":<42} ${biz_ded:>11,.2f}')
    p(f'    {"Credits received (add back)":<42} ${credits:>11,.2f}')
    p(f'    {"Non-deductible":<42} ${sum(d["nd"].values()):>11,.2f}')
    p(f'    {"Refunds (revenue line)":<42} ${d["refund_total"]:>11,.2f}')
    p(f'    {"Difference (should be ~0)":<42} ${d["biz_exp_raw"]-accounted:>11,.2f}')
    p('')
    p(f'    {"Home office (from personal CSV)":<42} ${d["ho_ded"]:>11,.2f}')
    p(f'    {"Personal-card business (separate)":<42} ${d["pcard_total"]:>11,.2f}')

    result = '\n'.join(out)
    print(result)
    fname = {'full': 'profit-and-loss.txt'}.get(pkey, f'{pkey}-profit-and-loss.txt')
    outpath = ROOT / str(year) / fname
    if year in frozen_years() and not args.force_frozen:
        print(f'\nNOT written: {year} is frozen (as-filed). Pass --force-frozen to overwrite {outpath.relative_to(ROOT)}.')
        return
    outpath.write_text(result)
    print(f'\nWritten to {outpath.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
