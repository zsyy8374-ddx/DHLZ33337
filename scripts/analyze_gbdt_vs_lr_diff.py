"""分析 GBDT 与 LR 预测分歧 - 找 GBDT 学到了什么 LR 错过的
- 训 v1.1 LR + GBDT-100-d3 (各自全量)
- 用 5-fold OOS 拿到 OOS 概率 (确保不是 in-sample)
- 找 |p_gbdt - p_lr| 最大的事件
- 分两种:
  A. GBDT 推高 (p_gbdt >> p_lr): GBDT 看到了 LR 看不到的"反转信号"
  B. GBDT 拉低 (p_lr >> p_gbdt): GBDT 看到了 LR 看不到的"陷阱"
- 看每种里 outcome 实际分布, 找共同特征
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

# 5 折时序 OOS, 拿到每个事件的 OOS 概率
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
fold_size = N // 5
oos_p_lr = [None]*N
oos_p_gb = [None]*N

print("跑 5 折 OOS...")
for fold in range(5):
    test_start = fold * fold_size
    test_end = (fold + 1) * fold_size if fold < 4 else N
    test_idx = sorted_idx[test_start:test_end]
    train_idx_f = sorted_idx[:test_start] + sorted_idx[test_end:]
    
    Xtr_r = [features[i] for i in train_idx_f]
    y_tr = [labels[i] for i in train_idx_f]
    Xte_r = [features[i] for i in test_idx]
    
    Xtr_n, mu_f, sd_f = normalize(Xtr_r, cont_keys)
    w_f, b_f = train_lr(Xtr_n, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n = [{k: ((v-mu_f[k])/sd_f[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r]
    p_lr_f = predict(Xte_n, w_f, b_f)
    
    gbdt_f = train_gbdt(Xtr_r, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
    p_gb_f = predict_gbdt(gbdt_f, Xte_r)
    
    for k, idx in enumerate(test_idx):
        oos_p_lr[idx] = p_lr_f[k]
        oos_p_gb[idx] = p_gb_f[k]
    print(f"  fold {fold+1}: ok")

# 整体 OOS AUC
all_pairs = [(oos_p_lr[i], oos_p_gb[i], labels[i], i) for i in range(N) if oos_p_lr[i] is not None]
print(f"\nOOS 数据: {len(all_pairs)} 事件")
print(f"LR OOS AUC : {auc([p[0] for p in all_pairs], [p[2] for p in all_pairs]):.4f}")
print(f"GBDT OOS AUC: {auc([p[1] for p in all_pairs], [p[2] for p in all_pairs]):.4f}")
print(f"集成 OOS AUC: {auc([0.6*p[0]+0.4*p[1] for p in all_pairs], [p[2] for p in all_pairs]):.4f}")

# === A. GBDT 推高 (p_gb >> p_lr) ===
diffs_up = sorted(all_pairs, key=lambda x: x[1] - x[0], reverse=True)
print(f"\n=== A. GBDT 推高 Top 50 (p_gbdt >> p_lr) ===")
print(f"{'#':<4}{'p_lr':<7}{'p_gb':<7}{'差':<7}{'结果':<6}{'代码':<8}{'lbc':<4}{'cb%':<6}{'cb5亿':<8}{'量比':<6}{'D0日期'}")
print("-"*80)
hits_up = 0
for k, (plr, pgb, y, idx) in enumerate(diffs_up[:50]):
    e = events[idx]
    f = features[idx]
    if y == 1: hits_up += 1
    flag = "✅反转" if y else "❌失败"
    print(f"{k+1:<4}{plr:<7.3f}{pgb:<7.3f}{pgb-plr:<+7.3f}{flag:<6}{e['code']:<8}{f['lbc_num']:<4.0f}{f['callback_pct']:<6.1f}{f['cb5_main_avg']:<+8.2f}{f['vol_callback_ratio']:<6.2f}{e['d0_date']}")
print(f"\n   GBDT 推高 Top 50 实际反转率: {hits_up}/50 = {hits_up*2}%")
print(f"   全样本反转率基线: 36.8%")

# 看这 50 只的特征均值 vs 全样本
print(f"\n   GBDT 推高 Top 50 特征均值:")
for k in ["callback_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","vol_callback_ratio","lbc_num","cb5_in_ratio"]:
    if k in features[0]:
        avg_top = sum(features[d[3]].get(k,0) for d in diffs_up[:50]) / 50
        avg_all = sum(f.get(k,0) for f in features) / N
        diff_pct = (avg_top - avg_all) / max(abs(avg_all), 0.01) * 100
        print(f"     {k:25s}: top50 {avg_top:+.3f}  vs  全样本 {avg_all:+.3f}  ({diff_pct:+.0f}%)")

# === B. GBDT 拉低 (p_gb << p_lr) ===
diffs_dn = sorted(all_pairs, key=lambda x: x[0] - x[1], reverse=True)
print(f"\n=== B. GBDT 拉低 Top 50 (p_lr >> p_gbdt) ===")
print(f"{'#':<4}{'p_lr':<7}{'p_gb':<7}{'差':<7}{'结果':<6}{'代码':<8}{'lbc':<4}{'cb%':<6}{'cb5亿':<8}{'量比':<6}{'D0日期'}")
print("-"*80)
hits_dn = 0
for k, (plr, pgb, y, idx) in enumerate(diffs_dn[:50]):
    e = events[idx]
    f = features[idx]
    if y == 1: hits_dn += 1
    flag = "✅反转" if y else "❌失败"
    print(f"{k+1:<4}{plr:<7.3f}{pgb:<7.3f}{plr-pgb:<+7.3f}{flag:<6}{e['code']:<8}{f['lbc_num']:<4.0f}{f['callback_pct']:<6.1f}{f['cb5_main_avg']:<+8.2f}{f['vol_callback_ratio']:<6.2f}{e['d0_date']}")
print(f"\n   GBDT 拉低 Top 50 实际反转率: {hits_dn}/50 = {hits_dn*2}%")

# 这 50 只的特征
print(f"\n   GBDT 拉低 Top 50 特征均值:")
for k in ["callback_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","vol_callback_ratio","lbc_num","cb5_in_ratio"]:
    if k in features[0]:
        avg_top = sum(features[d[3]].get(k,0) for d in diffs_dn[:50]) / 50
        avg_all = sum(f.get(k,0) for f in features) / N
        diff_pct = (avg_top - avg_all) / max(abs(avg_all), 0.01) * 100
        print(f"     {k:25s}: top50 {avg_top:+.3f}  vs  全样本 {avg_all:+.3f}  ({diff_pct:+.0f}%)")
