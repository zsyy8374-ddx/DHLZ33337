#!/usr/bin/env python3
"""
reversal_mine_v4.py — v0.4 修复 v0.3 的窗口泄漏

v0.3 BUG:
  - reversal 的 callback_main_flow_avg 是 D0+1 到 D_t-1 (1-9 天)
  - failed   的 callback_main_flow_avg 是 D0+1 到 D0+10 (固定 10 天)
  - callback_window 100% 区分两类样本 → 资金流均值间接编码 outcome
  - AUC 0.80 不可信

v0.4 修复:
  - 所有事件统一用 D0+1 到 D0+5 的资金流均值 (cb5)
  - 同时保留 D0+1 到 D0+min(实际, 5) 来覆盖 D_t<=5 天的 reversal
  - 增加 cb1 (D0+1 单天), cb3 (D0+1 到 D0+3) 用做对比

预期: AUC 会比 0.80 低, 但代表真实样本外性能
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


def fetch_sina_fflow(code, num=120):
    prefix = "sh" if code.startswith('6') else "sz"
    url = (f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={num}&sort=opendate&asc=0&daima={prefix}{code}")
    data = http_get(url, timeout=8)
    if not data or not data.startswith("[{"): return {}
    try:
        items = json.loads(data)
        out = {}
        for it in items:
            date = it.get("opendate")
            if not date: continue
            try:
                out[date] = {
                    "net": float(it.get("netamount") or 0),
                    "main_net": float(it.get("r0_net") or 0),
                    "main_ratio": float(it.get("r0_ratio") or 0),
                    "main_strength": float(it.get("r0x_ratio") or 0),
                }
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        return {}


def enrich_event(event, fflow):
    """统一用 D0+1 到 D0+5 / D0+3 / D0+1 三个窗口算资金流, 不依赖 D_t"""
    out = copy.copy(event)
    
    # 清理 v0.3 的旧字段 (会被替换)
    for k in ["callback_main_flow_avg", "callback_main_ratio_avg",
              "callback_in_days", "callback_in_days_ratio", "callback_window"]:
        out.pop(k, None)
    
    if not fflow:
        return None
    
    d0_date = event["d0_date"]
    sorted_dates = sorted(fflow.keys())
    if d0_date not in sorted_dates:
        return None
    d0_idx = sorted_dates.index(d0_date)
    
    if d0_date not in fflow:
        return None
    d0 = fflow[d0_date]
    
    # D0 字段已经在 v0.3 算过, 保留
    if "d0_main_flow" not in out:
        out["d0_main_flow"] = round(d0["main_net"] / 1e8, 4)
        out["d0_main_ratio"] = round(d0["main_ratio"] * 100, 2) if abs(d0["main_ratio"]) < 10 else round(d0["main_ratio"], 2)
    
    # ✅ 关键: 统一窗口 (D0+1 到 D0+k)
    for k in [1, 3, 5]:
        end_idx = min(d0_idx + k, len(sorted_dates) - 1)
        win_dates = sorted_dates[d0_idx + 1:end_idx + 1]
        if not win_dates:
            out[f"cb{k}_main_avg"] = 0
            out[f"cb{k}_in_ratio"] = 0
            out[f"cb{k}_window"] = 0
            continue
        main_nets = [fflow[d]["main_net"] for d in win_dates if d in fflow]
        if main_nets:
            out[f"cb{k}_main_avg"] = round(sum(main_nets) / len(main_nets) / 1e8, 4)
            out[f"cb{k}_in_ratio"] = round(sum(1 for v in main_nets if v > 0) / len(main_nets), 3)
            out[f"cb{k}_window"] = len(main_nets)
        else:
            out[f"cb{k}_main_avg"] = 0
            out[f"cb{k}_in_ratio"] = 0
            out[f"cb{k}_window"] = 0
    
    return out


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    src = BACKTEST_DIR / f"reversal-events-{today}-v3.json"
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 加载 v0.3: {len(events)} 个事件", flush=True)
    
    # 按 code 分组, 每只票拉一次资金流
    codes = sorted(set(e["code"] for e in events))
    print(f"   独立股票 {len(codes)} 只\n", flush=True)
    
    fflow_cache = {}
    enriched = []
    failed = 0
    t0 = time.time()
    
    for i, code in enumerate(codes):
        # 重用 v0.3 拉过的 (但因为 v0.3 缓存过了, 可能已没了, 再拉一次)
        fflow = fetch_sina_fflow(code, num=120)
        time.sleep(0.05)
        fflow_cache[code] = fflow
        
        for e in events:
            if e["code"] != code: continue
            ne = enrich_event(e, fflow)
            if ne:
                enriched.append(ne)
            else:
                failed += 1
        
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i+1) / elapsed
            eta = (len(codes) - i - 1) / rate
            print(f"   [{i+1}/{len(codes)}] 累计 {len(enriched)} | 失败 {failed} | {elapsed:.0f}s ETA {eta:.0f}s", flush=True)
    
    print(f"\n✅ v0.4 enriched: {len(enriched)} (失败 {failed})", flush=True)
    
    # 落档
    save_path = BACKTEST_DIR / f"reversal-events-{today}-v4.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump({"version": "reversal-events-v0.4", "n_events": len(enriched), "events": enriched},
                  f, ensure_ascii=False, indent=2)
    print(f"\n📁 落档: {save_path}", flush=True)
    
    # 快速分箱看 cb5_main_avg 的信号
    print("\n📊 cb5_main_avg 分箱 (D0+1 到 D0+5 主力日均, 统一窗口):", flush=True)
    bins = [(-99, -2), (-2, -0.5), (-0.5, 0), (0, 0.5), (0.5, 2), (2, 5), (5, 999)]
    labels = ["<-2亿", "-2~-0.5亿", "-0.5~0亿", "0~0.5亿", "0.5~2亿", "2~5亿", "≥5亿"]
    for (lo, hi), lbl in zip(bins, labels):
        sub = [e for e in enriched if lo <= e["cb5_main_avg"] < hi]
        if not sub: continue
        rev = sum(1 for e in sub if e["outcome"] == "reversal")
        print(f"   {lbl:<12} n={len(sub):>4} 回马枪率={rev/len(sub)*100:5.1f}%", flush=True)
    
    print("\n📊 cb5_in_ratio 分箱:", flush=True)
    bins2 = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    labels2 = ["<20%", "20-40%", "40-60%", "60-80%", "≥80%"]
    for (lo, hi), lbl in zip(bins2, labels2):
        sub = [e for e in enriched if lo <= e["cb5_in_ratio"] < hi]
        if not sub: continue
        rev = sum(1 for e in sub if e["outcome"] == "reversal")
        print(f"   {lbl:<8} n={len(sub):>4} 回马枪率={rev/len(sub)*100:5.1f}%", flush=True)
    
    # 关键验证: 现在 cb5_window 是不是 reversal/failed 都一样了?
    print("\n✅ 验证窗口是否对称:", flush=True)
    from collections import Counter
    rev_w5 = Counter(e["cb5_window"] for e in enriched if e["outcome"] == "reversal")
    fail_w5 = Counter(e["cb5_window"] for e in enriched if e["outcome"] != "reversal")
    print(f"   reversal cb5_window: {dict(rev_w5.most_common(5))}", flush=True)
    print(f"   failed   cb5_window: {dict(fail_w5.most_common(5))}", flush=True)


if __name__ == "__main__":
    main()
