"""集合竞价代理特征 (auction proxy)
原理: 5m K 没有 9:15-9:25 独立 bar, 但 9:30 那根 5m bar (= 9:30-9:34:59) 包含:
  - 集合竞价撮合后的成交 (9:25 那一笔, 量大表示隔夜单大)
  - 9:30-9:35 连续竞价
9:30-9:35 vol / 9:35-9:40 vol 高 = 集合竞价相对强 = 隔夜单大

新特征:
- au_amt_yi: 9:30-9:35 5m bar 成交 (亿)
- au_amt_ratio: au_amt / 9:35-9:40 amt
- au_amt_pct_day: 9:30-9:35 amt / 当日总 amt (越大早盘越爆)
- au_strong: 1 if au_amt_pct_day >= 0.15 (早盘已成交 ≥15%)
- au_amt_5_15min: 9:30-9:45 (前 3 根) amt 总和 (亿) 
- au_amt_morn: 9:30-10:00 (前 6 根) amt 总和 (亿)

⚠️ 这些跟 pm_* 部分重叠, 但不同 — pm 关注价格, au 关注量
"""
import json, time
from pathlib import Path
from urllib.request import urlopen, Request

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
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=5&ma=no&datalen={datalen}'
    data = http_get(url)
    if not data: return []
    try:
        return json.loads(data)
    except Exception:
        return []


def calc_auction(klines_5m, dt_date):
    dt_bars = [k for k in klines_5m if k['day'].startswith(dt_date)]
    if len(dt_bars) < 6:
        return None
    
    # 5m bar 标识时间是结束时间
    # bars[0] = 9:35:00 = 9:30-9:35 (含集合竞价撮合后)
    # bars[1] = 9:40:00 = 9:35-9:40
    
    def bar_amt(b):
        return float(b['volume']) * float(b['close']) / 1e8
    
    au_amt = bar_amt(dt_bars[0])
    next_amt = bar_amt(dt_bars[1])
    
    day_amt = sum(bar_amt(b) for b in dt_bars)
    
    amt_5_15min = sum(bar_amt(b) for b in dt_bars[:3])  # 前 3 根 = 0-15 分钟
    amt_morn = sum(bar_amt(b) for b in dt_bars[:6])  # 前 6 根 = 0-30 分钟
    
    return {
        "au_amt_yi": round(au_amt, 4),
        "au_amt_ratio": round(au_amt / next_amt, 3) if next_amt > 0 else 0,
        "au_amt_pct_day": round(au_amt / day_amt, 3) if day_amt > 0 else 0,
        "au_strong": 1 if au_amt > 0 and day_amt > 0 and au_amt / day_amt >= 0.15 else 0,
        "au_amt_5_15min": round(amt_5_15min, 4),
        "au_amt_morn": round(amt_morn, 4),
        "au_morn_pct_day": round(amt_morn / day_amt, 3) if day_amt > 0 else 0,
    }


def main():
    src = BACKTEST_DIR / "reversal-events-2026-05-01-v9-with-pre10.json"
    with open(src) as f:
        events = json.load(f)['events']
    
    target = [e for e in events if e['d0_date'] >= '2025-12-01']
    by_code = {}
    for e in events:
        by_code.setdefault(e['code'], []).append(e)
    
    target_codes = sorted(set(e['code'] for e in target))
    print(f"📊 待补: {len(target)} events, {len(target_codes)} codes")
    
    ckpt_path = BACKTEST_DIR / "v12_auction_ckpt.json"
    done_codes = set()
    enriched_results = []
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        done_codes = set(ckpt.get("done", []))
        enriched_results = ckpt.get("enriched", [])
        print(f"♻️ ckpt: done {len(done_codes)} codes, {len(enriched_results)} rows")
    
    fail_count = 0
    skip_count = 0
    t0 = time.time()
    for i, code in enumerate(target_codes):
        if code in done_codes: continue
        klines = get_5m_klines(code)
        if not klines:
            done_codes.add(code)
            time.sleep(0.5)
            continue
        for e in by_code[code]:
            if e not in target: continue
            # 用 D_t 日期 (reversal: d_t_date, failed: d0+10 工作日)
            from datetime import datetime, timedelta
            if e['outcome'] == 'reversal':
                dt_date = e.get('d_t_date')
            else:
                d0 = datetime.strptime(e['d0_date'], '%Y-%m-%d')
                dt_date = (d0 + timedelta(days=14)).strftime('%Y-%m-%d')
            if not dt_date:
                skip_count += 1
                continue
            f = calc_auction(klines, dt_date)
            if f:
                f['code'] = code
                f['d0_date'] = e['d0_date']
                enriched_results.append(f)
            else:
                skip_count += 1
        done_codes.add(code)
        time.sleep(0.5)
        
        if (i+1) % 30 == 0:
            elapsed = time.time() - t0
            with open(ckpt_path, "w") as f:
                json.dump({"done": list(done_codes), "enriched": enriched_results}, f)
            speed = (i+1) / elapsed if elapsed > 0 else 0
            eta = (len(target_codes) - i - 1) / max(speed, 0.01)
            print(f"  [{i+1}/{len(target_codes)}] enriched={len(enriched_results)} fail={fail_count} skip={skip_count} speed={speed*60:.1f}/分 ETA={eta/60:.1f}分", flush=True)
    
    out_path = BACKTEST_DIR / "reversal-events-2026-05-01-v12-auction.json"
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
        json.dump({"events": merged, "n_with_au": len(enriched_results)}, f, ensure_ascii=False)
    print(f"\n✅ {out_path.name}: {len(enriched_results)} 事件有 au 数据")
    print(f"   失败 {fail_count}, 跳过 {skip_count}")
    print(f"   耗时 {(time.time()-t0)/60:.1f} 分钟")
    
    if ckpt_path.exists():
        ckpt_path.unlink()


if __name__ == "__main__":
    main()
