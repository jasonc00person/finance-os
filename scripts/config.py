"""Shared config loader + federal tax tables.

Everything client-specific lives in config.toml at the data root. The data root is
the repo root, or $FINANCE_HOME if set (e.g. FINANCE_HOME=demo to run the demo books).
"""
import os
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

CODE_ROOT = Path(__file__).resolve().parent.parent
ROOT = (CODE_ROOT / os.environ['FINANCE_HOME']).resolve() if os.environ.get('FINANCE_HOME') else CODE_ROOT
TEMPLATES = CODE_ROOT / 'templates'

_cfg = None


def cfg():
    global _cfg
    if _cfg is None:
        path = ROOT / 'config.toml'
        if not path.exists():
            raise SystemExit(f'No config at {path}. Run the setup skill (or copy config.toml from the template).')
        _cfg = tomllib.loads(path.read_text())
    return _cfg


def default_year():
    return int(cfg()['business'].get('year') or __import__('datetime').date.today().year)


def frozen_years():
    return set(cfg()['business'].get('frozen_years', []))


def camel(s):
    """'Software & Subscriptions' -> 'SoftwareSubscriptions' (beancount account leaf)."""
    seg = re.sub(r'[^A-Za-z0-9]+', ' ', s or 'Uncategorized').title().replace(' ', '')
    return seg if seg and seg[0].isalpha() else f'X{seg}'


def match_account(display_name):
    """Monarch displayName -> config [[accounts]] entry. A match starting '(...' or
    '(....' is an account-number mask matched on the END of the name (rename-proof);
    anything else matches the START of the name."""
    for a in cfg().get('accounts', []):
        m = a['match']
        if (m.startswith('(..') and display_name.endswith(m)) or (not m.startswith('(..') and display_name.startswith(m)):
            return a
    return None


# ---- Federal constants (verify each year; IRS Rev. Proc. 2025-32 for 2026) ----
FEDERAL = {
    2025: {
        'ss_wage_base': 176100,
        'single': dict(std_ded=15750, qbi_threshold=197300, qbi_phase_in=50000, addl_medicare=200000,
                       brackets=[(11925, .10), (48475, .12), (103350, .22), (197300, .24),
                                 (250525, .32), (626350, .35), (float('inf'), .37)]),
        'mfj': dict(std_ded=31500, qbi_threshold=394600, qbi_phase_in=100000, addl_medicare=250000,
                    brackets=[(23850, .10), (96950, .12), (206700, .22), (394600, .24),
                              (501050, .32), (751600, .35), (float('inf'), .37)]),
    },
    2026: {
        'ss_wage_base': 184500,
        'single': dict(std_ded=16100, qbi_threshold=201750, qbi_phase_in=75000, addl_medicare=200000,
                       brackets=[(12400, .10), (50400, .12), (105700, .22), (201775, .24),
                                 (256225, .32), (640600, .35), (float('inf'), .37)]),
        'mfj': dict(std_ded=32200, qbi_threshold=403500, qbi_phase_in=150000, addl_medicare=250000,
                    brackets=[(24800, .10), (100800, .12), (211400, .22), (403550, .24),
                              (512450, .32), (768700, .35), (float('inf'), .37)]),
    },
}


def tax_year(year):
    """Merged tax config for a year: federal tables for the filing status + the
    client's own figures from [tax.years.<year>] in config.toml."""
    t = cfg().get('tax', {})
    status = t.get('filing_status', 'single')
    if year not in FEDERAL:
        raise SystemExit(f'No federal tables for {year} in scripts/config.py FEDERAL. Add them (verify current-law numbers first).')
    fed = FEDERAL[year]
    own = t.get('years', {}).get(str(year), {})
    return dict(fed[status], ss_wage_base=fed['ss_wage_base'], filing_status=status,
                state_rate=float(t.get('state_rate', 0.0)),
                other_income=float(own.get('other_income', t.get('other_income', 0.0))),
                prior_year_total_tax=own.get('prior_year_total_tax') or None,
                estimates_paid=[tuple(x) for x in own.get('estimates_paid', [])],
                retirement_contrib=float(own.get('retirement_contrib', 0.0)))
