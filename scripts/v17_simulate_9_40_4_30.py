"""模拟 4-30 早上 9:40 用 v1.7 给 4-29 推送的候选重排
- 4-29 推送 332 候选
- 给每个候选拉 4-30 早盘 5m (pm 特征)
- 给每个候选拉 D0 涨停板成交 (d0zt, 用候选的 d0_date)
- v1.7 集成打分 → 看 vs v1.4 的命中
"""
import json, sys, math, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from pathlib import Path
from urllib.request import urlopen, Request
from reversal_lr_v4 import normalize, predict
from lr_v17_with_pm_d0zt import extract_v17

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')


def http_get(url, timeout=12, retries=2):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(1.0 + attempt)
    return None


def get_5m_klines(code, datalen=5000):
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=5&ma=no&datalen={datalen}'
    data = http_get(url)
    if not data: return []
    try:
        return json.loads(data)
    except Exception:
        return []


def get_daily_close(code, days=200):
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,{days},qfq'
    data = http_get(url)
    if not data: return {}
    try:
        d = json.loads(data)
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        return {b[0]: float(b[2]) for b in bars}
    except Exception:
        return {}


def calc_pm(klines_5m, dt_date, daily_map):
    dt_bars = [k for k in klines_5m if k['day'].startswith(dt_date)]
    if len(dt_bars) < 1: return None
    bar_930 = dt_bars[0]
    open_p = float(bar_930['open'])
    
    sorted_dates = sorted(daily_map.keys())
    prev_close = None
    for dd in reversed(sorted_dates):
        if dd < dt_date:
            prev_close = daily_map[dd]
            break
    if not prev_close: return None
    
    open_pct = (open_p / prev_close - 1) * 100
    high_5m = float(bar_930['high'])
    close_5m = float(bar_930['close'])
    vol_5m = float(bar_930.get('volume', 0))
    amt_5m_yi = vol_5m * close_5m / 1e8
    high_5m_pct = (high_5m / open_p - 1) * 100
    close_5m_pct = (close_5m / open_p - 1) * 100
    
    if len(dt_bars) >= 2:
        high_10m = max(high_5m, float(dt_bars[1]['high']))
    else:
        high_10m = high_5m
    high_10m_pct = (high_10m / open_p - 1) * 100
    
    return {
        "pm_open_pct": round(open_pct, 3),
        "pm_5m_high_pct": round(high_5m_pct, 3),
        "pm_5m_close_pct": round(close_5m_pct, 3),
        "pm_10m_high_pct": round(high_10m_pct, 3),
        "pm_5m_amt_yi": round(amt_5m_yi, 4),
        "pm_strong_open": 1 if open_pct >= 0.3 and high_10m_pct >= 3 else 0,
        "pm_weak_open": 1 if open_pct < 0 else 0,
        "pm_open_red_5m": 1 if open_pct >= 0.5 and close_5m < open_p else 0,
    }


def calc_d0zt(klines_5m, d0_date):
    d0_bars = [k for k in klines_5m if k['day'].startswith(d0_date)]
    if len(d0_bars) < 30: return None
    day_high = max(float(k['high']) for k in d0_bars)
    locked_idx = None
    for i, k in enumerate(d0_bars):
        if abs(float(k['close']) - day_high) < 0.005:
            locked_idx = i
            break
    if locked_idx is None:
        return {"d0_zt_lock_pct": 1.0, "d0_zt_after_amt_yi": 0, "d0_zt_after_amt_pct": 0,
                "d0_zt_lock_strength": 0, "d0_strong_lock": 0, "d0_weak_lock": 1, "d0_unsealed": 1}
    n_bars = len(d0_bars)
    after_bars = d0_bars[locked_idx + 1:]
    after_vol = sum(float(k['volume']) for k in after_bars)
    after_amt_yi = after_vol * day_high / 1e8
    day_total_vol = sum(float(k['volume']) for k in d0_bars)
    after_amt_pct = after_vol / day_total_vol if day_total_vol > 0 else 0
    locked_bars = sum(1 for k in d0_bars[locked_idx:] if abs(float(k['close']) - day_high) < 0.005)
    lock_strength = locked_bars / max(1, n_bars - locked_idx)
    lock_pct = locked_idx / n_bars
    return {
        "d0_zt_lock_pct": round(lock_pct, 3),
        "d0_zt_after_amt_yi": round(after_amt_yi, 4),
        "d0_zt_after_amt_pct": round(after_amt_pct, 3),
        "d0_zt_lock_strength": round(lock_strength, 3),
        "d0_strong_lock": 1 if (lock_pct < 0.6 and lock_strength >= 0.8) else 0,
        "d0_weak_lock": 1 if (lock_pct > 0.85 or lock_strength < 0.6) else 0,
        "d0_unsealed": 0,
    }


# 加载 v1.7 模型
with open(WORKSPACE / 'picks' / 'lr_v17_ensemble_model.json') as f:
    model = json.load(f)

cont_keys = model['cont_keys']
mu = model['feature_means']; sd = model['feature_stds']
w = model['weights']; b = model['bias']
gbdt_base, gbdt_trees, gbdt_lr = model['gbdt'][0], model['gbdt'][1], model['gbdt'][2]


def predict_v17(features):
    f_norm = {k:((v-mu[k])/sd[k] if k in cont_keys else v) for k,v in features.items()}
    z = b
    for k, v in f_norm.items(): z += w.get(k, 0) * v
    p_lr = 1 / (1 + math.exp(-z))
    
    z_gb = gbdt_base
    for tree in gbdt_trees:
        node = tree
        while node[0] == 'node':
            _, feat, thr, lc, rc = node
            v = features.get(feat, 0)
            node = lc if v < thr else rc
        z_gb += gbdt_lr * node[1]
    p_gb = 1 / (1 + math.exp(-z_gb))
    
    return 0.6 * p_lr + 0.4 * p_gb, p_lr, p_gb


# 加载 4-29 推送 + 4-30 实战
with open(WORKSPACE / 'picks' / 'reversal_hits_full.jsonl') as f:
    for line in f:
        row = json.loads(line)
        if row.get('pick_date') == '2026-04-29':
            data = row; break

with open(WORKSPACE / 'picks' / 'reversal-v4-2026-04-29.json') as g:
    full = json.load(g)
cand_by_code = {c['code']: c for c in full['candidates']}

results_by_code = {r['code']: r for r in data['results']}

print(f"📊 4-29 推送 {len(data['results'])} 只, 4-30 涨停 {sum(1 for r in data['results'] if r.get('is_zt'))}")
print(f"   开始模拟 4-30 早上 9:40 v1.7 重扫...")

recent_5d, recent_10d, recent_20d = 0.28, 0.39, 0.45

# 只对 lr_prob>=0.4 的扫 (跟生产一致)
to_scan = [r for r in data['results'] if r.get('lr_prob', 0) >= 0.4]
print(f"   待扫描: {len(to_scan)}")

scored = []
for i, r in enumerate(to_scan):
    cand = cand_by_code.get(r['code'])
    if not cand: continue
    
    klines = get_5m_klines(r['code'])
    daily_map = get_daily_close(r['code'])
    if not klines or not daily_map:
        time.sleep(0.4); continue
    
    pm = calc_pm(klines, '2026-04-30', daily_map)  # 4-30 早盘
    d0zt = calc_d0zt(klines, cand.get('d0_date', ''))  # D0 当天涨停板
    
    e = {
        'd0_chg': cand.get('d0_chg', 10), 'd0_lbc': cand.get('d0_lbc', 1),
        'callback_pct': cand.get('callback_pct', 0), 'min_close_pct': cand.get('min_close_pct', 0),
        'broke_ma5': cand.get('broke_ma5', False), 'broke_ma10': cand.get('broke_ma10', False),
        'vol_callback_ratio': cand.get('vol_callback_ratio', 0),
        'cb5_main_avg': cand.get('cb5_main_avg', 0), 'cb3_main_avg': cand.get('cb3_main_avg', 0),
        'cb1_main_avg': cand.get('cb1_main_avg', 0), 'cb5_in_ratio': cand.get('cb5_in_ratio', 0),
        'd0_main_flow': cand.get('d0_main_flow', 0), 'pre_d0_5d_main_avg': cand.get('pre_d0_5d_main_avg', 0),
        'd0_date': cand.get('d0_date', ''),
        'outcome': 'na'
    }
    if pm: e.update(pm)
    if d0zt: e.update(d0zt)
    
    f = extract_v17(e)
    f['recent_5d_rev_rate'] = recent_5d
    f['recent_10d_rev_rate'] = recent_10d
    f['recent_20d_rev_rate'] = recent_20d
    
    p_ens, p_lr, p_gb = predict_v17(f)
    
    scored.append({
        'code': r['code'],
        'name': r.get('name', ''),
        'p_v11': r['lr_prob'],
        'p_v17': p_ens,
        'p_v17_lr': p_lr,
        'p_v17_gb': p_gb,
        'is_zt': r.get('is_zt', False),
        'today_chg': r.get('today_chg', 0),
        'today_high': r.get('today_high', 0),
        'has_pm': pm is not None,
        'pm_open_pct': e.get('pm_open_pct'),
        'pm_10m_high_pct': e.get('pm_10m_high_pct'),
        'pm_5m_amt_yi': e.get('pm_5m_amt_yi'),
        'd0_zt_lock_pct': e.get('d0_zt_lock_pct'),
    })
    
    time.sleep(0.4)
    if (i+1) % 30 == 0:
        print(f"   [{i+1}/{len(to_scan)}] 已扫 {len(scored)}", flush=True)

# 落档
out = WORKSPACE / 'picks' / 'v17_simulate_9_40_4_30.json'
with open(out, 'w') as f:
    json.dump({"date": "2026-04-30", "n_scored": len(scored), "scored": scored}, f, ensure_ascii=False)
print(f"\n✅ 落档: {out.name}, 扫到 {len(scored)}")

# 分析
with_pm = sum(1 for s in scored if s['has_pm'])
zt_total = sum(1 for s in scored if s['is_zt'])
print(f"\n=== 总结: scored {len(scored)}, has_pm {with_pm}, 4-30 涨停 {zt_total} ===")

P_high = model['P_high']
P_mid = model['P_mid']
scored.sort(key=lambda x: -x['p_v17'])

tier_a = [s for s in scored if s['p_v17'] >= P_high]
tier_b = [s for s in scored if P_mid <= s['p_v17'] < P_high]
tier_c = [s for s in scored if 0.55 <= s['p_v17'] < P_mid]

print(f"\n=== v1.7 9:40 二次扫描分档 ===")
print(f"  极强 (P≥{P_high}): {len(tier_a)} 只, 涨停 {sum(1 for s in tier_a if s['is_zt'])}, 平均 {sum(s['today_chg'] for s in tier_a)/max(1,len(tier_a)):+.2f}%")
print(f"  强档 ({P_mid}~{P_high}): {len(tier_b)} 只, 涨停 {sum(1 for s in tier_b if s['is_zt'])}, 平均 {sum(s['today_chg'] for s in tier_b)/max(1,len(tier_b)):+.2f}%")
print(f"  关注 (0.55~{P_mid}): {len(tier_c)} 只, 涨停 {sum(1 for s in tier_c if s['is_zt'])}")

print(f"\n=== v1.7 极强档详情 ===")
for s in sorted(tier_a, key=lambda x: -x['p_v17']):
    flag = "✅" if s['is_zt'] else "❌"
    pm_info = f"开{s.get('pm_open_pct',0):+.1f}% 10m高{s.get('pm_10m_high_pct',0):+.1f}% 量{s.get('pm_5m_amt_yi',0):.1f}亿"
    print(f"  {s['code']} {s['name']:8s} v1.7={s['p_v17']:.3f} {flag} {s['today_chg']:+5.2f}% (最高 {s['today_high']:+.2f}%) | {pm_info}")

print(f"\n=== v1.7 强档详情 ===")
for s in sorted(tier_b, key=lambda x: -x['p_v17']):
    flag = "✅" if s['is_zt'] else "❌"
    pm_info = f"开{s.get('pm_open_pct',0):+.1f}% 10m高{s.get('pm_10m_high_pct',0):+.1f}%"
    print(f"  {s['code']} {s['name']:8s} v1.7={s['p_v17']:.3f} {flag} {s['today_chg']:+5.2f}% (最高 {s['today_high']:+.2f}%) | {pm_info}")
