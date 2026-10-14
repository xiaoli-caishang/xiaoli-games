"""China tier-1 cities: 职友集 (jobui.com) salary pages -> monthly pay histograms.

  https://www.jobui.com/salary/<city>-<job-pinyin>/          all experience levels
  https://www.jobui.com/salary/<city>-<job-pinyin>/exp2/     3-5 年经验 only

Each page is server-rendered and contains a bar chart of the monthly-pay
distribution ("2-3K 1.3%", "20-30K 14.4%", ...) plus the sample size
("数据统计来自近一年 397 份样本").  The two largest bars are hidden behind a
paywall ("***"), but the page still leaks enough to recover them exactly up to
a two-way ambiguity:

  * every visible bar has style="height:H%" with H = pct / max_pct * 100, so
    max_pct = pct / H * 100 is known from any visible bar;
  * the hidden pair sums to 100 - sum(visible);
  * the page also shows the same chart partitioned by education
    (本科 / 硕士 / 博士 ...) together with the education mix, so the two
    possible assignments can be checked for consistency against the
    sub-charts.  When that check is inconclusive we fall back to a density
    interpolation rule (see density_pick) and record the alternative median so
    the ambiguity stays visible.

Raw pages are cached under cache/ (git-ignored).  out/cn.json only contains
histograms and sample sizes.
"""
from __future__ import annotations

import html as htmlmod
import itertools
import math
import re
import sys

from common import HERE, fetch, hist_quantile, log, read_json, write_json

OUT = f"{HERE}/out/cn.json"
BASE = "https://www.jobui.com/salary"
CITIES = {"上海": "shanghai", "北京": "beijing", "深圳": "shenzhen"}

# role -> [(slug, 中文岗位名)]
ROLES: dict[str, list[tuple[str, str]]] = {
    "qr": [("lianghuayanjiuyuan", "量化研究员"), ("lianghuafenxishi", "量化分析师")],
    "qdev": [("lianghuakaifa", "量化开发"), ("lianghuakaifagongchengshi", "量化开发工程师")],
    "trader": [("jiaoyiyuan", "交易员"), ("zhengquanjiaoyiyuan", "证券交易员"), ("qihuojiaoyiyuan", "期货交易员")],
    "research": [("zhengquanfenxishi", "证券分析师"), ("jijinyanjiuyuan", "基金研究员"), ("gupiaofenxishi", "股票分析师"),
                 ("hongguanyanjiuyuan", "宏观研究员"), ("zhengquanyanjiuyuan", "证券研究员"), ("touziyanjiuyuan", "投资研究员")],
    "pm": [("jijinjingli", "基金经理"), ("simujijinjingli", "私募基金经理")],
    "vc": [("touzijingli", "投资经理"), ("guquantouzijingli", "股权投资经理"), ("touzifenxishi", "投资分析师")],
    "risk": [("fengkong", "风控"), ("hegui", "合规"), ("fengxianguanli", "风险管理")],
    "wealth": [("caifuguwen", "财富顾问"), ("licaijingli", "理财经理"), ("licaiguwen", "理财顾问")],
    "sales": [("jigouxiaoshou", "机构销售"), ("jigouxiaoshoujingli", "机构销售经理"),
              ("jigouyewujingli", "机构业务经理"), ("jigoukehujingli", "机构客户经理")],
    "product": [("jinrongchanpinjingli", "金融产品经理"), ("jijinchanpinjingli", "基金产品经理"),
                ("jijinyunying", "基金运营"), ("licaichanpinjingli", "理财产品经理")],
    "actuary": [("jingsuanshi", "精算师")],
}

VARIANTS = {"all": "", "exp3_5": "exp2/"}

CHART_RE = re.compile(r'<div class="(salary-analysis-table[^"]*)"\s*title="([^"]*)">(.*?)</div>', re.S)
BAR_RE = re.compile(
    r'<span class="company-salary-analysis-list[^"]*" style="height:([\d.]+)%;">(.*?)</span>', re.S)
PCT_RE = re.compile(r'<em class="salary-analysis-percent">\s*([\d.]+)%\s*</em>')
LABEL_RE = re.compile(r'<em class="salary-analysis-num[^"]*">([^<]+)</em>')
N_RE = re.compile(r"近一年\s*(\d+)\s*份样本")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
EDU_LABELS = ("大专", "本科", "硕士", "博士", "不限", "中专", "高中", "初中")


def parse_label(label: str) -> tuple[float | None, float | None]:
    """'2-3K' -> (2000, 3000); '50K以上' -> (50000, None); '2K以下' -> (None, 2000)."""
    label = label.strip()
    m = re.fullmatch(r"([\d.]+)-([\d.]+)K", label)
    if m:
        return float(m.group(1)) * 1000, float(m.group(2)) * 1000
    m = re.fullmatch(r"([\d.]+)K以上", label)
    if m:
        return float(m.group(1)) * 1000, None
    m = re.fullmatch(r"([\d.]+)K以下", label)
    if m:
        return None, float(m.group(1)) * 1000
    raise ValueError(f"unknown bin label {label!r}")


def parse_chart(inner: str) -> list[dict]:
    """Bars of one chart; [] if it is not a monthly chart (e.g. '18-24W' yearly labels)."""
    bars = []
    for height, body in BAR_RE.findall(inner):
        lab = LABEL_RE.search(body)
        if not lab:
            continue
        try:
            lo, hi = parse_label(htmlmod.unescape(lab.group(1)))
        except ValueError:
            return []
        pm = PCT_RE.search(body)
        bars.append({"lo": lo, "hi": hi, "pct": float(pm.group(1)) if pm else None, "h": float(height)})
    return bars


def resolve_pair(bars: list[dict]) -> list[list[float]]:
    """Return the list of possible pct vectors (1 when unambiguous, 2 otherwise)."""
    vis = [b for b in bars if b["pct"] is not None]
    masked = [i for i, b in enumerate(bars) if b["pct"] is None]
    base = [b["pct"] if b["pct"] is not None else 0.0 for b in bars]
    if not masked:
        return [base]
    masked_sum = max(0.0, 100.0 - sum(b["pct"] for b in vis))
    if len(masked) == 1 or not vis:
        v = list(base)
        for i in masked:
            v[i] = masked_sum / len(masked)
        return [v]
    ref = max(vis, key=lambda b: b["pct"])
    max_pct = ref["pct"] / ref["h"] * 100.0 if ref["h"] > 0 else masked_sum / 2
    max_pct = min(max_pct, masked_sum)
    rest = masked_sum - max_pct
    if len(masked) == 2:
        a, b = masked
        v1, v2 = list(base), list(base)
        v1[a], v1[b] = max_pct, rest
        v2[a], v2[b] = rest, max_pct
        return [v1, v2]
    # 3+ hidden bars: max to one of them, remainder split evenly (rare)
    out = []
    for i in masked:
        v = list(base)
        for j in masked:
            v[j] = max_pct if j == i else rest / (len(masked) - 1)
        out.append(v)
    return out


def _bin_width(bars: list[dict], i: int) -> float:
    b = bars[i]
    if b["hi"] is None:  # open top ("50K以上"): reuse the previous bin's width
        prev = bars[i - 1] if i > 0 else None
        return (prev["hi"] - prev["lo"]) if prev and prev["lo"] is not None else b["lo"]
    if b["lo"] is None:
        return b["hi"]
    return b["hi"] - b["lo"]


def density_pick(bars: list[dict], options: list[list[float]]) -> int:
    """Fallback when sub-charts cannot tell the two hidden bars apart.

    Interpolate the (log) density of the visible bars across each hidden bar,
    multiply by the bar's width to get its expected share, and give the larger
    hidden value to the bar with the larger expected share.  Against the pages
    where the sub-chart check *is* conclusive this picks the right bar ~85% of
    the time (vs ~68% for a nearest-neighbour rule), mostly because the wide
    30-50K bar naturally collects more mass than its neighbours.
    """
    masked = [i for i, b in enumerate(bars) if b["pct"] is None]
    if len(options) < 2 or len(masked) != 2:
        return 0
    dens = {i: b["pct"] / _bin_width(bars, i) for i, b in enumerate(bars) if b["pct"] is not None}
    if not dens:
        return 0

    def expected_share(i: int) -> float:
        left = [j for j in dens if j < i]
        right = [j for j in dens if j > i]
        if left and right:
            l, r = max(left), min(right)
            dl, dr = math.log(dens[l] + 1e-6), math.log(dens[r] + 1e-6)
            d = math.exp(dl + (dr - dl) * (i - l) / (r - l))
        elif left:
            d = dens[max(left)]
        else:
            d = dens[min(right)]
        return d * _bin_width(bars, i)

    a, b = masked
    big = a if expected_share(a) >= expected_share(b) else b
    small = b if big == a else a
    for k, v in enumerate(options):
        if v[big] >= v[small]:
            return k
    return 0


def parse_edu_mix(page: str) -> dict[str, float]:
    """'招聘学历要求' block -> {'本科': 36.2, '硕士': 53.2, ...} (percent)."""
    i = page.find("招聘学历要求")
    if i < 0:
        return {}
    chunk = re.sub(r"<[^>]+>", " ", page[i:i + 6000])
    chunk = htmlmod.unescape(re.sub(r"\s+", " ", chunk))
    mix = {}
    for pct, lab in re.findall(r"([\d.]+)%\s*(大专|本科|硕士|博士|不限|中专|高中|初中|中技)", chunk):
        mix.setdefault(lab, float(pct))
    return mix


def feasibility_score(main: list[float], bars: list[dict], subs: list[tuple[float, list[list[float]], list[dict]]],
                      unknown_w: float) -> float:
    """Smallest total violation (pct points) over all sub-chart assignments."""
    keys = [(b["lo"], b["hi"]) for b in bars]
    best = float("inf")
    for combo in itertools.product(*[range(len(opts)) for _, opts, _ in subs]):
        known = dict.fromkeys(keys, 0.0)
        for (w, opts, sbars), k in zip(subs, combo):
            for sb, p in zip(sbars, opts[k]):
                key = (sb["lo"], sb["hi"])
                if key in known:
                    known[key] += w / 100.0 * p
        viol = 0.0
        for key, m in zip(keys, main):
            r = m - known[key]
            tol = 1.5
            if r < -tol:
                viol += -r - tol
            elif r > unknown_w + tol:
                viol += r - unknown_w - tol
        best = min(best, viol)
    return best


def parse_page(page: str, expect_name: str) -> dict | None:
    title = TITLE_RE.search(page)
    title_txt = htmlmod.unescape(title.group(1)) if title else ""
    if expect_name not in title_txt or "平均工资" in title_txt:
        return None  # slug does not exist -> jobui falls back to the city-wide page
    nm = N_RE.search(page)
    n = int(nm.group(1)) if nm else 0
    charts = CHART_RE.findall(page)
    main_bars = None
    sub_charts: list[tuple[str, list[dict]]] = []
    for cls, ctitle, inner in charts:
        ctitle = htmlmod.unescape(ctitle)
        if "j-year" in cls:
            continue
        bars = parse_chart(inner)
        if not bars:
            continue
        if "j-month-salary-analysis" in cls:
            main_bars = bars
        else:
            for lab in EDU_LABELS:
                if f"{lab}薪酬区间" in ctitle:
                    sub_charts.append((lab, bars))
                    break
    if not main_bars or n == 0:
        return None
    options = resolve_pair(main_bars)
    method = "exact"
    chosen = 0
    alt_median = None
    if len(options) > 1:
        mix = parse_edu_mix(page)
        subs = []
        covered = 0.0
        for lab, sbars in sub_charts:
            if lab in mix and mix[lab] > 0:
                subs.append((mix[lab], resolve_pair(sbars), sbars))
                covered += mix[lab]
        unknown_w = max(0.0, 100.0 - covered) if mix else 100.0
        scores = [feasibility_score(o, main_bars, subs, unknown_w) for o in options] if subs else []
        if scores and (max(scores) - min(scores)) > 1.0:
            chosen = scores.index(min(scores))
            method = "subchart"
        else:
            chosen = density_pick(main_bars, options)
            method = "density"
        alt = options[1 - chosen] if len(options) == 2 else None
        if alt is not None:
            alt_bins = [{"lo": b["lo"], "hi": b["hi"], "w": p} for b, p in zip(main_bars, alt)]
            alt_median = hist_quantile(alt_bins, 0.5)[0]
    pcts = options[chosen]
    bins = [{"lo": b["lo"], "hi": b["hi"], "w": round(p * n / 100.0, 3)} for b, p in zip(main_bars, pcts)]
    med = hist_quantile(bins, 0.5)[0]
    return {
        "n": n,
        "bins": bins,  # weights are estimated job counts (pct * n)
        "hidden_bars": sum(1 for b in main_bars if b["pct"] is None),
        "resolution": method,
        "median": med,
        "alt_median": alt_median,
    }


def fetch_cell(city_slug: str, slug: str, variant: str) -> str:
    url = f"{BASE}/{city_slug}-{slug}/{VARIANTS[variant]}"
    return fetch(url, "jobui", min_bytes=20000)


def main(argv: list[str]) -> None:
    only = set(argv[1:]) or set(ROLES)
    prev = read_json(OUT) or {"roles": {}}
    result = {"source": "jobui", "currency": "CNY", "unit": "monthly", "roles": prev.get("roles", {})}
    for role, slugs in ROLES.items():
        if role not in only:
            continue
        role_out: dict = {}
        for city, city_slug in CITIES.items():
            city_out: dict = {}
            for slug, name in slugs:
                entry: dict = {"name": name}
                for variant in VARIANTS:
                    try:
                        page = fetch_cell(city_slug, slug, variant)
                        parsed = parse_page(page, name)
                    except Exception as e:  # network failure after retries
                        log(f"  [cn] {city}/{slug}/{variant}: {e}")
                        parsed = None
                    entry[variant] = parsed
                    if parsed:
                        log(f"[cn] {role} {city} {name} {variant}: n={parsed['n']} median={parsed['median']:.0f} "
                            f"({parsed['resolution']}, alt={parsed['alt_median']})")
                    else:
                        log(f"[cn] {role} {city} {name} {variant}: no data")
                city_out[slug] = entry
            role_out[city] = city_out
        result["roles"][role] = role_out
        write_json(OUT, result)
    log(f"[cn] wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv)
