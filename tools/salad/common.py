"""Shared helpers for the salary-salad pipeline (stdlib only).

- polite HTTP fetching: desktop UA, >=1s spacing between requests, 3 retries
- on-disk cache under tools/salad/cache/ (git-ignored; raw pages are never committed)
- histogram -> quantile helpers (linear interpolation inside a bin)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Iterable, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache")
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ASSET_DIR = os.path.join(REPO_ROOT, "assets", "salad")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)
MIN_INTERVAL = 1.0  # seconds between live requests
RETRIES = 3

ROLES: Sequence[tuple[str, str]] = (
    ("qr", "量化研究员"),
    ("qdev", "量化开发"),
    ("trader", "交易员"),
    ("research", "行业研究员"),
    ("pm", "基金经理"),
    ("vc", "一级市场投资"),
    ("risk", "风控合规"),
    ("wealth", "财富顾问"),
    ("sales", "机构销售"),
    ("product", "产品与运营"),
    ("actuary", "精算师"),
)
ROLE_IDS = [r[0] for r in ROLES]

_last_request_at = 0.0


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def _cache_path(sub: str, key: str, ext: str) -> str:
    d = os.path.join(CACHE_DIR, sub)
    os.makedirs(d, exist_ok=True)
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:80]
    return os.path.join(d, f"{safe}__{h}.{ext}")


def fetch(url: str, sub: str, *, ext: str = "html", refresh: bool = False,
          min_bytes: int = 0, headers: Optional[dict] = None) -> str:
    """GET `url` as text, caching the body on disk. Retries 3x, >=1s apart."""
    global _last_request_at
    path = _cache_path(sub, url, ext)
    if not refresh and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    hdrs = {
        "User-Agent": UA,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        hdrs.update(headers)
    err: Optional[Exception] = None
    for attempt in range(RETRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=40) as resp:
                body = resp.read()
            text = body.decode("utf-8", errors="replace")
            if len(body) < min_bytes:
                raise ValueError(f"short body ({len(body)} bytes)")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError, OSError) as e:
            err = e
            log(f"  retry {attempt + 1}/{RETRIES} for {url}: {e}")
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"failed after {RETRIES} attempts: {url}: {err}")


def fetch_json(url: str, sub: str, **kw) -> dict:
    return json.loads(fetch(url, sub, ext="json", **kw))


def write_json(path: str, obj: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_json(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- histograms
# A histogram is a list of bins: {"lo": float, "hi": float|None, "w": float}
# `hi` None means open-ended ("50K以上", "150000-").  Weights can be counts
# or percentages; only their ratios matter.


def hist_quantile(bins: Sequence[dict], q: float) -> tuple[Optional[float], str]:
    """Return (value, flag). flag is "" normally, ">=" when the quantile sits in
    an open-ended top bin (value is then the bin's lower edge), "<=" when it
    sits in an open-ended bottom bin."""
    total = sum(b["w"] for b in bins)
    if total <= 0:
        return None, ""
    target = q * total
    acc = 0.0
    for b in sorted(bins, key=lambda x: (x["lo"] if x["lo"] is not None else -1)):
        w = b["w"]
        if w <= 0:
            continue
        if acc + w >= target:
            lo, hi = b["lo"], b["hi"]
            if hi is None:
                return float(lo), ">="
            if lo is None:
                return float(hi), "<="
            frac = (target - acc) / w
            return lo + (hi - lo) * frac, ""
        acc += w
    last = bins[-1]
    return (float(last["lo"]), ">=") if last["hi"] is None else (float(last["hi"]), "")


def merge_hists(hists: Iterable[Sequence[dict]]) -> list[dict]:
    """Sum bins with identical (lo, hi) edges across histograms."""
    acc: dict[tuple, float] = {}
    for h in hists:
        for b in h:
            k = (b["lo"], b["hi"])
            acc[k] = acc.get(k, 0.0) + b["w"]
    out = [{"lo": k[0], "hi": k[1], "w": v} for k, v in acc.items()]
    out.sort(key=lambda b: (b["lo"] if b["lo"] is not None else -1))
    return out


def list_quantile(values: Sequence[float], q: float) -> Optional[float]:
    """Linear-interpolated quantile of raw values."""
    if not values:
        return None
    v = sorted(values)
    if len(v) == 1:
        return float(v[0])
    pos = q * (len(v) - 1)
    i = int(pos)
    frac = pos - i
    if i + 1 >= len(v):
        return float(v[-1])
    return v[i] + (v[i + 1] - v[i]) * frac
