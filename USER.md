# USER.md - About Your Human

- **Name:** Dengxian (登贤)
- **What to call them:** 董哥
- **Pronouns:** _(待补)_
- **Timezone:** 中国北京时间 (UTC+8) — 你在中国, 但我(dengxian)运行在美西主机 (PDT)
- **Language:** 中文沟通
- **QQ Email:** 1628354330@qq.com

## 设备 / Devices

### 💻 Dengxian 的个人电脑 (唯一)
- **名称**: `XTXBDDX`
- **型号**: 联想拯救者 Y7000 2019 (GTX 1050)
- **用途**: 个人日常, 看微信, 跑通达信, 看股票
- ⚠️ 重要: Dengxian 说"我电脑"、“我的电脑” = **这台 XTXBDDX**, 不是别的
- 公式安装/选股/看盘都是在这台上进行

### 🖥️ 服务器 / 我(dengxian) 的运行环境
- **名称**: Dengxian's Mac Studio
- **用途**: 运行 OpenClaw / 我(dengxian)、后台服务, 不是 Dengxian 日常使用的设备
- 我的所有 exec / 脚本 / 邮件发送 / 回测 都在这台上跑
- 不要把这台误以为是"Dengxian的电脑"

## Context (背景)
- **股票交易是重点**: A股选股, 使用通达信; 我的长期使命是不停迭代选股公式, 寻找趋势起点
- **持仓/关注**: 600330 天通股份, 002866 传艺科技
- **职业/兴趣**: 待补充— Dengxian 愿意告诉我更多时再写

## 两个主任务简称 (set 2026-04-29)
- **DAILY** = A股每日候选股推送 (北京 17:30 cron f6884a8a)
  - Dengxian 说 "跑 DAILY" / "DAILY 重发" → 执行 scripts/daily_picks.py, 双发微信+邮件
  - 同系列: DAILY-track 实战命中追踪 (北京 18:30 cron d0742bc1)
- **OPTIM** = A股策略持续优化 (不停迭代公式, 当前 v3.0-lr-rolling)
  - Dengxian 说 "OPTIM 进展?" → 汇报当前版本+最近实验
  - Dengxian 说 "OPTIM 试 XXX" → 把想法起一轮实验 (回测/ablation/上线决策)
  - 包含的 cron: OPTIM-retrain 周一到周五 22:00 滚动 retrain (cron f925e459)
  - 关键文件: scripts/lr_retrain.py, scripts/backtest_v25.py, picks/lr_history/
- **REVERSAL** = 涨停回马枪研究 (set 2026-04-29)
  - 模式: 涨停(D0) → 2-10 天回调 → 再涨停(D_t)
  - 默认: 不要求创新高, 不要求同板块, 回调期 2-10 天
  - 输出: 每日扫描最近 2-10 天涨过停的股, 推荐明日可能回马枪的票
  - Dengxian 说 "REVERSAL 进展?" / "跑 REVERSAL" → 挑幢当前版本或推送候选列表

## 交流偏好
- 说中文, 不要太形式化; 不喜欢套话套素
- 不要主动问"要不要发邮件" (他明确订了规则: 只有公式最新版才邮箱+微信双发, 其他只发微信)
- 被批评时不要辩解, 认错、查原因、修正、写防范规则

---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
