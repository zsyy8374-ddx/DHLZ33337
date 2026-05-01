"""v1.4 实验: LR + GBDT 概率集成
- 简单平均: p_ens = 0.5 * p_lr + 0.5 * p_gbdt
- 加权平均: 0.6 LR + 0.4 GBDT (LR 更稳)
- 几何平均: sqrt(p_lr * p_gbdt)
- max(p_lr, p_gbdt) (更激进)

目标: 滚动 OOS T20 + P≥0.7 命中 不低于 v1.1 LR
"""
import json, sys, math
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

months = sorted(set(e['d0_date'][:7] for e in events))

stats = {name: {"auc": [], "t20": [], "high_hit": [], "high_n": []} 
         for name in ["LR", "GBDT", "AVG", "0.6LR+0.4GBDT", "GEO", "MAX"]}

print("=== 滚动 OOS: LR + GBDT 集成 ===")
print(f"{'月':10} {'n':>4}  {'LR T20':>7} {'GBDT T20':>9} {'AVG T20':>8} {'0.6+0.4 T20':>12} {'AVG P>=0.7':>11}")

for m in months[6:]:
    tr_i = [i for i, e in enumerate(events) if e['d0_date'][:7] < m]
    te_i = [i for i, e in enumerate(events) if e['d0_date'][:7] == m]
    if len(tr_i) < 100 or len(te_i) < 30: continue
    
    Xtr_r = [features[i] for i in tr_i]
    y_tr = [labels[i] for i in tr_i]
    Xte_r = [features[i] for i in te_i]
    y_te = [labels[i] for i in te_i]
    
    Xtr_n, mu_m, sd_m = normalize(Xtr_r, cont_keys)
    w_m, b_m = train_lr(Xtr_n, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n = [{k: ((v-mu_m[k])/sd_m[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r]
    p_lr = predict(Xte_n, w_m, b_m)
    
    gbdt_m = train_gbdt(Xtr_r, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb = predict_gbdt(gbdt_m, Xte_r)
    
    p_avg = [(a+b)/2 for a,b in zip(p_lr, p_gb)]
    p_w = [0.6*a + 0.4*b for a,b in zip(p_lr, p_gb)]
    p_geo = [math.sqrt(max(0,a)*max(0,b)) for a,b in zip(p_lr, p_gb)]
    p_max = [max(a,b) for a,b in zip(p_lr, p_gb)]
    
    def collect(p, name):
        paired = sorted(zip(p, y_te), reverse=True)
        au = auc(p, y_te)
        t20 = sum(y for _,y in paired[:20]) / min(20, len(paired))
        nh = sum(1 for x,_ in paired if x>=0.7)
        hh = sum(y for x,y in paired if x>=0.7) / max(1, nh)
        stats[name]["auc"].append(au)
        stats[name]["t20"].append(t20)
        stats[name]["high_hit"].append(hh)
        stats[name]["high_n"].append(nh)
        return t20, nh, hh
    
    lr_t20, _, _ = collect(p_lr, "LR")
    gb_t20, _, _ = collect(p_gb, "GBDT")
    avg_t20, avg_nh, avg_hh = collect(p_avg, "AVG")
    w_t20, _, _ = collect(p_w, "0.6LR+0.4GBDT")
    geo_t20, _, _ = collect(p_geo, "GEO")
    max_t20, _, _ = collect(p_max, "MAX")
    
    print(f"  {m:8} {len(te_i):>4}  {lr_t20*100:>6.0f}%  {gb_t20*100:>8.0f}%  {avg_t20*100:>7.0f}%  {w_t20*100:>11.0f}%  {avg_hh*100:>9.0f}% (n={avg_nh})")

print(f"\n=== 平均 ===")
for name in stats:
    s = stats[name]
    if not s["auc"]: continue
    print(f"  {name:18}  AUC={sum(s['auc'])/len(s['auc']):.3f}  T20={sum(s['t20'])/len(s['t20'])*100:.1f}%  P>=0.7命中={sum(s['high_hit'])/len(s['high_hit'])*100:.1f}%  n={sum(s['high_n'])/len(s['high_n']):.1f}")
