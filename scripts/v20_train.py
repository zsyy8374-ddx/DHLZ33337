#!/usr/bin/env python3
"""v2.0 训练 — 在 v1.8 31 个特征基础上加 12 个新特征
新特征:
  HVB (5): hvb_d0_vol_mult_20, hvb_d0_is_max_20, hvb_d0_vol_ratio_prev, hvb_d0_yang, hvb_d0_body_pct
  N 字 (3): n_p1_gain, n_p2_drop, n_in_n_pattern
  位置 (4): price_vs_ma10, price_vs_ma20, price_vs_ma60, dist_from_60d_high

对比 v1.8 看 OOS AUC + Top 10/20 命中率是否提升
"""
import json, sys
import numpy as np
from pathlib import Path
import pickle
import warnings; warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
SRC = WS / 'backtest' / 'v20_events_enriched.json'
OUT_MODEL = WS / 'picks' / 'v20_model.pkl'
OUT_RESULT = WS / 'picks' / 'v20_train_result.json'

V17_F = ['d0_chg', 'd0_vol', 'd0_lbc', 'd0_main_flow', 'pre_d0_5d_main_avg',
    'cb1_main_avg', 'cb3_main_avg', 'cb5_main_avg', 'cb5_in_ratio',
    'pre10_n', 'pre10_days_in', 'pre10_in_ratio', 'pre10_max_streak',
    'pre10_main_total', 'pre10_main_avg', 'pre10_strong_days']
V18_NEW = ['auc_buy', 'auc_sell', 'auc_diff', 'auc_ratio',
    'auc_match_close', 'auc_amt', 'auc_vol', 'auc_turn',
    'auc_chg', 'auc_amp',
    'auc_buy_to_float', 'auc_sell_to_float', 'auc_amt_to_mcap',
    'auc_strong_open', 'auc_zt_open']
V20_NEW = ['hvb_d0_vol_mult_20', 'hvb_d0_is_max_20', 'hvb_d0_vol_ratio_prev', 
           'hvb_d0_yang', 'hvb_d0_body_pct',
           'n_p1_gain', 'n_p2_drop', 'n_in_n_pattern',
           'price_vs_ma10', 'price_vs_ma20', 'price_vs_ma60', 'dist_from_60d_high']

ALL_F_V18 = V17_F + V18_NEW
ALL_F_V20 = V17_F + V18_NEW + V20_NEW


def safe_float(v, default=0.0):
    if v is None: return default
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return default
        return f
    except: return default


def evaluate(p, y, k_list=[10, 20, 30, 50]):
    """Top K 命中率"""
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(y, p) if len(set(y)) > 1 else 0
    sorted_idx = np.argsort(-p)
    out = {'auc': auc}
    for k in k_list:
        if len(sorted_idx) < k: continue
        topk = sorted_idx[:k]
        hits = y[topk].sum()
        out[f'top{k}_hits'] = int(hits)
        out[f'top{k}_rate'] = float(hits / k)
    return out


def main():
    print('🔬 v2.0 训练', flush=True)
    
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    
    with open(SRC) as f:
        events = [e for e in json.load(f)['events'] 
                  if e.get('auc_buy') is not None and e.get('hvb_d0_vol_mult_20') is not None]
    print(f'  events (有 auc + v20 特征): {len(events)}', flush=True)
    events.sort(key=lambda e: e.get('d_t_strict', '0'))
    
    # 训练 v18 (旧特征) vs v20 (新特征) 对比
    X_v18 = np.array([[safe_float(e.get(f)) for f in ALL_F_V18] for e in events])
    X_v20 = np.array([[safe_float(e.get(f)) for f in ALL_F_V20] for e in events])
    y = np.array([1 if e['outcome']=='reversal' else 0 for e in events])
    
    print(f'  v18 X: {X_v18.shape}, v20 X: {X_v20.shape}', flush=True)
    print(f'  pos: {y.sum()}, neg: {len(y)-y.sum()}', flush=True)
    
    # 时序 OOS
    split = int(len(events) * 0.8)
    
    print(f'\n=== v1.8 (旧特征 31 维) ===', flush=True)
    sc18 = StandardScaler().fit(X_v18[:split])
    Xtr18 = sc18.transform(X_v18[:split])
    Xoos18 = sc18.transform(X_v18[split:])
    
    lr18 = LogisticRegression(C=1.0, max_iter=500, class_weight='balanced').fit(Xtr18, y[:split])
    p_oos_lr18 = lr18.predict_proba(Xoos18)[:, 1]
    eval_lr18 = evaluate(p_oos_lr18, y[split:])
    print(f'  LR OOS AUC: {eval_lr18["auc"]:.4f}, Top10: {eval_lr18.get("top10_hits","-")}/10', flush=True)
    
    gb18 = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42).fit(Xtr18, y[:split])
    p_oos_gb18 = gb18.predict_proba(Xoos18)[:, 1]
    eval_gb18 = evaluate(p_oos_gb18, y[split:])
    print(f'  GBDT OOS AUC: {eval_gb18["auc"]:.4f}, Top10: {eval_gb18.get("top10_hits","-")}/10', flush=True)
    
    print(f'\n=== v2.0 (新特征 43 维) ===', flush=True)
    sc20 = StandardScaler().fit(X_v20[:split])
    Xtr20 = sc20.transform(X_v20[:split])
    Xoos20 = sc20.transform(X_v20[split:])
    
    lr20 = LogisticRegression(C=1.0, max_iter=500, class_weight='balanced').fit(Xtr20, y[:split])
    p_oos_lr20 = lr20.predict_proba(Xoos20)[:, 1]
    eval_lr20 = evaluate(p_oos_lr20, y[split:])
    print(f'  LR OOS AUC: {eval_lr20["auc"]:.4f}, Top10: {eval_lr20.get("top10_hits","-")}/10', flush=True)
    
    gb20 = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42).fit(Xtr20, y[:split])
    p_oos_gb20 = gb20.predict_proba(Xoos20)[:, 1]
    eval_gb20 = evaluate(p_oos_gb20, y[split:])
    print(f'  GBDT OOS AUC: {eval_gb20["auc"]:.4f}, Top10: {eval_gb20.get("top10_hits","-")}/10', flush=True)
    
    # 详细对比
    print(f'\n=== 对比 (v18 vs v20, OOS) ===', flush=True)
    print(f'{"":>14} {"AUC":>10} {"Top10":>8} {"Top20":>8} {"Top30":>8} {"Top50":>8}')
    for label, ev in [('LR v18', eval_lr18), ('LR v20', eval_lr20),
                      ('GBDT v18', eval_gb18), ('GBDT v20', eval_gb20)]:
        line = f'  {label:<12}'
        line += f' {ev.get("auc",0):>10.4f}'
        for k in [10, 20, 30, 50]:
            line += f' {ev.get(f"top{k}_hits","-"):>5}/{k}'
        print(line, flush=True)
    
    # 特征重要性 (GBDT v20)
    print(f'\n=== GBDT v20 特征重要性 (Top 15) ===', flush=True)
    fi = list(zip(ALL_F_V20, gb20.feature_importances_))
    fi.sort(key=lambda x: -x[1])
    for name, imp in fi[:15]:
        is_new = '⭐' if name in V20_NEW else '  '
        print(f'  {is_new} {name:<30} {imp:.4f}', flush=True)
    
    # 落档
    result = {
        'v18': {'lr_oos': eval_lr18, 'gbdt_oos': eval_gb18},
        'v20': {'lr_oos': eval_lr20, 'gbdt_oos': eval_gb20},
        'features_v20_new': V20_NEW,
        'feature_importance_gbdt_v20': [(n, float(i)) for n, i in fi],
    }
    with open(OUT_RESULT, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {OUT_RESULT}', flush=True)
    
    # 存模型 (best)
    best = max([('lr_v18', lr18, sc18, ALL_F_V18, eval_lr18),
                ('gbdt_v18', gb18, sc18, ALL_F_V18, eval_gb18),
                ('lr_v20', lr20, sc20, ALL_F_V20, eval_lr20),
                ('gbdt_v20', gb20, sc20, ALL_F_V20, eval_gb20)],
               key=lambda x: x[4]['auc'])
    print(f'\n🏆 Best: {best[0]} (AUC={best[4]["auc"]:.4f})', flush=True)
    
    with open(OUT_MODEL, 'wb') as f:
        pickle.dump({'model': best[1], 'scaler': best[2], 'features': best[3], 
                     'name': best[0], 'eval': best[4]}, f)
    print(f'💾 模型: {OUT_MODEL}', flush=True)


if __name__ == '__main__':
    main()
