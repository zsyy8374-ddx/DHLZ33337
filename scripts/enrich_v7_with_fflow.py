"""给 v7_extended 的 3262 events 补新浪资金流
- 新浪 fflow API 能拉 600 条/股 (近 2.5 年)
- 每个 event 算 cb1/cb3/cb5_main_avg, d0_main_flow, pre_d0_5d_main_avg
- 用 unified D0+1 to D0+5 窗口 (避免泄漏)
"""
import json, time, sys
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"

def http_get(url, timeout=12):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_sina_fflow(code, num=600, retries=3):
    prefix = "sh" if code.startswith('6') else "sz"
    url = (f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={num}&sort=opendate&asc=0&daima={prefix}{code}")
    for attempt in range(retries):
        data = http_get(url, timeout=15)
        if data and data.startswith("[{"): break
        time.sleep(2 + attempt * 2)
    if not data or not data.startswith("[{"): return {}
    try:
        items = json.loads(data)
        out = {}
        for it in items:
            date = it.get("opendate")
            if not date: continue
            try:
                out[date] = {
                    "main_net": float(it.get("r0_net") or 0),  # 主力净流入 (元)
                    "main_ratio": float(it.get("r0_ratio") or 0),
                    "main_strength": float(it.get("r0x_ratio") or 0),
                }
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        return {}


def enrich_event(e, fflow):
    """给单个事件补资金流"""
    d0 = e["d0_date"]
    if d0 not in fflow: return None  # 这天没数据
    
    # D0 当日主力流入
    d0_main = fflow[d0]["main_net"] / 1e8  # 转亿
    
    # 近 5 个交易日 (D0-5 到 D0-1) 主力日均
    pre_dates = sorted([d for d in fflow if d < d0])[-5:]
    if pre_dates:
        pre_avg = sum(fflow[d]["main_net"] for d in pre_dates) / len(pre_dates) / 1e8
    else:
        pre_avg = 0
    
    # D0+1 到 D0+5 主力 (不依赖 D_t, 避免泄漏)
    post_dates = sorted([d for d in fflow if d > d0])[:5]
    cb1_main = fflow[post_dates[0]]["main_net"] / 1e8 if post_dates else 0
    cb3_dates = post_dates[:3]
    cb5_dates = post_dates[:5]
    cb3_main = sum(fflow[d]["main_net"] for d in cb3_dates) / max(1, len(cb3_dates)) / 1e8
    cb5_main = sum(fflow[d]["main_net"] for d in cb5_dates) / max(1, len(cb5_dates)) / 1e8
    
    # cb5_in_ratio: 5 天里主力净流入为正的比例
    cb5_pos = sum(1 for d in cb5_dates if fflow[d]["main_net"] > 0)
    cb5_in_ratio = cb5_pos / max(1, len(cb5_dates))
    
    # 至少要有 D0+1
    if not post_dates: return None
    
    e2 = dict(e)
    e2["d0_main_flow"] = round(d0_main, 3)
    e2["pre_d0_5d_main_avg"] = round(pre_avg, 3)
    e2["cb1_main_avg"] = round(cb1_main, 3)
    e2["cb3_main_avg"] = round(cb3_main, 3)
    e2["cb5_main_avg"] = round(cb5_main, 3)
    e2["cb5_in_ratio"] = round(cb5_in_ratio, 3)
    return e2


def main():
    src = BACKTEST_DIR / "reversal-events-2026-05-01-v7.json"
    with open(src) as f:
        data = json.load(f)
    events = data["events"]
    print(f"📊 待补资金流: {len(events)} 事件", flush=True)
    
    # 按 code 分组
    by_code = {}
    for e in events:
        by_code.setdefault(e["code"], []).append(e)
    codes = sorted(by_code.keys())
    print(f"📊 unique codes: {len(codes)}", flush=True)
    
    # checkpoint
    ckpt_path = BACKTEST_DIR / "v7_enrich_ckpt.json"
    done_codes = set()
    enriched = []
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        done_codes = set(ckpt.get("done", []))
        enriched = ckpt.get("enriched", [])
        print(f"♻️ checkpoint: {len(done_codes)} codes done, {len(enriched)} enriched events", flush=True)
    
    fail_count = 0
    skip_count = 0
    t0 = time.time()
    for i, code in enumerate(codes):
        if code in done_codes:
            continue
        fflow = fetch_sina_fflow(code, num=600)
        if not fflow:
            fail_count += len(by_code[code])
            done_codes.add(code)
            time.sleep(0.5)
            continue
        for e in by_code[code]:
            ne = enrich_event(e, fflow)
            if ne:
                enriched.append(ne)
            else:
                skip_count += 1
        done_codes.add(code)
        time.sleep(0.3)
        if (i+1) % 30 == 0:
            elapsed = time.time() - t0
            new_done = i+1 - len([c for c in codes[:i+1] if c not in done_codes])
            rate = (i+1) / elapsed
            eta = (len(codes) - i - 1) / rate
            print(f"  [{i+1}/{len(codes)}] enriched {len(enriched)} | fail {fail_count} | skip {skip_count} | {elapsed:.0f}s ETA {eta:.0f}s", flush=True)
            with open(ckpt_path, "w") as f:
                json.dump({"done": list(done_codes), "enriched": enriched}, f, ensure_ascii=False)
    
    print(f"\n✅ Enriched {len(enriched)} events (fail {fail_count}, skip {skip_count})", flush=True)
    
    # 落档
    out = BACKTEST_DIR / "reversal-events-2026-05-01-v8-enriched.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v0.8-enriched",
            "n_events": len(enriched),
            "events": enriched,
        }, f, ensure_ascii=False, indent=2)
    print(f"📁 落档: {out}", flush=True)
    
    # cb5 分箱
    print("\n📊 cb5_main_avg 分箱反转率:")
    bins = [(-99, -1), (-1, -0.3), (-0.3, 0), (0, 0.3), (0.3, 1), (1, 2), (2, 5), (5, 999)]
    for lo, hi in bins:
        sub = [e for e in enriched if lo <= e["cb5_main_avg"] < hi]
        if not sub: continue
        rev = sum(1 for e in sub if e["outcome"] == "reversal")
        print(f"  {lo:>+3}~{hi:<+3}亿: n={len(sub):>4}, 反转 {rev/len(sub)*100:.1f}%")


if __name__ == "__main__":
    main()
