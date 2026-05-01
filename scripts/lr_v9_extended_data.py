"""v0.9 用扩展数据集 (3262 events) 训 LR
- 数据: 2025-02 至 2026-04 (15 个月)
- 资金流缺失: 历史数据没 cb5/cb1, 用 0 fillna
- 这测试: 大数据 + 简化特征 是否比 1151 + 复杂特征更稳
"""
import json, sys, random, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v7.json') as f:
    events = json.load(f)['events']

# 限制只用 K 线特征, 因为新数据没资金流
def extract_v9(e):
    callback = e.get("callback_pct", 0) or 0
    vol_ratio = e.get("vol_callback_ratio", 0) or 0
    d0_chg = e.get("d0_chg", 10) or 10
    lbc = e.get("d0_lbc", 1) or 1
    return {
        "callback_pct": callback,
        "min_close_pct": e.get("min_close_pct", 0) or 0,
        "broke_ma5": 1.0 if e.get("broke_ma5") else 0.0,
        "double_break": 1.0 if e.get("broke_ma5") and e.get("broke_ma10") else 0.0,
        "shallow": 1.0 if callback < 3 else 0.0,
        "deep": 1.0 if callback >= 10 else 0.0,
        # 量比 U 型
        "vol_extreme_low": 1.0 if vol_ratio < 0.3 else 0.0,
        "vol_dead_zone": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,
        "vol_callback_ratio": vol_ratio,
        # D0 涨幅
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
        "lbc_num": lbc,
        "is_lianban": 1.0 if lbc >= 2 else 0.0,
        "lianban_shallow": 1.0 if lbc >= 2 and 2 <= callback < 5 else 0.0,
    }

features = [extract_v9(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]

cont_keys = ["callback_pct", "min_close_pct", "vol_callback_ratio", "lbc_num"]

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

# 时序拆分: 80% 训 20% 测
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
test_idx = sorted_idx[int(N*0.8):]
train_idx = sorted_idx[:int(N*0.8)]

print(f"📊 数据: 总 {N}, 反转 {sum(labels)}, 反转率 {sum(labels)/N*100:.1f}%")
print(f"📊 时序拆分: 训 {len(train_idx)}, 测 {len(test_idx)}")

Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)

Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p_te = predict(Xte, w, b)
ts_auc = auc(p_te, yv)
print(f"\n时序 OOS AUC: {ts_auc:.4f}")

# Top N 命中率
sorted_pte = sorted(zip(p_te, yv), reverse=True)
print("\nTop N 命中:")
for n in [10, 20, 30, 50, 100, 150]:
    if len(sorted_pte) < n: continue
    sub = sorted_pte[:n]
    hit = sum(y for _, y in sub) / n
    p_thr = sub[-1][0]
    print(f"   Top {n:>3}: 命中 {hit*100:.1f}%, P 阈值 {p_thr:.3f}")

# 全量训
X_all, mu_all, sd_all = normalize(features, cont_keys)
w_all, b_all = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)

print(f"\n📊 v0.9 全量权重 (n={N}):")
for k, v in sorted(w_all.items(), key=lambda x: -abs(x[1]))[:15]:
    sign = "↑" if v > 0 else "↓"
    print(f"   {k:<22} {v:+.4f} {sign}")

# 落档
out = {
    "version": "v0.9",
    "data_basis": "扩展 3262 events (2025-02 至 2026-04)",
    "features": list(features[0].keys()),
    "cont_keys": cont_keys,
    "feature_means": mu_all,
    "feature_stds": sd_all,
    "weights": w_all,
    "bias": b_all,
    "ts_auc": ts_auc,
    "n_events": N,
    "reversal_rate": sum(labels)/N,
}

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v9_kline_only.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n📁 落档: lr_v9_kline_only.json")

# 跟 v0.8 (1151 events) 比较: AUC 是不是显著改善?
print(f"\n=== 比较: v0.8 (1151 + 资金流) vs v0.9 (3262 仅 K 线) ===")
print(f"  v0.8 OOS AUC: 0.7738 (含资金流)")
print(f"  v0.9 OOS AUC: {ts_auc:.4f} (仅 K 线, 但 3 倍样本)")
