# 小梨财商游戏厅

@小梨🍐 有价值的财商分享 · 财商教育小游戏合集。

所有游戏都是单个 HTML 文件，没有外部依赖，断网也能运行。

## 目录结构

```
index.html                 游戏大厅首页
games/
  quant-fund/index.html    量化基金生存录
functions/api/             匿名统计接口（EdgeOne Pages 边缘函数）
  log/                     游戏上报每一局的选择和成绩
  stats/                   返回挑战人数（开场展示）
  export/                  管理员导出原始数据（需要口令）
tools/analyze.py           下载数据并生成 Excel 分析报告
```

## 新增一个游戏

1. 在 `games/` 下新建一个英文文件夹，例如 `games/dca-replay/`
2. 把游戏文件放进去，命名为 `index.html`
3. 在根目录 `index.html` 里复制一张游戏卡片，把链接改成 `games/dca-replay/`
4. 提交并推送到 GitHub，EdgeOne Pages 会自动重新部署，几分钟后生效

## 上线方式

GitHub 仓库连接腾讯云 EdgeOne Pages，每次推送自动部署。详见视频方案文档里的「上线方案」一节。

## 玩家数据统计（只需设置一次）

游戏会匿名记录每一局的选择、成绩、投资人格、每年思考时长和来源渠道，不记录 IP 和任何个人信息。玩家看不到统计界面，只会在开场看到「已有 N 人挑战」（满 100 人后显示），结局看到「在 N 位真实玩家中超过 X%」（满 30 人后显示）。

1. EdgeOne Pages 控制台 →「KV 存储」→ 开通并新建命名空间，名字随意，例如 `xiaoli_stats`
2. 在命名空间里点「绑定项目」，选这个项目，**变量名填 `xl_kv`**（必须一致）
3. 项目 →「设置」→「环境变量」→ 新增 `ADMIN_TOKEN`，值是一串至少 12 位、只有你知道的口令
4. 重新部署一次（推送代码或在控制台点「重新部署」）
5. 验证：打开 `https://你的域名/api/stats`，看到 `{"starts":0,"finished":0}` 就成功了

分渠道统计：发链接时在后面加 `?from=dy`（抖音）、`?from=bl`（B站）、`?from=xhs`（小红书）、`?from=wx`（微信），报告里会分开统计。

导出和分析（在自己电脑上运行）：

```
pip install openpyxl
python3 tools/analyze.py --url https://xiaolipearl.com --token 你的ADMIN_TOKEN
```

会生成原始数据 `raw_日期.json` 和 `玩家数据报告_日期.xlsx`，报告包含：概览、流失漏斗、每年选择分布（标出最优选择）、投资人格分布、最常听谁的、成绩分布、每年思考时长、可直接用于下期视频的「下期素材」。

## 免责声明

所有游戏仅为财商教育演示，不构成任何投资建议。投资有风险，入市需谨慎。
