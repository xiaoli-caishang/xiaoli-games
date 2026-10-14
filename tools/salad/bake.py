#!/usr/bin/env python3
"""把 assets/salad/data.json 里的薪资沙拉数据烘进游戏 games/finance-persona/index.html。

游戏是单个 HTML、零外部依赖、离线可运行，不能 fetch JSON，所以数据以常量写进文件中
`// ==== SALAD_BAKE_START ====` 与 `// ==== SALAD_BAKE_END ====` 两个标记之间：

    const SALARY_DEMO=false;
    const SALARY_META={level,date,n,src,fx,updated};
    const SALARY={qr:{cn:40,hk:80,us:125},...};          // 中位数，整数沙拉；缺数据为 null
    const SALARY_X={qr:{cn:{p25,p75,n},...},...};        // p25/p75 也折成整数沙拉；缺数据为 null

用法（仓库任意位置执行，路径默认相对仓库根）：
    python3 tools/salad/bake.py            # 校验并写入
    python3 tools/salad/bake.py --check    # 只校验（数据合法 + 游戏文件是否已是最新），不写
    python3 tools/salad/bake.py --data /tmp/x.json --game games/finance-persona/index.html

幂等：同一份 data.json 重复执行，游戏文件不会再变化。仅依赖 Python 3.12 标准库。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "assets" / "salad" / "data.json"
DEFAULT_GAME = ROOT / "games" / "finance-persona" / "index.html"

MARK_START = "// ==== SALAD_BAKE_START ===="
MARK_END = "// ==== SALAD_BAKE_END ===="

REGION_IDS = ("cn", "hk", "us")
REGION_ZH = {"cn": "内地", "hk": "香港", "us": "美国"}
STAT_KEYS = ("median_local", "p25_local", "p75_local", "median_cny", "salad", "n")


class BakeError(Exception):
    pass


def round_half_up(v: float) -> int:
    """四舍五入到整数（与 JS Math.round 一致，避免 Python 的银行家舍入）。"""
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def js_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def js_num(v: int | None) -> str:
    return "null" if v is None else str(int(v))


# ---------------------------------------------------------------- 读取 / 校验

def game_role_ids(game_html: str) -> list[str]:
    """从游戏文件 `const ROLES={ ... };` 里抓岗位 id，保证数据与游戏键一致。"""
    m = re.search(r"^const ROLES=\{\n(.*?)^\};", game_html, re.S | re.M)
    if not m:
        raise BakeError("游戏文件里找不到 `const ROLES={...};`")
    ids = re.findall(r"^ ([a-z_][a-z0-9_]*):\{", m.group(1), re.M)
    if not ids:
        raise BakeError("游戏文件 ROLES 解析不到任何岗位 id")
    return ids


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_data(data: dict, role_ids: list[str], warn) -> None:
    errs: list[str] = []
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise BakeError("缺少 meta")
    for k in ("date", "level", "salad_cny", "generated_at", "fx", "sources"):
        if k not in meta:
            errs.append(f"meta.{k} 缺失")
    if not is_num(meta.get("salad_cny")) or meta.get("salad_cny", 0) <= 0:
        errs.append("meta.salad_cny 必须是正数")
    fx = meta.get("fx") or {}
    for k in ("HKD_CNY", "USD_CNY"):
        if not is_num(fx.get(k)) or fx.get(k, 0) <= 0:
            errs.append(f"meta.fx.{k} 必须是正数")
    if not fx.get("as_of"):
        errs.append("meta.fx.as_of 缺失")
    srcs = meta.get("sources") or []
    if not isinstance(srcs, list) or not srcs:
        errs.append("meta.sources 为空")
    src_ids = {s.get("id") for s in srcs if isinstance(s, dict)}
    for s in srcs:
        if not isinstance(s, dict) or not s.get("id") or not s.get("name"):
            errs.append(f"meta.sources 条目缺 id/name：{s!r}")

    regions = data.get("regions") or []
    rids = [r.get("id") for r in regions if isinstance(r, dict)]
    if rids != list(REGION_IDS):
        errs.append(f"regions 的 id 顺序必须是 {list(REGION_IDS)}，现为 {rids}")
    cur = {r.get("id"): r.get("currency") for r in regions if isinstance(r, dict)}
    for g, c in cur.items():
        if c != "CNY" and f"{c}_CNY" not in fx:
            errs.append(f"regions.{g} 货币 {c} 在 meta.fx 里没有 {c}_CNY 汇率")

    roles = data.get("roles") or []
    data_role_ids = [r.get("id") for r in roles if isinstance(r, dict)]
    if data_role_ids != role_ids:
        errs.append(f"roles 的 id/顺序必须与游戏 ROLES 一致。\n  游戏：{role_ids}\n  数据：{data_role_ids}")

    stats = data.get("stats")
    if not isinstance(stats, dict):
        raise BakeError("缺少 stats")
    extra = sorted(set(stats) - set(role_ids))
    if extra:
        errs.append(f"stats 里有游戏不认识的岗位：{extra}")
    for rid in role_ids:
        cell_map = stats.get(rid)
        if not isinstance(cell_map, dict):
            errs.append(f"stats.{rid} 缺失")
            continue
        for g in REGION_IDS:
            cell = cell_map.get(g, "MISSING")
            if cell == "MISSING":
                errs.append(f"stats.{rid}.{g} 缺失（没有数据请写 null）")
                continue
            if cell is None:
                continue
            if not isinstance(cell, dict):
                errs.append(f"stats.{rid}.{g} 既不是对象也不是 null")
                continue
            if cell.get("median_local") is None and cell.get("median_cny") is None:
                # 空格：n 应为 0，note 应写原因
                if cell.get("n") not in (0, None):
                    errs.append(f"stats.{rid}.{g} 没有中位数却有样本数 n={cell.get('n')}")
                if not cell.get("note"):
                    warn(f"stats.{rid}.{g} 为空但 note 没写原因")
                continue
            for k in STAT_KEYS:
                v = cell.get(k)
                if v is not None and (not is_num(v) or v < 0):
                    errs.append(f"stats.{rid}.{g}.{k} 不是非负数：{v!r}")
            if not is_num(cell.get("n")) or cell.get("n", 0) <= 0:
                errs.append(f"stats.{rid}.{g}.n 必须是正整数（有数据的格）")
            p25, p75, med = cell.get("p25_local"), cell.get("p75_local"), cell.get("median_local")
            if is_num(p25) and is_num(p75) and p25 > p75:
                errs.append(f"stats.{rid}.{g} p25 > p75")
            if is_num(p25) and is_num(med) and is_num(p75) and not (p25 <= med <= p75):
                warn(f"stats.{rid}.{g} 中位数 {med} 不在 p25–p75 [{p25},{p75}] 之间")
            for sid in cell.get("src") or []:
                if sid not in src_ids:
                    errs.append(f"stats.{rid}.{g}.src 引用了 meta.sources 里没有的来源 {sid!r}")
    if errs:
        raise BakeError("data.json 校验失败：\n  - " + "\n  - ".join(errs))


# ---------------------------------------------------------------- 换算

def rate_of(data: dict, g: str) -> float:
    cur = next(r["currency"] for r in data["regions"] if r["id"] == g)
    return 1.0 if cur == "CNY" else float(data["meta"]["fx"][f"{cur}_CNY"])


def to_salad(local, rate: float, salad_cny: float) -> int | None:
    if local is None:
        return None
    return round_half_up(float(local) * rate / salad_cny)


def compute(data: dict, role_ids: list[str], warn):
    meta = data["meta"]
    salad_cny = float(meta["salad_cny"])
    salary: dict[str, dict[str, int | None]] = {}
    salary_x: dict[str, dict[str, dict | None]] = {}
    total_n = 0
    for rid in role_ids:
        salary[rid], salary_x[rid] = {}, {}
        for g in REGION_IDS:
            cell = data["stats"][rid].get(g)
            if cell is None or (cell.get("median_local") is None and cell.get("median_cny") is None):
                salary[rid][g] = None
                salary_x[rid][g] = None
                continue
            rate = rate_of(data, g)
            med_cny = cell.get("median_cny")
            if med_cny is None:
                med_cny = float(cell["median_local"]) * rate
            salad = round_half_up(float(med_cny) / salad_cny)
            if cell.get("salad") is not None:
                given = int(cell["salad"])
                if abs(given - salad) > 1:
                    raise BakeError(f"stats.{rid}.{g}.salad={given} 与 round(median_cny/salad_cny)={salad} 不符")
                if given != salad:
                    warn(f"stats.{rid}.{g}.salad={given} 与重算值 {salad} 差 1（舍入方式），以数据文件为准")
                salad = given
            if salad <= 0:
                raise BakeError(f"stats.{rid}.{g} 折算后沙拉数为 {salad}，请检查单位")
            n = int(cell.get("n") or 0)
            total_n += n
            salary[rid][g] = salad
            salary_x[rid][g] = {
                "p25": to_salad(cell.get("p25_local"), rate, salad_cny),
                "p75": to_salad(cell.get("p75_local"), rate, salad_cny),
                "n": n,
            }
    return salary, salary_x, total_n


def date_zh(s: str) -> str:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", str(s).strip())
    return f"{m.group(1)} 年 {int(m.group(2))} 月" if m else str(s)


def src_sentence(sources: list[dict]) -> str:
    """来源名拼成一句中文：内地取自 A，香港取自 B，美国取自 C；其余来源直接列出。"""
    by_region: dict[str, list[str]] = {}
    other: list[str] = []
    for s in sources:
        g = s.get("region")
        (by_region.setdefault(g, []) if g in REGION_ZH else other).append(s["name"])
    # 中文后面紧跟拉丁字母/数字时补一个空格（“香港取自 JobsDB”）
    pad = lambda s: (" " + s) if re.match(r"[A-Za-z0-9]", s) else s
    parts = [f"{REGION_ZH[g]}取自{pad('、'.join(by_region[g]))}" for g in REGION_IDS if g in by_region]
    if other:
        parts.append("另参考" + pad("、".join(other)))
    return "，".join(parts) if parts else "小梨团队整理"


def fmt_rate(v: float) -> str:
    return f"{float(v):.2f}"


def render_block(data: dict, role_ids: list[str], salary, salary_x, total_n: int) -> str:
    meta, fx = data["meta"], data["meta"]["fx"]
    fx_txt = (f"港币、美元按 {fx['as_of']} 汇率折算（1 HKD={fmt_rate(fx['HKD_CNY'])} CNY，"
              f"1 USD={fmt_rate(fx['USD_CNY'])} CNY）")
    meta_js = ("{level:" + js_str(str(meta["level"])) + ",date:" + js_str(date_zh(meta["date"]))
               + ",n:" + str(int(total_n)) + ",src:" + js_str(src_sentence(meta["sources"]))
               + ",fx:" + js_str(fx_txt) + ",updated:" + js_str(str(meta["generated_at"])) + "}")
    sal_lines = []
    for rid in role_ids:
        cells = ",".join(f"{g}:{js_num(salary[rid][g])}" for g in REGION_IDS)
        sal_lines.append(f" {rid}:{{{cells}}},")
    x_lines = []
    for rid in role_ids:
        cells = []
        for g in REGION_IDS:
            c = salary_x[rid][g]
            cells.append(f"{g}:null" if c is None else
                         f"{g}:{{p25:{js_num(c['p25'])},p75:{js_num(c['p75'])},n:{int(c['n'])}}}")
        x_lines.append(f" {rid}:{{{','.join(cells)}}},")
    return "\n".join([
        MARK_START,
        "const SALARY_DEMO=false;",
        f"const SALARY_META={meta_js};",
        "const SALARY={",
        *sal_lines,
        "};",
        "const SALARY_X={",
        *x_lines,
        "};",
        MARK_END,
    ])


def splice(game_html: str, block: str) -> str:
    s, e = game_html.find(MARK_START), game_html.find(MARK_END)
    if s < 0 or e < 0 or e < s:
        raise BakeError(f"游戏文件里找不到成对的标记 {MARK_START!r} / {MARK_END!r}")
    if game_html.find(MARK_START, s + 1) >= 0 or game_html.find(MARK_END, e + 1) >= 0:
        raise BakeError("游戏文件里标记出现了多次")
    return game_html[:s] + block + game_html[e + len(MARK_END):]


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help=f"数据文件（默认 {DEFAULT_DATA.relative_to(ROOT)}）")
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME, help=f"游戏文件（默认 {DEFAULT_GAME.relative_to(ROOT)}）")
    ap.add_argument("--check", action="store_true", help="只校验数据并报告游戏文件是否已是最新，不写入")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    def log(*x):
        if not a.quiet:
            print(*x)

    def warn(msg: str):
        print("warning:", msg, file=sys.stderr)

    try:
        if not a.data.exists():
            raise BakeError(f"数据文件不存在：{a.data}")
        if not a.game.exists():
            raise BakeError(f"游戏文件不存在：{a.game}")
        try:
            data = json.loads(a.data.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise BakeError(f"{a.data} 不是合法 JSON：{e}") from None
        game_html = a.game.read_text(encoding="utf-8")
        role_ids = game_role_ids(game_html)
        check_data(data, role_ids, warn)
        salary, salary_x, total_n = compute(data, role_ids, warn)
        block = render_block(data, role_ids, salary, salary_x, total_n)
        new_html = splice(game_html, block)
    except BakeError as e:
        print("error:", e, file=sys.stderr)
        return 1

    cells = sum(1 for r in salary.values() for v in r.values())
    nulls = sum(1 for r in salary.values() for v in r.values() if v is None)
    log(f"ok: {len(role_ids)} 个岗位 × {len(REGION_IDS)} 地 = {cells} 格，其中 {nulls} 格无数据；总样本 {total_n} 条")
    if new_html == game_html:
        log(f"游戏文件已是最新，无需改动：{a.game}")
        return 0
    if a.check:
        print(f"游戏文件与 data.json 不一致，需要重新 bake：{a.game}", file=sys.stderr)
        return 1
    a.game.write_text(new_html, encoding="utf-8")
    log(f"已写入：{a.game}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
