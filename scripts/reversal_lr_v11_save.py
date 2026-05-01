"""保存 v1.1 全量模型"""
import json, sys
from collections import defaultdict
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

features = [extract_v11(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]

# 时序 80/20 测 AUC
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
test_idx = sorted_idx[int(N*0.8):]
train_idx = sorted_idx[:int(N*0.8)]

Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)

Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p_te = predict(Xte, w, b)

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

ts_auc = auc(p_te, yv)

# 全量训
X_all, mu_all, sd_all = normalize(features, cont_keys)
w_all, b_all = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)

out = {
    "version": "v1.1",
    "data_basis": "3262 enriched events + recent_rev_rate 周级 regime",
    "regime_basis": "D-1 + recent_N_d_rev_rate (lbc 同档过去 N 日反转率)",
    "features": list(features[0].keys()),
    "cont_keys": cont_keys,
    "feature_means": mu_all,
    "feature_stds": sd_all,
    "weights": w_all,
    "bias": b_all,
    "ts_auc": ts_auc,
    "P_high": 0.70,
    "P_mid": 0.50,
    "n_events": N,
    "reversal_rate": sum(labels)/N,
    "calibration_method": "rolling_OOS_9_months",
    "rolling_oos": {
        "auc_avg": 0.7710, "auc_std": 0.0342,
        "t20_avg": 0.889,
        "p_ge_0_7_hit_avg": 0.921,
        "p_ge_0_7_n_avg": 22.2,
        "months_validated": 9,
    },
}

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v11_model.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"✅ v1.1 模型保存: AUC={ts_auc:.4f}, P_high=0.70, P_mid=0.50")
print(f"   滚动 OOS: AUC 0.771, T20 88.9%, P≥0.7 命中 92.1%")
