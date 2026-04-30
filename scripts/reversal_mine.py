#!/usr/bin/env python3
"""
reversal_mine.py — 涨停回马枪研究 v0.1: 数据挖掘

目标: 从历史 K 线找出所有 "涨停(D0) → 2-10 天回调 → 再涨停(D_t)" 的样本

输入: backtest/v24-results-2026-04-28-enriched.json (786 个涨停事件)
扫描: 对每只票, 找最近 90 天所有涨停日, 看其后 2-10 天是否再次涨停

输出: backtest/reversal-events-2026-04-29.json
  {
    "events": [
      {
        "code", "name", "d0_date" (第一次涨停日), "d0_close", "d0_chg",
        "lookback_window": 涨停后 2-10 天内,
        "outcome": "reversal"|"failed",
        "d_t_date": (若 reversal) 第二次涨停日,
        "days_between": d0 到 d_t 间隔,
        "callback_pct": 回调最大跌幅 (高 → 低),
        "min_close_pct": 最低收盘价 vs d0 收盘的跌幅,
        "broke_ma5": 是否跌破 d0 当日 MA5,
        "broke_ma10": 是否跌破 d0 当日 MA10,
        "vol_callback": 回调期日均量 / d0 量,
      }
    ]
  }
"""
import json, time, sys
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
    """判断涨停 (考虑创业板/科创板/北交所幅度)"""
    if code.startswith(('300', '688')): return chg >= 19.5
    if code.startswith(('8', '4', '9')): return chg >= 29.5
    return chg >= 9.7


def fetch_kline(code, beg, end, lookback=120):
    sym = ("sh" if code.startswith('6') else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},{lookback},qfq"
    d = http_get(url)
    if not d: return [], None
    sd = d.get("data", {}).get(sym, {})
    klines = sd.get("qfqday") or sd.get("day") or []
    name = sd.get("qt", {}).get(sym, [None]*2)[1] if sd.get("qt") else None
    return klines, name


def calc_ma(klines, idx, period):
    """计算第 idx 天的 N 日均线 (用 close)"""
    if idx < period - 1: return None
    closes = [float(klines[i][2]) for i in range(idx-period+1, idx+1)]
    return sum(closes) / len(closes)


def find_reversal_events(klines, code, lookback_min=2, lookback_max=10):
    """扫描 K 线找所有 D0 涨停, 看 D0+2 到 D0+10 内是否再次涨停"""
    events = []
    n = len(klines)
    for i in range(20, n - lookback_max - 1):  # 留 20 天给 MA, 留尾巴看后续
        k = klines[i]
        if len(k) < 6: continue
        c = float(k[2]); pc = float(klines[i-1][2])
        if pc <= 0: continue
        chg = (c - pc) / pc * 100
        if not is_zt(code, chg): continue
        
        # 找到 D0 涨停, 看后续 2-10 天
        d0_date = k[0]
        d0_close = c
        d0_high = float(k[3])
        d0_vol = float(k[5])
        ma5_d0 = calc_ma(klines, i, 5)
        ma10_d0 = calc_ma(klines, i, 10)
        
        outcome = "failed"
        d_t_date = None
        days_between = None
        callback_pct = 0  # 最大回调
        min_close = d0_close
        broke_ma5 = False
        broke_ma10 = False
        vols_callback = []
        
        for j in range(i + lookback_min, min(i + lookback_max + 1, n)):
            jk = klines[j]
            if len(jk) < 6: continue
            j_c = float(jk[2]); j_pc = float(klines[j-1][2])
            j_l = float(jk[4]); j_v = float(jk[5])
            if j_pc <= 0: continue
            j_chg = (j_c - j_pc) / j_pc * 100
            
            # 跟踪回调期数据 (从 D0+1 到 D_t-1 都算)
            for jj in range(i + 1, j):
                jjk = klines[jj]
                jj_l = float(jjk[4]); jj_c = float(jjk[2])
                if d0_close > 0:
                    drop = (d0_close - jj_l) / d0_close * 100
                    if drop > callback_pct: callback_pct = drop
                if jj_c < min_close: min_close = jj_c
                if ma5_d0 and jj_c < ma5_d0: broke_ma5 = True
                if ma10_d0 and jj_c < ma10_d0: broke_ma10 = True
                vols_callback.append(float(jjk[5]))
            
            # 判断 D_t 是否再次涨停
            if is_zt(code, j_chg):
                outcome = "reversal"
                d_t_date = jk[0]
                days_between = j - i
                break
        
        # 没出现再涨停, 但要算回调数据
        if outcome == "failed":
            for jj in range(i + 1, min(i + lookback_max + 1, n)):
                jjk = klines[jj]
                jj_l = float(jjk[4]); jj_c = float(jjk[2])
                if d0_close > 0:
                    drop = (d0_close - jj_l) / d0_close * 100
                    if drop > callback_pct: callback_pct = drop
                if jj_c < min_close: min_close = jj_c
                if ma5_d0 and jj_c < ma5_d0: broke_ma5 = True
                if ma10_d0 and jj_c < ma10_d0: broke_ma10 = True
                vols_callback.append(float(jjk[5]))
        
        events.append({
            "code": code,
            "d0_date": d0_date,
            "d0_close": round(d0_close, 3),
            "d0_chg": round(chg, 2),
            "outcome": outcome,
            "d_t_date": d_t_date,
            "days_between": days_between,
            "callback_pct": round(callback_pct, 2),
            "min_close_pct": round((d0_close - min_close) / d0_close * 100, 2) if d0_close > 0 else 0,
            "broke_ma5": broke_ma5,
            "broke_ma10": broke_ma10,
            "vol_callback_ratio": round(sum(vols_callback) / len(vols_callback) / d0_vol, 3) if vols_callback and d0_vol > 0 else 0,
        })
    
    return events


def main():
    # 加载 v2.4 已有的 786 涨停事件, 提取 unique code 列表
    src = BACKTEST_DIR / "v24-results-2026-04-28-enriched.json"
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)
    
    codes = sorted(set(s["code"] for s in d["samples"]))
    print(f"📊 扫描 {len(codes)} 只独立股票 (来自 v2.4 786 个涨停事件)", flush=True)
    
    # 时间窗: 近 120 天 K 线 (回测范围 + buffer)
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    beg = (datetime.now(BJT) - timedelta(days=130)).strftime("%Y-%m-%d")
    
    all_events = []
    name_map = {}
    for i, code in enumerate(codes):
        klines, name = fetch_kline(code, beg, today, lookback=130)
        if name: name_map[code] = name
        if not klines or len(klines) < 30:
            continue
        events = find_reversal_events(klines, code)
        for e in events:
            e["name"] = name or "?"
        all_events.extend(events)
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(codes)}] 累计事件 {len(all_events)}", flush=True)
        time.sleep(0.05)
    
    # 统计
    n_total = len(all_events)
    n_reversal = sum(1 for e in all_events if e["outcome"] == "reversal")
    print(f"\n📈 总涨停事件: {n_total}", flush=True)
    print(f"   回马枪成功: {n_reversal} ({n_reversal/n_total*100:.1f}%)", flush=True)
    print(f"   失败: {n_total - n_reversal}", flush=True)
    
    # 按 days_between 分布
    if n_reversal:
        from collections import Counter
        days_dist = Counter(e["days_between"] for e in all_events if e["outcome"] == "reversal")
        print(f"\n   回马枪间隔天数分布:", flush=True)
        for d_, c_ in sorted(days_dist.items()):
            print(f"     {d_} 天: {c_} ({c_/n_reversal*100:.1f}%)", flush=True)
    
    # 落档
    out = BACKTEST_DIR / f"reversal-events-{today}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "scan_date": today,
            "scan_window": f"{beg} ~ {today}",
            "n_codes": len(codes),
            "n_total": n_total,
            "n_reversal": n_reversal,
            "events": all_events,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {out}", flush=True)


if __name__ == "__main__":
    main()
