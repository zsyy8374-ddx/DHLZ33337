#!/usr/bin/env python3
"""v1.9 9:35 推送 — 用当天 9:25 + 9:30-9:35 5m K 重排, 推送极强档 P≥0.85
触发时间: 北京 09:36 (5m K 闭合后, 美西 18:36 PDT / 17:36 PST)
"""
import json, sys, time, pickle, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
import math
import warnings; warnings.filterwarnings('ignore')

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))


def get_today_str():
    return datetime.now(BJT).strftime('%Y-%m-%d')


def http_get(url, timeout=10, retries=2):
    for _ in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(1.0)
    return None


def get_5m_first(code, today_str):
    """拉今天 D_t 第一根 5m K (9:30-9:34) 及前一日收盘"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=5&ma=no&datalen=10'
    data = http_get(url)
    if not data: return None, None
    try:
        klines = json.loads(data)
        today_bars = [k for k in klines if k['day'].startswith(today_str)]
    except Exception:
        return None, None
    if not today_bars: return None, None
    
    url2 = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    daily_data = http_get(url2)
    prev_close = None
    if daily_data:
        try:
            d = json.loads(daily_data)
            bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
            for b in reversed(bars):
                if b[0] < today_str:
                    prev_close = float(b[2])
                    break
        except Exception: pass
    
    return today_bars[0], prev_close


def fetch_925_data(date_yyyymmdd, max_retry=5):
    import pywencai
    q = f'{date_yyyymmdd} 9:25 委买 委卖 委差 多空比 撮合价 成交额 流通股本 涨跌幅'
    print(f'[{datetime.now().strftime("%H:%M:%S")}] 拉 9:25: {q}', flush=True)
    df = None
    for retry in range(max_retry):
        df_try = pywencai.get(query=q, loop=True, timeout=180)
        if df_try is None or isinstance(df_try, dict) or not len(df_try):
            time.sleep(30); continue
        if len(df_try) < 1000:
            time.sleep(30); continue
        df = df_try; break
    if df is None:
        return None
    print(f'✅ 拉到 {len(df)} 行', flush=True)
    
    day_data = {}
    for _, row in df.iterrows():
        code = str(row.get('code', '')).strip()
        if not code: continue
        rec = {}
        for col in df.columns:
            if date_yyyymmdd in col:
                clean = col.replace(f'[{date_yyyymmdd} 09:25]', '').replace(f'[{date_yyyymmdd}]', '')
                try:
                    v = float(row[col])
                    rec[clean] = v
                except (TypeError, ValueError):
                    rec[clean] = row[col]
        day_data[code] = rec
    return day_data


def safe_float(v, default=0.0):
    if v is None: return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f): return default
        return f
    except (TypeError, ValueError): return default


def get_features(pick, day_data, bar_5m, prev_close, feature_names):
    code = pick.get('code')
    if not code or code not in day_data: return None
    if not bar_5m or not prev_close or prev_close <= 0: return None
    rec = day_data[code]
    
    f = {}
    for fn in feature_names[:16]:
        f[fn] = safe_float(pick.get(fn, 0))
    
    def g(k, default=None):
        for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
            if kk in rec:
                v = rec[kk]
                try:
                    fv = float(v)
                    return None if (math.isnan(fv) or math.isinf(fv)) else fv
                except (TypeError, ValueError): return default
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
    
    open_p = float(bar_5m['open'])
    high_5m = float(bar_5m['high'])
    close_5m = float(bar_5m['close'])
    vol_5m = float(bar_5m.get('volume', 0))
    f['pm_open_pct'] = (open_p / prev_close - 1) * 100
    f['pm_5m_high_pct'] = (high_5m / open_p - 1) * 100 if open_p > 0 else 0
    f['pm_5m_close_pct'] = (close_5m / open_p - 1) * 100 if open_p > 0 else 0
    f['pm_5m_amt_yi'] = vol_5m * close_5m / 1e8
    
    return [f.get(fn, 0) for fn in feature_names]


WATCH_LIST = {
    '600330': '天通股份',
    '002866': '传艺科技',
}


def format_msg(top, date_str, all_results=None):
    lines = [
        f'🚀 v1.9 [9:35 极强档] {date_str}',
        f'━━━━━━━━━━━━━━━━━━',
        f'📦 v1.9 model: OOS AUC 0.91 / 4-30 P≥0.85 命中 67%',
        f'⚙️ v1.4 候选 + 9:25 撮合 + 9:30-9:35 5m K → {len(top)} 只极强档',
        f'',
    ]
    for i, r in enumerate(top, 1):
        lines.append(f'{i}. {r["code"]} {r["name"]:<8} P={r["p_v19"]:.3f}')
        lines.append(f'   9:25 撮合 {r["auc_chg"]:+.2f}%, 5m 高 {r.get("pm_5m_high",0):+.2f}%, 5m 收 {r.get("pm_5m_close",0):+.2f}%')
    
    if all_results:
        watch_in_results = [r for r in all_results if r.get('code') in WATCH_LIST]
        if watch_in_results:
            lines.append('')
            lines.append('━━━ 你的持仓/关注 ━━━')
            for r in watch_in_results:
                p = r.get('p_v19', 0)
                rank = sorted(all_results, key=lambda x: -x.get('p_v19', 0)).index(r) + 1
                judge = '⭐强' if p >= 0.85 else '✅中等' if p >= 0.6 else '⚠️弱'
                lines.append(f'  {r["code"]} {r.get("name","")[:8]} #{rank} P={p:.3f} {judge}')
                lines.append(f'    9:25 撚合 {r.get("auc_chg",0):+.2f}%, 5m 高 {r.get("pm_5m_high",0):+.2f}%, 5m 收 {r.get("pm_5m_close",0):+.2f}%')
    
    lines.append('')
    lines.append('━━━ 操作建议 ━━━')
    lines.append('• 极强档 (P≥0.85): 4-30 OOS 实战命中 67%')
    lines.append('• 9:35 是 5m K 闭合点, 已确认开盘强势')
    lines.append('• 不破 5m 低点可考虑切入')
    lines.append('• ⚠️ 模型推荐, 不是投资建议')
    return '\n'.join(lines)


WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


def send_wechat(msg):
    import subprocess, re
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL, "--account", WX_ACCOUNT,
           "--target", WX_TARGET, "--message", msg, "--json"]
    for retry in range(3):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            mid = None
            if r.returncode == 0:
                m = re.search(r'\{[\s\S]*\}', r.stdout)
                if m:
                    try:
                        d = json.loads(m.group(0))
                        mid = d.get("payload", {}).get("result", {}).get("messageId")
                    except Exception: pass
            if mid:
                print(f"✅ 微信推送成功 mid={mid}", flush=True)
                return True
            print(f"⚠️ 微信 #{retry+1}: {r.stderr[-200:]}", flush=True)
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ 异常 #{retry+1}: {e}", flush=True)
            time.sleep(2)
    return False


def main():
    target_date = None
    dry_run = False
    for a in sys.argv[1:]:
        if a == 'dry': dry_run = True
        elif a.startswith('20'): target_date = a
    if not target_date:
        target_date = get_today_str()
    target_yyyymmdd = target_date.replace('-', '')
    
    print(f'🎯 v1.9 9:35 推送 — {target_date}', flush=True)
    
    pkl_path = WORKSPACE / 'picks' / 'v19_sklearn_model.pkl'
    if not pkl_path.exists():
        print(f'❌ 找不到 v1.9 model: {pkl_path}'); sys.exit(1)
    with open(pkl_path, 'rb') as f:
        m = pickle.load(f)
    lr = m['lr']; gb = m['gb']; scaler = m['scaler']
    features = m['features']
    print(f'✅ v1.9 model loaded ({len(features)} features)', flush=True)
    
    picks_dir = WORKSPACE / 'picks'
    candidate_files = sorted(picks_dir.glob('reversal-v4-*.json'), reverse=True)
    candidate_files = [f for f in candidate_files if f.name < f'reversal-v4-{target_date}.json']
    if not candidate_files:
        print(f'❌ 找不到 D-1 v1.4 候选'); sys.exit(1)
    latest_pick_file = candidate_files[0]
    print(f'📂 D-1 v1.4 picks: {latest_pick_file.name}', flush=True)
    with open(latest_pick_file) as f:
        candidates = json.load(f).get('candidates', [])
    print(f'   候选: {len(candidates)}', flush=True)
    
    day_data = fetch_925_data(target_yyyymmdd)
    if not day_data:
        print(f'❌ pywencai 失败'); sys.exit(1)
    
    print(f'\n🌐 拉 5m K (9:30-9:34) {len(candidates)} 只...', flush=True)
    bar5m_cache = {}
    for i, p in enumerate(candidates):
        bar, prev = get_5m_first(p['code'], target_date)
        if bar and prev: bar5m_cache[p['code']] = (bar, prev)
        if (i+1) % 50 == 0:
            print(f'  [{i+1}/{len(candidates)}] 5m: {len(bar5m_cache)}', flush=True)
        time.sleep(0.15)
    print(f'✅ 5m K 拉到 {len(bar5m_cache)}/{len(candidates)}', flush=True)
    
    import numpy as np
    results = []
    for pick in candidates:
        code = pick['code']
        if code not in bar5m_cache: continue
        bar_5m, prev_close = bar5m_cache[code]
        feat = get_features(pick, day_data, bar_5m, prev_close, features)
        if feat is None: continue
        X = scaler.transform([feat])
        p_lr = float(lr.predict_proba(X)[0, 1])
        p_gb = float(gb.predict_proba(X)[0, 1])
        p_ens = 0.4 * p_lr + 0.6 * p_gb
        
        rec = day_data[code]
        def g(k):
            for kk in [k, k.replace(':前复权','').replace(':不复权','')]:
                if kk in rec:
                    try: return float(rec[kk])
                    except: return 0
            return 0
        
        open_p = float(bar_5m['open'])
        high_5m = float(bar_5m['high'])
        close_5m = float(bar_5m['close'])
        
        results.append({
            'code': code, 'name': pick.get('name', ''),
            'p_v19': p_ens,
            'auc_chg': g('分时涨跌幅:前复权'),
            'pm_5m_high': (high_5m/open_p-1)*100 if open_p>0 else 0,
            'pm_5m_close': (close_5m/open_p-1)*100 if open_p>0 else 0,
        })
    
    results.sort(key=lambda x: -x['p_v19'])
    print(f'\n✅ 重排完成: {len(results)} 只', flush=True)
    
    top = [r for r in results if r['p_v19'] >= 0.85]
    print(f'📊 P≥0.85 极强档: {len(top)} 只', flush=True)
    
    out_path = WORKSPACE / 'picks' / f'reversal-v19-{target_date}.json'
    with open(out_path, 'w') as f:
        json.dump({
            'date': target_date, 'model_version': 'v1.9-ensemble-925-935',
            'd_minus_1_picks': latest_pick_file.name,
            'top_p085': len(top), 'all_results': results,
        }, f, ensure_ascii=False, indent=2)
    print(f'💾 落档: {out_path}', flush=True)
    
    if not top:
        print('⚠️ 今日无 P≥0.85 候选, 不推送')
        return
    
    msg = format_msg(top, target_date, all_results=results)
    print('\n' + '='*60)
    print(msg)
    print('='*60 + '\n')
    
    if dry_run:
        print('📭 dry-run, 跳过微信推送', flush=True)
        return
    
    ok = send_wechat(msg)
    print('✅ 微信推送' if ok else '⚠️ 微信推送失败', flush=True)


if __name__ == '__main__':
    main()
