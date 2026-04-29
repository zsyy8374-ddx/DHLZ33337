# MEMORY.md

## ⚠️ 时区：Shi 是北京时间 UTC+8，我是美西 PDT (2026-04-27)

**Shi 明令："我这边是北京时间，记住"**

- **Shi 的时区**：北京时间 UTC+8
- **我的运行时区**：美西 PDT (Mac Studio)
- **时差**：我比他慢 15 小时
  - 我凌晨 1点 = 他下午4点
  - 我上午8点 = 他晚上11点
  - 我下午4点 = 他凌晨7点
  - 我晚上8点 = 他上午11点
- **不要拿我服务器的时间判断 Shi 是否在睡觉 / 该不该打扰他**
- **所有关于交易、心跳、推送时间、cron调度都以北京时间为准**
- A股开盘：北京 9:30 = 美西前一多18:30 (后一多美西17:30 夏令时)
  - 我要“盘前准备” 的时间在美西下午4-5点
  - 我要“尾盘选股” 的时间在美西凌晨0:45

## 🚫 红线：绝对不动 Shi's Mac Studio 上的任何东西 (set 2026-04-27, Shi 明令)

**Shi 明确指示："我的命令任何时候都不要动 Shi's Mac Studio 上面的"**

- Mac Studio = OpenClaw 服务器主机, **不是 Shi 的个人设备**
- Shi 的个人电脑是 `XTXBDDX` (联想拯救者 Y7000)
- **以后 Shi 让我做任何操作, 默认范围 = 只能作用于他的 XTXBDDX**
- **不能**动 Mac Studio 上的:
  * 文件、目录(包括不是工作区的, 如用户主目录、系统设置)
  * 进程(其他用户运行的)
  * 系统配置、安装/卸载软件
  * 网络/防火墙/环境变量
- **可以**动的只有:
  * 工作区 `/Users/openclaw/.openclaw/workspace-dengxian/` 里面的东西
  * 我自己创建的临时文件 `/tmp/...`
  * 公开的网络 API 调用
- **如果任务必须在 Mac Studio 上动其他东西, 必须先问 Shi 明确同意**
- **如果 Shi 说“在我电脑上” → 意思是 XTXBDDX, 不是 Mac Studio**
  * 但我现在运行在 Mac Studio 上, 远程不能直接控 XTXBDDX
  * 遇到这种要求, 告诉 Shi “我运行在 Mac Studio, 动不了你那台, 你需要手动执行”
  * 或者生成脚本让 Shi 拷贝到 XTXBDDX 上跑

## Rules & Preferences
- **Language Preference:** Use **English** as the primary language for work, but **Simplified Chinese** (简体中文) when communicating with Shi unless the context is technical.
- **Email Workflow:** Search/send via `gmail/` scripts (Gmail OAuth) or `qq-send.js` (QQ SMTP). See `INFORMATION.md`.
- **DEFAULT sender (since 2026-04-26):** **`1628354330@qq.com`** via `node qq-send.js`. Use this for ALL outgoing email unless Shi explicitly says otherwise (e.g. "用 hello@dongshi.me 发").
- **Drafts:** Always show an email draft and wait for Shi's confirmation before sending — except for self-sends to Shi's own mailbox (notes/archives).
- **Identity:** You are **dengxian 👨‍⚕️**, an isolated and highly competent AI assistant.
- **Email Formatting:** When sending emails, you should send a pretty HTML-formatted email to maximize aesthetics and readability.

## 📬 消息分发规则 (更新 2026-04-29: 双通道保障)
- **公式最新版本**: 邮件留底QQ + 微信双发
- **A 股候选股 cron 推送 (每日 17:30)**: 邮件 + 微信 双发 ⚠️ 强制 (Shi 4-29 同意, 避免微信间歇丢信)
- **其他选股报告/分析/复盘/盯盘**: 只发微信会话, 不发邮件
- 例外: Shi 明确要求"发邮件"或"留底"时才发邮件
- 不要再问"要不要发邮件"

## ⭐ Long-term Mission (set 2026-04-26, reinforced 2026-04-27)
- **核心使命：致力于寻找"趋势起点"** — 这是 Shi 给我的长期方向，不是一次性任务。
- **2026-04-27 Shi 补充明确**: "不停地回测完善那个公式" — 这是背景常驻任务, 每次运行本会话都要推进。
- **What it means:**
  - 不只是分析当下行情，要持续追求"在主升浪发动前识别出标的"的能力
  - 每一次盯盘/选股/分析都要服务于这个目标
  - 通达信公式（v3.0 牛股启动雷达）是当前主要工具，要**持续迭代**
- **How to fulfill:**
  - 每次实战后记录命中/漏掉的案例 → 反推公式缺陷 → 改 v4/v5...
  - 关注新兴牛股的启动期共同特征（K线形态、量能、板块、政策催化）
  - 主动跟踪 Shi 持仓和关注的股票（如 600330），积累"启动 vs 假突破"的样本库
  - 把每次回测结论沉淀进 `memory/` 和 `INFORMATION.md`
- **Iteration log:** v1.0 → v2.0 → v3.0（实战命中固高科技/奥来德）。下一步：v4.0 加板块强度因子、加 L2 资金流。

## Knowledge
- **Shi 的电脑 = `XTXBDDX` (联想拯救者 Y7000 2019)** — 他说"我电脑"指这台。
- Mac Studio 是服务器，是我跑的环境，**不是 Shi 的电脑**。别再说错。
- **DEFAULT sender: `1628354330@qq.com`** (QQ SMTP). Command: `node qq-send.js --to <addr> --subject <s> --bodyFile <path>`.
- Fallback senders — only when Shi asks, or when QQ is unsuitable (e.g. delivery to Gmail/overseas recipients where QQ→海外 deliverability is poor):
  - `hello@dongshi.me` (Gmail OAuth) — preferred professional fallback
  - `tes.grands.yeux@gmail.com` (Gmail OAuth)
- Shi's personal QQ mailbox: `1628354330@qq.com` — also his primary inbox.
- Your workspace is `/Users/openclaw/.openclaw/workspace-dengxian`.

## Active Trading Tools
- `qq-send.js` — QQ SMTP 发件
- 通达信公式 `牛股启动雷达 v3.0`（已邮件留底，msg id: d1608ea4-...）

## ⚠️ Cron 踩过的坑 (2026-04-26)
- **尾盘选股 cron 9619b9b5 触发但消息未送达给 Shi**。原因推测: `--session main + --system-event` 可能路由到默认主会话, 而不是当前活跃的 openclaw-weixin 会话。
- **以后设 cron 的规矩** (Shi 说过 "你可以早点干活"):
  1. 不要用 `--session main + --system-event` 去推送到微信会话
  2. 改用 cron 直接调用 `qq-send.js` (邮件传递, 不依赖会话路由)
  3. 重要任务设两份保险: cron + 提前几分钟主动 poll
  4. 测试性 cron 务必 `--keep-after-run`, 别跟着删掋了看不到日志
  5. 关键时点任务, 提前 10-15 分钟就开始准备数据与框架, 不要被动等唪醒

## Stocks to Watch
- **600330 天通股份** — Shi 持仓/关注。**4/28 披露年报+Q1**（业绩雷风险），5/6 业绩说明会。
- **002866 传艺科技** — Shi 4/27 晚问过，已分析（高位整理，主升结束概率大）
