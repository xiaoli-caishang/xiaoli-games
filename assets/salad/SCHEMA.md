# 薪资沙拉数据约定 `assets/salad/data.json`

一份沙拉 = 月薪 ¥1,000。三地统一折成人民币后再换算成沙拉。

```jsonc
{
  "meta": {
    "date": "2026-10",                 // 数据月份，展示用
    "level": "3–5 年经验",              // 口径说明
    "salad_cny": 1000,                 // 1 份沙拉 = 多少人民币/月
    "generated_at": "2026-10-14T18:00:00Z",
    "fx": { "HKD_CNY": 0.92, "USD_CNY": 7.10, "as_of": "2026-10-14", "src": "open.er-api.com" },
    "sources": [                        // 所有用到的来源，展示在数据页和游戏里
      { "id": "jobui", "name": "职友集", "region": "cn", "url": "https://www.jobui.com/", "note": "岗位×城市 月薪分布，样本为公开招聘信息" },
      { "id": "jobsdb", "name": "JobsDB", "region": "hk", "url": "https://hk.jobsdb.com/", "note": "按月薪区间的在招职位数量分布" },
      { "id": "h1b", "name": "美国劳工部 H-1B LCA 公开数据（经 h1bdata.info 整理）", "region": "us", "url": "https://h1bdata.info/", "note": "实际申报年薪，按 12 折月" }
    ]
  },
  "regions": [
    { "id": "cn", "name": "中国一线", "currency": "CNY", "cities": ["上海", "北京", "深圳"] },
    { "id": "hk", "name": "香港",     "currency": "HKD", "cities": ["香港"] },
    { "id": "us", "name": "美国",     "currency": "USD", "cities": ["New York", "Chicago", "San Francisco"] }
  ],
  "roles": [                            // 顺序和 id 必须与游戏 games/finance-persona 的 SALARY 键一致
    { "id": "qr",       "name": "量化研究员" },
    { "id": "qdev",     "name": "量化开发" },
    { "id": "trader",   "name": "交易员" },
    { "id": "research", "name": "行业研究员" },
    { "id": "pm",       "name": "基金经理" },
    { "id": "vc",       "name": "一级市场投资" },
    { "id": "risk",     "name": "风控合规" },
    { "id": "wealth",   "name": "财富顾问" },
    { "id": "sales",    "name": "机构销售" },
    { "id": "product",  "name": "产品与运营" },
    { "id": "actuary",  "name": "精算师" }
  ],
  "stats": {
    "qr": {
      "cn": {
        "median_local": 40000, "p25_local": 30000, "p75_local": 60000,   // 当地货币，月薪
        "median_cny": 40000, "salad": 40,                                  // 折人民币后的中位数与沙拉数（四舍五入到整数）
        "n": 1234,                                                         // 样本数（职位条数或申报条数）
        "src": ["jobui"],
        "cities": { "上海": { "median_local": 42000, "n": 600 }, "北京": { "median_local": 40000, "n": 400 } },
        "note": ""                                                         // 口径备注，可空
      },
      "hk": { "...": "同上，currency HKD" },
      "us": { "...": "同上，currency USD，年薪/12" }
    },
    "qdev": { "...": "..." }
  }
}
```

规则：

- 任何一格拿不到数据时写 `null`，`n` 写 0，并在 `note` 里写原因；不要用估算数填。
- `salad = round(median_cny / meta.salad_cny)`。
- 所有数字都是月薪，不含年终奖；年薪来源除以 12。
- 页面与游戏只读这份文件（游戏是单文件离线运行，由 `tools/salad/bake.py` 把 `stats` 烘进 `SALARY` 常量）。
