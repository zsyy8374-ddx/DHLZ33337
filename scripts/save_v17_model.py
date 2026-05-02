"""保存 v1.7 集成模型 (LR + GBDT, AUC 0.872 / T20 97.5%)
- 用 v12 数据 (含 pm + d0zt)
- 仅在 has_pm AND has_d0zt 的事件上训练 (1346)
- 输出: picks/lr_v17_ensemble_model.json
"""
import json, sys, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from pathlib import Path
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v17_with_pm_d0zt import extract_v17
from mini_gbdt import train_gbdt, predict_gbdt

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WORKSPACE / 'backtest' / 'reversal-events-2026-05-01-v12-with-pm-d0zt.json') as f:
    events = json.load(f)['events']

valid = [e for e in events if 'pm_open_pct' in e and 'd0_zt_lock_pct' in e]
print(f"valid events: {len(valid)}")

features = [extract_v17(e) for e in valid]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in valid]
feat_names = list(features[0].keys())

cont_keys = [
    "callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
    "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
    "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate",
    "pm_open_pct","pm_5m_high_pct","pm_5m_close_pct","pm_10m_high_pct","pm_5m_amt_yi",
    "d0_zt_lock_pct","d0_zt_after_amt_yi","d0_zt_after_amt_pct","d0_zt_lock_strength",
]

X_norm, mu, sd = normalize(features, cont_keys)
w, b = train_lr(X_norm, labels, lr=0.1, iters=500, l2=0.01)
gbdt = train_gbdt(features, labels, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)


def predict_ens(f):
    f_norm = {k:((v-mu[k])/sd[k] if k in cont_keys else v) for k,v in f.items()}
    z = b
    for k, v in f_norm.items(): z += w.get(k, 0) * v
    import math
    p_lr = 1 / (1 + math.exp(-z))
    p_gb = predict_gbdt(gbdt, [f])[0]
    return 0.6 * p_lr + 0.4 * p_gb


# OOS 校准 (用最近 2 个月)
test_idx = [i for i, e in enumerate(valid) if e['d0_date'][:7] >= '2026-03']
train_idx = [i for i, e in enumerate(valid) if e['d0_date'][:7] < '2026-03']
print(f"\n训 {len(train_idx)} | OOS {len(test_idx)}")

if len(train_idx) >= 100:
    Xtr = [features[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [features[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    Xtr_n, mu_tr, sd_tr = normalize(Xtr, cont_keys)
    w_tr, b_tr = train_lr(Xtr_n, ytr, lr=0.1, iters=500, l2=0.01)
    gbdt_tr = train_gbdt(Xtr, ytr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    
    Xte_n = [{k:((v-mu_tr[k])/sd_tr[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte]
    p_lr = predict(Xte_n, w_tr, b_tr)
    p_gb = predict_gbdt(gbdt_tr, Xte)
    p_te = [0.6*a + 0.4*b for a,b in zip(p_lr, p_gb)]
    
    print(f"\n=== OOS 校准 ===")
    for thr in [0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5, 0.45]:
        above = [(p, y) for p, y in zip(p_te, yte) if p >= thr]
        if len(above) < 5: continue
        hit = sum(y for _, y in above) / len(above)
        print(f"  P>={thr:.2f}: n={len(above)}, 命中率 {hit*100:.1f}%")
    
    P_high = 0.85
    P_mid = 0.7

# 全量训完保存
import math
def predict_lr_only(features_list):
    out = []
    for f in features_list:
        f_norm = {k:((v-mu[k])/sd[k] if k in cont_keys else v) for k,v in f.items()}
        z = b
        for k, v in f_norm.items(): z += w.get(k, 0) * v
        out.append(1 / (1 + math.exp(-z)))
    return out

# AUC, T20 from 滚动 OOS in lr_v17_with_pm_d0zt: AUC=0.872 T20=97.5%
model = {
    "version": "v1.7-ensemble-pm-d0zt",
    "trained_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    "n_train": len(features),
    "weights": w,
    "bias": b,
    "feature_means": mu,
    "feature_stds": sd,
    "cont_keys": cont_keys,
    "feature_names": feat_names,
    "lr_weight": 0.6,
    "gbdt_weight": 0.4,
    "gbdt": gbdt,  # 保存树结构
    "P_high": 0.85,
    "P_mid": 0.7,
    "ts_auc": 0.872,
    "top10_hit": 0.975,
    "purpose": "v1.7 集成: v1.4 + pm + d0zt, AUC 0.872 / T20 97.5%",
}

out_path = WORKSPACE / 'picks' / 'lr_v17_ensemble_model.json'
with open(out_path, 'w') as f:
    json.dump(model, f, ensure_ascii=False)
print(f"\n✅ 落档: {out_path.name}")
print(f"   trees: {len(gbdt)} 棵, weights: {len(w)} 个")
print(f"   AUC=0.872, T20=97.5%, P_high=0.85, P_mid=0.7")
