"""v1.1 加'近期反转率'特征 - 反映周级别市场温度
- recent_5d_rev_rate: 过去 5 个交易日内, 类似事件 (lbc=1) 的反转率
- recent_10d_rev_rate: 过去 10 天
- 这些都是 "推送时 D-1 可见" 的特征 (用 D0 之前的反转事件)
"""
import json, sys
from collections import defaultdict
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from reversal_lr_v10 import extract_v10, get_dminus1, detect_v6, idx_by_date

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

# 按 D0 日期排序
events_sorted = sorted(events, key=lambda e: (e['d0_date'], e.get('code','')))

# 拼一个 "时间序列": 每天的事件结果
date_events = defaultdict(list)
for e in events_sorted:
    date_events[e['d0_date']].append(e)
all_dates = sorted(date_events.keys())
date_to_idx = {d: i for i, d in enumerate(all_dates)}

# 对每个事件, 算它前 5/10/20 交易日的反转率 (基于已发生事件, 这里用 D0 当天前的 D0 事件)
# ⚠️ 这里要特别小心: 用 D0 之前的事件 (不是 D0 当天), 否则就是事后信息
def get_recent_rev_rate(e, lookback_days):
    d0 = e['d0_date']
    if d0 not in date_to_idx: return 0.5, 0
    i0 = date_to_idx[d0]
    start_i = max(0, i0 - lookback_days)
    related = []
    for d in all_dates[start_i:i0]:  # 不含 d0 当天
        for ev in date_events[d]:
            if ev.get('d0_lbc', 1) == e.get('d0_lbc', 1):  # 同 lbc
                related.append(ev)
    if not related: return 0.5, 0  # 默认 50%
    rev = sum(1 for ev in related if ev['outcome'] == 'reversal')
    return rev / len(related), len(related)


def extract_v11(e):
    f = extract_v10(e)
    rate_5, n_5 = get_recent_rev_rate(e, 5)
    rate_10, n_10 = get_recent_rev_rate(e, 10)
    rate_20, n_20 = get_recent_rev_rate(e, 20)
    f["recent_5d_rev_rate"] = rate_5
    f["recent_10d_rev_rate"] = rate_10
    f["recent_20d_rev_rate"] = rate_20
    # 强弱接力信号
    f["strong_relay"] = 1.0 if rate_10 >= 0.6 else 0.0
    f["weak_relay"] = 1.0 if rate_10 < 0.3 else 0.0
    return f


# 训
features = [extract_v11(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

# 滚动 OOS 验证
by_month = defaultdict(list)
for i, e in enumerate(events):
    by_month[e['d0_date'][:7]].append(i)
months = sorted(by_month.keys())

print("=== v1.1 (含近期反转率) 滚动 OOS ===")
print(f"{'月':<10}{'AUC':>8}{'T10':>6}{'T20':>6}{'T50':>6}{'P>=0.7 命中':>15}{'候选数':>8}")
print("-"*60)

aucs_v11 = []; t20s_v11 = []; phig_v11 = []
for i, test_month in enumerate(months):
    if i < 6: continue
    train_idx = []
    for prev_m in months[:i]:
        train_idx.extend(by_month[prev_m])
    test_idx = by_month[test_month]
    
    Xtr_raw = [features[j] for j in train_idx]
    Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
    yt = [labels[j] for j in train_idx]
    w, b = train_lr(Xtr, yt, lr=0.1, iters=200, l2=0.01)
    
    Xte_raw = [features[j] for j in test_idx]
    Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
    yv = [labels[j] for j in test_idx]
    p = predict(Xte, w, b)
    
    auc_v = auc(p, yv)
    paired = sorted(zip(p, yv), reverse=True)
    
    t10 = sum(y for _, y in paired[:10]) / max(1, min(10, len(paired)))
    t20 = sum(y for _, y in paired[:20]) / max(1, min(20, len(paired)))
    t50 = sum(y for _, y in paired[:50]) / max(1, min(50, len(paired)))
    
    high07 = [(p_, y_) for p_, y_ in paired if p_ >= 0.7]
    h07 = sum(y for _, y in high07) / len(high07) if high07 else 0
    
    print(f"{test_month:<10}{auc_v:>8.3f}{t10*100:>5.0f}%{t20*100:>5.0f}%{t50*100:>5.0f}%{h07*100:>11.0f}%(n{len(high07):>2}){'  '}")
    aucs_v11.append(auc_v)
    t20s_v11.append(t20)
    phig_v11.append((h07, len(high07)))

import statistics
print(f"\n📊 v1.1 滚动 OOS 平均:")
print(f"  AUC: {statistics.mean(aucs_v11):.4f} (std {statistics.stdev(aucs_v11):.4f})")
print(f"  T20 命中: {statistics.mean(t20s_v11)*100:.1f}% (std {statistics.stdev(t20s_v11)*100:.1f})")
print(f"  P>=0.7 命中平均: {statistics.mean(p[0] for p in phig_v11)*100:.1f}%")
print(f"  P>=0.7 候选数平均: {statistics.mean(p[1] for p in phig_v11):.1f}")

# 跟 v1.0 比
print("\n=== 对比 v1.0 (无 recent_rev_rate) ===")
print(f"  v1.0 AUC 平均: 0.770, T20 命中 88.3%, P≥0.7 命中 90%")
print(f"  v1.1 AUC 平均: {statistics.mean(aucs_v11):.3f}, T20 命中 {statistics.mean(t20s_v11)*100:.1f}%")

# 看 recent 特征学到了什么
features_full = features
X_all, mu_all, sd_all = normalize(features_full, cont_keys)
w_all, b_all = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)
print(f"\n📊 v1.1 全量权重 Top 25:")
for k, v in sorted(w_all.items(), key=lambda x: -abs(x[1]))[:25]:
    sign = "↑" if v > 0 else "↓"
    print(f"   {k:<26} {v:+.4f} {sign}")
