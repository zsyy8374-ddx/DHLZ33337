"""实验 4: 4-30 启发的'低吸日'信号
规则: 1 板 + cb5 ≤ +1.5 亿 + callback ≥ 5%
对比 v0.4 LR
看历史 5 折是否稳定"""
import json, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import extract_v4, normalize, train_lr, predict

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

# 历史: 1板 + cb5 ≤ 1.5 + cb ≥ 5
print("📊 4-30 启发的'低吸日'规则历史命中:")
for cb_max in [0.5, 1.0, 1.5, 2.0]:
    sub = [e for e in events 
           if (e.get("d0_lbc",1) or 1) == 1 
           and (e.get("cb5_main_avg",0) or 0) <= cb_max
           and (e.get("callback_pct",0) or 0) >= 5]
    if not sub: continue
    rate = sum(1 for e in sub if e["outcome"]=="reversal")/len(sub)
    print(f"   1板 + cb5 ≤ {cb_max:.1f}亿 + callback ≥5%: n={len(sub):>4} 命中 {rate*100:.1f}%")

# 反指: ≥2 板 + cb5 ≥ 2 亿 (4-30 翻车特征)
print(f"\n📊 4-30 翻车特征历史命中:")
sub = [e for e in events 
       if (e.get("d0_lbc",1) or 1) >= 2 
       and (e.get("cb5_main_avg",0) or 0) >= 2]
if sub:
    rate = sum(1 for e in sub if e["outcome"]=="reversal")/len(sub)
    print(f"   ≥2板 + cb5 ≥2亿: n={len(sub):>4} 命中 {rate*100:.1f}%")

# 加入 boost 5 折验证
labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
features = [extract_v4(e) for e in events]
cont_keys = ["callback_pct","min_close_pct","lbc_num","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg"]
X, _, _ = normalize(features, cont_keys)
sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))

def auc(preds, lbls):
    paired = sorted(zip(preds, lbls), reverse=True)
    pos = sum(lbls); neg = len(lbls)-pos
    if pos==0 or neg==0: return 0.5
    rs = sum((len(lbls)-i) for i,(_,y) in enumerate(paired) if y==1)
    return (rs - pos*(pos+1)/2)/(pos*neg)

def boost(e):
    """组合 boost: 低吸 +0.05, 高位透支 -0.05"""
    boost = 0
    lbc = e.get("d0_lbc",1) or 1
    cb5 = e.get("cb5_main_avg",0) or 0
    cb_pct = e.get("callback_pct",0) or 0
    
    # 低吸 +0.05
    if lbc == 1 and cb5 <= 1.5 and cb_pct >= 5:
        boost += 0.05
    # 高位透支 -0.05
    if lbc >= 2 and cb5 >= 2:
        boost -= 0.05
    return boost

n = len(events)
print(f"\n📊 5 折 (低吸+0.05/透支-0.05) boost:")
print(f"{'Fold':<6} {'base AUC':>10} {'boost AUC':>10} {'ΔAUC':>9} {'base T10':>10} {'boost T10':>10} {'ΔT10':>7} {'base T20':>10} {'boost T20':>10}")
print("-" * 100)
results = []
for fold in range(5):
    ts = int(n*(0.5+fold*0.1)); te = int(n*(0.6+fold*0.1))
    tr = [sorted_idx[i] for i in range(ts)]
    teid = [sorted_idx[i] for i in range(ts, te)]
    Xtr=[X[i] for i in tr]; ytr=[labels[i] for i in tr]
    Xte=[X[i] for i in teid]; yte=[labels[i] for i in teid]
    w,b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
    base = predict(Xte, w, b)
    boosted = [max(0.01, min(0.99, p + boost(events[idx]))) for p,idx in zip(base, teid)]
    a0=auc(base,yte); a1=auc(boosted,yte)
    r0=sorted(zip(base,yte),reverse=True); r1=sorted(zip(boosted,yte),reverse=True)
    t10_0 = sum(y for _,y in r0[:10])/10 if len(r0)>=10 else 0
    t10_1 = sum(y for _,y in r1[:10])/10 if len(r1)>=10 else 0
    t20_0 = sum(y for _,y in r0[:20])/20 if len(r0)>=20 else 0
    t20_1 = sum(y for _,y in r1[:20])/20 if len(r1)>=20 else 0
    results.append((a0,a1,t10_0,t10_1,t20_0,t20_1))
    print(f"{fold+1:<6} {a0:>10.4f} {a1:>10.4f} {a1-a0:>+9.4f} {t10_0*100:>8.0f}%   {t10_1*100:>8.0f}%   {(t10_1-t10_0)*100:>+5.0f}% {t20_0*100:>8.0f}%   {t20_1*100:>8.0f}%")

avg = [sum(r[i] for r in results)/5 for i in range(6)]
print(f"\n  平均: AUC {avg[0]:.4f} → {avg[1]:.4f} ({avg[1]-avg[0]:+.4f})")
print(f"        T10  {avg[2]*100:.1f}% → {avg[3]*100:.1f}% ({(avg[3]-avg[2])*100:+.1f}pp)")
print(f"        T20  {avg[4]*100:.1f}% → {avg[5]*100:.1f}% ({(avg[5]-avg[4])*100:+.1f}pp)")
