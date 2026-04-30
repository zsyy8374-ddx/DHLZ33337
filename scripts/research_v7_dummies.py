"""实验 5: 把所有 4-30 启发的 dummy 直接加到 LR 里
让模型自己学权重 + L2 防过拟合
看 5 折是否更稳"""
import json, sys, math
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import normalize, train_lr, predict

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

def extract_v7(e):
    """v7: v4 + dummy 特征"""
    cb_pct = e.get("callback_pct", 0) or 0
    cb5_avg = e.get("cb5_main_avg", 0) or 0
    cb3_avg = e.get("cb3_main_avg", 0) or 0
    cb1 = e.get("cb1_main_avg", 0) or 0
    d0_main = e.get("d0_main_flow", 0) or 0
    pre_avg = e.get("pre_d0_5d_main_avg", 0) or 0
    lbc = e.get("d0_lbc", 1) or 1
    min_close = e.get("min_close_pct", 0) or 0
    
    return {
        "callback_pct": cb_pct,
        "min_close_pct": min_close,
        "lbc_num": lbc,
        "cb5_main_avg": cb5_avg,
        "cb3_main_avg": cb3_avg,
        "cb1_main_avg": cb1,
        "d0_main_flow": d0_main,
        "pre_d0_5d_main_avg": pre_avg,
        # 新 dummy
        "dummy_1plate_lowcb": 1 if (lbc == 1 and cb5_avg <= 1.5 and cb_pct >= 5) else 0,
        "dummy_high_concentrated": 1 if (lbc >= 2 and cb5_avg >= 2) else 0,  # 高位透支 (历史 88%)
        "dummy_d0_huge": 1 if d0_main >= 5 else 0,  # D0 巨量
        "dummy_d0_negative": 1 if d0_main < 0 else 0,  # D0 反流
        "dummy_callback_deep": 1 if cb_pct >= 12 else 0,  # 深度回调
    }

labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
features = [extract_v7(e) for e in events]
cont_keys = ["callback_pct","min_close_pct","lbc_num","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg"]

X, _, _ = normalize(features, cont_keys)
sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))

def auc(preds, lbls):
    paired = sorted(zip(preds, lbls), reverse=True)
    pos = sum(lbls); neg = len(lbls)-pos
    if pos==0 or neg==0: return 0.5
    rs = sum((len(lbls)-i) for i,(_,y) in enumerate(paired) if y==1)
    return (rs - pos*(pos+1)/2)/(pos*neg)

# v4 baseline (只用原始 8 特征)
from reversal_lr_v4 import extract_v4
features_v4 = [extract_v4(e) for e in events]
X_v4, _, _ = normalize(features_v4, cont_keys)

n = len(events)
print(f"\n📊 5 折 v0.4 (8 特征) vs v0.7 (8+5 dummy):")
print(f"{'Fold':<6} {'v4 AUC':>9} {'v7 AUC':>9} {'Δ':>8} {'v4 T10':>8} {'v7 T10':>8} {'v4 T20':>8} {'v7 T20':>8}")
print("-" * 75)
results = []
for fold in range(5):
    ts = int(n*(0.5+fold*0.1)); te = int(n*(0.6+fold*0.1))
    tr = [sorted_idx[i] for i in range(ts)]
    teid = [sorted_idx[i] for i in range(ts, te)]
    
    # v4
    Xtr_v4=[X_v4[i] for i in tr]; ytr=[labels[i] for i in tr]
    Xte_v4=[X_v4[i] for i in teid]; yte=[labels[i] for i in teid]
    w4,b4 = train_lr(Xtr_v4, ytr, lr=0.2, iters=500, l2=0.01)
    p_v4 = predict(Xte_v4, w4, b4)
    
    # v7
    Xtr_v7=[X[i] for i in tr]
    Xte_v7=[X[i] for i in teid]
    w7,b7 = train_lr(Xtr_v7, ytr, lr=0.2, iters=500, l2=0.01)
    p_v7 = predict(Xte_v7, w7, b7)
    
    a4=auc(p_v4,yte); a7=auc(p_v7,yte)
    r4=sorted(zip(p_v4,yte),reverse=True); r7=sorted(zip(p_v7,yte),reverse=True)
    t10_4 = sum(y for _,y in r4[:10])/10 if len(r4)>=10 else 0
    t10_7 = sum(y for _,y in r7[:10])/10 if len(r7)>=10 else 0
    t20_4 = sum(y for _,y in r4[:20])/20 if len(r4)>=20 else 0
    t20_7 = sum(y for _,y in r7[:20])/20 if len(r7)>=20 else 0
    
    results.append((a4,a7,t10_4,t10_7,t20_4,t20_7))
    print(f"{fold+1:<6} {a4:>9.4f} {a7:>9.4f} {a7-a4:>+8.4f} {t10_4*100:>6.0f}%  {t10_7*100:>6.0f}%  {t20_4*100:>6.0f}%  {t20_7*100:>6.0f}%")

avg = [sum(r[i] for r in results)/5 for i in range(6)]
print(f"\n  v0.4 平均 AUC {avg[0]:.4f}, T10 {avg[2]*100:.1f}%, T20 {avg[4]*100:.1f}%")
print(f"  v0.7 平均 AUC {avg[1]:.4f}, T10 {avg[3]*100:.1f}%, T20 {avg[5]*100:.1f}%")
print(f"  Δ:        AUC {avg[1]-avg[0]:+.4f},  T10 {(avg[3]-avg[2])*100:+.1f}pp,  T20 {(avg[5]-avg[4])*100:+.1f}pp")

# 最终模型用全部数据 train, 看 dummy 权重
all_indices = list(range(n))
Xall = X
yall = labels
w_full, b_full = train_lr(Xall, yall, lr=0.2, iters=500, l2=0.01)
print(f"\n📊 v0.7 最终 dummy 权重 (l2=0.01):")
for k in features[0].keys():
    if k.startswith("dummy"):
        print(f"   {k:<35} weight = {w_full.get(k, 0):+.4f}")
