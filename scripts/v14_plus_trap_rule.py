"""v1.4 + trap rule 叠加测试
- v1.4 集成已经学了大部分 trap (lbc>=3 + 巨量 + 资金流出)
- 看显式规则 -0.20 还能不能再加一点

也试反向: 加分规则 (持续主力流入)
- pre10 数据还在 enriching, 但能用其他代理: cb5_in_ratio >=0.6 + cb5_main_avg>=1
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


def trap_penalty(f):
    """死陷阱: 高连板 + 巨量 + 资金流出 (-0.15)"""
    lbc = f.get('lbc_num', 1)
    vol = f.get('vol_callback_ratio', 0)
    cb1 = f.get('cb1_main_avg', 0)
    cb3 = f.get('cb3_main_avg', 0)
    if lbc >= 3 and vol >= 5.0 and (cb1 < -1.0 or cb3 < -0.3):
        return -0.15  # 比 v1.5 的 -0.20 略弱, 因为 v1.4 GBDT 已部分识别
    return 0.0


def shake_boost(f):
    """末日反差强信号: cb5>=1 + cb1<0 (历史反转 92%) +0.05"""
    cb5 = f.get('cb5_main_avg', 0)
    cb1 = f.get('cb1_main_avg', 0)
    if cb5 >= 1 and cb1 < 0:
        return +0.05
    return 0.0


def persistence_boost(f):
    """持续性信号: cb5_in_ratio>=0.8 + cb5_main_avg>=0.5 (+0.05)"""
    cb5_ratio = f.get('cb5_in_high', 0)  # >=0.6 才是 1
    cb5 = f.get('cb5_main_avg', 0)
    if cb5_ratio == 1.0 and cb5 >= 0.5:
        return +0.05
    return 0.0


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
configs = {
    "v1.4 (集成)": (False, False, False),
    "v1.4 + trap": (True, False, False),
    "v1.4 + shake": (False, True, False),
    "v1.4 + trap + shake": (True, True, False),
    "v1.4 + 全部 (trap+shake+persist)": (True, True, True),
}
results = {n: {"auc": [], "t20": [], "high_hit": [], "high_n": [], "high65_hit": [], "high65_n": []} for n in configs}

print("=== 滚动 OOS: v1.4 + 各种 post-hoc rule ===")
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
    
    p_v14 = [0.6*a + 0.4*b for a,b in zip(p_lr, p_gb)]
    
    for name, (use_trap, use_shake, use_persist) in configs.items():
        p_adj = []
        for k, p in enumerate(p_v14):
            adj = p
            if use_trap: adj += trap_penalty(Xte_r[k])
            if use_shake: adj += shake_boost(Xte_r[k])
            if use_persist: adj += persistence_boost(Xte_r[k])
            p_adj.append(max(0.001, min(0.999, adj)))
        
        paired = sorted(zip(p_adj, y_te), reverse=True)
        results[name]["auc"].append(auc_local(p_adj, y_te))
        results[name]["t20"].append(sum(y for _,y in paired[:20]) / min(20, len(paired)))
        nh7 = sum(1 for x,_ in paired if x>=0.7)
        hh7 = sum(y for x,y in paired if x>=0.7) / max(1, nh7)
        results[name]["high_hit"].append(hh7)
        results[name]["high_n"].append(nh7)
        nh65 = sum(1 for x,_ in paired if x>=0.65)
        hh65 = sum(y for x,y in paired if x>=0.65) / max(1, nh65)
        results[name]["high65_hit"].append(hh65)
        results[name]["high65_n"].append(nh65)

print(f"\n{'config':<35}{'AUC':>7}{'T20':>7}{'P>=0.65 hit':>14}{'P>=0.65 n':>11}{'P>=0.7 hit':>13}{'P>=0.7 n':>10}")
for name, s in results.items():
    if not s["auc"]: continue
    print(f"  {name:<33}{sum(s['auc'])/len(s['auc']):>7.3f}{sum(s['t20'])/len(s['t20'])*100:>6.1f}%{sum(s['high65_hit'])/len(s['high65_hit'])*100:>13.1f}%{sum(s['high65_n'])/len(s['high65_n']):>11.1f}{sum(s['high_hit'])/len(s['high_hit'])*100:>12.1f}%{sum(s['high_n'])/len(s['high_n']):>10.1f}")

# 看每个规则触发频率
trap_hits = sum(1 for f in features if trap_penalty(f) < 0)
shake_hits = sum(1 for f in features if shake_boost(f) > 0)
persist_hits = sum(1 for f in features if persistence_boost(f) > 0)
print(f"\n规则触发频率:")
print(f"  trap_penalty (-0.15): {trap_hits}/{len(features)} = {trap_hits/len(features)*100:.1f}%, 反转率 {sum(labels[i] for i,f in enumerate(features) if trap_penalty(f)<0)/max(1,trap_hits)*100:.1f}%")
print(f"  shake_boost (+0.05) : {shake_hits}/{len(features)} = {shake_hits/len(features)*100:.1f}%, 反转率 {sum(labels[i] for i,f in enumerate(features) if shake_boost(f)>0)/max(1,shake_hits)*100:.1f}%")
print(f"  persist_boost (+0.05): {persist_hits}/{len(features)} = {persist_hits/len(features)*100:.1f}%, 反转率 {sum(labels[i] for i,f in enumerate(features) if persistence_boost(f)>0)/max(1,persist_hits)*100:.1f}%")
