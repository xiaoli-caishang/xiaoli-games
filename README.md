# 小梨财商游戏厅

@小梨🍐 有价值的财商分享 · 财商教育小游戏合集。

所有游戏都是单个 HTML 文件，没有外部依赖，断网也能运行。

## 目录结构

```
index.html                     官网首页「小梨 · 知识实验室」
games/
  finance-persona/index.html   金融里，你是什么登？（人格测试，含分享海报和合盘）
  jinrongnan/index.html        旧地址，跳转到 finance-persona
  quant-fund/index.html        量化基金生存录
functions/api/                 后端接口（EdgeOne Pages 边缘函数，数据都在 KV：xl_kv）
  health/                      部署自检：KV 和口令是否配好
  lead/                        官网「你想解决什么问题？」表单提交
  evt/                         通用游戏事件（金融里，你是什么登？）
  log/                         量化基金生存录每一局的选择和成绩
  stats/                       返回挑战人数（开场展示）
  export/                      管理员导出原始数据（需要口令）
  admin/                       工作台读写：资产 / 任务 / 花期（需要口令）
admin/index.html               小梨工作台（统一后台，需要口令）
admin/quant/index.html         量化基金生存录详细看板
tools/analyze.py               下载数据并生成 Excel 分析报告
.github/workflows/deploy.yml   自动部署
```

## 统一入口

| 用途 | 地址 |
|---|---|
| 官网 | https://xiaolipearl.com/ |
| 工作台（所有数据） | https://xiaolipearl.com/admin/ |
| 部署自检 | https://xiaolipearl.com/api/health ，`"ok":true` 表示 KV 和口令都配好了 |

KV 里的数据按前缀区分：`r_` 量化基金每局，`e_fp_` 金融人格每局，`lead_` 咨询申请，`c_` 计数器，`asset_` 工作台资产索引（把封面/脚本/成片拖到王国地图上就会写入）。大文件仍放网盘，仓里只记来自哪、用在哪、外链。

**工作台演进与发群监控说明（给 Codex / 协作者）：见根目录 [`ADMIN_ROADMAP.md`](./ADMIN_ROADMAP.md)。**

发群统计示例：`https://xiaolipearl.com/games/finance-persona/?from=wx`（后台按 `from` 区分渠道）。

## 上线方式（唯一来源是本仓库的 main 分支）

- 正式域名绑在 EdgeOne 项目 **`xiaoli-kingdom-web`**，该项目关联本仓库 `main`，推送后自动部署。
- 不要再在 EdgeOne 控制台手动上传整站覆盖，否则会和仓库不一致。
- GitHub Actions 以健康检查为主（`EDGEONE_DEPLOY_MODE=github`）；Variable `EDGEONE_PROJECT` 应为 `xiaoli-kingdom-web`。

## 金融里，你是什么登？

- 地址：`https://xiaolipearl.com/games/finance-persona/`；旧地址 `/games/jinrongnan/` 保留为跳转页，旧海报二维码仍然有效。改路径要同时重新生成二维码（代码里的 `QR` 常量）。
- 薪资在代码里的 `SALARY` 表（单位“份沙拉”，1 份 = 月薪 ¥1k，三地折成人民币）。换成爬虫数据时，同时改 `SALARY_META` 里的 `src`、`date` 和样本数 `n`。
- 合盘：同一台设备上“测自己”和“鉴定他”都做过，结果页自动出合盘（结果存在浏览器本地，不上传）。
- 已接入匿名统计（`/api/evt`）：开始、完成、人格代码、用时、生成海报、合盘、来源渠道。

## 新增一个游戏

1. 在 `games/` 下新建一个英文文件夹，例如 `games/dca-replay/`
2. 把游戏文件放进去，命名为 `index.html`
3. 在根目录 `index.html` 里复制一张游戏卡片，把链接改成 `games/dca-replay/`
4. 需要统计时，在 `functions/api/evt/index.js` 的 `GAMES` 里登记游戏代号和事件
5. 开 PR 合并到 `main`，GitHub Actions 自动部署，几分钟后生效

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

**工作台（监控链接）**：`https://xiaolipearl.com/admin/`，第一次打开输入 ADMIN_TOKEN，之后这台设备会记住。也可以把 `https://xiaolipearl.com/admin/#t=你的口令` 存成书签，一点就进（`#` 后面的口令不会发给服务器，但别把这个链接发给别人）。看板每 5 分钟自动刷新，可按时间和渠道筛选，可下载 CSV。

如果要做更深的分析（在自己电脑上运行）：

```
pip install openpyxl
python3 tools/analyze.py --url https://xiaolipearl.com --token 你的ADMIN_TOKEN
```

会生成原始数据 `raw_日期.json` 和 `玩家数据报告_日期.xlsx`，报告包含：概览、流失漏斗、每年选择分布（标出最优选择）、投资人格分布、最常听谁的、成绩分布、每年思考时长、可直接用于下期视频的「下期素材」。

## 剪辑工作室（/admin/studio）

在网站上做视频：上传口播 → 电脑（worker）自动转写、粗剪、抠像、排画面 → 网站上改画面计划 → 渲染成片。网站只管调度（KV），文件放腾讯云 COS 私有桶，算力在小梨的电脑上（以后可以加云 GPU，网站不用改）。

一次性设置：

1. 腾讯云 COS：私有桶 `xiaoli-studio-1501112605`（广州），跨域规则放行 `https://xiaolipearl.com`、`https://www.xiaolipearl.com`、`http://127.0.0.1:8790`，方法 PUT/GET/POST/HEAD
2. 访问管理里建子用户（只开编程访问），只关联策略 `XiaoliStudioCosRW`（只能读写这一个桶）
3. EdgeOne 项目 → 设置 → 环境变量，新增：`COS_SECRET_ID`、`COS_SECRET_KEY`（子用户的密钥）、`COS_BUCKET=xiaoli-studio-1501112605`、`COS_REGION=ap-guangzhou`、`WORKER_TOKEN`（≥16 位，只给 worker 用）；重新部署
4. 验证：`/api/health` 里 `cos` 和 `worker_token` 都是 `true`
5. 电脑上（xiaoli-studio 工程）双击 `worker.bat`，粘贴同一个 `WORKER_TOKEN`；会注册成登录自启

接口都在 `functions/api/studio/index.js`：浏览器用 `ADMIN_TOKEN`，worker 用 `WORKER_TOKEN`（只能领任务、报进度、签 COS 链接）。KV 前缀：`ep_`（一期索引，`.studio` 字段）、`job_`（任务）、`jlog_`（日志尾巴）、`wk_`（worker 心跳）。COS 路径：`raw/<期>/` 原片和稿子，`ep/<期>/` 粗剪、抠像、episode.json，`out/<期>/` 成片和封面，`assets/` 3D 序列、B-roll、画面计划历史版本。密钥只在 EdgeOne 环境变量里，浏览器和 worker 只拿短时签名链接。

## 免责声明

所有游戏仅为财商教育演示，不构成任何投资建议。投资有风险，入市需谨慎。
