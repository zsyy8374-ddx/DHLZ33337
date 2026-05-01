"""v1.3 实验: GBDT vs LR 对照
- 同一份 v1.1 特征 (40 维, 含 recent_rev_rate)
- 同一份 3262 events
- 同一份滚动 OOS (按月)
- 比较 AUC, T20 命中, P_high 命中
"""
import json, sys, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11
from mini_gbdt import train_gbdt, predict_gbdt, auc

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

features = [extract_v11(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
feat_names = list(features[0].keys())
print(f"📊 数据: {len(events)} 事件, 特征 {len(feat_names)} 维, 反转率 {sum(labels)/len(labels)*100:.1f}%")

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]


def eval_oos(p_te, y_te, label, n_p_high=20):
    paired = sorted(zip(p_te, y_te), reverse=True)
    auc_v = auc(p_te, y_te)
    t10 = sum(y for _, y in paired[:10]) / min(10, len(paired))
    t20 = sum(y for _, y in paired[:20]) / min(20, len(paired))
    t50 = sum(y for _, y in paired[:50]) / min(50, len(paired))
    high_n = sum(1 for p,_ in paired if p >= 0.7)
    high_hit = sum(y for p,y in paired if p >= 0.7) / max(1, high_n)
    print(f"  {label}  AUC={auc_v:.3f}  T10={t10*100:.0f}%  T20={t20*100:.0f}%  T50={t50*100:.0f}%  P>=0.7 n={high_n} hit={high_hit*100:.0f}%")
    return {"auc": auc_v, "t20": t20, "p_high_hit": high_hit, "p_high_n": high_n}


# === 1. 时序 80/20 OOS 总比 ===
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
test_idx = sorted_idx[int(N*0.8):]
train_idx = sorted_idx[:int(N*0.8)]

print(f"\n=== 时序 80/20 OOS (训 {len(train_idx)}, 测 {len(test_idx)}) ===")

# LR
Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)
Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p_lr = predict(Xte, w, b)
eval_oos(p_lr, yv, "LR v1.1 ")

# GBDT
print("  训 GBDT (100 棵 depth=3)...", end=" ", flush=True)
t0 = time.time()
Xtr_g = [features[i] for i in train_idx]
y_tr_g = [labels[i] for i in train_idx]
gbdt_model = train_gbdt(Xtr_g, y_tr_g, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8)
print(f"{time.time()-t0:.1f}s")
p_gbdt = predict_gbdt(gbdt_model, Xte_raw)
eval_oos(p_gbdt, yv, "GBDT-100 ")

# GBDT 深一点
print("  训 GBDT (200 棵 depth=4)...", end=" ", flush=True)
t0 = time.time()
gbdt_model2 = train_gbdt(Xtr_g, y_tr_g, feat_names, n_trees=200, max_depth=4, lr=0.05, lambda_reg=1.0, min_leaf=20, subsample=0.8)
print(f"{time.time()-t0:.1f}s")
p_gbdt2 = predict_gbdt(gbdt_model2, Xte_raw)
eval_oos(p_gbdt2, yv, "GBDT-200d4")


# === 2. 滚动 OOS (按月) ===
print("\n=== 滚动 OOS (按月) GBDT-100 d=3 ===")
months = sorted(set(e['d0_date'][:7] for e in events))
gbdt_aucs, gbdt_t20, gbdt_high_hit, gbdt_high_n = [], [], [], []
lr_aucs, lr_t20, lr_high_hit, lr_high_n = [], [], [], []

for m in months[6:]:
    tr_i = [i for i, e in enumerate(events) if e['d0_date'][:7] < m]
    te_i = [i for i, e in enumerate(events) if e['d0_date'][:7] == m]
    if len(tr_i) < 100 or len(te_i) < 30: continue
    
    Xtr_r = [features[i] for i in tr_i]
    y_tr = [labels[i] for i in tr_i]
    Xte_r = [features[i] for i in te_i]
    y_te = [labels[i] for i in te_i]
    
    # LR
    Xtr_n, mu_m, sd_m = normalize(Xtr_r, cont_keys)
    w_m, b_m = train_lr(Xtr_n, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n = [{k: ((v-mu_m[k])/sd_m[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r]
    p_lr = predict(Xte_n, w_m, b_m)
    paired_lr = sorted(zip(p_lr, y_te), reverse=True)
    lr_aucs.append(auc(p_lr, y_te))
    lr_t20.append(sum(y for _,y in paired_lr[:20]) / min(20, len(paired_lr)))
    nh_lr = sum(1 for p,_ in paired_lr if p>=0.7)
    lr_high_hit.append(sum(y for p,y in paired_lr if p>=0.7) / max(1, nh_lr))
    lr_high_n.append(nh_lr)
    
    # GBDT
    gbdt_m = train_gbdt(Xtr_r, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb = predict_gbdt(gbdt_m, Xte_r)
    paired_gb = sorted(zip(p_gb, y_te), reverse=True)
    gbdt_aucs.append(auc(p_gb, y_te))
    gbdt_t20.append(sum(y for _,y in paired_gb[:20]) / min(20, len(paired_gb)))
    nh_gb = sum(1 for p,_ in paired_gb if p>=0.7)
    gbdt_high_hit.append(sum(y for p,y in paired_gb if p>=0.7) / max(1, nh_gb))
    gbdt_high_n.append(nh_gb)
    
    print(f"  {m} n={len(te_i):>3}  LR: AUC={lr_aucs[-1]:.3f} T20={lr_t20[-1]*100:.0f}% P>=0.7 {nh_lr:>2}/{lr_high_hit[-1]*100:.0f}%  | "
          f"GBDT: AUC={gbdt_aucs[-1]:.3f} T20={gbdt_t20[-1]*100:.0f}% P>=0.7 {nh_gb:>2}/{gbdt_high_hit[-1]*100:.0f}%")

if lr_aucs:
    print(f"\n  LR 平均  : AUC={sum(lr_aucs)/len(lr_aucs):.3f} T20={sum(lr_t20)/len(lr_t20)*100:.1f}% P>=0.7命中={sum(lr_high_hit)/len(lr_high_hit)*100:.1f}% n={sum(lr_high_n)/len(lr_high_n):.1f}")
    print(f"  GBDT 平均: AUC={sum(gbdt_aucs)/len(gbdt_aucs):.3f} T20={sum(gbdt_t20)/len(gbdt_t20)*100:.1f}% P>=0.7命中={sum(gbdt_high_hit)/len(gbdt_high_hit)*100:.1f}% n={sum(gbdt_high_n)/len(gbdt_high_n):.1f}")
