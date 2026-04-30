"""实验 10: cb1 主力 ≥ X 亿 是否是历史反指
4-30 翻车 6 只 cb1 中位 +4.28亿, 涨停 18 只 cb1 中位 +0.01亿"""
import json, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import extract_v4, normalize, train_lr, predict

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

# cb1 分箱
print("📊 cb1_main_avg (D0+1 当日主力日均) 历史分箱:")
for lo, hi in [(-99,-2),(-2,-1),(-1,0),(0,1),(1,2),(2,3),(3,5),(5,10),(10,99)]:
    sub = [e for e in events if lo <= (e.get("cb1_main_avg",0) or 0) < hi]
    if not sub: continue
    rate = sum(1 for e in sub if e["outcome"]=="reversal")/len(sub)
    print(f"   [{lo:>3},{hi:>3}): n={len(sub):>4} 命中 {rate*100:>5.1f}%")

# cb1 ≥3 vs <3
big = [e for e in events if (e.get("cb1_main_avg",0) or 0) >= 3]
small = [e for e in events if (e.get("cb1_main_avg",0) or 0) < 3]
print(f"\n   cb1 ≥3亿: n={len(big)} 命中 {sum(1 for e in big if e['outcome']=='reversal')/len(big)*100:.1f}%")
print(f"   cb1 <3亿: n={len(small)} 命中 {sum(1 for e in small if e['outcome']=='reversal')/len(small)*100:.1f}%")

# 原: 想测的是反指
# 但实际历史 cb1 ≥3 也是正信号 (主力次日继续买)
# 4-30 翻车原因可能是: cb1 ≥3 这种票需要"次日真的爆发", 但 4-30 已经过去 4-9 天, 风险积累

# 看相对 D0 的天数对 cb1 ≥3 命中的影响
print(f"\n📊 cb1 ≥3 + D0 距 d_t (回马枪) 天数:")
from collections import defaultdict
buckets = defaultdict(lambda: {"n": 0, "zt": 0})
for e in events:
    cb1 = e.get("cb1_main_avg",0) or 0
    if cb1 < 3: continue
    if e["outcome"] != "reversal": continue
    # gap = d_t - d0
    from datetime import datetime
    d0 = e.get("d0_date"); dt = e.get("d_t_date")
    if not d0 or not dt: continue
    gap = (datetime.strptime(dt, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days
    buckets[gap]["zt"] += 1

# 对比 cb1 <3 同样
buckets2 = defaultdict(lambda: {"n": 0, "zt": 0})
for e in events:
    cb1 = e.get("cb1_main_avg",0) or 0
    if cb1 >= 3: continue
    if e["outcome"] != "reversal": continue
    from datetime import datetime
    d0 = e.get("d0_date"); dt = e.get("d_t_date")
    if not d0 or not dt: continue
    gap = (datetime.strptime(dt, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days
    buckets2[gap]["zt"] += 1

# 总数
print(f"\n   cb1 ≥3 命中分布 (按 d_t-d0 间隔):")
for g in sorted(set(list(buckets.keys()) + list(buckets2.keys()))):
    z1 = buckets[g]["zt"]; z2 = buckets2[g]["zt"]
    print(f"     gap=D0+{g:>2}: cb1≥3 {z1:>3} 次  cb1<3 {z2:>3} 次")

# 5 折 cb1 ≥3 减分 boost
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

n = len(events)
print(f"\n📊 5 折 cb1 ≥X 减分 boost:")
for thresh in [1, 2, 3, 5]:
    deltas_t10 = []; deltas_t20 = []; deltas_auc = []
    for fold in range(5):
        ts = int(n*(0.5+fold*0.1)); te = int(n*(0.6+fold*0.1))
        tr = [sorted_idx[i] for i in range(ts)]
        teid = [sorted_idx[i] for i in range(ts, te)]
        Xtr=[X[i] for i in tr]; ytr=[labels[i] for i in tr]
        Xte=[X[i] for i in teid]; yte=[labels[i] for i in teid]
        w,b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
        base = predict(Xte, w, b)
        boosted = []
        for p, idx in zip(base, teid):
            cb1 = events[idx].get("cb1_main_avg",0) or 0
            adj = -0.05 if cb1 >= thresh else 0
            boosted.append(max(0.01, min(0.99, p + adj)))
        a0=auc(base,yte); a1=auc(boosted,yte)
        r0=sorted(zip(base,yte),reverse=True); r1=sorted(zip(boosted,yte),reverse=True)
        t10_0 = sum(y for _,y in r0[:10])/10 if len(r0)>=10 else 0
        t10_1 = sum(y for _,y in r1[:10])/10 if len(r1)>=10 else 0
        t20_0 = sum(y for _,y in r0[:20])/20 if len(r0)>=20 else 0
        t20_1 = sum(y for _,y in r1[:20])/20 if len(r1)>=20 else 0
        deltas_t10.append(t10_1-t10_0); deltas_t20.append(t20_1-t20_0); deltas_auc.append(a1-a0)
    print(f"\n   cb1 ≥{thresh}亿 -0.05:")
    print(f"     AUC Δ {[f'{d:+.4f}' for d in deltas_auc]} 平均 {sum(deltas_auc)/5:+.4f}")
    print(f"     T10 Δ {[f'{d*100:+.0f}%' for d in deltas_t10]} 平均 {sum(deltas_t10)/5*100:+.1f}%")
    print(f"     T20 Δ {[f'{d*100:+.0f}%' for d in deltas_t20]} 平均 {sum(deltas_t20)/5*100:+.1f}%")
