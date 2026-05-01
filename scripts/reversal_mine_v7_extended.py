"""v0.7 mining: 扩展事件池
- 数据源: 东方财富 K 线 (能拉 2 年+)
- 时间: 2025-01 至 2026-04 (16 个月, 比之前 4 个月多 4 倍)
- 股票池: 用 v2.4 的 786 + 已有的 reversal events 的 unique codes
- 目标: 把 1151 事件扩到 4000+
"""
import json, sys, time, copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))

def http_get(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_em_kline(code, beg="20250101", end="20260430", retries=3):
    """新浪日 K (不复权 - 不影响涨跌幅判断), 带重试"""
    prefix = "sh" if code.startswith("6") else "sz"
    url = (f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen=600")
    r = None
    for attempt in range(retries):
        r = http_get(url, timeout=15)
        if r: break
        time.sleep(2 + attempt * 3)
    if not r: return [], None
    try:
        j = json.loads(r)
        if not isinstance(j, list) or not j: return [], None
        rows = []
        prev_close = None
        for k in j:
            try:
                close = float(k['close'])
                chg = ((close - prev_close) / prev_close * 100) if prev_close else 0.0
                rows.append({
                    "date": k['day'],
                    "open": float(k['open']),
                    "close": close,
                    "high": float(k['high']),
                    "low": float(k['low']),
                    "vol": float(k['volume']),
                    "chg": chg,
                })
                prev_close = close
            except (ValueError, KeyError):
                continue
        # 过滤 beg 之后的
        beg_str = f"{beg[:4]}-{beg[4:6]}-{beg[6:]}"
        rows = [r for r in rows if r['date'] >= beg_str]
        return rows, ""  # 新浪接口不返回 name, 后面拼 name_map
    except Exception:
        return [], None


def is_zt(code, chg):
    """涨停判断 (考虑 ST/科创/创业板的不同涨停幅度)"""
    if code.startswith("688"):  # 科创板 20%
        return chg >= 19.5
    if code.startswith("300") and code >= "300700":  # 创业板注册制 20%
        return chg >= 19.5
    if code.startswith("301"):  # 创业板注册制 20%
        return chg >= 19.5
    if "ST" in (str(code) or ""):  # ST 5%
        return chg >= 4.8
    return chg >= 9.5  # 主板 10%


def find_reversals(klines, code):
    """找该股 K 线里的所有 (D0 涨停 → 2-10 天后 D_t 再涨停 / 失败) 事件"""
    events = []
    n = len(klines)
    if n < 30: return events
    
    for i in range(20, n - 10):  # 至少前 20 天有数据 (算 MA), 后 10 天有数据 (看回马)
        kl = klines[i]
        if not is_zt(code, kl["chg"]): continue
        d0_close = kl["close"]
        d0_date = kl["date"]
        d0_vol = kl["vol"]
        
        # 看 d0_lbc (前几天连板)
        lbc = 1
        for j in range(i-1, max(0, i-10), -1):
            if is_zt(code, klines[j]["chg"]): lbc += 1
            else: break
        
        # MA5/MA10
        ma5 = sum(k["close"] for k in klines[i-5:i]) / 5
        ma10 = sum(k["close"] for k in klines[i-10:i]) / 10
        
        # 看 D0+1 到 D0+10 是否再次涨停
        d_t = None; d_t_date = None
        for j in range(i+1, min(n, i+11)):
            if is_zt(code, klines[j]["chg"]):
                d_t = j; d_t_date = klines[j]["date"]
                break
        
        # 计算回调幅度 (高点到回调期最低收盘)
        if d_t is not None:
            cb_period = klines[i+1:d_t]
            outcome = "reversal"
            days_between = d_t - i
        else:
            cb_period = klines[i+1:i+11]  # 失败: 用 D0+1 到 D0+10
            outcome = "failed"
            days_between = None
        
        if not cb_period: continue
        min_close = min(k["close"] for k in cb_period)
        max_high = max(k["high"] for k in cb_period)
        callback_pct = (d0_close - min_close) / d0_close * 100
        min_close_pct = (d0_close - min_close) / d0_close * 100
        
        # 是否破 MA5/MA10
        broke_ma5 = min_close < ma5
        broke_ma10 = min_close < ma10
        
        # 量能比
        vol_avg = sum(k["vol"] for k in cb_period) / len(cb_period)
        vol_ratio = vol_avg / d0_vol if d0_vol > 0 else 0
        
        events.append({
            "code": code,
            "name": "",  # 后填
            "d0_date": d0_date,
            "d0_close": d0_close,
            "d0_chg": kl["chg"],
            "d0_vol": d0_vol,
            "d0_lbc": lbc,
            "outcome": outcome,
            "d_t_date": d_t_date,
            "days_between": days_between,
            "callback_pct": round(callback_pct, 2),
            "min_close_pct": round(min_close_pct, 2),
            "broke_ma5": broke_ma5,
            "broke_ma10": broke_ma10,
            "vol_callback_ratio": round(vol_ratio, 3),
        })
    
    return events


def main():
    # 拿到要扫的 code 池: v0.6 events 现有 codes + v2.4 codes
    codes = set()
    for fn in ["reversal-events-2026-04-30-v6.json", "v24-results-2026-04-28-enriched.json"]:
        path = BACKTEST_DIR / fn
        if not path.exists(): continue
        with open(path) as f:
            d = json.load(f)
        items = d.get("events", []) or d.get("samples", [])
        for it in items:
            codes.add(it["code"])
    codes = sorted(codes)
    print(f"📊 扫描 {len(codes)} 只股 (V6 events + V24 samples)", flush=True)
    
    # checkpoint 机制
    ckpt_path = BACKTEST_DIR / "v7_mine_ckpt.json"
    done_codes = set()
    all_events = []
    name_map = {}
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        done_codes = set(ckpt.get("done", []))
        all_events = ckpt.get("events", [])
        name_map = ckpt.get("name_map", {})
        print(f"♻️ 从 checkpoint 恢复: {len(done_codes)} codes done, {len(all_events)} events", flush=True)
    t0 = time.time()
    failed = 0
    for i, code in enumerate(codes):
        if code in done_codes: continue
        klines, name = fetch_em_kline(code, "20250101", "20260430")
        if name: name_map[code] = name
        if not klines or len(klines) < 30:
            failed += 1
            time.sleep(0.5)  # 失败后多休息
            continue
        events = find_reversals(klines, code)
        for e in events: e["name"] = name or "?"
        all_events.extend(events)
        time.sleep(0.3)  # 调慢避免限速
        done_codes.add(code)
        if (i+1) % 50 == 0:
            elapsed = time.time() - t0
            done_rate = (i+1 - len([c for c in codes[:i+1] if c not in done_codes])) / max(1, elapsed)
            eta = (len(codes) - i - 1) / max(0.001, done_rate)
            print(f"  [{i+1}/{len(codes)}] 累计 {len(all_events)} 事件 | 失败 {failed} | {elapsed:.0f}s ETA {eta:.0f}s", flush=True)
            # 落 checkpoint
            with open(ckpt_path, "w") as f:
                json.dump({"done": list(done_codes), "events": all_events, "name_map": name_map}, f, ensure_ascii=False)
    
    print(f"\n✅ Mined {len(all_events)} events (失败 {failed})", flush=True)
    
    # 落档
    out = BACKTEST_DIR / "reversal-events-2026-05-01-v7.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"version": "v0.7-extended", "n_events": len(all_events), "events": all_events}, f, ensure_ascii=False, indent=2)
    print(f"📁 落档: {out}", flush=True)
    
    # 统计
    n_rev = sum(1 for e in all_events if e["outcome"] == "reversal")
    print(f"\n📊 反转率: {n_rev}/{len(all_events)} = {n_rev/len(all_events)*100:.1f}%")
    
    # 按月统计
    from collections import Counter
    months = Counter(e["d0_date"][:7] for e in all_events)
    for m in sorted(months.keys()):
        sub = [e for e in all_events if e["d0_date"].startswith(m)]
        rev = sum(1 for e in sub if e["outcome"]=="reversal")
        print(f"  {m}: {len(sub)} 事件, 反转 {rev/len(sub)*100:.1f}%")


if __name__ == "__main__":
    main()
