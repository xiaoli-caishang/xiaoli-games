"""Hong Kong: JobsDB search API -> monthly-salary histogram per role.

How it works
------------
JobsDB exposes a public search endpoint

  https://hk.jobsdb.com/api/jobsearch/v5/search?siteKey=HK-Main&keywords=...
      &salarytype=monthly&salaryrange=<lo>-<hi>&classification=...

For every role we run 1-3 quoted keyword phrases and scan monthly-salary bands
of HK$10k from 10,000 up to 200,000 (last band open-ended).  Because JobsDB
keyword matching is fuzzy, we download the listings in each band and keep only
those whose *title* matches a per-role regex (and does not match an exclusion
regex for interns / graduate programmes / back-office roles).

A listing whose salary range spans several bands shows up in each of them; we
spread such a listing uniformly over the bands it appears in, so every listing
contributes exactly 1 to n.  Quantiles are then linearly interpolated inside
the band.  No experience filter exists on this endpoint, so the figures are for
all seniority levels except interns/graduates (noted in the output).

Only aggregated counts and histograms are written to out/hk.json; raw API
responses are cached under cache/ (git-ignored).
"""
from __future__ import annotations

import re
import sys
import urllib.parse

from common import HERE, fetch_json, hist_quantile, log, write_json

OUT = f"{HERE}/out/hk.json"
BASE = "https://hk.jobsdb.com/api/jobsearch/v5/search?siteKey=HK-Main&salarytype=monthly&pageSize=100"
FIN = "1203"  # classification: Banking & Financial Services
INS = "1214"  # Insurance & Superannuation
ICT = "6281"  # Information & Communication Technology

BAND_EDGES = list(range(10_000, 200_001, 10_000))  # 10k..200k -> bands + open top
MAX_SPAN = 10  # listings spanning this many bands or more are treated as "salary unspecified"

EXCLUDE_COMMON = r"intern|internship|graduate|trainee|fresh grad|summer|placement|student|apprentice"

ROLES: dict[str, dict] = {
    "qr": {
        "keywords": ['"quantitative researcher"', '"quant researcher"', '"quantitative analyst"', '"quant analyst"', '"quant"'],
        "classification": None,
        "title_re": r"quant\w*\s+(research|analy|strateg)|quant\w*\s+(trading\s+)?research",
        "exclude_re": EXCLUDE_COMMON + r"|develop|engineer|risk",
    },
    "qdev": {
        "keywords": ['"quantitative developer"', '"quant developer"', '"quantitative engineer"', '"quant"'],
        "classification": None,
        "title_re": r"quant\w*\s+(develop|engineer|programm)|quant\w*.*\b(c\+\+|python|kdb)\b.*develop",
        "exclude_re": EXCLUDE_COMMON,
    },
    "trader": {
        "keywords": ['"trader"'],
        "classification": FIN,
        "title_re": r"\btrader\b",
        "exclude_re": EXCLUDE_COMMON + r"|trade support|trader assistant|assistant to|sales trader|dealer",
    },
    "research": {
        "keywords": ['"equity research"', '"research analyst"', '"investment analyst"'],
        "classification": FIN,
        "title_re": r"equity research|research analyst|investment analyst|sector analyst|(equity|credit|industry)\s+analyst|analyst,?\s+equity",
        "exclude_re": EXCLUDE_COMMON + r"|market research|editor|writing|quant|data analyst|business analyst|product|marketing",
    },
    "pm": {
        "keywords": ['"portfolio manager"', '"fund manager"'],
        "classification": FIN,
        "title_re": r"portfolio manager|fund manager|投資經理|基金經理",
        "exclude_re": EXCLUDE_COMMON + r"|assistant|loan|credit portfolio|project portfolio|propert|real estate|fund management (officer|assistant)|operations|administration|accountant|compliance|risk",
    },
    "vc": {
        "keywords": ['"private equity"', '"venture capital"', '"investment associate"', '"investment manager"'],
        "classification": FIN,
        "title_re": r"(private equity|venture capital|\bpe\b|\bvc\b|investment)\s*.*\b(analyst|associate|manager|professional|director|vp|vice president)\b|\b(analyst|associate|manager|vp)\b.*(private equity|venture capital|\bpe\b|\bvc\b)",
        "exclude_re": EXCLUDE_COMMON + r"|account|administr|secretar|assistant|finance (associate|manager)|compliance|risk|legal|tax|operations|investor relations|audit|fund admin|valuation|kyc|onboarding|marketing|sales|insurance|product|banking|relationship|wealth|portfolio manager|fund manager|research|advisor|advisory|consultant|clerk|officer|loan|credit"
                      r"|equities|fixed income|derivative|treasury|real estate|asset management|\bfof\b|distressed|financing|capital sourcing|arbitrage|trading|etf|hedge fund",
    },
    "risk": {
        "keywords": ['"risk analyst"', '"risk manager"', '"compliance officer"', '"compliance manager"'],
        "classification": FIN,
        "title_re": r"\brisk\b|compliance",
        "exclude_re": EXCLUDE_COMMON + r"|head of|chief|director|md\b|managing director|clerk|secretar|assistant to",
    },
    "wealth": {
        "keywords": ['"relationship manager"', '"wealth manager"', '"financial planner"', '"financial consultant"', '"wealth management"'],
        "classification": FIN,
        "title_re": r"relationship manager|wealth (manager|advis|consult|planner|management)|financial (planner|advis|consult)|private bank|client advis|investment consultant|\brm\b",
        "exclude_re": EXCLUDE_COMMON + r"|corporate|commercial|sme|business banking|institution|head of|chief|director|trade|cash management|operations|assistant to|secretar|compliance|risk|product|credit|insurance"
                      r"|administration|execution|control|regulatory|service manager|business finance|program|dealing|settlement|kyc|onboarding|metals|mining|esop",
    },
    "sales": {
        "keywords": ['"institutional sales"', '"sales trader"', '"institutional business"'],
        "classification": FIN,
        "title_re": r"institutional (sales|business|client)|sales trad|(equit|fixed income|ficc|fx|derivative|structured|bond|prime)\w*\s+sales|sales,?\s+(equit|fixed income|ficc|fx|institution)",
        "exclude_re": EXCLUDE_COMMON + r"|kyc|support|assistant|head of|chief|director|md\b|operations|marketing",
    },
    "product": {
        "keywords": ['"product manager"', '"product specialist"', '"investment product"'],
        "classification": FIN,
        "title_re": r"product (manager|specialist|development|officer|lead|owner)|investment product",
        "exclude_re": EXCLUDE_COMMON + r"|head of|chief|director|md\b|assistant to|secretar|credit card|card product|payment|trade product|loan|mortgage|insurance",
    },
    "actuary": {
        "keywords": ['"actuarial"', '"actuary"'],
        "classification": None,
        "title_re": r"actuar",
        "exclude_re": EXCLUDE_COMMON + r"|head of|chief|director|appointed|clerk|secretar|assistant to",
    },
}


def bands() -> list[tuple[int, int | None]]:
    out: list[tuple[int, int | None]] = []
    for i, lo in enumerate(BAND_EDGES):
        hi = BAND_EDGES[i + 1] if i + 1 < len(BAND_EDGES) else None
        out.append((lo, hi))
    return out


def band_param(lo: int, hi: int | None) -> str:
    return f"{lo}-{hi}" if hi is not None else f"{lo}-"


def search(keyword: str, lo: int, hi: int | None, classification: str | None, page: int) -> dict:
    url = (
        f"{BASE}&keywords={urllib.parse.quote(keyword)}&salaryrange={band_param(lo, hi)}&page={page}"
        + (f"&classification={classification}" if classification else "")
    )
    return fetch_json(url, "jobsdb", min_bytes=20)


def collect_role(role: str, cfg: dict) -> dict:
    title_re = re.compile(cfg["title_re"], re.I)
    excl_re = re.compile(cfg["exclude_re"], re.I)
    jobs: dict[str, dict] = {}  # id -> {"title":..., "bands": set()}
    raw_total = 0
    for kw in cfg["keywords"]:
        for lo, hi in bands():
            page = 1
            while True:
                d = search(kw, lo, hi, cfg["classification"], page)
                data = d.get("data", [])
                if page == 1:
                    raw_total += int(d.get("totalCount", 0))
                for j in data:
                    jid = str(j.get("id"))
                    title = (j.get("title") or "").strip()
                    rec = jobs.setdefault(jid, {"title": title, "bands": set()})
                    rec["bands"].add((lo, hi))
                if len(data) < 100 or page >= 10:
                    break
                page += 1
    matched = {k: v for k, v in jobs.items() if title_re.search(v["title"]) and not excl_re.search(v["title"])}
    # A listing that shows up in >= MAX_SPAN bands (>= HK$100k wide) carries
    # no usable salary information ("negotiable"); drop it from the histogram.
    too_wide = {k for k, v in matched.items() if len(v["bands"]) >= MAX_SPAN}
    matched = {k: v for k, v in matched.items() if k not in too_wide}
    hist: dict[tuple[int, int | None], float] = {b: 0.0 for b in bands()}
    for v in matched.values():
        k = len(v["bands"])
        for b in v["bands"]:
            hist[b] += 1.0 / k
    bins = [{"lo": lo, "hi": hi, "w": round(w, 4)} for (lo, hi), w in hist.items()]
    n = len(matched)
    med, mf = hist_quantile(bins, 0.5) if n else (None, "")
    p25, f25 = hist_quantile(bins, 0.25) if n else (None, "")
    p75, f75 = hist_quantile(bins, 0.75) if n else (None, "")
    sample_titles = sorted({v["title"] for v in matched.values()})[:40]
    log(f"[hk] {role}: raw hits={raw_total} distinct listings={len(jobs)} title-matched n={n} "
        f"(dropped {len(too_wide)} with unspecified/too-wide salary) median={med} p25={p25} p75={p75}")
    return {
        "n": n,
        "distinct_listings_before_title_filter": len(jobs),
        "dropped_salary_unspecified": len(too_wide),
        "median": med, "median_flag": mf,
        "p25": p25, "p25_flag": f25,
        "p75": p75, "p75_flag": f75,
        "hist": bins,
        "keywords": cfg["keywords"],
        "classification": cfg["classification"],
        "title_re": cfg["title_re"],
        "sample_titles": sample_titles,
    }


def main(argv: list[str]) -> None:
    only = set(argv[1:]) or set(ROLES)
    from common import read_json
    prev = read_json(OUT) or {"roles": {}}
    result = {"source": "jobsdb", "currency": "HKD", "unit": "monthly",
              "bands": [band_param(lo, hi) for lo, hi in bands()],
              "roles": prev.get("roles", {})}
    for role, cfg in ROLES.items():
        if role not in only:
            continue
        result["roles"][role] = collect_role(role, cfg)
        write_json(OUT, result)
    log(f"[hk] wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv)
