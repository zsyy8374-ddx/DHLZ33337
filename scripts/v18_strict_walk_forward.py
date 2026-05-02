#!/usr/bin/env python3
"""v1.8 严格 walk-forward OOS — 验证 v1.8 多日稳健性
- 训练截止日 T: 用 [start, T-1] 的 events 训练
- 测试: T 当天的 events
- 滚动 T = 4-21 ~ 4-30
- 不让模型看到 T 当天的任何数据 (严格)
"""
import json, pickle, sys, os
from pathlib import Path
import numpy as np
from datetime import datetime
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


def build_features(events, auc_data):
    """给每个 event 拼 v1.8 35 维特征"""
    X, y, meta = [], [], []
    
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
    
    for e in events:
        d_t = e.get('d_t_date')
        if not d_t: continue
        # outcome: reversal = 1, failed/timeout = 0
        outcome = e.get('outcome', '')
        label = 1 if outcome == 'reversal' else 0
        
        # auc data for D_t
        auc = auc_data.get(d_t, {}).get(e['code'], {})
        if not auc: continue  # 没 auc 数据, 跳过
        
        feat = {fn: safe(e.get(fn, 0)) for fn in BASE_FEATURES}
        for fn in AUC_FEATURES:
            feat[fn] = safe(auc.get(fn, 0))
        
        # 衍生
        if feat['auc_chg'] > 0.5 and feat['auc_ratio'] > 1.5:
            feat['auc_strong_open'] = 1
        else:
            feat['auc_strong_open'] = 0
        feat['auc_zt_open'] = 1 if feat['auc_chg'] > 9.5 else 0
        
        X.append([feat[fn] for fn in BASE_FEATURES + AUC_FEATURES])
        y.append(label)
        meta.append({'code': e['code'], 'name': e.get('name'), 'd0_date': e['d0_date'], 'd_t_date': d_t})
    
    return np.array(X), np.array(y), meta, BASE_FEATURES + AUC_FEATURES


def train_v18(X_train, y_train):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    
    # 1:1 平衡
    pos_idx = np.where(y_train == 1)[0]
    neg_idx = np.where(y_train == 0)[0]
    if len(pos_idx) < 5 or len(neg_idx) < 5:
        return None
    
    np.random.seed(42)
    if len(neg_idx) > len(pos_idx):
        neg_idx_s = np.random.choice(neg_idx, len(pos_idx), replace=False)
    else:
        neg_idx_s = neg_idx
    train_idx = np.concatenate([pos_idx, neg_idx_s])
    np.random.shuffle(train_idx)
    
    X_t = X_train[train_idx]
    y_t = y_train[train_idx]
    
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


def main():
    print('🧪 v1.8 严格 walk-forward OOS', flush=True)
    
    # 加载所有 events + auc data
    with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
        all_events = json.load(f)['events']
    
    with open(WS / 'backtest' / 'v18_auc_data.json') as f:
        auc_data = json.load(f)
    
    print(f'  events: {len(all_events)}', flush=True)
    print(f'  auc dates: {len(auc_data)}', flush=True)
    
    # 按 D_t 排序
    all_events_with_dt = [e for e in all_events if e.get('d_t_date')]
    all_events_with_dt.sort(key=lambda x: x['d_t_date'])
    print(f'  events with d_t: {len(all_events_with_dt)}', flush=True)
    
    # 测试日期
    test_dates = ['2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24',
                  '2026-04-25', '2026-04-28', '2026-04-29', '2026-04-30']
    
    results_by_date = []
    
    for test_date in test_dates:
        train_events = [e for e in all_events_with_dt if e['d_t_date'] < test_date]
        test_events = [e for e in all_events_with_dt if e['d_t_date'] == test_date]
        
        if not train_events or not test_events:
            print(f'\n[{test_date}] 跳过 (train={len(train_events)}, test={len(test_events)})', flush=True)
            continue
        
        X_tr, y_tr, _, _ = build_features(train_events, auc_data)
        X_te, y_te, meta_te, features = build_features(test_events, auc_data)
        
        if len(X_tr) < 20 or len(X_te) < 5:
            print(f'\n[{test_date}] 数据不足 (tr={len(X_tr)}, te={len(X_te)})', flush=True)
            continue
        
        n_pos_tr = int(y_tr.sum())
        n_pos_te = int(y_te.sum())
        
        model = train_v18(X_tr, y_tr)
        if model is None:
            print(f'\n[{test_date}] 训练失败', flush=True)
            continue
        
        p_te = predict(model, X_te)
        
        # 排序并算 Top K 命中
        sorted_idx = np.argsort(-p_te)
        top10 = sorted_idx[:10] if len(p_te) >= 10 else sorted_idx
        top20 = sorted_idx[:20] if len(p_te) >= 20 else sorted_idx
        
        top10_hit = int(y_te[top10].sum())
        top20_hit = int(y_te[top20].sum())
        
        # 阈值 P≥0.85
        p85_idx = np.where(p_te >= 0.85)[0]
        p85_hit = int(y_te[p85_idx].sum()) if len(p85_idx) > 0 else 0
        
        # 阈值 P≥0.8
        p80_idx = np.where(p_te >= 0.8)[0]
        p80_hit = int(y_te[p80_idx].sum()) if len(p80_idx) > 0 else 0
        
        from sklearn.metrics import roc_auc_score
        try:
            auc = roc_auc_score(y_te, p_te) if len(set(y_te)) > 1 else None
        except:
            auc = None
        
        result = {
            'date': test_date,
            'n_train': len(X_tr), 'n_pos_train': n_pos_tr,
            'n_test': len(X_te), 'n_pos_test': n_pos_te,
            'auc': auc,
            'top10_hit': top10_hit, 'top10_n': min(10, len(p_te)),
            'top20_hit': top20_hit, 'top20_n': min(20, len(p_te)),
            'p85_hit': p85_hit, 'p85_n': len(p85_idx),
            'p80_hit': p80_hit, 'p80_n': len(p80_idx),
        }
        results_by_date.append(result)
        
        print(f'\n[{test_date}] tr={len(X_tr)} ({n_pos_tr}+) | te={len(X_te)} ({n_pos_te}+)', flush=True)
        if auc is not None:
            print(f'  AUC: {auc:.3f}', flush=True)
        print(f'  Top 10: {top10_hit}/{min(10,len(p_te))} ({top10_hit/min(10,len(p_te))*100:.0f}%)', flush=True)
        print(f'  Top 20: {top20_hit}/{min(20,len(p_te))} ({top20_hit/min(20,len(p_te))*100:.0f}%)', flush=True)
        if len(p85_idx) > 0:
            print(f'  P≥0.85: {p85_hit}/{len(p85_idx)} ({p85_hit/len(p85_idx)*100:.0f}%)', flush=True)
        if len(p80_idx) > 0:
            print(f'  P≥0.80: {p80_hit}/{len(p80_idx)} ({p80_hit/len(p80_idx)*100:.0f}%)', flush=True)
    
    # 总结
    print('\n' + '='*60, flush=True)
    print('📊 v1.8 严格 walk-forward OOS 总结:', flush=True)
    print('='*60, flush=True)
    
    aucs = [r['auc'] for r in results_by_date if r.get('auc') is not None]
    top10_rates = [r['top10_hit']/r['top10_n']*100 for r in results_by_date]
    top20_rates = [r['top20_hit']/r['top20_n']*100 for r in results_by_date]
    p85_rates = [r['p85_hit']/r['p85_n']*100 for r in results_by_date if r['p85_n'] > 0]
    p80_rates = [r['p80_hit']/r['p80_n']*100 for r in results_by_date if r['p80_n'] > 0]
    
    print(f'\n  天数: {len(results_by_date)}', flush=True)
    if aucs:
        print(f'  AUC: 平均 {np.mean(aucs):.3f}, 中位 {np.median(aucs):.3f}, 最差 {np.min(aucs):.3f}', flush=True)
    print(f'  Top 10 命中: 平均 {np.mean(top10_rates):.1f}%, 中位 {np.median(top10_rates):.0f}%, 最差 {np.min(top10_rates):.0f}%, 最好 {np.max(top10_rates):.0f}%', flush=True)
    print(f'  Top 20 命中: 平均 {np.mean(top20_rates):.1f}%, 中位 {np.median(top20_rates):.0f}%, 最差 {np.min(top20_rates):.0f}%, 最好 {np.max(top20_rates):.0f}%', flush=True)
    if p85_rates:
        print(f'  P≥0.85: 平均 {np.mean(p85_rates):.1f}%, 中位 {np.median(p85_rates):.0f}%, n_days={len(p85_rates)}', flush=True)
    if p80_rates:
        print(f'  P≥0.80: 平均 {np.mean(p80_rates):.1f}%, n_days={len(p80_rates)}', flush=True)
    
    # 详情逐日
    print(f'\n📋 逐日详情:', flush=True)
    for r in results_by_date:
        auc_s = f'{r["auc"]:.3f}' if r.get('auc') is not None else 'NA'
        print(f'  {r["date"]}: AUC={auc_s} Top10={r["top10_hit"]}/{r["top10_n"]} Top20={r["top20_hit"]}/{r["top20_n"]} P85={r["p85_hit"]}/{r["p85_n"]} P80={r["p80_hit"]}/{r["p80_n"]}', flush=True)
    
    # 落档
    out = WS / 'backtest' / 'v18_strict_walkforward.json'
    with open(out, 'w') as f:
        json.dump({
            'method': 'walk-forward strict (each day train on prior, test on current)',
            'results': results_by_date,
            'summary': {
                'n_days': len(results_by_date),
                'auc_avg': float(np.mean(aucs)) if aucs else None,
                'top10_avg': float(np.mean(top10_rates)),
                'top20_avg': float(np.mean(top20_rates)),
                'p85_avg': float(np.mean(p85_rates)) if p85_rates else None,
                'p80_avg': float(np.mean(p80_rates)) if p80_rates else None,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
