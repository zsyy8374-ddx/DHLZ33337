"""v1.5: v1.4 集成 + pre10 持续性特征
基础: v1.1 LR (40 维) + GBDT
增量: pre10_days_in, pre10_strong_days, pre10_main_total, pre10_main_avg, pre10_max_streak

新数据: backtest/reversal-events-2026-05-01-v9-with-pre10.json (3262 事件 含 pre10)

测试: 滚动 OOS 9 个月 平均 vs v1.4
"""
import json, sys, math
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11
from mini_gbdt import train_gbdt, predict_gbdt, auc

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v9-with-pre10.json') as f:
    events = json.load(f)['events']


def extract_v15(e):
    """v1.5 = v1.1 特征 + pre10 持续性"""
    f = extract_v11(e)
    pre10_in = e.get('pre10_days_in', 5) or 5
    pre10_strong = e.get('pre10_strong_days', 0) or 0
    pre10_total = e.get('pre10_main_total', 0) or 0
    pre10_avg = e.get('pre10_main_avg', 0) or 0
    pre10_streak = e.get('pre10_max_streak', 0) or 0
    
    # 连续值
    f['pre10_days_in'] = pre10_in
    f['pre10_strong_days'] = pre10_strong
    f['pre10_main_total'] = pre10_total
    f['pre10_main_avg'] = pre10_avg
    f['pre10_max_streak'] = pre10_streak
    
    # 强信号 dummy (反转率 ≥45%)
    f['pre10_persistent_strong'] = 1.0 if pre10_in >= 7 and pre10_strong >= 3 else 0.0
    f['pre10_extreme_persistent'] = 1.0 if pre10_strong >= 5 else 0.0  # 反转率 57%
    f['pre10_sleep'] = 1.0 if pre10_in <= 2 else 0.0  # 反转率 30% (反指)
    
    return f


features = [extract_v15(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
feat_names = list(features[0].keys())
print(f"📊 数据: {len(events)}, 特征 {len(feat_names)} 维 (v1.1 40 + pre10 8 = 48)")

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate",
             "pre10_days_in","pre10_strong_days","pre10_main_total","pre10_main_avg","pre10_max_streak"]


def auc_local(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)


months = sorted(set(e['d0_date'][:7] for e in events))

print("\n=== 滚动 OOS: v1.5 (v1.4 + pre10) vs v1.4 ===")

stats = {n: {"auc": [], "t20": [], "high_hit": [], "high_n": [], "high65_hit": [], "high65_n": []}
         for n in ["v1.4 (40维)", "v1.5 LR单 (48维)", "v1.5 GBDT单", "v1.5 集成 0.6/0.4"]}

# 还需要 v1.1 features 给 v1.4 对照
features_v11 = [extract_v11(e) for e in events]

for m in months[6:]:
    tr_i = [i for i, e in enumerate(events) if e['d0_date'][:7] < m]
    te_i = [i for i, e in enumerate(events) if e['d0_date'][:7] == m]
    if len(tr_i) < 100 or len(te_i) < 30: continue
    
    # v1.4 (旧 40 维 v1.1 特征 + 集成)
    Xtr_r4 = [features_v11[i] for i in tr_i]
    y_tr = [labels[i] for i in tr_i]
    Xte_r4 = [features_v11[i] for i in te_i]
    y_te = [labels[i] for i in te_i]
    
    cont_keys_v4 = [k for k in cont_keys if k in features_v11[0]]
    Xtr_n4, mu4, sd4 = normalize(Xtr_r4, cont_keys_v4)
    w4, b4 = train_lr(Xtr_n4, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n4 = [{k:((v-mu4[k])/sd4[k] if k in cont_keys_v4 else v) for k,v in f.items()} for f in Xte_r4]
    p_lr4 = predict(Xte_n4, w4, b4)
    feat_names_v4 = list(features_v11[0].keys())
    gbdt4 = train_gbdt(Xtr_r4, y_tr, feat_names_v4, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb4 = predict_gbdt(gbdt4, Xte_r4)
    p_v4 = [0.6*a + 0.4*b for a,b in zip(p_lr4, p_gb4)]
    
    # v1.5 (48 维)
    Xtr_r5 = [features[i] for i in tr_i]
    Xte_r5 = [features[i] for i in te_i]
    
    Xtr_n5, mu5, sd5 = normalize(Xtr_r5, cont_keys)
    w5, b5 = train_lr(Xtr_n5, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n5 = [{k:((v-mu5[k])/sd5[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r5]
    p_lr5 = predict(Xte_n5, w5, b5)
    
    gbdt5 = train_gbdt(Xtr_r5, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb5 = predict_gbdt(gbdt5, Xte_r5)
    p_v5_ens = [0.6*a + 0.4*b for a,b in zip(p_lr5, p_gb5)]
    
    for name, pval in [
        ("v1.4 (40维)", p_v4),
        ("v1.5 LR单 (48维)", p_lr5),
        ("v1.5 GBDT单", p_gb5),
        ("v1.5 集成 0.6/0.4", p_v5_ens),
    ]:
        paired = sorted(zip(pval, y_te), reverse=True)
        stats[name]["auc"].append(auc_local(pval, y_te))
        stats[name]["t20"].append(sum(y for _,y in paired[:20]) / min(20, len(paired)))
        nh7 = sum(1 for x,_ in paired if x>=0.7)
        hh7 = sum(y for x,y in paired if x>=0.7) / max(1, nh7)
        stats[name]["high_hit"].append(hh7)
        stats[name]["high_n"].append(nh7)
        nh65 = sum(1 for x,_ in paired if x>=0.65)
        hh65 = sum(y for x,y in paired if x>=0.65) / max(1, nh65)
        stats[name]["high65_hit"].append(hh65)
        stats[name]["high65_n"].append(nh65)
    
    print(f"  {m} n={len(te_i):>3}: v1.4 AUC={stats['v1.4 (40维)']['auc'][-1]:.3f} T20={stats['v1.4 (40维)']['t20'][-1]*100:.0f}%  | v1.5 AUC={stats['v1.5 集成 0.6/0.4']['auc'][-1]:.3f} T20={stats['v1.5 集成 0.6/0.4']['t20'][-1]*100:.0f}%")

print(f"\n=== 平均 ===")
for name, s in stats.items():
    if not s["auc"]: continue
    print(f"  {name:20}  AUC={sum(s['auc'])/len(s['auc']):.3f}  T20={sum(s['t20'])/len(s['t20'])*100:.1f}%  P>=0.65 {sum(s['high65_hit'])/len(s['high65_hit'])*100:.1f}%/{sum(s['high65_n'])/len(s['high65_n']):.1f}  P>=0.7 {sum(s['high_hit'])/len(s['high_hit'])*100:.1f}%/{sum(s['high_n'])/len(s['high_n']):.1f}")
