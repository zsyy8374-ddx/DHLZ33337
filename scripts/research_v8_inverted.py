"""实验 10 (v0.8 思路): 翻转 cb5_main_avg 在浅回调时的方向

4-30 实战教训:
- 翻车 6 只: callback 2-7%, cb5 +0.3~+7亿 (主力还在阻击)
- 涨停 18 只: callback 5-18%, cb5 -3~+1.4亿 (主力洗盘)

假设: 短期反转 = 主力洗盘到位 = 浅回调 + cb5 大正 = 反指
"""
import json, sys, math
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import train_lr, predict, sigmoid

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

def normalize_dicts(features, keys):
    """归一化 list of dict 中的 keys 字段"""
    n = len(features)
    mu = {}
    sd = {}
    for k in keys:
        vals = [f[k] for f in features]
        mu[k] = sum(vals) / n
        sd[k] = math.sqrt(sum((v - mu[k])**2 for v in vals) / n) or 1.0
    out = []
    for f in features:
        d = dict(f)
        for k in keys:
            d[k] = (f[k] - mu[k]) / sd[k]
        out.append(d)
    return out, mu, sd

def extract_v4(e):
    return {
        "callback_pct": e.get("callback_pct", 0) or 0,
        "min_close_pct": e.get("min_close_pct", 0) or 0,
        "lbc_num": e.get("d0_lbc", 1) or 1,
        "cb5_main_avg": e.get("cb5_main_avg", 0) or 0,
        "cb3_main_avg": e.get("cb3_main_avg", 0) or 0,
        "cb1_main_avg": e.get("cb1_main_avg", 0) or 0,
        "d0_main_flow": e.get("d0_main_flow", 0) or 0,
        "pre_d0_5d_main_avg": e.get("pre_d0_5d_main_avg", 0) or 0,
    }

def extract_v8(e):
    cb_pct = e.get("callback_pct", 0) or 0
    cb5 = e.get("cb5_main_avg", 0) or 0
    cb3 = e.get("cb3_main_avg", 0) or 0
    cb1 = e.get("cb1_main_avg", 0) or 0
    d0 = e.get("d0_main_flow", 0) or 0
    pre = e.get("pre_d0_5d_main_avg", 0) or 0
    lbc = e.get("d0_lbc", 1) or 1
    mc = e.get("min_close_pct", 0) or 0
    return {
        "callback_pct": cb_pct,
        "min_close_pct": mc,
        "lbc_num": lbc,
        "cb5_x_callback": cb5 * cb_pct,
        "cb3_main_avg": cb3,
        "cb1_main_avg": cb1,
        "d0_main_flow": d0,
        "pre_d0_5d_main_avg": pre,
        "trap_high_shallow": float(1 if (lbc >= 2 and cb_pct < 5 and cb5 > 1) else 0),
        "low_absorb": float(1 if (lbc == 1 and 5 <= cb_pct <= 12 and -1 <= cb5 <= 1) else 0),
    }

labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
features_v4 = [extract_v4(e) for e in events]
features_v8 = [extract_v8(e) for e in events]
v4_keys = list(features_v4[0].keys())
v8_cont_keys = ["callback_pct","min_close_pct","lbc_num","cb5_x_callback","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg"]

X_v4, _, _ = normalize_dicts(features_v4, v4_keys)
X_v8, _, _ = normalize_dicts(features_v8, v8_cont_keys)

sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))

def auc_simple(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

def topn_hit(scores, ys, n):
    paired = sorted(zip(scores, ys), reverse=True)[:n]
    return sum(y for _, y in paired) / max(1, len(paired))

K = 5
fold_size = len(events) // K
v4_aucs, v8_aucs = [], []
v4_t10s, v8_t10s = [], []
v4_t20s, v8_t20s = [], []

print("📊 5 折 CV (v0.4 vs v0.8 反向):")
print(f"{'Fold':<6}{'v4 AUC':>10}{'v8 AUC':>10}{'ΔAUC':>10}{'v4 T10':>9}{'v8 T10':>9}{'v4 T20':>9}{'v8 T20':>9}")
print("-"*75)

for k in range(K):
    test_start = k * fold_size
    test_end = test_start + fold_size if k < K-1 else len(events)
    test_idx = set(sorted_idx[test_start:test_end])
    train_idx = [i for i in sorted_idx if i not in test_idx]
    test_idx = list(test_idx)
    
    Xtr4 = [X_v4[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte4 = [X_v4[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    Xtr8 = [X_v8[i] for i in train_idx]; Xte8 = [X_v8[i] for i in test_idx]
    
    w4, b4 = train_lr(Xtr4, ytr, lr=0.1, iters=300, l2=0.01)
    w8, b8 = train_lr(Xtr8, ytr, lr=0.1, iters=300, l2=0.01)
    
    pre4 = predict(Xte4, w4, b4)
    pre8 = predict(Xte8, w8, b8)
    
    a4 = auc_simple(pre4, yte); a8 = auc_simple(pre8, yte)
    t4_10 = topn_hit(pre4, yte, 10); t8_10 = topn_hit(pre8, yte, 10)
    t4_20 = topn_hit(pre4, yte, 20); t8_20 = topn_hit(pre8, yte, 20)
    v4_aucs.append(a4); v8_aucs.append(a8)
    v4_t10s.append(t4_10); v8_t10s.append(t8_10)
    v4_t20s.append(t4_20); v8_t20s.append(t8_20)
    print(f"{k+1:<6}{a4:>10.4f}{a8:>10.4f}{a8-a4:>+10.4f}{int(t4_10*100):>8}%{int(t8_10*100):>8}%{int(t4_20*100):>8}%{int(t8_20*100):>8}%")

avg = lambda l: sum(l)/len(l)
print(f"\n  v4 平均: AUC {avg(v4_aucs):.4f}, T10 {avg(v4_t10s)*100:.1f}%, T20 {avg(v4_t20s)*100:.1f}%")
print(f"  v8 平均: AUC {avg(v8_aucs):.4f}, T10 {avg(v8_t10s)*100:.1f}%, T20 {avg(v8_t20s)*100:.1f}%")
print(f"  Δ:       AUC {avg(v8_aucs)-avg(v4_aucs):+.4f}, T10 {(avg(v8_t10s)-avg(v4_t10s))*100:+.1f}pp, T20 {(avg(v8_t20s)-avg(v4_t20s))*100:+.1f}pp")

w_full, b_full = train_lr(X_v8, labels, lr=0.1, iters=500, l2=0.01)
print(f"\n📊 v0.8 关键特征系数 (全样本):")
all_keys = v8_cont_keys + ["trap_high_shallow", "low_absorb"]
for k in all_keys:
    w = w_full[k]
    arrow = "↑" if w > 0 else "↓"
    print(f"   {k:<28} {w:+.4f} {arrow}")
print(f"   bias                         {b_full:+.4f}")
