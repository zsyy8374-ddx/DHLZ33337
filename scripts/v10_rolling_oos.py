"""v1.0 滚动 OOS 测试: 用历史月份滚动训, 验证下一月
- 训练: 历史所有月份
- 测试: 下一个月
- 看跨时间段稳定性
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from reversal_lr_v10 import extract_v10

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

# 按月分桶
from collections import defaultdict
by_month = defaultdict(list)
for i, e in enumerate(events):
    m = e['d0_date'][:7]
    by_month[m].append(i)

months = sorted(by_month.keys())
print(f"📊 月份: {months[0]} 至 {months[-1]} ({len(months)} 个月)")
for m in months:
    n = len(by_month[m])
    rev = sum(1 for i in by_month[m] if events[i]['outcome']=='reversal')
    print(f"  {m}: n={n:>4}, 反转 {rev/n*100:.1f}%")

features = [extract_v10(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio"]

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

print("\n=== 滚动 OOS: 用 ≤month-1 训, month 测 ===")
print(f"{'测试月':<10}{'n':>5}{'反转率':>8}{'AUC':>7}{'T10':>6}{'T20':>6}{'T30':>6}{'T50':>6}")
print("-"*60)

results = []
for i, test_month in enumerate(months):
    if i < 6: continue  # 至少 6 个月历史
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
    sorted_p = sorted(zip(p, yv), reverse=True)
    
    n = len(test_idx)
    rev_rate = sum(yv) / n
    
    t10 = sum(y for _, y in sorted_p[:10]) / max(1, min(10, n)) * 100
    t20 = sum(y for _, y in sorted_p[:20]) / max(1, min(20, n)) * 100
    t30 = sum(y for _, y in sorted_p[:30]) / max(1, min(30, n)) * 100
    t50 = sum(y for _, y in sorted_p[:50]) / max(1, min(50, n)) * 100
    
    print(f"{test_month:<10}{n:>5}{rev_rate*100:>7.1f}%{auc_v:>7.3f}{t10:>5.0f}%{t20:>5.0f}%{t30:>5.0f}%{t50:>5.0f}%")
    results.append({"month": test_month, "n": n, "rev_rate": rev_rate, "auc": auc_v, "t20": t20, "t50": t50})

# 平均 + 标准差
import statistics
aucs = [r['auc'] for r in results]
t20s = [r['t20'] for r in results]
t50s = [r['t50'] for r in results]
print(f"\n📊 滚动 OOS 平均:")
print(f"  AUC: 平均 {statistics.mean(aucs):.4f}, 标准差 {statistics.stdev(aucs):.4f}")
print(f"  T20 命中: 平均 {statistics.mean(t20s):.1f}%, 标准差 {statistics.stdev(t20s):.1f}")
print(f"  T50 命中: 平均 {statistics.mean(t50s):.1f}%, 标准差 {statistics.stdev(t50s):.1f}")
print(f"  T20 ≥80%: {sum(1 for x in t20s if x>=80)}/{len(t20s)}")
print(f"  T50 ≥75%: {sum(1 for x in t50s if x>=75)}/{len(t50s)}")
