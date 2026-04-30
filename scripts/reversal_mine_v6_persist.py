#!/usr/bin/env python3
"""
reversal_mine_v6_persist.py — 加"主力持续性"特征

灵感来自 4-30 复盘:
- 600400 红豆 P=0.52 涨停, 实际 10 天连续流入
- 模型只看 cb5 5 天均值, 没看 D0 前 10 日的连续性
- 验证: cb5_in_ratio ≥0.6 命中 59% vs <0.6 45%, 但 LR 没用上 (共线性)

新特征 (基于 D0 前 10 个交易日):
- pre10_days_in: D0 前 10 日主力流入天数 (0-10)
- pre10_streak: D0 前最长连续流入天数
- pre10_main_total: D0 前 10 日主力净流入总额
- pre10_main_strong_streak: D0 前累计 3+ 天连续日均 ≥0.5 亿的次数

策略: 在 v4 events 基础上 enrich, 不重新 mining
"""
import json, time, sys
from pathlib import Path
from urllib.request import urlopen, Request
from datetime import datetime, timedelta

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"


def http_get_json(url, timeout=8, retries=2):
    for _ in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.loads(urlopen(req, timeout=timeout).read().decode("utf-8"))
        except Exception:
            time.sleep(0.5)
    return None


_FLOW_CACHE = {}  # code -> all klines (一股拉一次)

def fetch_full_money_flow(code):
    """拉个股完整资金流 (lmt=200, 本地缓存)"""
    if code in _FLOW_CACHE:
        return _FLOW_CACHE[code]
    sym = ("1." if code.startswith("6") else "0.") + code
    url = (f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={sym}"
           f"&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
           f"&klt=101&fqt=1&lmt=200")
    d = http_get_json(url)
    klines = (d.get("data", {}).get("klines", []) or []) if d else []
    _FLOW_CACHE[code] = klines
    return klines


def compute_pre10_features(code, d0_date):
    """D0 前 10 个交易日的主力持续性 (从全量缓存切片)"""
    klines = fetch_full_money_flow(code)
    if not klines:
        return None
    
    # 解析 (date, main_flow_yuan)
    history = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                date = parts[0]
                main = float(parts[1])
                history.append((date, main))
            except Exception:
                pass
    
    # 只取 D0 之前的 (不含 D0)
    history = [(d, m) for d, m in history if d < d0_date]
    if len(history) < 5:
        return None
    
    # 取最近 10 个交易日
    pre10 = history[-10:] if len(history) >= 10 else history
    n = len(pre10)
    
    # 流入天数
    days_in = sum(1 for _, m in pre10 if m > 0)
    
    # 最长连续流入
    max_streak = cur_streak = 0
    for _, m in pre10:
        if m > 0:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0
    
    # 总额 (亿)
    total = sum(m for _, m in pre10) / 1e8
    
    # 强流入天数 (单日 ≥ 0.5 亿 = 5e7)
    strong_in_days = sum(1 for _, m in pre10 if m >= 5e7)
    
    return {
        "pre10_days_in": days_in,
        "pre10_n": n,
        "pre10_in_ratio": days_in / n if n > 0 else 0,
        "pre10_max_streak": max_streak,
        "pre10_main_total": round(total, 4),
        "pre10_main_avg": round(total / n if n > 0 else 0, 4),
        "pre10_strong_days": strong_in_days,
    }


def main():
    src = BACKTEST_DIR / "reversal-events-2026-04-30-v4.json"
    if not src.exists():
        print(f"❌ 找不到 v4 events: {src}", flush=True)
        return
    
    with open(src) as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 加载 v4: {len(events)} 事件", flush=True)
    
    enriched = []
    fail = 0
    t0 = time.time()
    
    # 按 (code, d0_date) 去重以减少重复 fetch
    cache = {}
    
    for i, e in enumerate(events):
        code = e["code"]
        d0_date = e.get("d0_date")
        if not d0_date:
            enriched.append(e)
            continue
        
        key = (code, d0_date)
        if key in cache:
            feats = cache[key]
        else:
            feats = compute_pre10_features(code, d0_date)
            cache[key] = feats
            # 只在未缓存股票后 sleep
            if code not in _FLOW_CACHE or len(_FLOW_CACHE[code]) > 0:
                time.sleep(0.08)
        
        if feats:
            new_e = dict(e)
            new_e.update(feats)
            enriched.append(new_e)
        else:
            enriched.append(e)
            fail += 1
        
        if (i + 1) % 100 == 0:
            elapsed = int(time.time() - t0)
            eta = int((len(events) - i - 1) * elapsed / (i + 1))
            print(f"   [{i+1}/{len(events)}] 失败 {fail} | {elapsed}s ETA {eta}s", flush=True)
    
    print(f"\n✅ v6 enriched: {len(enriched)} (失败 {fail})\n", flush=True)
    
    # 落档
    out_path = BACKTEST_DIR / "reversal-events-2026-04-30-v6.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"events": enriched, "version": "v6", "schema": "v4+pre10_persist"}, f,
                  ensure_ascii=False, indent=2)
    print(f"📁 落档: {out_path}", flush=True)
    
    # 信号检查
    print(f"\n📊 pre10_days_in (D0 前 10 日主力流入天数) 分箱:", flush=True)
    valid = [e for e in enriched if "pre10_days_in" in e]
    for n_in in range(0, 11):
        sub = [e for e in valid if e.get("pre10_days_in") == n_in]
        if not sub: continue
        rate = sum(1 for e in sub if e["outcome"] == "reversal") / len(sub)
        print(f"   {n_in}/10 天流入: n={len(sub):>4}  回马枪 {rate*100:5.1f}%", flush=True)
    
    print(f"\n📊 pre10_max_streak (D0 前最长连续流入天数) 分箱:", flush=True)
    for streak in range(0, 11):
        sub = [e for e in valid if e.get("pre10_max_streak") == streak]
        if not sub: continue
        rate = sum(1 for e in sub if e["outcome"] == "reversal") / len(sub)
        print(f"   连续 {streak} 天: n={len(sub):>4}  回马枪 {rate*100:5.1f}%", flush=True)
    
    print(f"\n📊 pre10_strong_days (D0 前 ≥0.5 亿/日 的强流入天数) 分箱:", flush=True)
    for n_strong in range(0, 11):
        sub = [e for e in valid if e.get("pre10_strong_days") == n_strong]
        if not sub: continue
        rate = sum(1 for e in sub if e["outcome"] == "reversal") / len(sub)
        print(f"   {n_strong} 天强流入: n={len(sub):>4}  回马枪 {rate*100:5.1f}%", flush=True)


if __name__ == "__main__":
    main()
