"""给 v9 events 补 D_t 早盘特征 (集合竞价 + 5 分钟开盘)
策略:
- 只补 2025-12 之后的 events (新浪 5m K 覆盖 104 天)
- failed 事件没有 d_t_date, 用 d0 + 10 个交易日近似 (默认 D_t)
- 数据源: 新浪 vMS_KLine 5m, datalen=5000, 单股一次拉 ~104 天

新增字段 (D_t 早盘):
- pm_open_pct: D_t 开盘价 (= 5m bar [9:30-9:34] 的 open) 相对前一日收盘
- pm_5m_high_pct: D_t 9:30-9:34 5m bar 的 high 相对开盘
- pm_5m_close_pct: D_t 9:30-9:34 5m bar 的 close 相对开盘
- pm_5m_amt_yi: D_t 9:30-9:34 5m bar 总成交金额 (亿) -- vol * close
- pm_5_10m_high_pct: D_t 9:30-9:39 (前 2 根 5m bar) 高点相对开盘
- pm_strong_open: 1 if open >= 0.5 + 5_10m_high >= 3
- pm_weak_open: 1 if open < 0
- pm_open_red_5m: 1 if open >= 0.5 but 5m close < open (高开低走)
"""
import json, time, sys
from pathlib import Path
from urllib.request import urlopen, Request
from datetime import datetime, timedelta

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"


def http_get(url, timeout=15, retries=3):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(1.5 + attempt * 2)
    return None


def get_5m_klines(code, datalen=5000):
    """新浪 5m K, ~104 天历史"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=5&ma=no&datalen={datalen}'
    data = http_get(url)
    if not data: return []
    try:
        return json.loads(data)
    except Exception:
        return []


def get_daily_close(code, days=200):
    """取日 K close 用于反推 D_t-1 收盘"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,{days},qfq'
    data = http_get(url)
    if not data: return {}
    try:
        d = json.loads(data)
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        return {b[0]: float(b[2]) for b in bars}  # date → close
    except Exception:
        return {}


def calc_premarket(klines_5m, daily_map, dt_date):
    """从 5m bar + daily 算 D_t 早盘特征
    
    klines_5m 每根: {"day": "2026-04-30 09:35:00", "open":"10.32", "high":"10.79", "low":"10.31", "close":"10.36", "volume":"..."}
    9:35:00 那根 = 9:30-9:35 (含集合竞价)
    9:40:00 那根 = 9:35-9:40
    """
    # 找 D_t 那天的 9:35 bar (= 9:30-9:35)
    bar_930 = None
    bar_935 = None
    for k in klines_5m:
        day = k['day']
        if day.startswith(dt_date):
            tt = day.split(' ')[1] if ' ' in day else ''
            if tt == '09:35:00':
                bar_930 = k
            elif tt == '09:40:00':
                bar_935 = k
    if not bar_930:
        return None
    
    open_p = float(bar_930['open'])
    
    # 前收: 用日 K 找 D_t 之前最近一天
    sorted_dates = sorted(daily_map.keys())
    prev_close = None
    for i, dd in enumerate(sorted_dates):
        if dd >= dt_date and i > 0:
            prev_close = daily_map[sorted_dates[i-1]]
            break
        if dd == sorted_dates[-1] and dd < dt_date:
            prev_close = daily_map[dd]  # D_t 是 today, prev = last
    if prev_close is None and sorted_dates:
        # D_t 在 sorted_dates 末尾或之外
        for dd in reversed(sorted_dates):
            if dd < dt_date:
                prev_close = daily_map[dd]
                break
    if prev_close is None or prev_close <= 0:
        return None
    
    open_pct = (open_p / prev_close - 1) * 100
    high_5m = float(bar_930['high'])
    low_5m = float(bar_930['low'])
    close_5m = float(bar_930['close'])
    vol_5m = float(bar_930.get('volume', 0))
    amt_5m_yi = vol_5m * close_5m / 1e8
    
    high_5m_pct = (high_5m / open_p - 1) * 100
    close_5m_pct = (close_5m / open_p - 1) * 100
    
    # 9:35-9:40 的 high
    if bar_935:
        high_10m = max(high_5m, float(bar_935['high']))
    else:
        high_10m = high_5m
    high_10m_pct = (high_10m / open_p - 1) * 100
    
    return {
        "pm_open_pct": round(open_pct, 3),
        "pm_5m_high_pct": round(high_5m_pct, 3),
        "pm_5m_close_pct": round(close_5m_pct, 3),
        "pm_5m_amt_yi": round(amt_5m_yi, 4),
        "pm_10m_high_pct": round(high_10m_pct, 3),
        "pm_strong_open": 1 if open_pct >= 0.3 and high_10m_pct >= 3 else 0,
        "pm_weak_open": 1 if open_pct < 0 else 0,
        "pm_open_red_5m": 1 if open_pct >= 0.5 and close_5m < open_p else 0,
    }


def calc_dt_for_failed(e, all_events_by_code):
    """failed 事件没 d_t_date, 估算: D0 + 10 交易日 (反转期最大窗口)"""
    if e['outcome'] == 'reversal':
        return e.get('d_t_date')
    # failed: 用 d0 + 10 工作日 (粗近似交易日)
    d0 = datetime.strptime(e['d0_date'], '%Y-%m-%d')
    candidates_dates = []
    for ev in all_events_by_code.get(e['code'], []):
        if ev.get('d_t_date') and ev['d0_date'] >= e['d0_date']:
            candidates_dates.append(ev['d_t_date'])
    
    target = d0 + timedelta(days=14)  # 大概 10 交易日
    return target.strftime('%Y-%m-%d')


def main():
    src = BACKTEST_DIR / "reversal-events-2026-05-01-v9-with-pre10.json"
    with open(src) as f:
        events = json.load(f)['events']
    
    # 只补 2025-12 后 (新浪 5m 能覆盖)
    target = [e for e in events if e['d0_date'] >= '2025-12-01']
    print(f"📊 全量: {len(events)}, 待补 (≥2025-12): {len(target)}")
    
    by_code = {}
    for e in events:
        by_code.setdefault(e['code'], []).append(e)
    
    target_codes = sorted(set(e['code'] for e in target))
    print(f"📊 unique codes: {len(target_codes)}")
    
    ckpt_path = BACKTEST_DIR / "v10_pm_ckpt.json"
    done_codes = set()
    enriched_results = []  # list of dicts (d0_date, code, pm fields)
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        done_codes = set(ckpt.get("done", []))
        enriched_results = ckpt.get("enriched", [])
        print(f"♻️ checkpoint: done {len(done_codes)} codes, {len(enriched_results)} pm rows")
    
    fail_count = 0
    skip_count = 0
    t0 = time.time()
    for i, code in enumerate(target_codes):
        if code in done_codes:
            continue
        klines = get_5m_klines(code, datalen=5000)
        daily = get_daily_close(code, days=200)
        if not klines or not daily:
            done_codes.add(code)
            fail_count += len([e for e in by_code[code] if e in target])
            time.sleep(0.4)
            continue
        
        # 拿 D_t (reversal 用 d_t_date, failed 估算)
        for e in by_code[code]:
            if e not in target: continue
            dt_date = e.get('d_t_date')
            if not dt_date and e['outcome'] == 'failed':
                dt_date = calc_dt_for_failed(e, by_code)
            if not dt_date:
                skip_count += 1
                continue
            pm = calc_premarket(klines, daily, dt_date)
            if pm:
                pm['code'] = code
                pm['d0_date'] = e['d0_date']
                pm['outcome'] = e['outcome']
                pm['d_t_date'] = dt_date
                enriched_results.append(pm)
            else:
                skip_count += 1
        done_codes.add(code)
        time.sleep(0.5)  # 新浪频率限制
        
        if (i+1) % 30 == 0:
            elapsed = time.time() - t0
            speed = (i+1) / elapsed if elapsed > 0 else 0
            eta = (len(target_codes) - i - 1) / max(speed, 0.01)
            with open(ckpt_path, "w") as f:
                json.dump({"done": list(done_codes), "enriched": enriched_results}, f)
            print(f"  [{i+1}/{len(target_codes)}] enriched={len(enriched_results)} fail={fail_count} skip={skip_count} speed={speed*60:.1f}/分 ETA={eta/60:.1f}分", flush=True)
    
    out_path = BACKTEST_DIR / "reversal-events-2026-05-01-v10-with-pm.json"
    
    # merge: 把 pm 字段合到原 events 里
    pm_by_key = {(r['code'], r['d0_date']): r for r in enriched_results}
    merged = []
    for e in events:
        key = (e['code'], e['d0_date'])
        if key in pm_by_key:
            e_new = dict(e)
            e_new.update(pm_by_key[key])
            merged.append(e_new)
        else:
            merged.append(e)
    
    with open(out_path, 'w') as f:
        json.dump({"events": merged, "n_orig": len(events), "n_with_pm": len(enriched_results)}, f, ensure_ascii=False)
    print(f"\n✅ 落档: {out_path.name}")
    print(f"   全量 {len(events)} 事件, {len(enriched_results)} 有 pm 数据 ({len(enriched_results)/len(events)*100:.1f}%)")
    print(f"   失败 {fail_count}, 跳过 {skip_count}")
    print(f"   耗时 {(time.time()-t0)/60:.1f} 分钟")
    
    if ckpt_path.exists():
        ckpt_path.unlink()


if __name__ == "__main__":
    main()
