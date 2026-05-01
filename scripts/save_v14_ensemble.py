"""保存 v1.4 集成模型 (0.6 LR + 0.4 GBDT)
- LR: 全量训
- GBDT: 全量训, 100 棵 d=3
- 推送时: p_ens = 0.6 * p_lr + 0.4 * p_gbdt
- 阈值用 5 折 OOS 校准
"""
import json, sys, math, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11
from mini_gbdt import train_gbdt, predict_gbdt, auc

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

features = [extract_v11(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
feat_names = list(features[0].keys())
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]

# 1. 全量训 LR
print("训 LR 全量...")
X_all, mu_all, sd_all = normalize(features, cont_keys)
w_all, b_all = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)

# 2. 全量训 GBDT
print("训 GBDT 全量 (100 棵 d=3, 这要 ~10 秒)...")
t0 = time.time()
gbdt_model = train_gbdt(features, labels, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
print(f"  {time.time()-t0:.1f}s")

# 3. 5 折时序 OOS 校准阈值 (用集成概率)
print("5 折时序 OOS 校准阈值...")
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
fold_size = N // 5
all_p_ens = []
all_y = []
for fold in range(5):
    test_start = fold * fold_size
    test_end = (fold + 1) * fold_size if fold < 4 else N
    test_idx = sorted_idx[test_start:test_end]
    train_idx_f = sorted_idx[:test_start] + sorted_idx[test_end:]
    if not train_idx_f or not test_idx: continue
    
    Xtr_r = [features[i] for i in train_idx_f]
    y_tr = [labels[i] for i in train_idx_f]
    Xte_r = [features[i] for i in test_idx]
    y_te = [labels[i] for i in test_idx]
    
    Xtr_n, mu_f, sd_f = normalize(Xtr_r, cont_keys)
    w_f, b_f = train_lr(Xtr_n, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n = [{k: ((v-mu_f[k])/sd_f[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r]
    p_lr_f = predict(Xte_n, w_f, b_f)
    
    gbdt_f = train_gbdt(Xtr_r, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb_f = predict_gbdt(gbdt_f, Xte_r)
    
    p_ens = [0.6*a + 0.4*b for a,b in zip(p_lr_f, p_gb_f)]
    all_p_ens.extend(p_ens)
    all_y.extend(y_te)
    print(f"  fold {fold+1}: AUC LR={auc(p_lr_f, y_te):.3f}, GBDT={auc(p_gb_f, y_te):.3f}, ENS={auc(p_ens, y_te):.3f}")

# 找 P>=0.7 真实命中率
paired = sorted(zip(all_p_ens, all_y), reverse=True)
total_ens_auc = auc(all_p_ens, all_y)
print(f"\n5 折 pooled OOS AUC (集成): {total_ens_auc:.4f}")

# 阈值: 找命中 >= 85% 和 >= 70% 的边界
def find_threshold(paired, target_hit):
    cum_y = 0
    for k, (p, y) in enumerate(paired):
        cum_y += y
        rate = cum_y / (k+1)
        if k >= 30 and rate < target_hit:
            return paired[k-1][0], k, cum_y - 1, (cum_y-1)/(k)
    return paired[-1][0], len(paired), cum_y, cum_y/len(paired)

p_hi, n_hi, hits_hi, rate_hi = find_threshold(paired, 0.85)
p_mid, n_mid, hits_mid, rate_mid = find_threshold(paired, 0.70)
print(f"\nP_high (85% 命中) = {p_hi:.3f}, n={n_hi}, hits={hits_hi}, 实测率={rate_hi*100:.1f}%")
print(f"P_mid  (70% 命中) = {p_mid:.3f}, n={n_mid}, hits={hits_mid}, 实测率={rate_mid*100:.1f}%")

# 简化: 直接定 0.6 / 0.45 然后看实际命中
for thr in [0.50, 0.55, 0.60, 0.65, 0.70]:
    sub = [(p, y) for p, y in paired if p >= thr]
    if not sub: continue
    rate = sum(y for _, y in sub) / len(sub)
    print(f"  P>={thr}: n={len(sub)}, 命中率={rate*100:.1f}%")

# 4. 落档
out = {
    "version": "v1.4-ensemble",
    "data_basis": "3262 enriched events (含资金流) + recent_rev_rate",
    "ensemble": "0.6 * LR_v1.1 + 0.4 * GBDT(100 trees, depth 3)",
    "n_events": len(events),
    "reversal_rate": sum(labels)/len(labels),
    
    # LR 部分
    "lr_features": feat_names,
    "lr_cont_keys": cont_keys,
    "lr_feature_means": mu_all,
    "lr_feature_stds": sd_all,
    "lr_weights": w_all,
    "lr_bias": b_all,
    
    # GBDT 部分: 序列化 trees
    "gbdt_base": gbdt_model[0],
    "gbdt_lr": gbdt_model[2],
    "gbdt_trees": gbdt_model[1],
    
    # 集成权重
    "lr_weight": 0.6,
    "gbdt_weight": 0.4,
    
    # 阈值 (基于 5-fold OOS pooled)
    "P_high": 0.6,
    "P_mid": 0.45,
    
    # 滚动 OOS 性能 (来自 ensemble_v14.py)
    "rolling_oos": {
        "auc_avg": 0.787,
        "t20_avg": 0.906,
        "p_high_hit_avg": 0.926,
        "p_high_n_avg": 22.6,
        "months_validated": 9
    }
}

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v14_ensemble_model.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=lambda o: float(o) if hasattr(o, '__float__') else str(o))

import os
size_kb = os.path.getsize('/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v14_ensemble_model.json') / 1024
print(f"\n✅ 落档: picks/lr_v14_ensemble_model.json ({size_kb:.0f} KB)")
