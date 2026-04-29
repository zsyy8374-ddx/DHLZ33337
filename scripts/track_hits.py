#!/usr/bin/env python3
"""
track_hits.py — 实盘命中追踪

每个交易日北京 18:30 跑 (在每天的 daily_picks 之后):
  1. 读 picks/{昨日}.json 拿到 LR Top 候选股
  2. 拉这些股的今日 K 线 (= picks 中"次日"开盘到收盘)
  3. 计算实际命中率 (是否再次涨停/收红/最高涨多少)
  4. 累积写入 picks/hit_log.jsonl
  5. 每周日同时输出过去 7 天命中率汇总
"""
import json, os, sys, urllib.request, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
PICKS_DIR = WORKSPACE / "picks"
HIT_LOG = PICKS_DIR / "hit_log.jsonl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"
BJT = timezone(timedelta(hours=8))


def http_get(url, retries=3, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(0.4 + i*0.5)
    return None


def is_zt(code, chg):
    if chg is None: return False
    if code.startswith(('300','688')): return chg >= 19.5
    if code.startswith(('8','4','9')): return chg >= 29.5
    return chg >= 9.7


def fetch_today_data(code, target_date):
    """拉指定日期的 K 线, 返回该日的 open/close/high/chg_pct"""
    sym = ("sh" if code.startswith('6') else "sz") + code
    beg = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},20,qfq"
    d = http_get(url)
    if not d: return None
    sd = d.get("data", {}).get(sym, {})
    klines = sd.get("qfqday") or sd.get("day") or []
    # 找到 target_date 的前一天和当天
    prev_close = None
    for i, k in enumerate(klines):
        if k[0] == target_date:
            if i > 0:
                prev_close = float(klines[i-1][2])
            o = float(k[1]); c = float(k[2]); h = float(k[3]); l = float(k[4])
            if prev_close and prev_close > 0:
                return {
                    "open_chg": (o - prev_close) / prev_close * 100,
                    "close_chg": (c - prev_close) / prev_close * 100,
                    "high_chg": (h - prev_close) / prev_close * 100,
                    "low_chg": (l - prev_close) / prev_close * 100,
                    "open": o, "close": c, "high": h, "low": l,
                }
    return None


def find_yesterday_picks():
    """找最近的有 LR Top 票的 picks 文件 (回看 7 天)"""
    today = datetime.now(BJT)
    for delta in range(1, 8):
        d = (today - timedelta(days=delta)).strftime("%Y-%m-%d")
        p = PICKS_DIR / f"{d}.json"
        if p.exists():
            return p, d
    return None, None


def evaluate_picks(picks_date, target_date):
    """评估 picks_date 的候选股在 target_date (次日) 的表现"""
    p = PICKS_DIR / f"{picks_date}.json"
    if not p.exists(): return None
    d = json.load(open(p, encoding="utf-8"))
    cands = d.get("candidates", [])
    if not cands: return None
    
    # 取 LR Top 候选股 (按概率分档)
    has_lr = any("lr_prob" in c for c in cands)
    if has_lr:
        tier_a = [c for c in cands if c.get("lr_prob", 0) >= 0.40]
        tier_b = [c for c in cands if 0.25 <= c.get("lr_prob", 0) < 0.40]
        tier_c = [c for c in cands if 0.15 <= c.get("lr_prob", 0) < 0.25]
    else:
        tier_a = [c for c in cands if c["total"] >= 120]
        tier_b = [c for c in cands if 110 <= c["total"] < 120]
        tier_c = [c for c in cands if 100 <= c["total"] < 110]
    
    print(f"\n📊 评估 {picks_date} 的 picks → 实际表现 ({target_date})", flush=True)
    
    results = {"picks_date": picks_date, "actual_date": target_date,
               "has_lr": has_lr, "tiers": {}}
    
    for tier_name, tier in [("A_extreme", tier_a), ("B_strong", tier_b), ("C_watch", tier_c)]:
        if not tier: continue
        rows = []
        for c in tier[:8]:
            data = fetch_today_data(c["code"], target_date)
            if not data: continue
            rows.append({
                "code": c["code"], "name": c["name"],
                "v24_score": c["total"],
                "lr_prob": c.get("lr_prob"),
                "lbc": c["features"].get("lbc"),
                "actual_open": round(data["open_chg"], 2),
                "actual_close": round(data["close_chg"], 2),
                "actual_high": round(data["high_chg"], 2),
                "actual_low": round(data["low_chg"], 2),
                "promoted": is_zt(c["code"], data["close_chg"]),
            })
        if not rows: continue
        n = len(rows)
        promoted = sum(1 for r in rows if r["promoted"])
        avg_close = sum(r["actual_close"] for r in rows) / n
        avg_high = sum(r["actual_high"] for r in rows) / n
        results["tiers"][tier_name] = {
            "n": n, "promoted": promoted,
            "rate": round(promoted/n*100, 1),
            "avg_close": round(avg_close, 2),
            "avg_high": round(avg_high, 2),
            "rows": rows,
        }
        print(f"   {tier_name}: n={n} 晋级={promoted} ({promoted/n*100:.1f}%) 均收{avg_close:+.2f}% 均高{avg_high:+.2f}%", flush=True)
        for r in rows:
            mark = "✅" if r["promoted"] else "❌"
            prob = f" P={r['lr_prob']:.2f}" if r["lr_prob"] else ""
            print(f"     {mark} {r['code']} {r['name']} score={r['v24_score']}{prob} 收{r['actual_close']:+.2f}% 高{r['actual_high']:+.2f}%", flush=True)
    
    return results


def write_log(record):
    if not record: return
    with open(HIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\n📁 已追加: {HIT_LOG}", flush=True)


def weekly_summary():
    """看过去 7 天 hit log 汇总"""
    if not HIT_LOG.exists(): return None
    cutoff = (datetime.now(BJT) - timedelta(days=8)).strftime("%Y-%m-%d")
    records = []
    for line in HIT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("picks_date", "") >= cutoff:
                records.append(r)
        except: pass
    if not records: return None
    
    # 各 tier 汇总
    agg = {}
    for r in records:
        for tier, data in r.get("tiers", {}).items():
            if tier not in agg:
                agg[tier] = {"n": 0, "promoted": 0, "close_sum": 0, "high_sum": 0}
            agg[tier]["n"] += data["n"]
            agg[tier]["promoted"] += data["promoted"]
            agg[tier]["close_sum"] += data["avg_close"] * data["n"]
            agg[tier]["high_sum"] += data["avg_high"] * data["n"]
    
    print(f"\n📈 近 7 天 LR 模型实战表现 ({cutoff} ~):", flush=True)
    for tier in ["A_extreme", "B_strong", "C_watch"]:
        if tier not in agg: continue
        a = agg[tier]
        if a["n"] == 0: continue
        rate = a["promoted"] / a["n"] * 100
        avg_close = a["close_sum"] / a["n"]
        avg_high = a["high_sum"] / a["n"]
        print(f"   {tier}: n={a['n']} 晋级率={rate:.1f}% 均收{avg_close:+.2f}% 均高{avg_high:+.2f}%", flush=True)
    
    return agg


def main():
    args = sys.argv[1:]
    
    if "summary" in args:
        weekly_summary()
        return
    
    # 找昨天的 picks
    picks_path, picks_date = find_yesterday_picks()
    if not picks_path:
        print("📭 7 天内没有 picks 文件", flush=True)
        return
    
    # 计算次日 (= today 北京)
    today_bj = datetime.now(BJT).strftime("%Y-%m-%d")
    if picks_date >= today_bj:
        print(f"📭 picks 是 {picks_date}, 还没到 {today_bj} 收盘", flush=True)
        return
    
    # 找 picks_date 的下一个工作日
    pd = datetime.strptime(picks_date, "%Y-%m-%d")
    target_date = None
    for delta in range(1, 5):
        cand = (pd + timedelta(days=delta))
        if cand.weekday() < 5:
            cand_str = cand.strftime("%Y-%m-%d")
            if cand_str <= today_bj:
                target_date = cand_str
                break
    
    if not target_date:
        print(f"📭 找不到 {picks_date} 的下一个交易日 (or 还没收盘)", flush=True)
        return
    
    record = evaluate_picks(picks_date, target_date)
    if record:
        write_log(record)
    
    weekly_summary()


if __name__ == "__main__":
    main()
