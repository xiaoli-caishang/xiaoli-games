"""Assemble assets/salad/data.json from out/{cn,hk,us}.json + live FX.

Run the three fetchers first (or let this script call them with --fetch).
Everything here is deterministic given the out/ files and the FX quote.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

from common import (ASSET_DIR, HERE, ROLES, fetch_json, hist_quantile, log, merge_hists, read_json,
                    write_json)

DATA_PATH = os.path.join(ASSET_DIR, "data.json")
SALAD_CNY = 1000
MIN_CELL_N = 8      # fewer matched records than this -> cell is null
MIN_CITY_N = 5      # city-level breakdown is listed only with at least this many records
MIN_EXP_N = 30      # use jobui's 3-5年 filter only if the merged sample is at least this big
SMALL_N = 30        # below this we flag "样本较少" in the note

REGIONS = [
    {"id": "cn", "name": "中国一线", "currency": "CNY", "cities": ["上海", "北京", "深圳"]},
    {"id": "hk", "name": "香港", "currency": "HKD", "cities": ["香港"]},
    {"id": "us", "name": "美国", "currency": "USD", "cities": ["New York", "Chicago", "San Francisco"]},
]

SOURCES = [
    {"id": "jobui", "name": "职友集", "region": "cn", "url": "https://www.jobui.com/",
     "note": "岗位×城市 月薪分布，样本为近一年公开招聘信息；优先取 3–5 年经验筛选页"},
    {"id": "jobsdb", "name": "JobsDB", "region": "hk", "url": "https://hk.jobsdb.com/",
     "note": "按月薪区间（每 1 万港元一档）的在招职位数量分布，职位标题二次筛选"},
    {"id": "h1b", "name": "美国劳工部 H-1B LCA 公开数据（经 h1bdata.info 整理）", "region": "us", "url": "https://h1bdata.info/",
     "note": "H-1B 申报底薪（年薪/12），偏保守，不含奖金"},
]


def rnd(x: float | None) -> int | None:
    return None if x is None else int(round(x))


def get_fx() -> dict:
    url = "https://open.er-api.com/v6/latest/CNY"
    try:
        d = fetch_json(url, "fx", refresh=True)
    except Exception as e:  # offline: fall back to cached quote
        log(f"[fx] live fetch failed ({e}); using cached quote")
        d = fetch_json(url, "fx")
    rates = d["rates"]
    as_of = dt.datetime.strptime(d["time_last_update_utc"][5:16], "%d %b %Y").date().isoformat()
    return {"HKD_CNY": round(1.0 / rates["HKD"], 4), "USD_CNY": round(1.0 / rates["USD"], 4),
            "as_of": as_of, "src": "open.er-api.com"}


def empty_cell(src: list[str], note: str) -> dict:
    return {"median_local": None, "p25_local": None, "p75_local": None, "median_cny": None, "salad": None,
            "n": 0, "src": src, "cities": {}, "note": note}


def finish_cell(med: float | None, p25: float | None, p75: float | None, n: int, fx: float,
                src: list[str], cities: dict, notes: list[str], flags: tuple[str, str, str] = ("", "", "")) -> dict:
    if med is None or n < MIN_CELL_N:
        why = f"样本不足（匹配到 {n} 条，低于阈值 {MIN_CELL_N}），不出数。" if n else "来源中没有可用样本。"
        return empty_cell(src, " ".join([why] + notes))
    extra = []
    if n < SMALL_N:
        extra.append(f"样本较少（n={n}），仅供参考。")
    for q, f in zip(("p25", "中位数", "p75"), flags):
        if f == ">=":
            extra.append(f"{q} 落在最高的开放区间，按区间下限记录（实际 ≥ 该值）。")
        elif f == "<=":
            extra.append(f"{q} 落在最低的开放区间，按区间上限记录（实际 ≤ 该值）。")
    med_cny = med * fx
    return {
        "median_local": rnd(med), "p25_local": rnd(p25), "p75_local": rnd(p75),
        "median_cny": rnd(med_cny), "salad": int(round(med_cny / SALAD_CNY)),
        "n": n, "src": src, "cities": cities, "note": " ".join(notes + extra),
    }


# ------------------------------------------------------------------ CN / jobui
def build_cn(role: str, cn: dict) -> dict:
    data = (cn or {}).get("roles", {}).get(role)
    if not data:
        return empty_cell(["jobui"], "未抓取到职友集数据。")
    names_used: list[str] = []

    def collect(variant: str):
        per_city = {}
        for city, slugs in data.items():
            hists, n, names, unimodal, alt = [], 0, [], 0, []
            for slug, entry in slugs.items():
                p = entry.get(variant)
                if not p:
                    continue
                hists.append(p["bins"])
                n += p["n"]
                names.append(entry["name"])
                if p["resolution"] == "density":
                    unimodal += 1
                    if p["alt_median"] is not None and p["median"] is not None:
                        alt.append((p["n"], p["median"], p["alt_median"]))
            per_city[city] = {"hist": merge_hists(hists) if hists else [], "n": n, "names": names,
                              "unimodal": unimodal, "alt": alt}
        return per_city

    exp = collect("exp3_5")
    n_exp = sum(c["n"] for c in exp.values())
    if n_exp >= MIN_EXP_N:
        per_city, level_note = exp, f"口径：职友集「3–5 年经验」筛选页（n={n_exp}）。"
    else:
        per_city = collect("all")
        level_note = (f"3–5 年经验筛选页样本太少（n={n_exp}），改用全部经验的样本"
                      f"（n={sum(c['n'] for c in per_city.values())}）。")
    for c in per_city.values():
        for nm in c["names"]:
            if nm not in names_used:
                names_used.append(nm)
    all_hist = merge_hists(c["hist"] for c in per_city.values() if c["hist"])
    n = int(round(sum(c["n"] for c in per_city.values())))
    if n == 0 or not all_hist:
        return empty_cell(["jobui"], "职友集没有这些岗位名的页面。 " + level_note)
    med, mf = hist_quantile(all_hist, 0.5)
    p25, f25 = hist_quantile(all_hist, 0.25)
    p75, f75 = hist_quantile(all_hist, 0.75)
    cities = {}
    for city, c in per_city.items():
        if c["n"] >= MIN_CITY_N and c["hist"]:
            cm, _ = hist_quantile(c["hist"], 0.5)
            cities[city] = {"median_local": rnd(cm), "n": int(c["n"])}
    notes = [f"岗位名合并：{'/'.join(names_used)}。", level_note,
             "样本为近一年公开招聘信息的薪资区间（在招薪资，非在职薪资）；分布按 10 个薪资档统计，档内线性插值。"]
    uni = sum(c["unimodal"] for c in per_city.values())
    if uni:
        alts = [a for c in per_city.values() for a in c["alt"]]
        spread = max(abs(m - a) for _, m, a in alts) if alts else 0
        notes.append(f"页面最高两档被遮罩，{uni} 个分页无法用学历分区完全确认，按密度插值规则分配"
                     f"（另一种分配下单页中位数最多相差约 ¥{spread:,.0f}）。")
    else:
        notes.append("页面最高两档被遮罩，均已用页面内的学历分区交叉验证还原。")
    return finish_cell(med, p25, p75, n, 1.0, ["jobui"], cities, notes, (f25, mf, f75))


# ------------------------------------------------------------------ HK / JobsDB
def build_hk(role: str, hk: dict, fx: float) -> dict:
    r = (hk or {}).get("roles", {}).get(role)
    if not r:
        return empty_cell(["jobsdb"], "未抓取到 JobsDB 数据。")
    n = int(r["n"])
    kws = "、".join(k.strip('"') for k in r["keywords"])
    notes = [f"JobsDB 关键词：{kws}；再按职位标题正则筛选，剔除实习/培训生。",
             "JobsDB 没有经验筛选，为全部年资的在招职位（非在职薪资）；月薪按每 1 万港元一档扫描 1–20 万，"
             "一条职位的薪资区间跨多档时按档数均摊；档内线性插值。"]
    if r.get("dropped_salary_unspecified"):
        notes.append(f"另有 {r['dropped_salary_unspecified']} 条薪资区间过宽/面议，已剔除。")
    cities = {"香港": {"median_local": rnd(r["median"]), "n": n}} if n >= MIN_CELL_N else {}
    return finish_cell(r["median"], r["p25"], r["p75"], n, fx, ["jobsdb"], cities, notes,
                       (r.get("p25_flag", ""), r.get("median_flag", ""), r.get("p75_flag", "")))


# ------------------------------------------------------------------ US / H-1B
def build_us(role: str, us: dict, fx: float) -> dict:
    r = (us or {}).get("roles", {}).get(role)
    if not r:
        return empty_cell(["h1b"], "未抓取到 H-1B 数据。")
    n = int(r["n"])
    years = "/".join(str(y) for y in r["years"])
    titles = "、".join(r["titles"])
    notes = [f"H-1B 申报底薪，偏保守，不含奖金；年薪/12。职位名（精确匹配）：{titles}；申报年份 {years}。",
             "H-1B 数据没有工作年限，为该职位名下全部申报记录。"]
    if r.get("finance_employer_filtered_titles"):
        notes.append("通用职位名（" + "、".join(r["finance_employer_filtered_titles"]) + "）只保留金融类雇主。")
    if role in ("wealth", "sales") and n < MIN_CELL_N:
        notes.append("面向客户的财富顾问/机构销售岗位几乎不做 H-1B 担保，尝试了十余个职位名均无足够记录。")
    cities = {}
    for city, c in r["cities"].items():
        if c["n"] >= MIN_CITY_N:
            cities[city] = {"median_local": rnd(c["median"]), "n": int(c["n"])}
    return finish_cell(r["median"], r["p25"], r["p75"], n, fx, ["h1b"], cities if n >= MIN_CELL_N else {}, notes)


def validate(doc: dict) -> None:
    assert [r["id"] for r in doc["roles"]] == [r for r, _ in ROLES]
    assert [r["id"] for r in doc["regions"]] == ["cn", "hk", "us"]
    for role, _ in ROLES:
        for reg in ("cn", "hk", "us"):
            c = doc["stats"][role][reg]
            for k in ("median_local", "p25_local", "p75_local", "median_cny", "salad", "n", "src", "cities", "note"):
                assert k in c, (role, reg, k)
            if c["median_local"] is None:
                assert c["n"] == 0 and c["salad"] is None and c["note"], (role, reg)
            else:
                assert c["n"] > 0 and c["salad"] == round(c["median_cny"] / doc["meta"]["salad_cny"]), (role, reg)


def main(argv: list[str]) -> None:
    if "--fetch" in argv:
        for script in ("fetch_cn.py", "fetch_hk.py", "fetch_us.py"):
            subprocess.run([sys.executable, os.path.join(HERE, script)], check=True)
    cn = read_json(os.path.join(HERE, "out", "cn.json"))
    hk = read_json(os.path.join(HERE, "out", "hk.json"))
    us = read_json(os.path.join(HERE, "out", "us.json"))
    fx = get_fx()
    now = dt.datetime.now(dt.timezone.utc)
    stats = {}
    for role, _ in ROLES:
        stats[role] = {
            "cn": build_cn(role, cn),
            "hk": build_hk(role, hk, fx["HKD_CNY"]),
            "us": build_us(role, us, fx["USD_CNY"]),
        }
    doc = {
        "meta": {
            "date": now.strftime("%Y-%m"),
            "level": "3–5 年经验",
            "salad_cny": SALAD_CNY,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fx": fx,
            "sources": SOURCES,
        },
        "regions": REGIONS,
        "roles": [{"id": r, "name": n} for r, n in ROLES],
        "stats": stats,
    }
    validate(doc)
    write_json(DATA_PATH, doc)
    log(f"[build] wrote {DATA_PATH}")
    for role, name in ROLES:
        row = []
        for reg in ("cn", "hk", "us"):
            c = stats[role][reg]
            row.append(f"{reg}: {c['salad'] if c['salad'] is not None else '-'} (n={c['n']})")
        log(f"  {name:6s} " + " | ".join(row))


if __name__ == "__main__":
    main(sys.argv[1:])
