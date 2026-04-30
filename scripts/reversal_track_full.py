#!/usr/bin/env python3
"""reversal_track_full.py - 追踪所有 P>=0.4 的候选 + R7 标志

vs 原 reversal_track.py:
- 不限 Top 30, 全部 P>=0.4 候选都追
- 自动判断当日是否极端分化 (R7 触发)
- 输出按"原 P 档" + "R7 调权后档"双重统计
- 持久化到 picks/reversal_hits_full.jsonl, 供未来滚动验证
"""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
PICKS_DIR = WORKSPACE / "picks"
BJT = timezone(timedelta(hours=8))


def http_get(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_quote(code):
    """腾讯实时行情"""
    if code.startswith("6"):
        sym = "sh" + code
    else:
        sym = "sz" + code
    txt = http_get(f"https://qt.gtimg.cn/q={sym}")
    if not txt: return None
    parts = txt.split("~")
    if len(parts) < 50: return None
    try:
        return {
            "name": parts[1],
            "price": float(parts[3]),
            "prev_close": float(parts[4]),
            "open": float(parts[5]),
            "high": float(parts[33]),
            "low": float(parts[34]),
            "chg_pct": float(parts[32]),
        }
    except Exception:
        return None


def is_zt(code, chg):
    if code.startswith(("300", "301", "688", "689")):
        return chg >= 19.5
    return chg >= 9.7


def fetch_index_today():
    """抓三大指数今日涨跌"""
    out = {}
    for sym, key in [("sh000001", "sh"), ("sz399006", "sz"), ("sh000688", "kc")]:
        txt = http_get(f"https://qt.gtimg.cn/q=s_{sym}")
        if not txt: continue
        parts = txt.split("~")
        if len(parts) < 6: continue
        try:
            out[key] = float(parts[5])
        except Exception:
            pass
    return out


def detect_r7(idx):
    """判断今日是否极端分化"""
    if not idx or len(idx) < 3: return False, {}
    vals = [idx.get("sh", 0), idx.get("sz", 0), idx.get("kc", 0)]
    spread = max(vals) - min(vals)
    triggered = spread > 3 and idx.get("sh", 0) < 0.5
    return triggered, {"sh": idx.get("sh"), "sz": idx.get("sz"), "kc": idx.get("kc"),
                      "spread": round(spread, 2), "triggered": triggered}


def r7_adjust(p, lbc):
    if (lbc or 1) >= 3:
        return max(0.0, p - 0.30)
    if (lbc or 1) >= 2:
        return max(0.0, p - 0.20)
    return p


def bucket(p):
    if p >= 0.78: return "极强"
    if p >= 0.70: return "强"
    if p >= 0.60: return "强中"
    if p >= 0.50: return "中"
    if p >= 0.40: return "中低"
    return "低"


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(BJT).strftime("%Y-%m-%d")
    # pick_date = 上一交易日
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    # 周一: 上一交易日是周五; 否则就是 -1 天
    if target_dt.weekday() == 0:
        pick_date = (target_dt - timedelta(days=3)).strftime("%Y-%m-%d")
    else:
        pick_date = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 找 picks 文件
    pick_path = None
    for name in [f"reversal-v4-{pick_date}.json", f"reversal-v3-{pick_date}.json", f"reversal-{pick_date}.json"]:
        p = PICKS_DIR / name
        if p.exists():
            pick_path = p
            break
    
    if not pick_path:
        print(f"❌ 找不到 {pick_date} 推送文件")
        sys.exit(1)
    
    print(f"📊 评估 {pick_date} 推荐, 评估日 {target_date}")
    with open(pick_path) as f:
        d = json.load(f)
    cands = d["candidates"]
    cands = [c for c in cands if c["lr_prob"] >= 0.4]
    cands.sort(key=lambda x: -x["lr_prob"])
    
    print(f"   候选 P>=0.4 共 {len(cands)} 只")
    
    # 拉今日大盘
    idx = fetch_index_today()
    r7_triggered, r7_info = detect_r7(idx)
    print(f"   大盘: 上证 {idx.get('sh','?')}%, 创业板 {idx.get('sz','?')}%, 科创50 {idx.get('kc','?')}%, spread={r7_info.get('spread')}, R7={'触发' if r7_triggered else '未触发'}")
    
    # 拉行情
    print(f"\n查询行情...", flush=True)
    results = []
    for i, c in enumerate(cands):
        q = fetch_quote(c["code"])
        if not q: continue
        p_orig = c["lr_prob"]
        p_adj = r7_adjust(p_orig, c.get("d0_lbc")) if r7_triggered else p_orig
        results.append({
            "code": c["code"], "name": c.get("name", q["name"]),
            "d0_date": c.get("d0_date"), "d0_lbc": c.get("d0_lbc"),
            "callback_pct": c.get("callback_pct"), "cb5_main_avg": c.get("cb5_main_avg"),
            "lr_prob": p_orig, "lr_prob_adj": p_adj,
            "today_chg": q["chg_pct"],
            "today_high": q["high"],
            "today_low": q["low"],
            "is_zt": is_zt(c["code"], q["chg_pct"]),
            "touched_zt": q["high"] >= c["d0_close"] * 1.097 if c.get("d0_close") else False,
            "bucket_orig": bucket(p_orig),
            "bucket_adj": bucket(p_adj),
        })
        if i % 30 == 29:
            print(f"   已查 {i+1}/{len(cands)}", flush=True)
            time.sleep(0.5)
    
    print(f"   行情拉取完成: {len(results)}/{len(cands)}")
    
    # 双重统计
    def stats(rows, key="bucket_orig"):
        from collections import defaultdict
        d = defaultdict(lambda: {"n": 0, "zt": 0, "pos": 0, "chg": 0.0})
        for r in rows:
            b = r[key]
            d[b]["n"] += 1
            d[b]["chg"] += r["today_chg"]
            if r["is_zt"]: d[b]["zt"] += 1
            if r["today_chg"] > 0: d[b]["pos"] += 1
        return d
    
    s_orig = stats(results, "bucket_orig")
    s_adj = stats(results, "bucket_adj")
    
    print(f"\n📊 原 P 档命中:")
    print(f"{'档位':<6}{'n':>5}{'涨停':>6}{'涨停率':>8}{'上涨':>6}{'平均%':>9}")
    for b in ["极强","强","强中","中","中低"]:
        if b in s_orig:
            t = s_orig[b]
            zt_pct = t['zt']/t['n']*100 if t['n'] else 0
            avg = t['chg']/t['n'] if t['n'] else 0
            print(f"{b:<6}{t['n']:>5}{t['zt']:>6}{zt_pct:>7.1f}%{t['pos']:>6}{avg:>+8.2f}%")
    
    if r7_triggered:
        print(f"\n📊 R7 调权后档命中 (理论应该更准):")
        print(f"{'档位':<6}{'n':>5}{'涨停':>6}{'涨停率':>8}{'上涨':>6}{'平均%':>9}")
        for b in ["极强","强","强中","中","中低"]:
            if b in s_adj:
                t = s_adj[b]
                zt_pct = t['zt']/t['n']*100 if t['n'] else 0
                avg = t['chg']/t['n'] if t['n'] else 0
                print(f"{b:<6}{t['n']:>5}{t['zt']:>6}{zt_pct:>7.1f}%{t['pos']:>6}{avg:>+8.2f}%")
    
    # 总体
    n = len(results)
    n_zt = sum(1 for r in results if r["is_zt"])
    avg = sum(r["today_chg"] for r in results) / n if n else 0
    print(f"\n📊 总体: n={n}, 涨停 {n_zt} ({n_zt/n*100:.1f}%), 平均 {avg:+.2f}%")
    
    # 落档 jsonl
    out_path = PICKS_DIR / "reversal_hits_full.jsonl"
    record = {
        "track_date": target_date,
        "pick_date": pick_date,
        "r7_info": r7_info,
        "n_total": n,
        "n_zt": n_zt,
        "avg_chg": round(avg, 3),
        "results": results,
        "stats_orig": {b: dict(s_orig[b]) for b in s_orig},
        "stats_adj": {b: dict(s_adj[b]) for b in s_adj} if r7_triggered else None,
    }
    with open(out_path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\n✅ 落档 {out_path}")


if __name__ == "__main__":
    main()
