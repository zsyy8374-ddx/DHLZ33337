# MEMORY.md

## ⚠️ 时区：Dengxian 是北京时间 UTC+8，我是美西 PDT (2026-04-27)

**Dengxian 明令："我这边是北京时间，记住"**

- **Dengxian 的时区**：北京时间 UTC+8
- **我的运行时区**：美西 PDT (Mac Studio)
- **时差**：我比他慢 15 小时
  - 我凌晨 1点 = 他下午4点
  - 我上午8点 = 他晚上11点
  - 我下午4点 = 他凌晨7点
  - 我晚上8点 = 他上午11点
- **不要拿我服务器的时间判断 Dengxian 是否在睡觉 / 该不该打扰他**
- **所有关于交易、心跳、推送时间、cron调度都以北京时间为准**
- A股开盘：北京 9:30 = 美西前一多18:30 (后一多美西17:30 夏令时)
  - 我要“盘前准备” 的时间在美西下午4-5点
  - 我要“尾盘选股” 的时间在美西凌晨0:45

## 🚫 红线：绝对不动 Dengxian's Mac Studio 上的任何东西 (set 2026-04-27, Dengxian 明令)

**Dengxian 明确指示："我的命令任何时候都不要动 Dengxian's Mac Studio 上面的"**

- Mac Studio = OpenClaw 服务器主机, **不是 Dengxian 的个人设备**
- Dengxian 的个人电脑是 `XTXBDDX` (联想拯救者 Y7000)
- **以后 Dengxian 让我做任何操作, 默认范围 = 只能作用于他的 XTXBDDX**
- **不能**动 Mac Studio 上的:
  * 文件、目录(包括不是工作区的, 如用户主目录、系统设置)
  * 进程(其他用户运行的)
  * 系统配置、安装/卸载软件
  * 网络/防火墙/环境变量
- **可以**动的只有:
  * 工作区 `/Users/openclaw/.openclaw/workspace-dengxian/` 里面的东西
  * 我自己创建的临时文件 `/tmp/...`
  * 公开的网络 API 调用
- **如果任务必须在 Mac Studio 上动其他东西, 必须先问 Dengxian 明确同意**
- **如果 Dengxian 说“在我电脑上” → 意思是 XTXBDDX, 不是 Mac Studio**
  * 但我现在运行在 Mac Studio 上, 远程不能直接控 XTXBDDX
  * 遇到这种要求, 告诉 Dengxian “我运行在 Mac Studio, 动不了你那台, 你需要手动执行”
  * 或者生成脚本让 Dengxian 拷贝到 XTXBDDX 上跑

## Rules & Preferences
- **Language Preference:** Use **English** as the primary language for work, but **Simplified Chinese** (简体中文) when communicating with Dengxian unless the context is technical.
- **Email Workflow:** Search/send via `gmail/` scripts (Gmail OAuth) or `qq-send.js` (QQ SMTP). See `INFORMATION.md`.
- **DEFAULT sender (since 2026-04-26):** **`1628354330@qq.com`** via `node qq-send.js`. Use this for ALL outgoing email unless Dengxian explicitly says otherwise (e.g. "用 hello@dongshi.me 发").
- **Drafts:** Always show an email draft and wait for Dengxian's confirmation before sending — except for self-sends to Dengxian's own mailbox (notes/archives).
- **Identity:** You are **dengxian 👨‍⚕️**, an isolated and highly competent AI assistant.
- **Email Formatting:** When sending emails, you should send a pretty HTML-formatted email to maximize aesthetics and readability.

## 📬 消息分发规则 (更新 2026-04-29: 双通道保障)
- **公式最新版本**: 邮件留底QQ + 微信双发
- **A 股候选股 cron 推送 (每日 17:30)**: 邮件 + 微信 双发 ⚠️ 强制 (Dengxian 4-29 同意, 避免微信间歇丢信)
- **其他选股报告/分析/复盘/盯盘**: 只发微信会话, 不发邮件
- 例外: Dengxian 明确要求"发邮件"或"留底"时才发邮件
- 不要再问"要不要发邮件"

## ⭐ Long-term Mission (set 2026-04-26, reinforced 2026-04-27)
- **核心使命：致力于寻找"趋势起点"** — 这是 Dengxian 给我的长期方向，不是一次性任务。
- **2026-04-27 Dengxian 补充明确**: "不停地回测完善那个公式" — 这是背景常驻任务, 每次运行本会话都要推进。
- **What it means:**
  - 不只是分析当下行情，要持续追求"在主升浪发动前识别出标的"的能力
  - 每一次盯盘/选股/分析都要服务于这个目标
  - 通达信公式（v3.0 牛股启动雷达）是当前主要工具，要**持续迭代**
- **How to fulfill:**
  - 每次实战后记录命中/漏掉的案例 → 反推公式缺陷 → 改 v4/v5...
  - 关注新兴牛股的启动期共同特征（K线形态、量能、板块、政策催化）
  - 主动跟踪 Dengxian 持仓和关注的股票（如 600330），积累"启动 vs 假突破"的样本库
  - 把每次回测结论沉淀进 `memory/` 和 `INFORMATION.md`
- **Iteration log:** v1.0 → v2.0 → v3.0（实战命中固高科技/奥来德）。下一步：v4.0 加板块强度因子、加 L2 资金流。

## Knowledge
- **Dengxian 的电脑 = `XTXBDDX` (联想拯救者 Y7000 2019)** — 他说"我电脑"指这台。
- Mac Studio 是服务器，是我跑的环境，**不是 Dengxian 的电脑**。别再说错。
- **DEFAULT sender: `1628354330@qq.com`** (QQ SMTP). Command: `node qq-send.js --to <addr> --subject <s> --bodyFile <path>`.
- Fallback senders — only when Dengxian asks, or when QQ is unsuitable (e.g. delivery to Gmail/overseas recipients where QQ→海外 deliverability is poor):
  - `hello@dongshi.me` (Gmail OAuth) — preferred professional fallback
  - `tes.grands.yeux@gmail.com` (Gmail OAuth)
- Dengxian's personal QQ mailbox: `1628354330@qq.com` — also his primary inbox.
- Your workspace is `/Users/openclaw/.openclaw/workspace-dengxian`.

## Active Trading Tools
- `qq-send.js` — QQ SMTP 发件
- 通达信公式 `牛股启动雷达 v3.0`（已邮件留底，msg id: d1608ea4-...）

## ⚠️ 金融 ML 踩过的坑: 窗口长度泄漏 (2026-04-29)

**事件**: REVERSAL v0.3 AUC 0.80 / Top10% 96% 是假的, 是 mining 泄漏.
- reversal_mine_v3_sina.py:96 里, callback_dates = D0+1 到 D_t-1
  - reversal 事件: 1-9 天 (有 D_t)
  - failed 事件: 10 天 (没 D_t, 默认 D0+10)
- callback_window 就 100% 区分 reversal 与 failed
- 资金流的均值 间接编码了 outcome

**教训** (写入脑子):
- 不要让正负样本的特征窗口长度由 outcome 决定
- 所有事件必须用 统一的、不依赖 D_t 的窗口 (如 D0+1 到 D0+5)
- **金融 ML AUC > 0.85 是很罕见的, 看到立刻警惕泄漏**
- v0.3 推送的“主力洗盘”类型是全假的 (实际命中 35%, 不是 90%)

**修复**: v0.4 用 cb1/cb3/cb5 统一窗口, 真实 AUC 0.77 / Top10% 91% (OOS 严格验证)

## ⚠️ Cron 踩过的坑 (2026-04-26)
- **尾盘选股 cron 9619b9b5 触发但消息未送达给 Dengxian**。原因推测: `--session main + --system-event` 可能路由到默认主会话, 而不是当前活跃的 openclaw-weixin 会话。
- **以后设 cron 的规矩** (Dengxian 说过 "你可以早点干活"):
  1. 不要用 `--session main + --system-event` 去推送到微信会话
  2. 改用 cron 直接调用 `qq-send.js` (邮件传递, 不依赖会话路由)
  3. 重要任务设两份保险: cron + 提前几分钟主动 poll
  4. 测试性 cron 务必 `--keep-after-run`, 别跟着删掋了看不到日志
  5. 关键时点任务, 提前 10-15 分钟就开始准备数据与框架, 不要被动等唪醒

## Stocks to Watch
- **600330 天通股份** — Dengxian 持仓/关注。**4/28 披露年报+Q1**（业绩雷风险），5/6 业绩说明会。
- **002866 传艺科技** — Dengxian 4/27 晚问过，已分析（高位整理，主升结束概率大）
