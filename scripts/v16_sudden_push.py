"""v1.6: 测试"突然 push" 信号
v15_diagnose 发现:
- cb5≥1亿 + pre10_strong≥3 (持续强): n=218, 反转率 75.7%
- cb5≥1亿 + pre10_strong≤1 (突然爆量): n=56, 反转率 80.4% ⭐⭐
- 所以"突然 push" 比"持续 push"更强信号!

新增特征:
- sudden_push: cb5_main_avg >= 1 + pre10_strong_days <= 1 (突然爆量 80%)
- gradual_push: cb5 >= 1 + pre10_strong >= 3 (持续推 75.7%)
- continuous_strong: cb5 >= 0.5 + pre10_in >= 7 (持续强中度 ~50%?)
- silent_d0: D0 当日大涨停 + pre10 安静 (D0 突然启动)

测试: v1.6 = v1.4 + sudden_push + 几个其他 dummy
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11
from mini_gbdt import train_gbdt, predict_gbdt, auc

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v9-with-pre10.json') as f:
    events = json.load(f)['events']


def extract_v16(e):
    f = extract_v11(e)
    cb5 = e.get('cb5_main_avg', 0) or 0
    cb1 = e.get('cb1_main_avg', 0) or 0
    pre10_strong = e.get('pre10_strong_days', 0) or 0
    pre10_in = e.get('pre10_days_in', 5) or 5
    pre10_total = e.get('pre10_main_total', 0) or 0
    d0_main = e.get('d0_main_flow', 0) or 0
    
    # 突然 push: cb5 强 + pre10 安静 (反转率 80%)
    f['sudden_push'] = 1.0 if cb5 >= 1.0 and pre10_strong <= 1 else 0.0
    
    # 持续 push: cb5 强 + pre10 也强 (反转率 75%, 正常档)
    f['gradual_push'] = 1.0 if cb5 >= 1.0 and pre10_strong >= 3 else 0.0
    
    # 沉默 D0: D0 主力大流入但 pre10 完全安静
    f['silent_d0_strong'] = 1.0 if d0_main >= 1.0 and pre10_in <= 3 else 0.0
    
    # 持续中等: pre10_in >= 7 + cb5 0.5-1
    f['steady_mid'] = 1.0 if pre10_in >= 7 and 0.5 <= cb5 < 1.5 else 0.0
    
    # 死亡组合: pre10 安静 + cb5 也安静 (反转率应低)
    f['silent_dead'] = 1.0 if pre10_strong == 0 and abs(cb5) < 0.3 else 0.0
    
    return f


# 先看 dummy 各自反转率
print("=== 候选 dummy 触发率和反转率 ===")
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
features = [extract_v16(e) for e in events]
for k in ['sudden_push', 'gradual_push', 'silent_d0_strong', 'steady_mid', 'silent_dead']:
    n = sum(1 for f in features if f.get(k) == 1)
    rev = sum(labels[i] for i, f in enumerate(features) if f.get(k) == 1)
    if n: print(f"  {k:25s}  n={n:>4}  反转率 {rev/n*100:.1f}%  (vs 36.8% 基线)")

print()
feat_names = list(features[0].keys())
print(f"📊 特征 {len(feat_names)} 维 (v1.4 40 + 5 = 45)")

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]


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

# v1.4 基线 (旧 40 维 v1.1 features)
features_v11 = [extract_v11(e) for e in events]

stats = {n: {"auc": [], "t20": [], "high65_hit": [], "high65_n": [], "high7_hit": [], "high7_n": []}
         for n in ["v1.4 (40 维)", "v1.6 集成 (45 维)"]}

print("\n=== 滚动 OOS ===")
for m in months[6:]:
    tr_i = [i for i, e in enumerate(events) if e['d0_date'][:7] < m]
    te_i = [i for i, e in enumerate(events) if e['d0_date'][:7] == m]
    if len(tr_i) < 100 or len(te_i) < 30: continue
    
    y_tr = [labels[i] for i in tr_i]
    y_te = [labels[i] for i in te_i]
    
    # v1.4
    Xtr_r4 = [features_v11[i] for i in tr_i]; Xte_r4 = [features_v11[i] for i in te_i]
    cont_v4 = [k for k in cont_keys if k in features_v11[0]]
    Xtr_n4, mu4, sd4 = normalize(Xtr_r4, cont_v4)
    w4, b4 = train_lr(Xtr_n4, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n4 = [{k:((v-mu4[k])/sd4[k] if k in cont_v4 else v) for k,v in f.items()} for f in Xte_r4]
    p_lr4 = predict(Xte_n4, w4, b4)
    feat_v4 = list(features_v11[0].keys())
    gbdt4 = train_gbdt(Xtr_r4, y_tr, feat_v4, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb4 = predict_gbdt(gbdt4, Xte_r4)
    p_v4 = [0.6*a + 0.4*b for a,b in zip(p_lr4, p_gb4)]
    
    # v1.6
    Xtr_r6 = [features[i] for i in tr_i]; Xte_r6 = [features[i] for i in te_i]
    Xtr_n6, mu6, sd6 = normalize(Xtr_r6, cont_keys)
    w6, b6 = train_lr(Xtr_n6, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n6 = [{k:((v-mu6[k])/sd6[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r6]
    p_lr6 = predict(Xte_n6, w6, b6)
    gbdt6 = train_gbdt(Xtr_r6, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb6 = predict_gbdt(gbdt6, Xte_r6)
    p_v6 = [0.6*a + 0.4*b for a,b in zip(p_lr6, p_gb6)]
    
    for name, pval in [("v1.4 (40 维)", p_v4), ("v1.6 集成 (45 维)", p_v6)]:
        paired = sorted(zip(pval, y_te), reverse=True)
        stats[name]["auc"].append(auc_local(pval, y_te))
        stats[name]["t20"].append(sum(y for _,y in paired[:20]) / min(20, len(paired)))
        for thr_key, thr in [("high65", 0.65), ("high7", 0.7)]:
            nh = sum(1 for x,_ in paired if x>=thr)
            hh = sum(y for x,y in paired if x>=thr) / max(1, nh)
            stats[name][thr_key+"_hit"].append(hh)
            stats[name][thr_key+"_n"].append(nh)

print(f"\n=== 平均 ===")
for name, s in stats.items():
    if not s["auc"]: continue
    print(f"  {name:25}  AUC={sum(s['auc'])/len(s['auc']):.3f}  T20={sum(s['t20'])/len(s['t20'])*100:.1f}%  P>=0.65 {sum(s['high65_hit'])/len(s['high65_hit'])*100:.1f}%/{sum(s['high65_n'])/len(s['high65_n']):.1f}  P>=0.7 {sum(s['high7_hit'])/len(s['high7_hit'])*100:.1f}%/{sum(s['high7_n'])/len(s['high7_n']):.1f}")

# 看 v1.6 LR 学到的新 dummy 权重
import statistics as stat
print(f"\n=== v1.6 全量 LR 学到的新 dummy 权重 ===")
X_all, mu, sd = normalize(features, cont_keys)
w, b = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)
for k in ['sudden_push', 'gradual_push', 'silent_d0_strong', 'steady_mid', 'silent_dead']:
    if k in w:
        print(f"  {k:25s}  {w[k]:+.4f}")
