#!/usr/bin/env python3
"""v1.8 实战测试 v2: 4-30 真实涨停 (从腾讯日 K) — 不是只 v12 reversal"""
import json, pickle, urllib.request, time
import numpy as np
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WS / 'picks' / 'v18_sklearn_model.pkl', 'rb') as f:
    m = pickle.load(f)
lr = m['lr']; gb = m['gb']; scaler = m['scaler']
features = m['features']

with open(WS / 'backtest' / 'v18_auc_data.json') as f:
    auc = json.load(f)
day_4_30 = auc.get('2026-04-30', {})

# 4-29 v14 picks
with open(WS / 'picks' / 'reversal-v4-2026-04-29.json') as f:
    picks_4_29 = json.load(f).get('candidates', [])

# 拉这些股 4-30 chg
def get_4_30_chg(code):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
            bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
            for i, b in enumerate(bars):
                if b[0] == '2026-04-30' and i > 0:
                    today = float(b[2])
                    prev = float(bars[i-1][2])
                    return (today - prev) / prev * 100
    except Exception:
        return None
    return None

print('🌐 拉 4-29 候选股的 4-30 涨幅...')
chg_cache = {}
for i, p in enumerate(picks_4_29):
    code = p['code']
    chg_cache[code] = get_4_30_chg(code)
    if (i+1) % 50 == 0:
        print(f'  [{i+1}/{len(picks_4_29)}]')
    time.sleep(0.2)

# 涨停判断
def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5

zt_4_30 = {c for c in chg_cache if is_zt(next((p['name'] for p in picks_4_29 if p['code']==c), ''), chg_cache.get(c), c)}
print(f'\n📊 4-29 候选中 4-30 真涨停: {len(zt_4_30)}/{len(picks_4_29)}')

# 重新预测
def safe_float(v, d=0.0):
    if v is None: return d
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return d
        return f
    except: return d

def get_features_for_pick(pick, day_data):
    code = pick['code']
    if code not in day_data: return None
    rec = day_data[code]
    f = {}
    for fn in features[:16]:
        f[fn] = safe_float(pick.get(fn, 0))
    
    def g(k, default=None):
        for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
            if kk in rec:
                v = rec[kk]
                try:
                    fv = float(v)
                    return None if (np.isnan(fv) or np.isinf(fv)) else fv
                except: return default
        return default
    
    auc_buy = g('分时委买'); auc_sell = g('分时委卖'); auc_diff = g('分时委差')
    auc_ratio = g('分时多空比'); auc_close = g('分时收盘价:不复权')
    auc_amt = g('分时成交额'); auc_vol = g('分时成交量')
    auc_turn = g('分时换手率'); auc_chg = g('分时涨跌幅:前复权')
    auc_amp = g('分时振幅'); float_a = g('流通a股')
    
    f['auc_buy'] = safe_float(auc_buy); f['auc_sell'] = safe_float(auc_sell)
    f['auc_diff'] = safe_float(auc_diff); f['auc_ratio'] = safe_float(auc_ratio)
    f['auc_match_close'] = safe_float(auc_close); f['auc_amt'] = safe_float(auc_amt)
    f['auc_vol'] = safe_float(auc_vol); f['auc_turn'] = safe_float(auc_turn)
    f['auc_chg'] = safe_float(auc_chg); f['auc_amp'] = safe_float(auc_amp)
    
    f['auc_buy_to_float'] = (auc_buy*100/float_a*100) if (auc_buy and float_a and float_a>0) else 0
    f['auc_sell_to_float'] = (auc_sell*100/float_a*100) if (auc_sell and float_a and float_a>0) else 0
    if auc_amt and float_a and auc_close and float_a*auc_close > 0:
        f['auc_amt_to_mcap'] = auc_amt / (float_a*auc_close) * 100
    else: f['auc_amt_to_mcap'] = 0
    f['auc_strong_open'] = 1 if (auc_chg and auc_chg>0.5 and auc_ratio and auc_ratio>1.5) else 0
    f['auc_zt_open'] = 1 if (auc_chg and auc_chg>9.5) else 0
    return [f.get(fn, 0) for fn in features]

results = []
for p in picks_4_29:
    feat = get_features_for_pick(p, day_4_30)
    if feat is None: continue
    X = scaler.transform([feat])
    p_lr = float(lr.predict_proba(X)[0,1])
    p_gb = float(gb.predict_proba(X)[0,1])
    p_ens = 0.4*p_lr + 0.6*p_gb
    results.append({
        'code': p['code'], 'name': p['name'],
        'p_v18': p_ens, 'p_v17': p.get('lr_prob_with_boost', p.get('lr_prob')),
        'chg_4_30': chg_cache.get(p['code']),
        'is_zt': p['code'] in zt_4_30,
    })

# v1.8 排序
results.sort(key=lambda x: -x['p_v18'])
print(f'\n📊 v1.8 重排 Top 30:')
print(f'{"#":>3} | {"code":>6} | {"name":8} | {"P_v18":>6} | {"P_v17":>6} | {"chg":>6} | zt')
print('-'*70)
for i, r in enumerate(results[:30], 1):
    chg = r['chg_4_30']
    chg_s = f'{chg:+.2f}%' if chg is not None else 'NA'
    zt = '✅' if r['is_zt'] else '❌'
    print(f'{i:>3} | {r["code"]:>6} | {(r["name"] or "")[:8]:8} | {r["p_v18"]:>6.3f} | '
          f'{(r["p_v17"] or 0):>6.3f} | {chg_s:>6} | {zt}')

# 命中统计 (v1.8 vs v1.7)
print(f'\n=== v1.8 vs v1.7 实战对比 (4-29 → 4-30) ===')
for k in [10, 20, 30, 50]:
    v18_zt = sum(1 for r in results[:k] if r['is_zt'])
    # v1.7 排序
    r_v17 = sorted(results, key=lambda x: -(x['p_v17'] or 0))[:k]
    v17_zt = sum(1 for r in r_v17 if r['is_zt'])
    print(f'  Top {k:>3}: v1.8 命中 {v18_zt}/{k} ({v18_zt/k*100:.0f}%), v1.7 命中 {v17_zt}/{k} ({v17_zt/k*100:.0f}%)')

# 阈值
print(f'\n=== v1.8 阈值校准 (4-30 OOS) ===')
for thr in [0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5]:
    sub = [r for r in results if r['p_v18'] >= thr]
    if sub:
        zt = sum(1 for r in sub if r['is_zt'])
        print(f'  P≥{thr}: n={len(sub)}, 涨停 {zt} ({zt/len(sub)*100:.0f}%)')

# 落档
out = WS / 'backtest' / 'v18_test_4_30_real.json'
with open(out, 'w') as f:
    json.dump({'results': results, 'zt_4_30': sorted(zt_4_30)}, f, ensure_ascii=False, indent=2)
print(f'\n💾 落档: {out}')
