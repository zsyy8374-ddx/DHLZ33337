"""v0.5 模型 OOS 阈值重校准 - 用 5 fold CV 的 OOS 预测做校准"""
import json, math, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import sigmoid, normalize, train_lr, predict
from reversal_lr_v5 import extract_v5, detect_regime, get_eval_date, load_index_data

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

idx_by_date, sorted_dates = load_index_data()
event_regimes = [detect_regime(idx_by_date, get_eval_date(e, sorted_dates) or "") for e in events]

features = [extract_v5(e, event_regimes[i]) for i, e in enumerate(events)]
labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]

# 5 fold CV: 收集 OOS 预测
sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
K = 5
fold_size = len(events) // K

oos_preds = [0.0] * len(events)  # 各 fold 的 OOS 预测

for k in range(K):
    test_start = k * fold_size
    test_end = test_start + fold_size if k < K-1 else len(events)
    test_set = set(sorted_idx[test_start:test_end])
    train_idx = [i for i in sorted_idx if i not in test_set]
    test_idx = list(test_set)
    
    Xtr_raw = [features[i] for i in train_idx]
    Xte_raw = [features[i] for i in test_idx]
    Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
    Xte = []
    for f in Xte_raw:
        nf = {kk: ((v - mu[kk])/sd[kk] if kk in cont_keys else v) for kk, v in f.items()}
        Xte.append(nf)
    yt = [labels[i] for i in train_idx]
    w, b = train_lr(Xtr, yt, lr=0.2, iters=500, l2=0.01)
    pre = predict(Xte, w, b)
    for j, p in zip(test_idx, pre):
        oos_preds[j] = p

# OOS 整体 AUC
def auc(y_true, y_pred):
    paired = sorted(zip(y_pred, y_true), reverse=True)
    pos = sum(y_true); neg = len(y_true) - pos
    if pos == 0 or neg == 0: return 0.5
    s = 0; tp = 0
    for _, yi in paired:
        if yi == 1: tp += 1
        else: s += tp
    return s / (pos * neg)

oos_auc = auc(labels, oos_preds)
print(f"📊 OOS AUC (5 fold pooled): {oos_auc:.4f}")

# OOS 校准 P 阈值
paired = sorted(zip(oos_preds, labels), reverse=True)
print(f"\n📊 OOS Top N 命中率:")
for n in [10, 20, 30, 50, 80, 100, 150]:
    hits = sum(yi for _, yi in paired[:n])
    print(f"   Top {n:>3}:  命中 {hits}/{n} = {hits/n*100:.1f}%, 此时 P 阈值 ≈ {paired[n-1][0]:.3f}")

# 找 ≥85% 命中率的 P 阈值
P_high_oos = None
n_pos = 0
for i, (p, yi) in enumerate(paired):
    n_pos += yi
    if i+1 >= 30 and n_pos/(i+1) >= 0.85 and P_high_oos is None:
        P_high_oos = round(p, 3)
        n_high = i+1
print(f"\n🎚️ OOS 阈值 (前 ≥30 且命中率 ≥85%): P_high = {P_high_oos}, 候选数 {n_high}")

# 找 ≥70% 命中率
P_mid_oos = None
n_pos = 0
for i, (p, yi) in enumerate(paired):
    n_pos += yi
    if i+1 >= 50 and n_pos/(i+1) >= 0.70 and P_mid_oos is None:
        P_mid_oos = round(p, 3)
        n_mid = i+1
print(f"🎚️ OOS 阈值 (前 ≥50 且命中率 ≥70%): P_mid = {P_mid_oos}, 候选数 {n_mid}")

# 更新模型文件的阈值
import json as j
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v5_model.json") as f:
    model = j.load(f)
print(f"\n📋 原 (in-sample) 阈值: P_high={model['P_high']}, P_mid={model['P_mid']}")
model["P_high"] = P_high_oos
model["P_mid"] = P_mid_oos
model["calibration_method"] = "OOS_5fold_pooled"
model["oos_auc"] = oos_auc
with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v5_model.json", "w") as f:
    j.dump(model, f, ensure_ascii=False, indent=2)
print(f"✅ 模型阈值已更新为 OOS 校准: P_high={P_high_oos}, P_mid={P_mid_oos}")
