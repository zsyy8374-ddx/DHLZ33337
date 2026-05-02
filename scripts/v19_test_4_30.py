#!/usr/bin/env python3
"""v1.9 4-30 实战测试: 拉真实 4-30 5m K + 9:25 → 跟 v1.8 比较"""
import json, pickle, urllib.request, time
import numpy as np
import math
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WS / 'picks' / 'v19_sklearn_model.pkl', 'rb') as f:
    m = pickle.load(f)
lr = m['lr']; gb = m['gb']; scaler = m['scaler']
features = m['features']

# 加载 4-29 v1.4 候选
with open(WS / 'picks' / 'reversal-v4-2026-04-29.json') as f:
    picks_4_29 = json.load(f).get('candidates', [])

# 加载 9:25 数据 (4-30)
with open(WS / 'backtest' / 'v18_auc_data.json') as f:
    auc = json.load(f)
day_4_30 = auc.get('2026-04-30', {})

# 拉 4-29 候选股的 4-30 5m K (9:30-9:35) + 4-30 chg
def get_5m_first(code):
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=5&ma=no&datalen=10'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        # 找 4-30 第 1 根 5m K
        bars_4_30 = [b for b in data if b['day'].startswith('2026-04-30')]
        if not bars_4_30: return None
        return bars_4_30[0]
    except Exception:
        return None


def get_4_30_chg(code):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        bars = data.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        prev_close = None
        for i, b in enumerate(bars):
            if b[0] == '2026-04-30' and i > 0:
                today = float(b[2])
                prev = float(bars[i-1][2])
                return (today - prev) / prev * 100, prev
        return None, None
    except Exception:
        return None, None


print('🌐 拉 4-29 候选股的 4-30 5m K + chg (332 只)...')
data_5m = {}; chg_data = {}
for i, p in enumerate(picks_4_29):
    code = p['code']
    bar = get_5m_first(code)
    if bar: data_5m[code] = bar
    chg, prev = get_4_30_chg(code)
    chg_data[code] = (chg, prev)
    if (i+1) % 50 == 0:
        print(f'  [{i+1}/{len(picks_4_29)}], 5m={len(data_5m)}, chg={sum(1 for v in chg_data.values() if v[0] is not None)}')
    time.sleep(0.15)

print(f'\n📊 5m K 拉到: {len(data_5m)}/{len(picks_4_29)}')

# 涨停判断
def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5

zt_4_30 = {p['code'] for p in picks_4_29 if is_zt(p.get('name'), chg_data.get(p['code'], (None, None))[0], p['code'])}
print(f'4-30 实涨停: {len(zt_4_30)}/{len(picks_4_29)}')

# 算 v1.9 特征
def safe_float(v, d=0.0):
    if v is None: return d
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f): return d
        return f
    except: return d

def get_features(pick):
    code = pick['code']
    if code not in day_4_30 or code not in data_5m: return None
    
    chg, prev_close = chg_data.get(code, (None, None))
    if not prev_close: return None
    bar_5m = data_5m[code]
    
    # v17_F (16 维) — 从 pick 拿
    f = {}
    for fn in features[:16]:
        f[fn] = safe_float(pick.get(fn, 0))
    
    # v18_NEW (15 维) — 从 day_4_30 算
    rec = day_4_30[code]
    def g(k, default=None):
        for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
            if kk in rec:
                v = rec[kk]
                try:
                    fv = float(v)
                    return None if (math.isnan(fv) or math.isinf(fv)) else fv
                except: return default
        return default
    
    auc_buy = g('分时委买'); auc_sell = g('分时委卖')
    auc_diff = g('分时委差'); auc_ratio = g('分时多空比')
    auc_close = g('分时收盘价:不复权'); auc_amt = g('分时成交额')
    auc_vol = g('分时成交量'); auc_turn = g('分时换手率')
    auc_chg = g('分时涨跌幅:前复权'); auc_amp = g('分时振幅')
    float_a = g('流通a股')
    
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
    
    # v19_NEW (4 维) — 从 5m bar 算
    open_p = float(bar_5m['open'])
    high_5m = float(bar_5m['high'])
    close_5m = float(bar_5m['close'])
    vol_5m = float(bar_5m.get('volume', 0))
    
    f['pm_open_pct'] = (open_p / prev_close - 1) * 100
    f['pm_5m_high_pct'] = (high_5m / open_p - 1) * 100 if open_p > 0 else 0
    f['pm_5m_close_pct'] = (close_5m / open_p - 1) * 100 if open_p > 0 else 0
    f['pm_5m_amt_yi'] = vol_5m * close_5m / 1e8
    
    return [f.get(fn, 0) for fn in features]


print('\n🔮 v1.9 重排...')
results = []
for p in picks_4_29:
    feat = get_features(p)
    if feat is None: continue
    X = scaler.transform([feat])
    p_lr = float(lr.predict_proba(X)[0,1])
    p_gb = float(gb.predict_proba(X)[0,1])
    p_ens = 0.4*p_lr + 0.6*p_gb
    results.append({
        'code': p['code'], 'name': p['name'],
        'p_v19': p_ens,
        'p_v17': p.get('lr_prob_with_boost', p.get('lr_prob')),
        'chg_4_30': chg_data.get(p['code'], (None, None))[0],
        'is_zt': p['code'] in zt_4_30,
    })

results.sort(key=lambda x: -x['p_v19'])

print(f'\n📊 v1.9 重排 Top 20:')
print(f'{"#":>3} | {"code":>6} | {"name":8} | {"P_v19":>6} | {"chg":>6} | zt')
print('-'*60)
for i, r in enumerate(results[:20], 1):
    chg = r['chg_4_30']
    chg_s = f'{chg:+.2f}%' if chg is not None else 'NA'
    zt = '✅' if r['is_zt'] else '❌'
    print(f'{i:>3} | {r["code"]:>6} | {(r["name"] or "")[:8]:8} | {r["p_v19"]:>6.3f} | {chg_s:>6} | {zt}')

print(f'\n=== v1.9 vs v1.8 vs v1.7 实战 (4-29 → 4-30) ===')

# 加载 v1.8 results
with open(WS / 'backtest' / 'v18_test_4_30_real.json') as f:
    v18_results = json.load(f)['results']

for k in [10, 20, 30, 50]:
    v19_zt = sum(1 for r in results[:k] if r['is_zt'])
    v18_top = sorted(v18_results, key=lambda x: -x.get('p_v18', 0))[:k]
    v18_zt = sum(1 for r in v18_top if r.get('is_zt'))
    v17_top = sorted(v18_results, key=lambda x: -(x.get('p_v17') or 0))[:k]
    v17_zt = sum(1 for r in v17_top if r.get('is_zt'))
    print(f'  Top {k:>3}: v1.9={v19_zt}/{k}({v19_zt/k*100:.0f}%), v1.8={v18_zt}/{k}({v18_zt/k*100:.0f}%), v1.7={v17_zt}/{k}({v17_zt/k*100:.0f}%)')

print(f'\n=== v1.9 阈值实战 ===')
for thr in [0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6]:
    sub = [r for r in results if r['p_v19'] >= thr]
    if sub:
        zt = sum(1 for r in sub if r['is_zt'])
        print(f'  P≥{thr}: n={len(sub)}, 涨停 {zt} ({zt/len(sub)*100:.0f}%)')

# 落档
out = WS / 'backtest' / 'v19_test_4_30_real.json'
with open(out, 'w') as f:
    json.dump({'results': results}, f, ensure_ascii=False, indent=2)
print(f'\n💾 落档: {out}')
