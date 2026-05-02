"""给 v9/v10 events 补 D0 涨停板上成交特征
- 数据源: 新浪 5m K 历史 (104 天, datalen=5000) — 仅覆盖 2025-12 后的 events
- 单股拉一次 K, 解析 D0 当天的 5m bar 序列, 找首次封板时刻

新增字段 (D0 涨停日):
- d0_zt_lock_idx: 首次封板的 5m bar 序号 (1-48), 越小越强 (早盘封)
- d0_zt_lock_pct: 首次封板时间占全天比例 (0-1, 越小越好)
- d0_zt_after_amt_yi: 封板后到收盘的总成交 (亿)
- d0_zt_after_amt_pct: 封板后成交占全天比例 (越小越锁紧)
- d0_zt_locked_bars: 持续锁住涨停的 5m bar 数 (max 48)
- d0_zt_lock_strength: 锁定强度 = locked_bars / (48 - lock_idx + 1)  (1.0=完全锁住)
- d0_strong_lock: 1 if 早盘 (14:05 前) 封板 AND lock_strength >= 0.8
- d0_weak_lock: 1 if 尾盘 (14:30 后) 才封 OR lock_strength < 0.6 (虚假涨停)
"""
import json, time, sys
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


def calc_d0_zt_features(klines_5m, d0_date):
    d0_bars = [k for k in klines_5m if k['day'].startswith(d0_date)]
    if len(d0_bars) < 30:  # 少于半天 5m bar 跳过
        return None
    
    day_high = max(float(k['high']) for k in d0_bars)
    
    # 找首次封板: high == day_high
    lock_idx = None
    for i, k in enumerate(d0_bars):
        if abs(float(k['high']) - day_high) < 0.005:
            lock_idx = i
            break
    
    # 找首次"锁住" close == day_high
    locked_idx = None
    for i, k in enumerate(d0_bars):
        if abs(float(k['close']) - day_high) < 0.005:
            locked_idx = i
            break
    
    # 没真锁住涨停: locked_idx None → 这天是炸板, 不算 D0 真涨停
    if locked_idx is None:
        # 涨停未封住, 给个 weak signal
        return {
            "d0_zt_lock_idx": -1,
            "d0_zt_lock_pct": 1.0,
            "d0_zt_after_amt_yi": 0.0,
            "d0_zt_after_amt_pct": 0.0,
            "d0_zt_locked_bars": 0,
            "d0_zt_lock_strength": 0.0,
            "d0_strong_lock": 0,
            "d0_weak_lock": 1,  # 没封住 = 弱
            "d0_unsealed": 1,  # 直接没封住涨停
        }
    
    n_bars = len(d0_bars)
    after_bars = d0_bars[locked_idx + 1:]
    after_vol = sum(float(k['volume']) for k in after_bars)
    after_amt_yi = after_vol * day_high / 1e8
    
    day_total_vol = sum(float(k['volume']) for k in d0_bars)
    day_total_amt_yi = day_total_vol * day_high / 1e8 if day_total_vol > 0 else 0  # 粗估
    after_amt_pct = after_vol / day_total_vol if day_total_vol > 0 else 0
    
    # 锁住的 bar 数: locked_idx 之后, close 仍是 day_high 的
    locked_bars = sum(1 for k in d0_bars[locked_idx:] if abs(float(k['close']) - day_high) < 0.005)
    lock_strength = locked_bars / max(1, n_bars - locked_idx)
    
    lock_pct = locked_idx / n_bars  # 0-1, 越小越早封
    
    return {
        "d0_zt_lock_idx": locked_idx,
        "d0_zt_lock_pct": round(lock_pct, 3),
        "d0_zt_after_amt_yi": round(after_amt_yi, 4),
        "d0_zt_after_amt_pct": round(after_amt_pct, 3),
        "d0_zt_locked_bars": locked_bars,
        "d0_zt_lock_strength": round(lock_strength, 3),
        "d0_strong_lock": 1 if (lock_pct < 0.6 and lock_strength >= 0.8) else 0,
        "d0_weak_lock": 1 if (lock_pct > 0.85 or lock_strength < 0.6) else 0,
        "d0_unsealed": 0,
    }


def main():
    src = BACKTEST_DIR / "reversal-events-2026-05-01-v9-with-pre10.json"
    with open(src) as f:
        events = json.load(f)['events']
    
    target = [e for e in events if e['d0_date'] >= '2025-12-01']
    print(f"📊 全量: {len(events)}, 待补 (≥2025-12): {len(target)}")
    
    by_code = {}
    for e in events:
        by_code.setdefault(e['code'], []).append(e)
    target_codes = sorted(set(e['code'] for e in target))
    print(f"📊 unique codes: {len(target_codes)}")
    
    ckpt_path = BACKTEST_DIR / "v11_d0zt_ckpt.json"
    done_codes = set()
    enriched_results = []
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        done_codes = set(ckpt.get("done", []))
        enriched_results = ckpt.get("enriched", [])
        print(f"♻️ checkpoint: done {len(done_codes)} codes, {len(enriched_results)} rows")
    
    fail_count = 0
    skip_count = 0
    t0 = time.time()
    for i, code in enumerate(target_codes):
        if code in done_codes:
            continue
        klines = get_5m_klines(code)
        if not klines:
            done_codes.add(code)
            fail_count += len([e for e in by_code[code] if e in target])
            time.sleep(0.5)
            continue
        for e in by_code[code]:
            if e not in target: continue
            f = calc_d0_zt_features(klines, e['d0_date'])
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
            speed = (i+1) / elapsed if elapsed > 0 else 0
            eta = (len(target_codes) - i - 1) / max(speed, 0.01)
            with open(ckpt_path, "w") as f:
                json.dump({"done": list(done_codes), "enriched": enriched_results}, f)
            print(f"  [{i+1}/{len(target_codes)}] enriched={len(enriched_results)} fail={fail_count} skip={skip_count} speed={speed*60:.1f}/分 ETA={eta/60:.1f}分", flush=True)
    
    out_path = BACKTEST_DIR / "reversal-events-2026-05-01-v11-d0zt.json"
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
        json.dump({"events": merged, "n_orig": len(events), "n_with_d0zt": len(enriched_results)}, f, ensure_ascii=False)
    print(f"\n✅ 落档: {out_path.name}")
    print(f"   全量 {len(events)} 事件, {len(enriched_results)} 有 d0zt 数据")
    print(f"   失败 {fail_count}, 跳过 {skip_count}")
    print(f"   耗时 {(time.time()-t0)/60:.1f} 分钟")
    
    if ckpt_path.exists():
        ckpt_path.unlink()


if __name__ == "__main__":
    main()
