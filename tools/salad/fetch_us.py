"""United States: H-1B LCA disclosure data via h1bdata.info -> monthly base pay.

  https://h1bdata.info/index.php?em=&job=<JOB TITLE>&city=<CITY>&year=<YEAR>

The page is a server-rendered table (employer, job title, base salary,
location, submit date, start date).  Job title matching on the site is exact,
so each role is covered by 2-4 titles.  We keep only the salary column (annual
USD base pay) and divide by 12.  Employer / dates are not stored.  For
`product` the table is restricted to employers whose name looks like a
financial firm (bank, capital, securities, asset management, ...).

Year: 2025 filings; if a role x city has fewer than MIN_N rows we also pull
2024 and merge (recorded in the output).  H-1B figures are the *declared base
wage* for visa sponsorship: conservative, no bonus, no experience filter.
"""
from __future__ import annotations

import html as htmlmod
import re
import sys
import urllib.parse

from common import HERE, fetch, list_quantile, log, read_json, write_json

OUT = f"{HERE}/out/us.json"
BASE = "https://h1bdata.info/index.php"
CITIES = {"New York": "new york", "Chicago": "chicago", "San Francisco": "san francisco"}
YEAR = 2025
FALLBACK_YEAR = 2024
MIN_N = 30

FIN_EMPLOYER_RE = re.compile(
    r"BANK|CAPITAL|SECURITIES|ASSET|INVEST|FINANC|FUND|GOLDMAN|MORGAN|CITI|JPMORGAN|J\.P\. MORGAN|"
    r"BLACKROCK|FIDELITY|VANGUARD|AMERICAN EXPRESS|VISA\b|MASTERCARD|PAYPAL|BLOOMBERG|WELLS FARGO|"
    r"BARCLAYS|UBS|CREDIT|DEUTSCHE|HSBC|NOMURA|MIZUHO|STATE STREET|BNY|MELLON|NORTHERN TRUST|"
    r"SCHWAB|ROBINHOOD|COINBASE|STRIPE|SQUARE|BLOCK, INC|AFFIRM|SOFI|CHIME|BROKER|TRADING|EXCHANGE|"
    r"NASDAQ|CBOE|CME|ICE\b|INTERCONTINENTAL|MOODY|S&P|MSCI|FACTSET|INSURANCE|MUTUAL|LIFE\b|"
    r"ANNUIT|ACTUAR|PAYMENT|LENDING|MORTGAGE|WEALTH|ADVISOR|PARTNERS|HOLDINGS|MARKETS|TREASUR",
    re.I,
)

# A title given as a plain string is used as-is; a dict {"title", "fin": True}
# keeps only filings from employers whose name matches FIN_EMPLOYER_RE (used
# for generic titles such as RESEARCH ANALYST / PRODUCT MANAGER).
ROLES: dict[str, dict] = {
    "qr": {"titles": ["QUANTITATIVE RESEARCHER", "QUANTITATIVE ANALYST", "QUANTITATIVE RESEARCH ANALYST",
                      "FINANCIAL QUANTITATIVE ANALYST", "FINANCIAL QUANTITATIVE ANALYSTS"]},
    "qdev": {"titles": ["QUANTITATIVE DEVELOPER", "QUANT DEVELOPER", "QUANTITATIVE SOFTWARE ENGINEER"]},
    "trader": {"titles": ["TRADER", "QUANTITATIVE TRADER", "EQUITY TRADER", "FIXED INCOME TRADER"]},
    "research": {"titles": [{"title": "RESEARCH ANALYST", "fin": True}, "EQUITY RESEARCH ASSOCIATE",
                            "EQUITY RESEARCH ANALYST", "INVESTMENT ANALYST"]},
    "pm": {"titles": ["PORTFOLIO MANAGER", "ASSOCIATE PORTFOLIO MANAGER"]},
    "vc": {"titles": ["PRIVATE EQUITY ASSOCIATE", "INVESTMENT ASSOCIATE", "PRIVATE EQUITY ANALYST", "VENTURE CAPITAL ASSOCIATE"]},
    "risk": {"titles": [{"title": "RISK ANALYST", "fin": True}, {"title": "COMPLIANCE ANALYST", "fin": True},
                        {"title": "RISK MANAGER", "fin": True}, "FINANCIAL RISK SPECIALISTS", "FINANCIAL RISK SPECIALIST"]},
    # Client-facing advisory / sales roles are almost never H-1B sponsored; the
    # titles below all return 0 rows for the three cities (kept for re-checks).
    "wealth": {"titles": ["FINANCIAL ADVISOR", "WEALTH MANAGEMENT ASSOCIATE", "WEALTH ADVISOR", "PRIVATE WEALTH ADVISOR",
                          "WEALTH MANAGEMENT ANALYST", "FINANCIAL PLANNER", "RELATIONSHIP MANAGER", "PERSONAL FINANCIAL ADVISORS"]},
    "sales": {"titles": ["INSTITUTIONAL SALES", "SALES TRADER", "INSTITUTIONAL SALES ASSOCIATE", "INSTITUTIONAL EQUITY SALES",
                         "EQUITY SALES", "SALES AND TRADING ANALYST", "SALES AND TRADING ASSOCIATE", "FIXED INCOME SALES"]},
    "product": {"titles": [{"title": "PRODUCT MANAGER", "fin": True}, {"title": "SENIOR PRODUCT MANAGER", "fin": True}]},
    "actuary": {"titles": ["ACTUARIAL ANALYST", "ACTUARIES", "ACTUARY", "ACTUARIAL ASSOCIATE", "ASSOCIATE ACTUARY"]},
}

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def fetch_rows(title: str, city: str, year: int) -> list[tuple[str, int]]:
    """Return [(employer, annual_salary)] for an exact title/city/year page."""
    url = f"{BASE}?em=&job={urllib.parse.quote_plus(title.lower())}&city={urllib.parse.quote_plus(city)}&year={year}"
    page = fetch(url, "h1bdata", min_bytes=1000)
    tbody = page.split("<tbody>", 1)[1] if "<tbody>" in page else page
    out = []
    for row in ROW_RE.findall(tbody):
        tds = [htmlmod.unescape(TAG_RE.sub("", x)).strip() for x in TD_RE.findall(row)]
        if len(tds) < 4:
            continue
        sal = re.sub(r"[^\d]", "", tds[2])
        if not sal:
            continue
        s = int(sal)
        if s < 20_000 or s > 2_000_000:  # obvious hourly / typo rows
            continue
        out.append((tds[0], s))
    return out


def _title_specs(cfg: dict) -> list[tuple[str, bool]]:
    out = []
    for t in cfg["titles"]:
        if isinstance(t, dict):
            out.append((t["title"], bool(t.get("fin"))))
        else:
            out.append((t, False))
    return out


def _rows_for_year(cfg: dict, city_q: str, year: int) -> list[int]:
    sal: list[int] = []
    for title, fin in _title_specs(cfg):
        for employer, s in fetch_rows(title, city_q, year):
            if fin and not FIN_EMPLOYER_RE.search(employer):
                continue
            sal.append(s)
    return sal


def collect_role(role: str, cfg: dict) -> dict:
    cities_out = {}
    all_monthly: list[float] = []
    for city_name, city_q in CITIES.items():
        years_used = [YEAR]
        annual = _rows_for_year(cfg, city_q, YEAR)
        if len(annual) < MIN_N:
            annual += _rows_for_year(cfg, city_q, FALLBACK_YEAR)
            years_used.append(FALLBACK_YEAR)
        monthly = [s / 12.0 for s in annual]
        all_monthly += monthly
        cities_out[city_name] = {
            "n": len(monthly),
            "median": list_quantile(monthly, 0.5),
            "p25": list_quantile(monthly, 0.25),
            "p75": list_quantile(monthly, 0.75),
            "years": years_used,
        }
        log(f"[us] {role} {city_name}: n={len(monthly)} median={cities_out[city_name]['median']} years={years_used}")
    return {
        "n": len(all_monthly),
        "median": list_quantile(all_monthly, 0.5),
        "p25": list_quantile(all_monthly, 0.25),
        "p75": list_quantile(all_monthly, 0.75),
        "cities": cities_out,
        "titles": [t for t, _ in _title_specs(cfg)],
        "finance_employer_filtered_titles": [t for t, fin in _title_specs(cfg) if fin],
        "years": sorted({y for c in cities_out.values() for y in c["years"]}),
    }


def main(argv: list[str]) -> None:
    only = set(argv[1:]) or set(ROLES)
    prev = read_json(OUT) or {"roles": {}}
    result = {"source": "h1b", "currency": "USD", "unit": "monthly (annual/12)",
              "roles": prev.get("roles", {})}
    for role, cfg in ROLES.items():
        if role not in only:
            continue
        result["roles"][role] = collect_role(role, cfg)
        write_json(OUT, result)
    log(f"[us] wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv)
