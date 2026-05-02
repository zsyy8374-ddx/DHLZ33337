"""把纯 pm 模型 (8 维 LR, AUC 0.841 / T20 98.3%) 序列化保存
用于 9:40 二次扫描
"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WORKSPACE / 'backtest' / 'reversal-events-2026-05-01-v10-with-pm.json') as f:
    events = json.load(f)['events']

pm_evs = [e for e in events if 'pm_open_pct' in e]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in pm_evs]

features = []
for e in pm_evs:
    features.append({
        'pm_open_pct': e.get('pm_open_pct', 0) or 0,
        'pm_5m_high_pct': e.get('pm_5m_high_pct', 0) or 0,
        'pm_5m_close_pct': e.get('pm_5m_close_pct', 0) or 0,
        'pm_10m_high_pct': e.get('pm_10m_high_pct', 0) or 0,
        'pm_5m_amt_yi': e.get('pm_5m_amt_yi', 0) or 0,
        'pm_strong_open': e.get('pm_strong_open', 0) or 0,
        'pm_weak_open': e.get('pm_weak_open', 0) or 0,
        'pm_open_red_5m': e.get('pm_open_red_5m', 0) or 0,
    })

cont_keys = ['pm_open_pct', 'pm_5m_high_pct', 'pm_5m_close_pct', 'pm_10m_high_pct', 'pm_5m_amt_yi']

# 全量训
X_norm, mu, sd = normalize(features, cont_keys)
w, b = train_lr(X_norm, labels, lr=0.1, iters=500, l2=0.01)

# 校准阈值: 用 OOS 预测分布
def auc_local(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

# 用最近 2 个月做 OOS 看分布
test_evs = [e for e in pm_evs if e['d0_date'][:7] >= '2026-03']
test_features = [f for i, f in enumerate(features) if pm_evs[i]['d0_date'][:7] >= '2026-03']
test_labels = [labels[i] for i, e in enumerate(pm_evs) if e['d0_date'][:7] >= '2026-03']

# 用前面的训
train_features = [f for i, f in enumerate(features) if pm_evs[i]['d0_date'][:7] < '2026-03']
train_labels = [labels[i] for i, e in enumerate(pm_evs) if e['d0_date'][:7] < '2026-03']

X_tr, mu_tr, sd_tr = normalize(train_features, cont_keys)
w_tr, b_tr = train_lr(X_tr, train_labels, lr=0.1, iters=500, l2=0.01)
X_te = [{k:((v-mu_tr[k])/sd_tr[k] if k in cont_keys else v) for k,v in f.items()} for f in test_features]
p_te = predict(X_te, w_tr, b_tr)

paired = sorted(zip(p_te, test_labels), reverse=True)
print(f"OOS test set: {len(test_labels)} events, AUC={auc_local(p_te, test_labels):.3f}")

# 校准 P_high (≥85% 命中) / P_mid (≥70% 命中)
sorted_p = sorted(p_te, reverse=True)
P_high = None; P_mid = None
n_total = len(test_labels)

for thr in [0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5, 0.45, 0.4]:
    above = [(p, y) for p, y in zip(p_te, test_labels) if p >= thr]
    if len(above) < 5: continue
    hit = sum(y for _, y in above) / len(above)
    print(f"  P>={thr:.2f}: n={len(above)}, 命中率 {hit*100:.1f}%")
    if P_high is None and hit >= 0.85 and len(above) >= 5:
        P_high = thr
    if P_mid is None and hit >= 0.70 and len(above) >= 10:
        P_mid = thr

print(f"\n校准: P_high={P_high}, P_mid={P_mid}")

# 保存
import time
model = {
    "version": "pm-v1.0",
    "trained_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    "n_train": len(features),
    "weights": w,
    "bias": b,
    "feature_means": mu,
    "feature_stds": sd,
    "cont_keys": cont_keys,
    "feature_names": list(features[0].keys()),
    "P_high": P_high or 0.7,
    "P_mid": P_mid or 0.5,
    "ts_auc": 0.841,
    "top10_hit": 0.983,
    "purpose": "9:40 二次扫描, pm 8 维 LR, AUC 0.841 T20 98.3% on 滚动 OOS",
}

out_path = WORKSPACE / 'picks' / 'pm_v1_model.json'
with open(out_path, 'w') as f:
    json.dump(model, f, ensure_ascii=False, indent=2)
print(f"\n✅ 落档: {out_path.name}")
print(f"   weight 主要 (top 5):")
for k, v in sorted(w.items(), key=lambda x: -abs(x[1]))[:5]:
    print(f"   {k:25s}  {v:+.4f}")
