#!/usr/bin/env python3
"""v1.8 训练窗口扫描 — 看 30/60/90/all 天哪个最好
策略: 每天用前 N 天 events 训, 测当天
"""
import json, sys
from pathlib import Path
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')


def safe(v, d=0.0):
    import math
    if v is None: return d
    try:
        f = float(v)
        return d if (math.isnan(f) or math.isinf(f)) else f
    except: return d


BASE_FEATURES = [
    'd0_chg', 'd0_lbc', 'd0_main_flow',
    'pre_d0_5d_main_avg', 'cb1_main_avg', 'cb3_main_avg', 'cb5_main_avg',
    'cb5_in_ratio', 'pre10_n', 'pre10_days_in', 'pre10_in_ratio',
    'pre10_max_streak', 'pre10_main_avg', 'pre10_strong_days', 'broke_ma5', 'broke_ma10',
]
AUC_FEATURES = ['auc_buy', 'auc_sell', 'auc_diff', 'auc_ratio',
                'auc_match_close', 'auc_amt', 'auc_vol', 'auc_turn',
                'auc_chg', 'auc_amp', 'auc_buy_to_float', 'auc_sell_to_float',
                'auc_amt_to_mcap', 'auc_strong_open', 'auc_zt_open']

ALL_FEATURES = BASE_FEATURES + AUC_FEATURES


def build_X(events, auc_data):
    X, y = [], []
    for e in events:
        d_t = e.get('d_t_date')
        if not d_t: continue
        outcome = e.get('outcome', '')
        label = 1 if outcome == 'reversal' else 0
        auc = auc_data.get(d_t, {}).get(e['code'], {})
        if not auc: continue
        feat = {fn: safe(e.get(fn, 0)) for fn in BASE_FEATURES}
        for fn in AUC_FEATURES:
            feat[fn] = safe(auc.get(fn, 0))
        feat['auc_strong_open'] = 1 if (feat['auc_chg']>0.5 and feat['auc_ratio']>1.5) else 0
        feat['auc_zt_open'] = 1 if feat['auc_chg']>9.5 else 0
        X.append([feat[fn] for fn in ALL_FEATURES])
        y.append(label)
    return np.array(X), np.array(y)


def train_v18(X_train, y_train, seed=42):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    pos_idx = np.where(y_train == 1)[0]
    neg_idx = np.where(y_train == 0)[0]
    if len(pos_idx) < 5: return None
    np.random.seed(seed)
    if len(neg_idx) > len(pos_idx):
        neg_s = np.random.choice(neg_idx, len(pos_idx), replace=False)
    else:
        neg_s = neg_idx
    idx = np.concatenate([pos_idx, neg_s])
    np.random.shuffle(idx)
    X_t, y_t = X_train[idx], y_train[idx]
    scaler = StandardScaler()
    X_n = scaler.fit_transform(X_t)
    lr = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced')
    lr.fit(X_n, y_t)
    gb = GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.05, random_state=seed)
    gb.fit(X_n, y_t)
    return {'scaler': scaler, 'lr': lr, 'gb': gb}


def predict(model, X):
    X_n = model['scaler'].transform(X)
    p_lr = model['lr'].predict_proba(X_n)[:, 1]
    p_gb = model['gb'].predict_proba(X_n)[:, 1]
    return 0.4 * p_lr + 0.6 * p_gb


def main():
    print('🔍 v1.8 训练窗口扫描', flush=True)
    
    with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
        all_events = json.load(f)['events']
    with open(WS / 'backtest' / 'v18_auc_data.json') as f:
        auc_data = json.load(f)
    
    all_with_dt = [e for e in all_events if e.get('d_t_date')]
    
    test_dates = ['2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24',
                  '2026-04-28', '2026-04-29', '2026-04-30']
    
    # 扫描窗口
    for window_days in [30, 60, 90, 9999]:
        win_label = 'all' if window_days >= 365 else f'{window_days}d'
        print(f'\n{"="*60}', flush=True)
        print(f'窗口: {win_label}', flush=True)
        print('='*60, flush=True)
        
        results = []
        for test_date in test_dates:
            test_d = datetime.strptime(test_date, '%Y-%m-%d')
            cutoff_d = test_d - timedelta(days=window_days)
            cutoff = cutoff_d.strftime('%Y-%m-%d')
            
            train = [e for e in all_with_dt if cutoff <= e['d_t_date'] < test_date]
            test = [e for e in all_with_dt if e['d_t_date'] == test_date]
            
            if not train or not test: continue
            
            X_tr, y_tr = build_X(train, auc_data)
            X_te, y_te = build_X(test, auc_data)
            if len(X_tr) < 20 or len(X_te) < 5: continue
            
            model = train_v18(X_tr, y_tr)
            if model is None: continue
            
            p = predict(model, X_te)
            top10 = np.argsort(-p)[:10] if len(p) >= 10 else np.argsort(-p)
            top20 = np.argsort(-p)[:20] if len(p) >= 20 else np.argsort(-p)
            
            top10_hit = int(y_te[top10].sum())
            top20_hit = int(y_te[top20].sum())
            
            from sklearn.metrics import roc_auc_score
            auc_v = roc_auc_score(y_te, p) if len(set(y_te)) > 1 else None
            
            results.append({
                'date': test_date, 'n_train': len(X_tr), 'n_test': len(X_te),
                'auc': auc_v,
                'top10_hit': top10_hit, 'top10_n': min(10, len(p)),
                'top20_hit': top20_hit, 'top20_n': min(20, len(p)),
            })
        
        if not results: continue
        
        top10_avg = np.mean([r['top10_hit']/r['top10_n']*100 for r in results])
        top20_avg = np.mean([r['top20_hit']/r['top20_n']*100 for r in results])
        aucs = [r['auc'] for r in results if r.get('auc') is not None]
        auc_avg = np.mean(aucs) if aucs else None
        
        auc_s = f'{auc_avg:.3f}' if auc_avg else 'NA'
        print(f'  天数: {len(results)}, AUC: {auc_s}', flush=True)
        print(f'  Top 10 平均: {top10_avg:.1f}%', flush=True)
        print(f'  Top 20 平均: {top20_avg:.1f}%', flush=True)
        for r in results:
            print(f'    {r["date"]}: tr={r["n_train"]} Top10={r["top10_hit"]}/{r["top10_n"]}', flush=True)


if __name__ == '__main__':
    main()
