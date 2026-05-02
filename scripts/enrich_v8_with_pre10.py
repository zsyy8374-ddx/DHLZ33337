"""给 v8-enriched (3262 events) 补 pre10 持续性特征
- pre10_days_in: D0 前 10 个交易日主力流入天数 (0-10)
- pre10_max_streak: 最长连续流入
- pre10_main_total: 累计净流入 (亿)
- pre10_main_avg: 日均
- pre10_strong_days: 单日 ≥0.5亿 的天数

数据源: 新浪 fflow API (跟 enrich_v7_with_fflow.py 同), num=600 一股拉一次

输出: backtest/reversal-events-2026-05-01-v9-with-pre10.json
"""
import json, time, sys
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"

def http_get(url, timeout=15):
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
        time.sleep(1.5 + attempt * 2)
    if not data or not data.startswith("[{"): return {}
    try:
        items = json.loads(data)
        out = {}
        for it in items:
            date = it.get("opendate")
            if not date: continue
            try:
                out[date] = float(it.get("r0_net") or 0)  # 主力净流入 元
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        return {}


def compute_pre10(fflow_map, d0_date):
    """从已拉好的 fflow 里切 D0 前 10 个交易日"""
    pre = sorted([(d, m) for d, m in fflow_map.items() if d < d0_date], key=lambda x: x[0])
    if len(pre) < 5: return None
    pre10 = pre[-10:]
    n = len(pre10)
    days_in = sum(1 for _, m in pre10 if m > 0)
    
    max_streak = cur_streak = 0
    for _, m in pre10:
        if m > 0:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0
    
    total_yuan = sum(m for _, m in pre10)
    strong_days = sum(1 for _, m in pre10 if m >= 5e7)  # ≥0.5亿
    
    return {
        "pre10_n": n,
        "pre10_days_in": days_in,
        "pre10_in_ratio": round(days_in / n, 3),
        "pre10_max_streak": max_streak,
        "pre10_main_total": round(total_yuan / 1e8, 3),
        "pre10_main_avg": round(total_yuan / n / 1e8, 3),
        "pre10_strong_days": strong_days,
    }


def main():
    src = BACKTEST_DIR / "reversal-events-2026-05-01-v8-enriched.json"
    with open(src) as f:
        data = json.load(f)
    events = data["events"]
    print(f"📊 待补 pre10: {len(events)} 事件", flush=True)
    
    by_code = {}
    for e in events:
        by_code.setdefault(e["code"], []).append(e)
    codes = sorted(by_code.keys())
    print(f"📊 unique codes: {len(codes)}", flush=True)
    
    ckpt_path = BACKTEST_DIR / "v9_pre10_ckpt.json"
    done_codes = set()
    enriched = []
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
        done_codes = set(ckpt.get("done", []))
        enriched = ckpt.get("enriched", [])
        print(f"♻️ checkpoint: {len(done_codes)} codes done, {len(enriched)} events", flush=True)
    
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
            time.sleep(0.4)
            continue
        for e in by_code[code]:
            pre10 = compute_pre10(fflow, e["d0_date"])
            if pre10:
                e2 = dict(e)
                e2.update(pre10)
                enriched.append(e2)
            else:
                skip_count += 1
        done_codes.add(code)
        time.sleep(0.4)
        
        # checkpoint 每 50 股
        if (i+1) % 50 == 0:
            elapsed = time.time() - t0
            speed = (i+1) / elapsed if elapsed > 0 else 0
            eta = (len(codes) - i - 1) / max(speed, 0.01)
            with open(ckpt_path, "w") as f:
                json.dump({"done": list(done_codes), "enriched": enriched}, f)
            print(f"  [{i+1}/{len(codes)}] enriched={len(enriched)} fail={fail_count} skip={skip_count} speed={speed*60:.1f}/分 ETA={eta/60:.1f}分", flush=True)
    
    # 落档
    out_path = BACKTEST_DIR / "reversal-events-2026-05-01-v9-with-pre10.json"
    with open(out_path, "w") as f:
        json.dump({"events": enriched, "n_orig": len(events), "n_enriched": len(enriched)}, f, ensure_ascii=False)
    print(f"\n✅ 落档: {out_path.name} ({len(enriched)} 事件)")
    
    # 删 checkpoint
    if ckpt_path.exists():
        ckpt_path.unlink()
    print(f"   总计: 成功 {len(enriched)}, 失败 {fail_count}, 缺数据跳过 {skip_count}")
    print(f"   耗时: {(time.time()-t0)/60:.1f} 分钟")


if __name__ == "__main__":
    main()
