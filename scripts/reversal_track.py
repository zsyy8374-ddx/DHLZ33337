#!/usr/bin/env python3
"""
reversal_track.py — REVERSAL 实战命中追踪

每日盘后跑: 看昨天推荐的候选股今天命中几只 (涨停 / 上涨 / 破位)

输入: picks/reversal-v3-{yesterday}.json
查询: 各候选今日涨跌幅 (腾讯实时)
落档: picks/reversal_hits.jsonl (每天追加一行)
推送: 微信汇总报告

用法: python3 reversal_track.py [date]   # date=今日 (评估昨天的推荐)
"""
import json, sys, time, subprocess, re
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
    sym = ("sh" if code.startswith('6') else "sz") + code
    d = http_get(f"http://qt.gtimg.cn/q={sym}")
    if not d or "=" not in d:
        return None
    parts = d.split("~")
    if len(parts) < 35:
        return None
    try:
        return {
            "code": code,
            "name": parts[1],
            "price": float(parts[3]),       # 当前价
            "yclose": float(parts[4]),      # 昨收
            "open": float(parts[5]),
            "high": float(parts[33]),       # 最高
            "low": float(parts[34]),        # 最低
            "chg_pct": float(parts[32]),    # 涨跌幅 %
        }
    except (ValueError, IndexError):
        return None


def is_zt(code, chg_pct):
    if code.startswith(('300', '688')): return chg_pct >= 19.5
    if code.startswith(('8', '4', '9')): return chg_pct >= 29.5
    return chg_pct >= 9.7


def find_recent_picks(target_date):
    """找 target_date 之前最近一天的推荐 (上一交易日推的, 今天来评估)"""
    # 倒推 7 天找
    for back in range(1, 8):
        d_str = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=back)).strftime("%Y-%m-%d")
        path = PICKS_DIR / f"reversal-v3-{d_str}.json"
        if path.exists():
            return path, d_str
    return None, None


def main():
    target_date = None
    for a in sys.argv[1:]:
        if a.startswith("20"): target_date = a
    if not target_date:
        target_date = datetime.now(BJT).strftime("%Y-%m-%d")
    
    pick_path, pick_date = find_recent_picks(target_date)
    if not pick_path:
        print(f"❌ 找不到 {target_date} 之前的 reversal-v3 推荐", flush=True)
        sys.exit(1)
    
    print(f"📊 评估 {pick_date} 的推荐, 评估日 {target_date}", flush=True)
    with open(pick_path) as f:
        d = json.load(f)
    candidates = d["candidates"]
    candidates.sort(key=lambda x: -x["lr_prob"])
    
    # 分档
    tier_a = [c for c in candidates if c["lr_prob"] >= 0.97]      # 极强
    tier_b = [c for c in candidates if 0.443 <= c["lr_prob"] < 0.97]  # 强
    tier_c = [c for c in candidates if 0.6 <= c["lr_prob"] < 0.443]   # (空)
    
    print(f"   极强 {len(tier_a)} | 强 {len(tier_b)}", flush=True)
    print(f"\n查询实时行情...", flush=True)
    
    # 查询所有强档 + 极强 (top 30)
    track_list = (tier_a + tier_b)[:30]
    results = []
    for c in track_list:
        q = fetch_quote(c["code"])
        if q:
            results.append({
                **c,
                "today_chg": q["chg_pct"],
                "today_high": q["high"],
                "today_low": q["low"],
                "today_close": q["price"],
                "is_zt_today": is_zt(c["code"], q["chg_pct"]),
                "touched_zt": q["high"] >= c["d0_close"] * 1.097 if c.get("d0_close") else False,
            })
        time.sleep(0.05)
    
    # 统计命中
    n_zt = sum(1 for r in results if r["is_zt_today"])
    n_pos = sum(1 for r in results if r["today_chg"] > 0)
    n_strong = sum(1 for r in results if r["today_chg"] >= 5)
    n_total = len(results)
    avg_chg = sum(r["today_chg"] for r in results) / n_total if n_total else 0
    
    print(f"\n📈 命中统计 ({n_total} 只):", flush=True)
    print(f"   涨停: {n_zt} ({n_zt/n_total*100:.1f}%)" if n_total else "", flush=True)
    print(f"   上涨: {n_pos} ({n_pos/n_total*100:.1f}%)" if n_total else "", flush=True)
    print(f"   ≥5%涨幅: {n_strong} ({n_strong/n_total*100:.1f}%)" if n_total else "", flush=True)
    print(f"   平均涨幅: {avg_chg:+.2f}%", flush=True)
    
    # 落档 hit_log
    hit_log_path = PICKS_DIR / "reversal_hits.jsonl"
    with open(hit_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "track_date": target_date,
            "pick_date": pick_date,
            "n_total": n_total,
            "n_zt": n_zt,
            "n_pos": n_pos,
            "n_strong5": n_strong,
            "avg_chg": round(avg_chg, 2),
            "results": results,
        }, ensure_ascii=False) + "\n")
    print(f"\n📁 已追加: {hit_log_path}", flush=True)
    
    # 格式化报告
    lines = []
    lines.append(f"⚔️ REVERSAL 命中追踪 {target_date}")
    lines.append(f"━━━━━━━━━━━━━━━━━")
    lines.append(f"评估 {pick_date} 推荐的 {n_total} 只候选")
    lines.append(f"")
    lines.append(f"📊 整体命中:")
    lines.append(f"  涨停: {n_zt}/{n_total} ({n_zt/n_total*100:.0f}%)" if n_total else "  无数据")
    lines.append(f"  上涨: {n_pos}/{n_total} ({n_pos/n_total*100:.0f}%)" if n_total else "")
    lines.append(f"  ≥5%: {n_strong}/{n_total} ({n_strong/n_total*100:.0f}%)" if n_total else "")
    lines.append(f"  平均: {avg_chg:+.2f}%")
    lines.append(f"")
    lines.append(f"🎯 涨停的票:")
    zt_hits = [r for r in results if r["is_zt_today"]]
    if zt_hits:
        for r in zt_hits[:8]:
            lines.append(f"  ✅ {r['code']} {r['name']} P={r['lr_prob']:.2f} +{r['today_chg']:.1f}%")
    else:
        lines.append(f"  无")
    
    lines.append(f"")
    lines.append(f"📈 表现 Top 5:")
    top5 = sorted(results, key=lambda x: -x["today_chg"])[:5]
    for r in top5:
        zt_tag = "✅" if r["is_zt_today"] else " "
        lines.append(f"  {zt_tag} {r['code']} {r['name']} P={r['lr_prob']:.2f} {r['today_chg']:+.1f}%")
    
    lines.append(f"")
    lines.append(f"📉 表现 Bottom 3:")
    bot3 = sorted(results, key=lambda x: x["today_chg"])[:3]
    for r in bot3:
        lines.append(f"  ⚠️ {r['code']} {r['name']} P={r['lr_prob']:.2f} {r['today_chg']:+.1f}%")
    
    msg = "\n".join(lines)
    print("\n" + "="*60, flush=True)
    print(msg, flush=True)
    print("="*60 + "\n", flush=True)
    
    # 推送微信
    cmd = ["openclaw", "message", "send",
           "--channel", "openclaw-weixin",
           "--account", "ba28cc3242ca-im-bot",
           "--target", "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat",
           "--message", msg, "--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        m = re.search(r'\{[\s\S]*\}', r.stdout)
        if m:
            d = json.loads(m.group(0))
            mid = d.get("payload", {}).get("result", {}).get("messageId")
            print(f"✅ 微信推送成功 mid={mid}", flush=True)
    except Exception as e:
        print(f"⚠️ 推送失败: {e}", flush=True)


if __name__ == "__main__":
    main()
