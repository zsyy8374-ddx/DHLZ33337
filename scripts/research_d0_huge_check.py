"""实验 1: D0 主力 ≥5 亿反指 dummy 严谨 5 折验证"""
import json, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import extract_v4, normalize, train_lr, predict

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

print("📊 历史分箱: D0 主力 大额")
for lo, hi in [(0,1),(1,2),(2,3),(3,5),(5,10),(10,99)]:
    sub = [e for e in events if lo <= (e.get("d0_main_flow",0) or 0) < hi]
    if not sub: continue
    rate = sum(1 for e in sub if e["outcome"]=="reversal")/len(sub)
    print(f"   [{lo:>2},{hi:>2}): n={len(sub):>3}  命中 {rate*100:>5.1f}%")

big = [e for e in events if (e.get("d0_main_flow",0) or 0) >= 5]
small = [e for e in events if (e.get("d0_main_flow",0) or 0) < 5]
print(f"\n   ≥5亿: n={len(big)} 命中 {sum(1 for e in big if e['outcome']=='reversal')/len(big)*100:.1f}%")
print(f"   <5亿: n={len(small)} 命中 {sum(1 for e in small if e['outcome']=='reversal')/len(small)*100:.1f}%")

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

def boost_d0big(e, level):
    if (e.get("d0_main_flow",0) or 0) >= 5:
        return -level
    return 0

n = len(events)
print(f"\n📊 5 折滚动: D0 主力 ≥5亿 减分 boost")
for level in [0.05, 0.08, 0.10, 0.12, 0.15]:
    deltas_auc = []; deltas_t10 = []; deltas_t20 = []
    for fold in range(5):
        ts = int(n*(0.5+fold*0.1)); te = int(n*(0.6+fold*0.1))
        tr = [sorted_idx[i] for i in range(ts)]
        teid = [sorted_idx[i] for i in range(ts, te)]
        Xtr=[X[i] for i in tr]; ytr=[labels[i] for i in tr]
        Xte=[X[i] for i in teid]; yte=[labels[i] for i in teid]
        w,b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
        base = predict(Xte, w, b)
        boosted = [max(0.01, min(0.99, p + boost_d0big(events[idx], level))) for p,idx in zip(base, teid)]
        a0=auc(base,yte); a1=auc(boosted,yte)
        r0=sorted(zip(base,yte),reverse=True); r1=sorted(zip(boosted,yte),reverse=True)
        t10_0 = sum(y for _,y in r0[:10])/10 if len(r0)>=10 else 0
        t10_1 = sum(y for _,y in r1[:10])/10 if len(r1)>=10 else 0
        t20_0 = sum(y for _,y in r0[:20])/20 if len(r0)>=20 else 0
        t20_1 = sum(y for _,y in r1[:20])/20 if len(r1)>=20 else 0
        deltas_auc.append(a1-a0); deltas_t10.append(t10_1-t10_0); deltas_t20.append(t20_1-t20_0)
    pos_n = sum(1 for d in deltas_auc if d>0)
    pos_t10 = sum(1 for d in deltas_t10 if d>=0)
    pos_t20 = sum(1 for d in deltas_t20 if d>=0)
    print(f"\n  减分 -{level:.2f}:")
    print(f"     AUC Δ {[f'{d:+.4f}' for d in deltas_auc]} 平均 {sum(deltas_auc)/5:+.4f} 正向 {pos_n}/5")
    print(f"     T10 Δ {[f'{d*100:+.0f}%' for d in deltas_t10]} 平均 {sum(deltas_t10)/5*100:+.1f}% 不亏 {pos_t10}/5")
    print(f"     T20 Δ {[f'{d*100:+.0f}%' for d in deltas_t20]} 平均 {sum(deltas_t20)/5*100:+.1f}% 不亏 {pos_t20}/5")
