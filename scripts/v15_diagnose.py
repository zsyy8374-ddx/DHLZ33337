"""诊断 v1.5 为何 pre10 没改善
- 全量训 v1.5 LR, 看 pre10 权重
- pre10 可能跟 cb5_main_avg 共线性 (主力流入持续 vs 5 日均额)
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v15_with_pre10 import extract_v15

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v9-with-pre10.json') as f:
    events = json.load(f)['events']

features = [extract_v15(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate",
             "pre10_days_in","pre10_strong_days","pre10_main_total","pre10_main_avg","pre10_max_streak"]

X_norm, mu, sd = normalize(features, cont_keys)
w, b = train_lr(X_norm, labels, lr=0.1, iters=300, l2=0.01)

pre10_weights = [(k, v) for k, v in w.items() if 'pre10' in k]
pre10_weights.sort(key=lambda x: abs(x[1]), reverse=True)
print("=== v1.5 LR 权重 (pre10 部分) ===")
for k, v in pre10_weights:
    arrow = "↑" if v > 0 else "↓"
    print(f"  {k:30s}  {v:+.4f}  {arrow}")

# 看相关性 (协方差)
import statistics
def corr(a, b):
    if len(a) < 2: return 0
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((a[i]-ma)*(b[i]-mb) for i in range(len(a)))
    da = sum((a[i]-ma)**2 for i in range(len(a))) ** 0.5
    db = sum((b[i]-mb)**2 for i in range(len(a))) ** 0.5
    return num / (da*db) if da*db else 0

print("\n=== pre10 与原特征的相关性 ===")
pre10_keys = ["pre10_days_in","pre10_strong_days","pre10_main_total","pre10_main_avg"]
orig_keys = ["cb5_main_avg","pre_d0_5d_main_avg","cb1_main_avg","cb5_in_high"]
print(f"{'':30s}{' '.join(f'{k:>15s}' for k in orig_keys)}")
for pk in pre10_keys:
    pa = [f.get(pk, 0) for f in features]
    row = []
    for ok in orig_keys:
        oa = [f.get(ok, 0) for f in features]
        c = corr(pa, oa)
        row.append(f"{c:>15.3f}")
    print(f"{pk:30s}{' '.join(row)}")

# 看 pre10_extreme 触发情况和被 LR 吃掉的程度
print("\n=== pre10_extreme_persistent 分组反转率 ===")
ev_extreme = [e for e in events if features[events.index(e)].get('pre10_extreme_persistent') == 1.0]
n = len(ev_extreme); rev = sum(1 for e in ev_extreme if e['outcome'] == 'reversal')
print(f"  pre10_strong_days >=5 (触发): n={n}, 反转率 {rev/n*100:.1f}%")
print(f"  vs 全样本: 36.8%")

# 看 cb5_main_avg 跟 pre10 重叠
print("\n=== cb5_main_avg ≥1亿 + pre10 强弱对比 ===")
cb5_strong = [e for e in events if e.get('cb5_main_avg', 0) >= 1]
n = len(cb5_strong); rev = sum(1 for e in cb5_strong if e['outcome'] == 'reversal')
print(f"  cb5≥1亿: n={n}, 反转率 {rev/n*100:.1f}%")

cb5_pre10 = [e for e in events if e.get('cb5_main_avg', 0) >= 1 and e.get('pre10_strong_days', 0) >= 3]
n = len(cb5_pre10); rev = sum(1 for e in cb5_pre10 if e['outcome'] == 'reversal')
print(f"  cb5≥1亿 + pre10_strong≥3: n={n}, 反转率 {rev/n*100:.1f}%")

cb5_only = [e for e in events if e.get('cb5_main_avg', 0) >= 1 and e.get('pre10_strong_days', 0) <= 1]
n = len(cb5_only); rev = sum(1 for e in cb5_only if e['outcome'] == 'reversal')
print(f"  cb5≥1亿 但 pre10_strong≤1 (突然 push): n={n}, 反转率 {rev/n*100:.1f}%")
