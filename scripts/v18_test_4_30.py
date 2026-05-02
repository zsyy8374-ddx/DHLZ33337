#!/usr/bin/env python3
"""v1.8 实战测试: 4-30 当天 9:25 数据 → 预测哪些会涨停
数据来源: v18_auc_data.json 4-30 那一天 (5521 stocks)
比较: 跟 4-29 推送的 v1.7 候选 + 4-30 实际涨停, 看 v1.8 能否更准
"""
import json, pickle
import numpy as np
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

# 加载 model
with open(WS / 'picks' / 'v18_sklearn_model.pkl', 'rb') as f:
    m = pickle.load(f)
lr = m['lr']; gb = m['gb']; scaler = m['scaler']
features = m['features']
print(f'📦 model loaded ({len(features)} features)')

# 加载 4-30 9:25 数据
with open(WS / 'backtest' / 'v18_auc_data.json') as f:
    auc = json.load(f)
day_4_30 = auc.get('2026-04-30', {})
print(f'📊 4-30 stocks: {len(day_4_30)}')

# 加载 4-29 v14 picks (候选股)
picks_4_29_path = WS / 'picks' / 'reversal-v4-2026-04-29.json'
if picks_4_29_path.exists():
    with open(picks_4_29_path) as f:
        picks_4_29 = json.load(f).get('candidates', [])
    print(f'📊 4-29 v1.4 候选: {len(picks_4_29)}')
else:
    picks_4_29 = []

# 4-30 实际涨停股 (从 v18_events_enriched 找 D_t=2026-04-30 的)
with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
    enr = json.load(f)['events']
zt_4_30 = set()
for e in enr:
    if e.get('d_t_strict') == '2026-04-30' and e['outcome'] == 'reversal':
        zt_4_30.add(e['code'])
print(f'📊 4-30 实际反转 (≥涨停, v12 标注): {len(zt_4_30)}')

# 看 v1.4 候选股的 4-30 9:25 特征
def safe_float(v, default=0.0):
    if v is None: return default
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return default
        return f
    except (TypeError, ValueError): return default


def get_features_for_pick(pick, day_data):
    """从 v1.4 pick + 当天 9:25 数据 提取 v1.8 特征"""
    code = pick.get('code')
    if not code or code not in day_data: return None
    rec = day_data[code]
    
    # v1.7 特征 (从 pick 拿, 因为 pick 已含)
    f = {}
    for fn in features[:16]:  # V17_F
        f[fn] = safe_float(pick.get(fn, 0))
    
    # v1.8 9:25 特征 (从 day_data 拿)
    def g(k, default=None):
        for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
            if kk in rec:
                v = rec[kk]
                try: 
                    fv = float(v)
                    if np.isnan(fv) or np.isinf(fv): return default
                    return fv
                except (TypeError, ValueError): return default
        return default
    
    auc_buy = g('分时委买')
    auc_sell = g('分时委卖')
    auc_diff = g('分时委差')
    auc_ratio = g('分时多空比')
    auc_close = g('分时收盘价:不复权')
    auc_amt = g('分时成交额')
    auc_vol = g('分时成交量')
    auc_turn = g('分时换手率')
    auc_chg = g('分时涨跌幅:前复权')
    auc_amp = g('分时振幅')
    float_a = g('流通a股')
    
    f['auc_buy'] = safe_float(auc_buy)
    f['auc_sell'] = safe_float(auc_sell)
    f['auc_diff'] = safe_float(auc_diff)
    f['auc_ratio'] = safe_float(auc_ratio)
    f['auc_match_close'] = safe_float(auc_close)
    f['auc_amt'] = safe_float(auc_amt)
    f['auc_vol'] = safe_float(auc_vol)
    f['auc_turn'] = safe_float(auc_turn)
    f['auc_chg'] = safe_float(auc_chg)
    f['auc_amp'] = safe_float(auc_amp)
    
    if auc_buy is not None and float_a and float_a > 0:
        f['auc_buy_to_float'] = (auc_buy * 100) / float_a * 100
    else: f['auc_buy_to_float'] = 0
    
    if auc_sell is not None and float_a and float_a > 0:
        f['auc_sell_to_float'] = (auc_sell * 100) / float_a * 100
    else: f['auc_sell_to_float'] = 0
    
    if auc_amt is not None and float_a and auc_close:
        mcap = float_a * auc_close
        f['auc_amt_to_mcap'] = auc_amt / mcap * 100 if mcap > 0 else 0
    else: f['auc_amt_to_mcap'] = 0
    
    f['auc_strong_open'] = 1 if (auc_chg is not None and auc_chg > 0.5 and auc_ratio is not None and auc_ratio > 1.5) else 0
    f['auc_zt_open'] = 1 if (auc_chg is not None and auc_chg > 9.5) else 0
    
    return [f.get(fn, 0) for fn in features]


# 对 4-29 候选股做预测
print(f'\n🔮 用 v1.8 对 4-29 候选股重排:')
results = []
for pick in picks_4_29:
    code = pick.get('code')
    feat = get_features_for_pick(pick, day_4_30)
    if feat is None: continue
    X = scaler.transform([feat])
    p_lr = lr.predict_proba(X)[0, 1]
    p_gb = gb.predict_proba(X)[0, 1]
    p_ens = 0.4 * p_lr + 0.6 * p_gb
    results.append({
        'code': code, 'name': pick.get('name'),
        'p_v18': float(p_ens), 'p_v17': pick.get('lr_prob_with_boost', pick.get('lr_prob')),
        'is_zt_4_30': code in zt_4_30,
    })

results.sort(key=lambda x: -x['p_v18'])

print(f'\n📊 v1.8 重排 4-29 候选 ({len(results)} 只), Top 30:')
print(f'{"排名":>4} | {"code":>7} | {"name":8} | {"P_v18":>7} | {"P_v17":>7} | {"4-30":>4}')
print('-'*70)
top_zt = 0
for i, r in enumerate(results[:30], 1):
    flag = '✅' if r['is_zt_4_30'] else '❌'
    if r['is_zt_4_30']: top_zt += 1
    print(f'{i:>4} | {r["code"]:>7} | {(r["name"] or ""):8} | {r["p_v18"]:>7.3f} | '
          f'{(r["p_v17"] or 0):>7.3f} | {flag:>4}')

print(f'\n📊 v1.8 Top 10 命中: {sum(1 for r in results[:10] if r["is_zt_4_30"])}/10')
print(f'📊 v1.8 Top 20 命中: {sum(1 for r in results[:20] if r["is_zt_4_30"])}/20')
print(f'📊 v1.8 Top 30 命中: {top_zt}/30')

# 阈值
for thr in [0.85, 0.8, 0.75, 0.7, 0.65, 0.6]:
    n = sum(1 for r in results if r['p_v18'] >= thr)
    h = sum(1 for r in results if r['p_v18'] >= thr and r['is_zt_4_30'])
    if n > 0:
        print(f'  P_v18 ≥ {thr}: n={n}, 命中 {h} ({h/n*100:.1f}%)')

# 落档
out = WS / 'backtest' / 'v18_test_4_30.json'
with open(out, 'w') as f:
    json.dump({'results': results, 'zt_4_30': sorted(zt_4_30)}, f, ensure_ascii=False, indent=2)
print(f'\n💾 落档: {out}')
