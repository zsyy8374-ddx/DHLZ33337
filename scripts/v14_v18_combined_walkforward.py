#!/usr/bin/env python3
"""v1.4 + v1.8 联动 walk-forward — 模拟真实实战场景
- D-1 17:35 v1.4 LR 推 332 候选
- D 9:25 v1.8 重排, P≥0.8 推送
- 测 4-21 ~ 4-30 共 N 天
"""
import json, sys
from pathlib import Path
import numpy as np
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
    X, y, meta = [], [], []
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
        if feat['auc_chg'] > 0.5 and feat['auc_ratio'] > 1.5:
            feat['auc_strong_open'] = 1
        else:
            feat['auc_strong_open'] = 0
        feat['auc_zt_open'] = 1 if feat['auc_chg'] > 9.5 else 0
        X.append([feat[fn] for fn in ALL_FEATURES])
        y.append(label)
        meta.append({'code': e['code'], 'name': e.get('name'), 
                     'd_t_date': d_t, 'd0_main_flow': e.get('d0_main_flow', 0),
                     'cb5_main_avg': e.get('cb5_main_avg', 0)})
    return np.array(X), np.array(y), meta


def train_v18(X_train, y_train):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    pos_idx = np.where(y_train == 1)[0]
    neg_idx = np.where(y_train == 0)[0]
    if len(pos_idx) < 5: return None
    np.random.seed(42)
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
    gb = GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.05, random_state=42)
    gb.fit(X_n, y_t)
    return {'scaler': scaler, 'lr': lr, 'gb': gb}


def predict(model, X):
    X_n = model['scaler'].transform(X)
    p_lr = model['lr'].predict_proba(X_n)[:, 1]
    p_gb = model['gb'].predict_proba(X_n)[:, 1]
    return 0.4 * p_lr + 0.6 * p_gb


def train_v14_lr(events_train):
    """v1.4 LR: 用 base 16 维 + boost"""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    X = np.array([[safe(e.get(fn, 0)) for fn in BASE_FEATURES] for e in events_train])
    y = np.array([1 if e.get('outcome') == 'reversal' else 0 for e in events_train])
    
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    if len(pos_idx) < 5: return None
    np.random.seed(42)
    neg_s = np.random.choice(neg_idx, min(len(neg_idx), len(pos_idx)*3), replace=False)
    idx = np.concatenate([pos_idx, neg_s])
    X_t, y_t = X[idx], y[idx]
    
    scaler = StandardScaler()
    X_n = scaler.fit_transform(X_t)
    lr = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced')
    lr.fit(X_n, y_t)
    return {'scaler': scaler, 'lr': lr}


def predict_v14(model, events):
    X = np.array([[safe(e.get(fn, 0)) for fn in BASE_FEATURES] for e in events])
    X_n = model['scaler'].transform(X)
    p = model['lr'].predict_proba(X_n)[:, 1]
    
    # boost 主力流入 (cb5_main_avg)
    boost = []
    for e in events:
        cb5 = safe(e.get('cb5_main_avg', 0))
        if cb5 > 1000: b = 0.10
        elif cb5 > 500: b = 0.05
        elif cb5 > 0: b = 0.02
        elif cb5 < -500: b = -0.10
        else: b = 0
        boost.append(b)
    return p + np.array(boost)


def main():
    print('🧪 v1.4 + v1.8 联动 walk-forward', flush=True)
    
    with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
        all_events = json.load(f)['events']
    with open(WS / 'backtest' / 'v18_auc_data.json') as f:
        auc_data = json.load(f)
    
    all_with_dt = [e for e in all_events if e.get('d_t_date')]
    all_with_dt.sort(key=lambda x: x['d_t_date'])
    
    test_dates = ['2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24',
                  '2026-04-25', '2026-04-28', '2026-04-29', '2026-04-30']
    
    results = []
    
    for test_date in test_dates:
        train = [e for e in all_with_dt if e['d_t_date'] < test_date]
        test = [e for e in all_with_dt if e['d_t_date'] == test_date]
        
        if not train or not test: continue
        
        # 1. v1.4 训 + 推 (在 test 上排序, 取 Top 30%)
        v14 = train_v14_lr(train)
        if v14 is None: continue
        p14 = predict_v14(v14, test)
        
        # v1.4 取所有 P>0.5 (~50% 候选)
        v14_pass_idx = np.where(p14 >= 0.5)[0]
        v14_top_n = max(30, len(test) // 3)  # 至少 30, 或 1/3
        v14_top_idx = np.argsort(-p14)[:v14_top_n]
        
        # 2. v1.8 训
        X_tr, y_tr, _ = build_X(train, auc_data)
        if len(X_tr) < 20: continue
        model = train_v18(X_tr, y_tr)
        if model is None: continue
        
        # 3. v1.8 在 v1.4 通过的票上重排
        X_te, y_te, meta_te = build_X(test, auc_data)
        if len(X_te) < 5: continue
        
        # 找 v1.4 通过的票在 X_te 里的索引
        # X_te 顺序 = test 里有 auc 的子集
        test_with_auc_idx = [i for i, e in enumerate(test) if auc_data.get(e['d_t_date'], {}).get(e['code'])]
        # v1.4 Top 在 test 里的位置
        v14_top_set = set(v14_top_idx)
        te_v14_pass = [i for i, ti in enumerate(test_with_auc_idx) if ti in v14_top_set]
        
        if not te_v14_pass: continue
        X_te_pass = X_te[te_v14_pass]
        y_te_pass = y_te[te_v14_pass]
        
        p18 = predict(model, X_te_pass)
        
        # Top 10 / 20 命中
        sort_idx = np.argsort(-p18)
        top10 = sort_idx[:10]
        top20 = sort_idx[:20]
        
        top10_hit = int(y_te_pass[top10].sum())
        top20_hit = int(y_te_pass[top20].sum())
        
        # 阈值
        p85 = np.where(p18 >= 0.85)[0]
        p80 = np.where(p18 >= 0.80)[0]
        p70 = np.where(p18 >= 0.70)[0]
        
        # 真实 base rate (v1.4 通过的票里有多少正)
        base_rate = y_te_pass.mean() * 100 if len(y_te_pass) > 0 else 0
        
        result = {
            'date': test_date,
            'n_test_total': len(test), 'n_test_with_auc': len(X_te),
            'n_v14_pass': len(te_v14_pass),
            'n_pos_in_v14_pass': int(y_te_pass.sum()),
            'base_rate': base_rate,
            'top10_hit': top10_hit, 'top10_n': min(10, len(p18)),
            'top20_hit': top20_hit, 'top20_n': min(20, len(p18)),
            'p85_hit': int(y_te_pass[p85].sum()) if len(p85) > 0 else 0, 'p85_n': len(p85),
            'p80_hit': int(y_te_pass[p80].sum()) if len(p80) > 0 else 0, 'p80_n': len(p80),
            'p70_hit': int(y_te_pass[p70].sum()) if len(p70) > 0 else 0, 'p70_n': len(p70),
        }
        results.append(result)
        
        print(f'\n[{test_date}] v1.4 通过 {len(te_v14_pass)}/{len(X_te)} ({y_te_pass.sum()}+, base={base_rate:.1f}%)', flush=True)
        print(f'  Top 10: {top10_hit}/{min(10,len(p18))} ({top10_hit/min(10,len(p18))*100:.0f}%)', flush=True)
        print(f'  Top 20: {top20_hit}/{min(20,len(p18))} ({top20_hit/min(20,len(p18))*100:.0f}%)', flush=True)
        if len(p85) > 0:
            print(f'  P≥0.85: {result["p85_hit"]}/{result["p85_n"]} ({result["p85_hit"]/result["p85_n"]*100:.0f}%)', flush=True)
        if len(p80) > 0:
            print(f'  P≥0.80: {result["p80_hit"]}/{result["p80_n"]} ({result["p80_hit"]/result["p80_n"]*100:.0f}%)', flush=True)
    
    # 总结
    print('\n' + '='*60, flush=True)
    print('📊 v1.4 + v1.8 联动 walk-forward 总结:', flush=True)
    print('='*60, flush=True)
    print(f'\n  天数: {len(results)}', flush=True)
    
    top10 = [r['top10_hit']/r['top10_n']*100 for r in results]
    top20 = [r['top20_hit']/r['top20_n']*100 for r in results]
    p85 = [r['p85_hit']/r['p85_n']*100 for r in results if r['p85_n'] > 0]
    p80 = [r['p80_hit']/r['p80_n']*100 for r in results if r['p80_n'] > 0]
    base = [r['base_rate'] for r in results]
    
    print(f'  v1.4 通过的 base rate (这是模型起点): 平均 {np.mean(base):.1f}%', flush=True)
    print(f'  v1.8 重排后 Top 10: 平均 {np.mean(top10):.1f}%, 中位 {np.median(top10):.0f}%, 最差 {np.min(top10):.0f}%, 最好 {np.max(top10):.0f}%', flush=True)
    print(f'  v1.8 重排后 Top 20: 平均 {np.mean(top20):.1f}%', flush=True)
    if p85:
        print(f'  P≥0.85: 平均 {np.mean(p85):.1f}%, n_days={len(p85)}', flush=True)
    if p80:
        print(f'  P≥0.80: 平均 {np.mean(p80):.1f}%, n_days={len(p80)}', flush=True)
    
    # 提升 vs base rate
    lifts = [(r['top10_hit']/r['top10_n']*100) / r['base_rate'] for r in results if r['base_rate'] > 0]
    if lifts:
        print(f'\n  Top 10 vs base lift: 平均 {np.mean(lifts):.2f}x', flush=True)
    
    out = WS / 'backtest' / 'v14_v18_combined_walkforward.json'
    with open(out, 'w') as f:
        json.dump({'results': results, 
                   'summary': {
                       'top10_avg': float(np.mean(top10)),
                       'top20_avg': float(np.mean(top20)),
                       'base_rate_avg': float(np.mean(base)),
                       'lift_avg': float(np.mean(lifts)) if lifts else None,
                   }}, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
