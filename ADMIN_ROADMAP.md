# 小梨工作台与数据资产路线图（交给 Codex 继续做）

本文是唯一规划入口。不要按日历估时，只按 **步骤顺序** 做：做完一步、验收通过，再做下一步。

---

## 0. 你接手时先搞清的事实

### 线上与仓库

| 项 | 值 |
|---|---|
| 仓库 | `xiaoli-caishang/xiaoli-games`，分支 `main` |
| 正式域名 | `https://xiaolipearl.com` |
| EdgeOne 项目（绑了域名） | **`xiaoli-kingdom-web`**（不是 xiaoli-games；未备案不能把自定义域名迁到 games） |
| KV 绑定 | 命名空间已绑到 `xiaoli-kingdom-web`，变量名必须是 **`xl_kv`** |
| 工作台 | `https://xiaolipearl.com/admin/`（`ADMIN_TOKEN` 登录） |
| 自检 | `https://xiaolipearl.com/api/health` → 期望 `"ok":true` |

### 已有后端（不要推倒重来）

| 路径 | 作用 |
|---|---|
| `functions/api/health` | KV / 口令是否就绪 |
| `functions/api/log` | 量化基金生存录每局上报 |
| `functions/api/stats` | 量化挑战人数汇总 |
| `functions/api/evt` | 通用游戏事件（已接「金融里，你是什么登？」`g=fp`） |
| `functions/api/lead` | 官网咨询表单 |
| `functions/api/export` | 管理员按前缀导出 KV（要 token） |
| `admin/index.html` | 工作台壳：总览 / 金融人格 / 量化 / 咨询 / 规划中 |
| `admin/quant/index.html` | 量化详细看板 |

KV 键前缀约定（继续沿用、只增不改语义）：

- `r_` 量化每局 · `e_fp_` 金融人格每局 · `lead_` 咨询 · `c_` 计数器  
- 以后新增：`task_` 工作流 · `asset_` 资产索引 · `agent_` Agent 注册 · `metric_` 手工渠道指标  

### 硬约束

1. 继续 EdgeOne Pages + Functions + KV，不新开云服务器后台。  
2. 新功能 = 新 `/api/*` + `/admin` 里新页或新 Tab，**一个登录、一个域名**。  
3. 推 `main` 由 EdgeOne 拉代码部署；不要在控制台手动覆盖整站文件。  
4. 游戏统计不记录 IP、不记录姓名手机；咨询线索含联系方式，必须留在口令墙后。  
5. 经营材料参考：本机桌面 `小梨Skill存档\小梨工作交接1011\`（交接原则：真实、可验收、不把候选当已批准）。

---

## 1. 群发游戏链接 → 后台监控：现在能不能用？

**能。这一步已经具备，不必等后面的大功能。**

### 数据抓口设在哪里

抓口在 **玩家浏览器里的游戏页面**，不是微信群、也不是工作台本身。

```
玩家点开带参数的链接
  → 游戏 HTML 在关键节点调用接口
  → EdgeOne Function 写入 KV（xl_kv）
  → 你打开 /admin/ 用口令读取 /api/export 看数
```

| 游戏 | 页面里的钩子 | 打到哪个接口 | 工作台哪里看 |
|---|---|---|---|
| 金融里，你是什么登？ | `xlT('start'|'end'|'poster'|'pair')` | `POST /api/evt`（`g:'fp'`） | `/admin/` →「金融里，你是什么登？」 |
| 量化基金生存录 | `track(...)` | `POST /api/log` | `/admin/` →「量化基金生存录」或 `/admin/quant/` |

上报时机（已实现）：

- **开始玩**：记一局 start（含渠道 `src`）  
- **玩完**：记 end（人格代码 / 成绩等）  
- **生成海报 / 合盘**（金融人格）：额外事件  

渠道来自 URL 查询参数 **`from`**（写入记录的 `src` 字段）：

```text
https://xiaolipearl.com/games/finance-persona/?from=wx
https://xiaolipearl.com/games/quant-fund/?from=wx
```

发群建议：

| 场景 | 链接后缀 |
|---|---|
| 微信群 / 朋友圈 | `?from=wx` |
| 某个固定群可再细分 | `?from=wx-qin`、`?from=wx-tongshi`（字母数字短横线，勿过长） |
| 抖音 / B 站 / 小红书 | `?from=dy` / `?from=bl` / `?from=xhs` |

注意：

- 必须发 **xiaolipearl.com** 的链接（或当前 EdgeOne 正式域）。本机 `file://` 打开不会上报。  
- 微信里打开若异常，让对方用系统浏览器打开同一链接再试。  
- 统计是 **匿名按「局」**，不是实名用户；同一人重玩会多条记录——看趋势可以，别当成精确 UV。  
- 发链接后打开 https://xiaolipearl.com/admin/ ，选对应游戏 Tab，按来源筛选或看分布；也可下载 CSV。

### 你现在就可以做的验收（发群前自测）

1. 无痕打开：`https://xiaolipearl.com/games/finance-persona/?from=wx-test`  
2. 点开始并尽量答完（或至少点开始）  
3. 打开 `/admin/` → 金融人格 → 应看到新增记录，`src` 为 `wx-test`  
4. 对量化基金同样测一遍 `?from=wx-test`

通过后就可以正式往群里丢链接，后台盯盘。

---

## 2. 工作台长期要长成什么样

一个入口管理三件事：

1. **看数**：游戏、咨询、以后各平台反馈  
2. **管事**：设计 / 拍摄 / 文案 / 剪辑等进度  
3. **沉淀**：规范、成片、封面、脚本、决策、可调用的 Agent  

信息架构（在现有 `/admin/` 上演进，Tab 可改名但不要拆第二个站）：

```
/admin/
  总览        ← 是否健康 + 今天关键数 + 未读咨询
  产品数据    ← 两款游戏（及以后新游戏）漏斗与渠道
  咨询线索    ← lead 状态机
  内容渠道    ← 各平台数据（先手工录入）
  工作流      ← 任务看板
  Agent 中心  ← 注册与调度不同 AI Agent
  资产库      ← 可检索的资产索引
  系统        ← health、导出、说明
```

---

## 3. 实施顺序（严格按步；无日历）

### 步骤 A — 发群监控可用（巩固现有能力）

目标：你发链接，后台稳定看到数。

- 确认 `/api/health` 为 ok；两游戏自测 `?from=` 写入成功  
- 总览页突出：今日开始/完成、按 `src` 汇总、health 红绿  
- README 或工作台内放「复制发群链接」按钮（预填 `?from=wx` 等）  
- 验收：用测试 from 玩一局 → 工作台 1 分钟内可见 → CSV 能导出  

**本步不做：** 新数据库、新域名、Agent。

### 步骤 B — 总览真正能「扫一眼决策」

- 漏斗：开始 → 完成 → 海报/合盘（金融人格）；量化同理用已有字段  
- 未读咨询数、health 非 ok 时顶栏告警  
- 验收：打开 `/admin` 不点二级 Tab 也能判断「今天正不正常」  

### 步骤 C — 咨询线索轻 CRM

- `lead_` 增加 `status`（new/contacted/closed/spam）、`note`  
- 列表筛选、改状态（新 API 如 `POST /api/lead/update`，要 ADMIN_TOKEN）  
- 验收：一条真实咨询从 new 点到 closed，刷新不丢  

### 步骤 D — 工作流看板

- KV：`task_*`；字段保持少：标题、类型、负责人、状态、链接、截止日期  
- 状态：todo / doing / review / done  
- `/admin` 新 Tab「工作流」CRUD  
- 验收：建 3 个真实任务并改状态  

### 步骤 E — 资产沉淀

仓库增加（大文件可外链，库内存 meta）：

```text
assets/
  brand/
  covers/
  videos/          # 或只存索引 JSON，文件在 COS/OneDrive
  scripts/
  skills/
  decisions/
```

- `asset_*` 或 `assets/index.json` + 工作台「资产库」检索  
- 规则写入验收：Agent/人工产出必须回写资产索引才算完成  
- 把交接包里已确认决策 / skill 快照迁入可检索位置  
- 验收：能按类型找到「角色规范」「某期封面定稿」  

### 步骤 F — 内容与渠道数据（先手工）

- `metric_*`：平台、日期、播放/互动等手工录入  
- 与游戏 `src` 渠道对照看，不要求先对接开放平台 API  
- 验收：连续录入几天后总览能并排看到「内容侧 vs 游戏侧」  

### 步骤 G — Agent 中心（调度多种 AI）

目标：工作台能 **登记、触发入口、查看产出与失败**，不是一上来自建编排引擎。

- `agent_*` 注册表：id、名称、说明、调用方式（HTTP / 文档约定 / 本机脚本路径）、关联 skill、最近状态  
- 运行记录：谁触发、入参摘要、产出资产 id、错误信息  
- 工作台「Agent 中心」：列表 +「打开说明/触发」；触发可以是：  
  - 调外部 AI HTTP API（Key 只放 EdgeOne 环境变量，绝不进仓库）  
  - 或生成给 Cursor/Codex 的任务单（复制提示词）  
- 先接入 2～3 个岗做样板：如剪辑素材、封面、专业回复（skill 已在交接资产里）  
- 验收：从工作台能看到 Agent 列表；手动跑通一次并把产出挂到资产库  

**后置增强（G 完成后再考虑）：** 队列、定时、多 Agent 流水线、与 GitHub Issues 双向同步。

### 步骤 H — 新游戏 / 新抓口规范（有新产品时）

每加一款游戏：

1. `games/<slug>/index.html`  
2. 在开始/结束等节点调用 `/api/evt`（或扩展 `GAMES` 登记）  
3. 大厅卡片 + 工作台产品数据 Tab  
4. 发群链接统一带 `?from=`  

---

## 4. 给 Codex 的接口与页面约定（实现时遵守）

- 写接口：`functions/api/<name>/index.js`，风格对齐现有 `evt` / `lead` / `export`  
- 管理写操作：校验 `ADMIN_TOKEN`（query 或 Header，与 export 一致即可）  
- 前端：优先扩展 `admin/index.html`；单页过重再拆 `admin/<section>/index.html` 并用工作台导航链过去  
- 密钥：AI Provider Key、Webhook Secret 等只进 EdgeOne 环境变量  
- 每步结束更新本文件顶部「已完成步骤」列表（见下）并用 `/api/health` + 对应页面做验收  

### 已完成步骤（实现者勾选）

- [x] 线上 KV + ADMIN_TOKEN + 工作台壳 + 两游戏上报 + 咨询 lead  
- [x] 域名在 `xiaoli-kingdom-web`，仓库 `main` 自动部署  
- [ ] 步骤 A 发群自测与总览渠道强化  
- [ ] 步骤 B  
- [ ] 步骤 C  
- [ ] 步骤 D  
- [ ] 步骤 E  
- [ ] 步骤 F  
- [ ] 步骤 G  
- [ ] 步骤 H（按需）  

---

## 5. 主人怎么用（给 Brian，非开发）

**发群监控（现在）：**

1. 复制：`https://xiaolipearl.com/games/finance-persona/?from=wx`  
   或量化：`https://xiaolipearl.com/games/quant-fund/?from=wx`  
2. 发到群里  
3. 打开 `https://xiaolipearl.com/admin/` 看对应游戏与来源  

**继续交给 Codex：**

说明：「按仓库根目录 `ADMIN_ROADMAP.md` 从步骤 A 未完成项继续；不要跳步；做完一步勾选并写清验收证据。」

---

## 6. 不要做的事

- 不要为了工作台再买一台 CVM 搭第二套后台  
- 不要把未备案域名硬迁到 `xiaoli-games` 项目  
- 不要把 API Key、ADMIN_TOKEN 写进 Git  
- 不要在未做步骤 A 验收前大改上报协议（以免发群期间丢数）  
- 不要把「规划中的 Agent 平台」一次做成；按步骤 G 先注册与可追溯  
