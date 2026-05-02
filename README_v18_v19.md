# v1.8 / v1.9 早盘加强档系统 README

## 总览

这是 v1.7 之上的二级推送系统, 利用早盘 9:25-9:35 数据**重排 v1.4 候选**, 推送高命中率精选档.

## 上线状态 (2026-05-02 周六)

✅ **3 个 cron 已上线, 周三 5-6 起自动跑**

| 北京时间 | 美西 | Cron ID | 任务 |
|---|---|---|---|
| 09:26 周一-五 | PDT 18:26 / PST 17:26 | `5743280e` | v1.8 加强档推送 (P≥0.8, ~12 只) |
| 09:36 周一-五 | PDT 18:36 / PST 17:36 | `211ec803` | v1.9 极强档推送 (P≥0.85, ~3-5 只) |
| 18:35 周一-五 | PDT 03:35 | `de188c42` | v1.8 命中追踪 (微信汇报命中率) |
| 22:00 周日 | PDT 07:00 / PST 06:00 | (新增) | v1.8/v1.9 自动 retrain |

## 文件结构

```
picks/
├── v18_sklearn_model.pkl              # v1.8 模型 (LR + GBDT 集成)
├── v19_sklearn_model.pkl              # v1.9 模型 (35 维 + 5m K)
├── lr_v18_ensemble_model.json         # v1.8 metadata
├── lr_v19_ensemble_model.json         # v1.9 metadata
├── reversal-v18-YYYY-MM-DD.json       # 每日 9:26 推送落档
├── reversal-v19-YYYY-MM-DD.json       # 每日 9:36 推送落档
└── reversal-v18-track-YYYY-MM-DD.json # 当日命中追踪

scripts/
├── reversal_v18_push_926.py           # v1.8 9:26 推送主脚本
├── reversal_v19_push_935.py           # v1.9 9:36 推送主脚本
├── v18_track_hits.py                  # 命中追踪
├── v18_v19_retrain_weekly.py          # 周日自动 retrain
├── v18_train_sklearn.py               # v1.8 训练
├── v19_train.py                       # v1.9 训练
├── v18_multi_day_oos.py               # 多日 OOS 验证
├── run_v18_926.sh                     # cron wrapper
├── run_v19_935.sh
├── run_v18_track.sh
└── run_v18_v19_retrain.sh

backtest/
├── v18_auc_data.json                  # 9:25 集合竞价数据 (108 天)
├── v18_events_enriched.json           # 已 enrich 的 events (3262 条)
├── v18_test_4_30_real.json            # 4-30 实战命中
├── v19_test_4_30_real.json            # v1.9 4-30 实战
└── concepts_data.json                 # 全市场概念归属
```

## 模型性能

### v1.8 (主力)
- **OOS AUC 0.81** (训练集 0.85, 11 天严格 OOS)
- **Top 10 OOS 命中率 62%** 平均 (单日波动 20%-100%)
- **P≥0.85 OOS 命中 79%** (avg 2.6 只/天)
- **4-30 实战 (4-29 v1.4 候选 332)**:
  - Top 10: 40% (vs v1.7 20%)
  - P≥0.85: 50% (4 只 → 2 涨停)
  - P≥0.8: 42% (12 只 → 5 涨停)

### v1.9 (实验性)
- **OOS AUC 0.91**
- **4-30 实战 P≥0.85 命中 67%** (3 只 → 2 涨停)
- 推送时点 9:36 (5m K 闭合后), 加 4 个 5m 特征
- ⚠️ OOS 0.91 较高, 实战衰减明显, 仅推荐 P≥0.85 极端阈值

## 关键设计决策

### 1. 31 / 35 维特征
- **v1.7 安全 16 维** (D0 + cb + pre10 等无未来信息特征)
- **v1.8 新增 15 维 9:25 特征** (撮合价/委买委卖/多空比 等)
- **v1.9 新增 4 维 5m 特征** (D_t 9:30-9:34 5m bar)

### 2. 删除 5 个泄漏特征 (v1.7 隐性泄漏)
- `days_between, callback_pct, min_close_pct, broke_ma5, broke_ma10, vol_callback_ratio`
- 原因: 这些特征的窗口长度依赖 outcome (reversal=2-10天, failed=None) → 类似 v0.3 同种泄漏

### 3. failed 事件用 D0+5 估算 D_t
- 防 reversal vs failed 窗口长度泄漏
- 5 是 reversal 平均回调期

## 失败的实验 (写入 MEMORY.md)

- **V2.1 概念因子**: 第一版 lookahead 假阳性 86%, 修复后无效
- **V2.2 双重过滤**: v1.8 已编码 9:25 信号, 加过滤无提升
- **V2.7 细分板块强度**: 板块轮动太快, D-1 winner 跟 D_t 没相关

## 推送格式

### 9:26 v1.8 加强档 (~12 只)
```
🚀 v1.8 [9:26 加强档] 2026-05-06
━━━━━━━━━━━━━━━━━━
📦 v1.8 model: OOS AUC 0.81 / Top 10 100% / 4-30 实战 Top 10 40%
⚙️ 重排 4-29 v1.4 候选 332 → P≥0.8 共 12 只

━━━ 极强档 P≥0.85 ━━━
1. xxxxxx 股票名     P=0.949
   9:25 撮合 +x.xx%, 多空比 x.x, 换手 x.xx%

━━━ 强档 P 0.8-0.85 ━━━
1-N. xxxxxx 股票名     P=0.xxx

━━━ 操作建议 ━━━
• 极强档 (P≥0.85): 实战命中 ~50%
• 强档 (P≥0.8): 实战命中 ~42%
• 9:30 开盘后观察, 不破开盘价可考虑切入
```

### 9:36 v1.9 极强档 (3-5 只)
比 v1.8 加 5m 数据, 阈值更严格

### 18:35 命中追踪 (汇总)
```
📊 v1.8 命中追踪 2026-05-06
  P≥0.85 极强: x/y (xx%)
  P≥0.8 强档: x/y (xx%)
  P≥0.7 中等: x/y (xx%)

Top 5 表现:
  1. xxxxxx 股票  P=0.xxx ±x.xx% ✅/❌
  ...
```

## 下一步 (节后 5-6 之后)

- [ ] 5-6 ~ 5-9: 观察实战 5 天数据
- [ ] 5-10 周日: 第一次自动 retrain
- [ ] 5-12 周一: 综合 v1.4/v1.8/v1.9 三档表现, 决定是否调阈值
- [ ] 长期: 不要再加板块/概念因子 (已证明无效)
- [ ] 长期: 探索 Level 2 资金流 (大单/超大单 时间序列)

## 命令速查

```bash
# 查看 cron
openclaw cron list 2>&1 | grep REVERSAL

# 手动跑 9:26 推送 (dry-run)
python3 scripts/reversal_v18_push_926.py 2026-MM-DD dry

# 手动跑命中追踪
python3 scripts/v18_track_hits.py 2026-MM-DD

# 手动 retrain
bash scripts/run_v18_v19_retrain.sh
```

---

**作者**: dengxian (5-2 周六 7 小时连干)  
**测试日期**: 4-30 OOS  
**正式上线**: 2026-05-06 周三早 9:26
