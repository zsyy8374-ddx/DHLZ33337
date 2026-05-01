"""v0.8 LR 模型: 全量训练 + OOS 阈值校准 + 保存"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v8_with_interactions import extract_v8

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json') as f:
    events = json.load(f)['events']

features = [extract_v8(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]

# 时序分: 80% 训练 20% 测试 (按 d0_date)
sorted_events = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_events]
N = len(events)
test_idx = sorted_idx[int(N*0.8):]
train_idx = sorted_idx[:int(N*0.8)]
print(f"📊 时序拆分: 训 {len(train_idx)}, 测 {len(test_idx)}")

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]

# 训
Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)

# 测
Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p_te = predict(Xte, w, b)

# AUC
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

# 全量重训 (用全数据落生产模型)
X_all_raw = features
X_all, mu_all, sd_all = normalize(X_all_raw, cont_keys)
w_all, b_all = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)

# OOS 阈值校准 (基于时序 OOS)
sorted_pte = sorted(zip(p_te, yv), reverse=True)
thresholds = {}
for n in [10, 20, 30, 50, 80, 100, 150]:
    if len(sorted_pte) < n: continue
    sub = sorted_pte[:n]
    hit = sum(y for _, y in sub) / n
    p_thr = sub[-1][0]
    thresholds[n] = (p_thr, hit)
    print(f"   Top {n}: 命中 {hit*100:.1f}%, P 阈值 ≈ {p_thr:.3f}")

# 找 ≥85% 的最大 N
P_high = 0.85
for n in [150, 100, 80, 50, 30]:
    if n in thresholds and thresholds[n][1] >= 0.85:
        # 用反推: 找命中 ≥85% 的最低 P
        cumhit = 0
        for i, (p, y) in enumerate(sorted_pte[:n]):
            cumhit += y
            if cumhit / (i+1) >= 0.85:
                P_high = p
        break

P_mid = 0.70
for n in [200, 150, 100]:
    if n in thresholds and thresholds[n][1] >= 0.70:
        cumhit = 0
        for i, (p, y) in enumerate(sorted_pte[:n]):
            cumhit += y
            if cumhit / (i+1) >= 0.70:
                P_mid = p
        break

# 写最终模型
keys = list(features[0].keys())
all_cont_keys = [k for k in cont_keys if k in keys]
out = {
    "version": "v0.8",
    "regime_basis": "D-1 (推送日, 不泄漏)",
    "features": keys,
    "cont_keys": all_cont_keys,
    "feature_means": mu_all,
    "feature_stds": sd_all,
    "weights": w_all,
    "bias": b_all,
    "ts_auc": ts_auc,
    "P_high": P_high,
    "P_mid": P_mid,
    "calibration_method": "OOS_top_N",
}
print(f"\n✅ v0.8 模型: 时序 OOS AUC={ts_auc:.4f}, P_high={P_high:.3f}, P_mid={P_mid:.3f}")

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v8_model.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# 写权重 Top
print(f"\n📊 v0.8 全量权重 Top 25:")
for k, v in sorted(w_all.items(), key=lambda x: -abs(x[1]))[:25]:
    sign = "↑" if v > 0 else "↓"
    print(f"   {k:<26} {v:+.4f} {sign}")
