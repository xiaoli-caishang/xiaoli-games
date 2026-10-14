# 金融人薪资沙拉 · 数据管线

产出 `assets/salad/data.json`（11 岗位 × 3 地区的月薪中位数 / p25 / p75 / 样本数，折算成「沙拉」）和配套的
`assets/salad/methods.md`。数据约定见 `assets/salad/SCHEMA.md`。

## 依赖

- Python 3.12，仅标准库（`urllib`、`re`、`html`、`json`），不需要 `pip install`。
- 需要能访问 jobui.com、hk.jobsdb.com、h1bdata.info、open.er-api.com。

## 运行

```bash
cd tools/salad
python3 fetch_cn.py        # 职友集：中国一线（上海/北京/深圳）     -> out/cn.json
python3 fetch_hk.py        # JobsDB：香港                            -> out/hk.json
python3 fetch_us.py        # h1bdata.info：美国（NY/Chicago/SF）     -> out/us.json
python3 build.py           # 取汇率、汇总、校验 schema，写 assets/salad/data.json
```

或者一步到位：`python3 build.py --fetch`。

- 每个 fetch 脚本都可以只跑部分岗位：`python3 fetch_hk.py qr trader`（岗位 id 见 SCHEMA）。
- 所有 HTTP 请求带桌面 UA、间隔 ≥ 1 秒、失败重试 3 次；原始页面 / JSON 缓存在 `cache/`（已 gitignore），
  删除对应缓存文件即可强制重新抓取。汇率每次 build 都重新拉取。
- `out/*.json` 只保存聚合后的直方图与样本数（不含雇主、日期等任何个体字段），可以提交。

## 文件

| 文件 | 作用 |
| --- | --- |
| `common.py` | 抓取（UA / 限速 / 重试 / 缓存）、直方图分位数、岗位表 |
| `fetch_cn.py` | 解析职友集薪资页（含被遮罩的最高两档的还原逻辑） |
| `fetch_hk.py` | JobsDB 搜索接口按 1 万港元一档扫描，职位标题二次筛选 |
| `fetch_us.py` | h1bdata.info 表格抓取，年薪 / 12 |
| `build.py` | 汇率、合并、null 规则、schema 校验、写 `data.json` |

## 调参

- 岗位同义词 / 关键词 / 职位名：各 fetch 脚本顶部的 `ROLES`。
- `build.py`：`MIN_CELL_N`（样本少于多少写 null，默认 8）、`MIN_EXP_N`（职友集 3–5 年筛选页样本够多才使用，默认 30）。
