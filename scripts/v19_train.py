#!/usr/bin/env python3
"""v1.9 训练: v1.8 (31维) + 9:35 5m K 数据 (4维) = 35 维
新增特征 (D_t 9:30-9:34 5m bar):
- pm_open_pct: 开盘相对前收
- pm_5m_high_pct: 5m 高点相对开盘
- pm_5m_close_pct: 5m close 相对开盘
- pm_5m_amt_yi: 5m 成交额(亿)

(从 v18_events_enriched 的 pm_* 字段直接取, 之前 v10 已 enrich 过)
"""
import json, pickle
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
SRC = WS / 'backtest' / 'v18_events_enriched.json'
OUT_MODEL = WS / 'picks' / 'lr_v19_ensemble_model.json'

V17_F = ['d0_chg', 'd0_vol', 'd0_lbc', 'd0_main_flow', 'pre_d0_5d_main_avg',
    'cb1_main_avg', 'cb3_main_avg', 'cb5_main_avg', 'cb5_in_ratio',
    'pre10_n', 'pre10_days_in', 'pre10_in_ratio', 'pre10_max_streak',
    'pre10_main_total', 'pre10_main_avg', 'pre10_strong_days']
V18_NEW = ['auc_buy', 'auc_sell', 'auc_diff', 'auc_ratio',
    'auc_match_close', 'auc_amt', 'auc_vol', 'auc_turn',
    'auc_chg', 'auc_amp',
    'auc_buy_to_float', 'auc_sell_to_float', 'auc_amt_to_mcap',
    'auc_strong_open', 'auc_zt_open']
V19_NEW = ['pm_open_pct', 'pm_5m_high_pct', 'pm_5m_close_pct', 'pm_5m_amt_yi']
ALL_F = V17_F + V18_NEW + V19_NEW


def safe_float(v, default=0.0):
    if v is None: return default
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return default
        return f
    except (TypeError, ValueError): return default


def main():
    print('📥 加载 enriched events...')
    with open(SRC) as f:
        events = json.load(f)['events']
    
    # 双重 filter: 有 9:25 数据 AND 有 9:35 5m 数据
    enriched = [e for e in events 
                if e.get('auc_buy') is not None 
                and e.get('pm_open_pct') is not None]
    print(f'  events 总: {len(events)}, 有 9:25 + 5m: {len(enriched)}')
    
    enriched.sort(key=lambda e: e.get('d_t_strict', '0'))
    
    X = np.array([[safe_float(e.get(f)) for f in ALL_F] for e in enriched])
    y = np.array([1 if e['outcome']=='reversal' else 0 for e in enriched])
    print(f'  X shape: {X.shape}, pos: {y.sum()}, neg: {len(y)-y.sum()}')
    
    split = int(len(X) * 0.8)
    X_tr, y_tr = X[:split], y[:split]
    X_oos, y_oos = X[split:], y[split:]
    
    scaler = StandardScaler().fit(X_tr)
    X_tr_n = scaler.transform(X_tr)
    X_oos_n = scaler.transform(X_oos)
    
    lr = LogisticRegression(C=1.0, max_iter=500, class_weight='balanced')
    lr.fit(X_tr_n, y_tr)
    p_tr_lr = lr.predict_proba(X_tr_n)[:, 1]
    p_oos_lr = lr.predict_proba(X_oos_n)[:, 1]
    
    gb = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42)
    gb.fit(X_tr_n, y_tr)
    p_tr_gb = gb.predict_proba(X_tr_n)[:, 1]
    p_oos_gb = gb.predict_proba(X_oos_n)[:, 1]
    
    # 集成
    p_oos_ens = 0.4 * p_oos_lr + 0.6 * p_oos_gb
    auc_ens = roc_auc_score(y_oos, p_oos_ens)
    
    print(f'\n🎯 v1.9 结果:')
    print(f'  LR AUC: 训练 {roc_auc_score(y_tr, p_tr_lr):.4f}, OOS {roc_auc_score(y_oos, p_oos_lr):.4f}')
    print(f'  GBDT AUC: 训练 {roc_auc_score(y_tr, p_tr_gb):.4f}, OOS {roc_auc_score(y_oos, p_oos_gb):.4f}')
    print(f'  集成 (0.4 LR + 0.6 GBDT) OOS AUC: {auc_ens:.4f}')
    
    print('\n📊 Top K 命中率:')
    for k in [5, 10, 20, 30, 50]:
        idx = np.argsort(-p_oos_ens)[:k]
        hit = y_oos[idx].mean()
        print(f'  Top {k:>3}: {hit*100:.1f}% ({y_oos[idx].sum()}/{k})')
    
    print('\n📊 OOS 阈值校准:')
    thr_table = []
    for thr in [0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5]:
        mask = p_oos_ens >= thr
        if mask.sum() >= 5:
            hit = y_oos[mask].mean()
            print(f'  P≥{thr}: n={mask.sum()}, 命中率 {hit*100:.1f}%')
            thr_table.append({'p_thr': thr, 'n': int(mask.sum()), 'hit': float(hit)})
    
    print('\n🔍 GBDT Top 15 重要特征:')
    imp = gb.feature_importances_
    sorted_idx = np.argsort(-imp)
    for i in sorted_idx[:15]:
        print(f'  {ALL_F[i]:25}: {imp[i]:.4f}')
    
    # 落档
    pkl_path = WS / 'picks' / 'v19_sklearn_model.pkl'
    with open(pkl_path, 'wb') as f:
        pickle.dump({'lr': lr, 'gb': gb, 'scaler': scaler, 'features': ALL_F}, f)
    
    meta = {
        'version': 'v1.9-ensemble-925-935',
        'features': ALL_F,
        'oos_auc': float(auc_ens),
        'oos_threshold_table': thr_table,
        'oos_topk': {f'top{k}': float(y_oos[np.argsort(-p_oos_ens)[:k]].mean()) for k in [5,10,20,30,50]},
        'feature_importance': {ALL_F[i]: float(imp[i]) for i in sorted_idx},
        'train_size': int(len(X_tr)), 'oos_size': int(len(X_oos)),
        'note': 'v1.9 = v1.8 + 9:30-9:35 5m K (35 维), 推送时点 9:35-9:36',
    }
    with open(OUT_MODEL, 'w') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f'\n💾 model: {pkl_path}')
    print(f'💾 meta: {OUT_MODEL}')


if __name__ == '__main__':
    main()
