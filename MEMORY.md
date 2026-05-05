# MEMORY.md

## ⚠️ 时区：Dengxian 是北京时间 UTC+8，我是美西 PDT (2026-04-27)

**Dengxian 明令："我这边是北京时间，记住"**

- **Dengxian 的时区**：北京时间 UTC+8
- **我的运行时区**：美西 PDT (Mac Studio)
- **时差**：北京 = 美西 + 15 小时 (北京比我快 15h)
  - **我 PDT 凌晨 1点 = 他北京下午 4点** (他刚收盘)
  - 我 PDT 上午 8点 = 他北京晚上 11点 (他要睡)
  - 我 PDT 下午 4点 = 他次日北京凌晨 7点 (他早起)
  - 我 PDT 晚上 8点 = 他次日北京上午 11点 (周末睡起来)
  - ⚠️ 不要反过来算 (我凌晨 ≠ 他凌晨)
  - 2026-04-30 又犯一次: 说他 "凌晨 5点该睡了", 实际他下午 4 点刚收盘
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

## 🚫 子代理默认用 Sonnet (set 2026-05-04, Dengxian 明令)

- **sessions_spawn 默认 `model: "claude-sonnet-4-6"`** (或 anthropic/claude-sonnet-4-6)
- **不要用 GLM (zai/glm-5)** — Dengxian 明说不信任质量
- 例外: 极简单的格式化/重命名可用 gpt-5-nano (更便宜, 但任务不能需要理解)
- 任何涉及 **内容理解 / 总结 / 压缩 / 代码 / 分析** → 一律 Sonnet
- cron 里跑的后台子代理 (如 token 监控) 可继续用 gpt-5-nano — 那些是机械任务

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

## ⚠️ 金融 ML 踩过的坑: 单日 lift 不可信 (2026-05-03)

**事件**: N 字回踩战法, 单日 (4-29) lift 4.65x, 几乎要上 cron.
- 多日验证 (4-21~4-29 共 7 天): lift 滑到 0.43-1.12x
- P1≥15+深调 子条件 n=6 → 单日运气

**教训** (写入脑子):
- **不要被单日高 lift 骗** — 必须 5+ 天回测
- **基线选择影响结论** — vs 池 vs vs 全市场可能差 3-6 倍
- **n<10 的 lift 都要警惕**, 必须扩样本
- 这次差点上 cron, 多日验证拦下来了

**修复**: N 字暂不上 cron, 加进 ML 模型作为特征 (待做)

## ⚠️ 金融 ML 踩过的坑: in-sample 阈值校准 (2026-04-30)

**事件**: v0.4 主要阈值用训练集校准, 导致推送时 "极强档 0 只".
- calibrate_thresholds() 在训练集上跳 P=0.97 才能 ≥85% 命中
- OOS 测试集上 P=0.784 就能 ≥85% 命中
- 阈值设太高 → 真实信号被埋, 推荐变空

**教训** (写入脑子):
- AUC 是排序质量, P 阈值是切档界限, **两件事**
- 切档界限永远要用 OOS 校准, 不能 in-sample
- 可靠指标是 "OOS Top N 命中率", Top 20 是金型师本金律
- 不要相信训练集上的 P-命中率 mapping

**修复**: scripts/reversal_recalibrate.py 干这件, 阈值从 0.97 调到 0.784

## ⚠️ Cron 踩过的坑 (2026-04-26)
- **尾盘选股 cron 9619b9b5 触发但消息未送达给 Dengxian**。原因推测: `--session main + --system-event` 可能路由到默认主会话, 而不是当前活跃的 openclaw-weixin 会话。
- **以后设 cron 的规矩** (Dengxian 说过 "你可以早点干活"):
  1. 不要用 `--session main + --system-event` 去推送到微信会话
  2. 改用 cron 直接调用 `qq-send.js` (邮件传递, 不依赖会话路由)
  3. 重要任务设两份保险: cron + 提前几分钟主动 poll
  4. 测试性 cron 务必 `--keep-after-run`, 别跟着删掋了看不到日志
  5. 关键时点任务, 提前 10-15 分钟就开始准备数据与框架, 不要被动等唪醒

## Stocks to Watch (现持仓 set 2026-05-04)
- **600330 天通股份** (持仓) — 4/28 披露年报+Q1, 5/6 业绩说明会。
- **002805 丰元股份** (持仓 新加 5-4) — 山东丰元化学, 主营工业草酸 + 锂电池正极材料。有色金属/金属非金属新材料/电池材料。
- ~~002866 传艺科技~~ — 已不是关注 (4/27 分析主升结束, 现已走)

## ⚠️ 金融 ML 踩过的坑: 用 outcome 反推 hot concepts (2026-05-02)

**事件**: V2.1 第一版"大成功" (P≥0.7 + hot≥2 命中 86%) 是 lookahead bias.
- 我用 4-30 涨停的 18 只股反推 hot concepts (lift ≥ 2)
- 然后给 4-29 候选打 hot_concept_n 重排
- 看起来 Top 7 / 7 全中
- 但**实战 4-29 推送时根本不知道 4-30 哪些概念会强**

**修复**: V2.1 v2 严格用 D-1 (4-29) 概念强度.
- D-1 涨停最多概念 → 仍然没用
- v1.8 + hot_4_29 联动 → 命中率不升反降
- Top 20 命中 6/20 < v1.8 原 7/20

**教训** (写入脑子):
- 算特征前问自己: 推送 D-1 17:30 时, 这个 feature 能不能算出来?
- 如果需要 D_t 数据 → 泄漏
- 如果用 outcome 反推 → 隐性泄漏
- **静态板块归属 (融资融券 / 深股通) 太泛, 没预测力**
- **动态板块强度 (D-1 涨停集中度) 也没预测力 — 板块轮动太快**

## ⚠️ V2.7 细分板块 — 仍然失败 (2026-05-02)

**事件**: 用 D-1 (4-29) 涨停集中度最高的细分概念 (50-200 只, 5+ 涨停) 作为加权特征
- 选了 "PCB概念/小金属/CPO/算力租赁/苹果/金属铜/工业母机/液冷服务器/柔性屏/第三代半导体" 10 个
- v1.8 + 0.05*narrow_hot 重排 → **Top 10 30% (vs 原 v1.8 40%) 下降**

**为什么**: 板块轮动太快, D_t 的 winner 不在 D-1 的强势板块里.
- 4-30 涨停: 粤传媒(文化传媒) / 万通发展(芯片) / 全筑(建筑节能) — 都不在 4-29 强势板块
- 4-29 强势的小金属/PCB 在 4-30 没继续大涨

**最终结论**: 板块强度不是 reversal 好特征. 死路.
**v1.8 自己已是当前 best**, 多日 OOS Top 10 62%, 不要再加板块/概念因子.

## ⚠️ 战法独立原则 (Dengxian 5-3 14:29 提醒)

**错误**: 把战法 B v2 的"软封+早封"+15分硬塞进 DAILY (commit 9fa525f, 已 revert)
- DAILY 综合评分变成偏向 B v2 信号, 失去独立性
- 两套战法变成同一套, 失去差异化分散价值

**规则**: 战法之间不互相污染
- DAILY = 综合评分 (反包/形态/连板/龙虎榜) + LR — 找潜力股
- B v2 = 单一信号 (软封+早封 T+1) — 稳定隔夜
- 各自独立优化, 各自独立回测, 各自独立推送
- 唯一可共享的是"数据完整性修复" (如一字板剔除), 不是战法逻辑

**Dengxian 在 13:08 已经说"DAILY 保留独立", 我当时没真正理解, 还塞了 B v2 加分**

## 🎯 两套战法的本质区别 (Dengxian 5-3 14:30 点醒)

### DAILY = 强者恒强 (动量型)
- **逻辑**: 找已经走出来的强势票, 赌动量延续
- **核心因子**: 连板高度 / 反包形态 / 龙虎榜机构 / 板块主升浪 / 量价配合
- **持仓时间**: 1-数日 (跟着主升浪)
- **思想**: "强者恒强" - 强势股第二天/第三天大概率继续强
- **典型标的**: 3 板以上 / 板块龙头 / 机构席位买入

### 战法 B v2 = 隔夜套利 (技术型)
- **逻辑**: 当晚抢入封单结构合理的涨停股, 次日开盘溢价卖出
- **核心因子**: 软封 (3-5 封流比) + 早封 (9:30-10:00) + 非一字板
- **持仓时间**: 1 晚 (T+0 买 T+1 卖)
- **思想**: "硬封 = 主力高调出货, 软封 = 散户跟风溢价" - 第二天开盘抢溢价
- **典型标的**: 1-2 板 + 中等盘子 + 中等封单

### 关键差异
| 维度 | DAILY | B v2 |
|---|---|---|
| 信号源 | 价量+龙虎榜+板块 | 封单结构 |
| 持仓 | 多日 | 1 晚 |
| 收益来源 | 主升浪延续 | 开盘溢价 |
| 选硬封 vs 软封 | 偏硬封 (强势) | **强烈偏软封** |
| 典型 P 票 | 越剑智能 (4连板) | 香飘飘 (1板软封) |

### 不能合并的原因
- DAILY 喜欢硬封 (主力锁筹, 后续走强)
- B v2 喜欢软封 (开盘溢价, 反而硬封是雷)
- **两套信号方向相反**, 强行融合会互相抵消
- 各自独立运行, 互相验证, 找差异股复盘
