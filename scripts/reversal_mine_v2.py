#!/usr/bin/env python3
"""
reversal_mine_v2.py — 涨停回马枪 v0.2 数据扩充

v0.1 → v0.2 新增特征:
1. d0_lbc: D0 当时是几连板 (扫之前 5 个交易日的连板)
2. callback_min_close_pos: 最低收盘 在 D0 后第几天 (前置回调 vs 末尾回调)
3. rebound_pct: 回调最低点之后的反弹幅度 (V 型 vs L 型)
4. first_red_at: 回调期第一个跌破 D0 收盘的日子
5. days_below_d0: 回调期收盘<D0 收盘的天数 (整体强弱)
6. d0_vol_z: D0 量能 z-score vs 之前 20 日均量 (D0 是不是放量启动)
7. is_first_zt: 是否首板 (D0 之前 5 天内是否有过涨停)

输入: backtest/reversal-events-2026-04-30.json (v0.1, 已含基础特征)
输出: backtest/reversal-events-2026-04-30-v2.json
"""
import json, time
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
            data = r.read().decode("utf-8", errors="ignore")
            if data.startswith("v="):
                data = data[2:].rstrip(";")
            return json.loads(data) if data.strip().startswith("{") else None
    except Exception:
        return None


def is_zt(code, chg):
    if code.startswith(('300', '688')): return chg >= 19.5
    if code.startswith(('8', '4', '9')): return chg >= 29.5
    return chg >= 9.7


def fetch_kline(code, beg, end, lookback=160):
    sym = ("sh" if code.startswith('6') else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},{lookback},qfq"
    d = http_get(url)
    if not d: return []
    sd = d.get("data", {}).get(sym, {})
    return sd.get("qfqday") or sd.get("day") or []


def extract_v2_features(klines, d0_idx, today_idx, d_t_idx, code):
    """对一个事件的 D0 索引, 计算 v0.2 新特征"""
    out = {}
    
    if d0_idx < 25 or d0_idx >= len(klines):
        return None
    
    d0 = klines[d0_idx]
    d0_close = float(d0[2])
    d0_vol = float(d0[5])
    
    # 1. d0_lbc: D0 之前几连板 (D0 这天起算第 1 板, 看 D0-1 是不是涨停)
    lbc = 1
    for back in range(1, 8):
        idx = d0_idx - back
        if idx < 1: break
        k = klines[idx]
        c = float(k[2]); pc = float(klines[idx-1][2])
        if pc <= 0: break
        chg = (c - pc) / pc * 100
        if is_zt(code, chg):
            lbc += 1
        else:
            break
    out["d0_lbc"] = lbc
    out["is_first_zt"] = 1 if lbc == 1 else 0  # D0 是首板
    
    # 2. d0_vol_z: D0 量能 vs 之前 20 日均量
    vols = [float(klines[i][5]) for i in range(max(0, d0_idx-20), d0_idx) if len(klines[i]) > 5]
    if vols:
        avg_vol = sum(vols) / len(vols)
        out["d0_vol_z"] = round(d0_vol / avg_vol, 2) if avg_vol > 0 else 0
    else:
        out["d0_vol_z"] = 0
    
    # 3. 回调期统计 (从 D0+1 到 D_t 前一天 或 today_idx)
    # ⚠️ 必须不含 D_t本身，避免数据泄漏
    end_idx = (d_t_idx - 1) if d_t_idx else today_idx
    if end_idx <= d0_idx:
        out["callback_min_close_pos"] = 0
        out["rebound_pct"] = 0
        out["first_red_at"] = 0
        out["days_below_d0"] = 0
        return out
    
    callback_klines = klines[d0_idx+1:end_idx+1]
    pre_dt = callback_klines  # 已不含 D_t
    if pre_dt:
        closes = [float(k[2]) for k in pre_dt]
        min_close = min(closes)
        min_pos = closes.index(min_close) + 1  # D0+1 = 1
        out["callback_min_close_pos"] = min_pos
        # rebound: min_close 之后到回调期结束的最高收盘
        if min_pos < len(pre_dt):
            after = closes[min_pos:]
            max_after = max(after) if after else min_close
            out["rebound_pct"] = round((max_after - min_close) / min_close * 100, 2) if min_close > 0 else 0
        else:
            out["rebound_pct"] = 0
        # first_red_at: 第一个跌破 D0 收盘的位置
        first_red = 0
        for i, c in enumerate(closes):
            if c < d0_close:
                first_red = i + 1
                break
        out["first_red_at"] = first_red
        # days_below_d0
        out["days_below_d0"] = sum(1 for c in closes if c < d0_close)
    else:
        out["callback_min_close_pos"] = 0
        out["rebound_pct"] = 0
        out["first_red_at"] = 0
        out["days_below_d0"] = 0
    
    return out


def main():
    src = BACKTEST_DIR / "reversal-events-2026-04-30.json"
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 加载 {len(events)} 个 v0.1 事件", flush=True)
    
    # 按 code 分组拉一次 K 线即可
    code_to_events = {}
    for e in events:
        code_to_events.setdefault(e["code"], []).append(e)
    print(f"   独立股票 {len(code_to_events)} 只", flush=True)
    
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    beg = (datetime.now(BJT) - timedelta(days=160)).strftime("%Y-%m-%d")
    
    enriched = []
    failed = 0
    for i, (code, code_events) in enumerate(code_to_events.items()):
        klines = fetch_kline(code, beg, today, lookback=160)
        if not klines or len(klines) < 30:
            failed += len(code_events)
            continue
        
        # 建 date → idx 索引
        date_idx = {k[0]: idx for idx, k in enumerate(klines)}
        
        for e in code_events:
            d0_idx = date_idx.get(e["d0_date"])
            if d0_idx is None:
                failed += 1
                continue
            d_t_idx = date_idx.get(e.get("d_t_date")) if e.get("outcome") == "reversal" else None
            today_idx = (d_t_idx if d_t_idx else min(d0_idx + 10, len(klines) - 1))
            
            v2 = extract_v2_features(klines, d0_idx, today_idx, d_t_idx, code)
            if v2 is None:
                failed += 1
                continue
            
            new_e = dict(e)
            new_e.update(v2)
            enriched.append(new_e)
        
        if (i + 1) % 50 == 0:
            print(f"   [{i+1}/{len(code_to_events)}] 累计 {len(enriched)}", flush=True)
        time.sleep(0.05)
    
    print(f"\n📈 v0.2 enriched: {len(enriched)} (失败 {failed})", flush=True)
    
    # 简单统计
    if enriched:
        from collections import Counter
        lbc_dist = Counter(e["d0_lbc"] for e in enriched)
        print(f"\n   D0 连板分布:", flush=True)
        for k in sorted(lbc_dist):
            sub = [e for e in enriched if e["d0_lbc"] == k]
            success = sum(1 for e in sub if e["outcome"] == "reversal")
            print(f"     {k} 板: n={len(sub)} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
        
        # vol_z 分箱
        print(f"\n   D0 量比 (vs 前 20 日均量):", flush=True)
        for lo, hi, lab in [(0,1,"<1x"), (1,2,"1-2x"), (2,3,"2-3x"), (3,5,"3-5x"), (5,100,"≥5x")]:
            sub = [e for e in enriched if lo <= e["d0_vol_z"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab}: n={len(sub)} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
    
    out = BACKTEST_DIR / f"reversal-events-{today}-v2.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "scan_date": today,
            "version": "v0.2",
            "n_total": len(enriched),
            "n_reversal": sum(1 for e in enriched if e["outcome"] == "reversal"),
            "events": enriched,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {out}", flush=True)


if __name__ == "__main__":
    main()
