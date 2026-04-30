#!/usr/bin/env python3
"""
reversal_mine_v3_sina.py — v0.3 主力资金流 (用新浪 API)

新浪 vip.stock.finance.sina.com.cn 资金流 API:
- 字段: netamount (净流入), r0_net (主力大单净流入), r0_ratio (主力大单占比)
- 一次拉 120 条 = 半年历史
- 没区分超大单/大单 (合并为 r0_net)

特征:
- d0_main_flow: D0 主力大单净流入 (亿)
- d0_main_ratio: D0 主力大单占比
- d0_net_flow: D0 总净流入 (亿)
- callback_main_flow_avg: 回调期日均主力大单 (亿) - 避免窗口长度泄漏
- callback_main_ratio_avg: 回调期日均主力占比
- callback_in_days_ratio: 回调期主力净流入 > 0 的天数比例
- pre_d0_5d_main_avg: D0 前 5 天主力大单日均 (吸筹信号)
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
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_sina_fflow(code, num=120, retry=3):
    """拉新浪资金流"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = (f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={num}&sort=opendate&asc=0&daima={prefix}{code}")
    for attempt in range(retry):
        d = http_get(url)
        if d and d.startswith("[{"):
            try:
                items = json.loads(d)
                # 转成 dict[date -> {...}]
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
                            "turnover": float(it.get("turnover") or 0),
                            "chg": float(it.get("changeratio") or 0) * 100,
                        }
                    except (ValueError, TypeError):
                        continue
                return out
            except Exception:
                pass
        time.sleep(0.5 * (attempt + 1))
    return {}


def extract_v3_features(fflow, e):
    d0_date = e["d0_date"]
    d_t_date = e.get("d_t_date")
    
    out = {}
    sorted_dates = sorted(fflow.keys())
    if d0_date not in sorted_dates:
        return None
    d0_idx = sorted_dates.index(d0_date)
    
    # D0 当天
    d0 = fflow.get(d0_date)
    if not d0:
        return None
    out["d0_main_flow"] = round(d0["main_net"] / 1e8, 4)
    out["d0_main_ratio"] = round(d0["main_ratio"] * 100, 2) if abs(d0["main_ratio"]) < 10 else round(d0["main_ratio"], 2)
    out["d0_net_flow"] = round(d0["net"] / 1e8, 4)
    out["d0_main_strength"] = round(d0["main_strength"], 2)
    
    # 回调期 (D0+1 ~ D_t-1, 不含 D_t; failed 用 D0+1 ~ D0+10)
    if d_t_date and d_t_date in sorted_dates:
        end_idx = sorted_dates.index(d_t_date) - 1
    else:
        end_idx = min(d0_idx + 10, len(sorted_dates) - 1)
    
    callback_dates = sorted_dates[d0_idx + 1:end_idx + 1]
    if callback_dates:
        n = len(callback_dates)
        main_nets = [fflow[d]["main_net"] for d in callback_dates if d in fflow]
        main_ratios = [fflow[d]["main_ratio"] for d in callback_dates if d in fflow]
        if main_nets:
            out["callback_main_flow_avg"] = round(sum(main_nets) / len(main_nets) / 1e8, 4)
            out["callback_main_ratio_avg"] = round(sum(main_ratios) / len(main_ratios) * 100, 2) if abs(main_ratios[0]) < 10 else round(sum(main_ratios) / len(main_ratios), 2)
            out["callback_in_days"] = sum(1 for v in main_nets if v > 0)
            out["callback_in_days_ratio"] = round(out["callback_in_days"] / len(main_nets), 3)
            out["callback_window"] = len(main_nets)
        else:
            out["callback_main_flow_avg"] = 0
            out["callback_main_ratio_avg"] = 0
            out["callback_in_days"] = 0
            out["callback_in_days_ratio"] = 0
            out["callback_window"] = 0
    else:
        out["callback_main_flow_avg"] = 0
        out["callback_main_ratio_avg"] = 0
        out["callback_in_days"] = 0
        out["callback_in_days_ratio"] = 0
        out["callback_window"] = 0
    
    # D0 前 5 天 (吸筹)
    pre5_dates = sorted_dates[max(0, d0_idx - 5):d0_idx]
    if pre5_dates:
        pre5_nets = [fflow[d]["main_net"] for d in pre5_dates if d in fflow]
        if pre5_nets:
            out["pre_d0_5d_main_avg"] = round(sum(pre5_nets) / len(pre5_nets) / 1e8, 4)
            out["pre_d0_5d_in_days"] = sum(1 for v in pre5_nets if v > 0)
        else:
            out["pre_d0_5d_main_avg"] = 0
            out["pre_d0_5d_in_days"] = 0
    else:
        out["pre_d0_5d_main_avg"] = 0
        out["pre_d0_5d_in_days"] = 0
    
    return out


def main():
    src = BACKTEST_DIR / "reversal-events-2026-04-30-v2.json"
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 加载 v0.2: {len(events)} 个事件", flush=True)
    
    code_to_events = {}
    for e in events:
        code_to_events.setdefault(e["code"], []).append(e)
    print(f"   独立股票 {len(code_to_events)} 只", flush=True)
    
    enriched = []
    failed = 0
    no_fflow = []
    
    t0 = time.time()
    for i, (code, code_events) in enumerate(code_to_events.items()):
        fflow = fetch_sina_fflow(code, num=120, retry=2)
        if not fflow:
            no_fflow.extend(e for e in code_events)
            time.sleep(0.05)
            continue
        
        for e in code_events:
            v3 = extract_v3_features(fflow, e)
            if v3 is None:
                failed += 1
                continue
            new_e = dict(e)
            new_e.update(v3)
            enriched.append(new_e)
        
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"   [{i+1}/{len(code_to_events)}] 累计 {len(enriched)} | 缺数据 {len(no_fflow)} | {elapsed:.0f}s", flush=True)
        time.sleep(0.05)
    
    print(f"\n📈 v0.3 enriched: {len(enriched)} (无资金流 {len(no_fflow)}, 提取失败 {failed})", flush=True)
    
    if enriched:
        # D0 主力净流入
        print(f"\n   D0 主力大单净流入分箱:", flush=True)
        bins = [(-100, -2, "<-2亿"), (-2, -0.5, "-2~-0.5亿"), (-0.5, 0, "-0.5~0亿"),
                (0, 0.5, "0~0.5亿"), (0.5, 2, "0.5~2亿"), (2, 5, "2~5亿"), (5, 100, "≥5亿")]
        for lo, hi, lab in bins:
            sub = [e for e in enriched if lo <= e["d0_main_flow"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
        
        # 回调期日均
        print(f"\n   回调期主力日均净流入分箱:", flush=True)
        for lo, hi, lab in bins:
            sub = [e for e in enriched if lo <= e["callback_main_flow_avg"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
        
        # 回调期净流入天数比例
        print(f"\n   回调期主力净流入>0 天数比例:", flush=True)
        for lo, hi, lab in [(0, 0.2, "<20%"), (0.2, 0.4, "20-40%"), (0.4, 0.6, "40-60%"),
                             (0.6, 0.8, "60-80%"), (0.8, 1.01, "≥80%")]:
            sub = [e for e in enriched if lo <= e["callback_in_days_ratio"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
        
        # D0 主力占比
        print(f"\n   D0 主力大单占比 r0_ratio (强度):", flush=True)
        for lo, hi, lab in [(-100, -10, "<-10%"), (-10, -5, "-10~-5%"), (-5, 0, "-5~0%"),
                             (0, 5, "0~5%"), (5, 10, "5~10%"), (10, 20, "10~20%"), (20, 100, "≥20%")]:
            sub = [e for e in enriched if lo <= e["d0_main_ratio"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
    
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    out = BACKTEST_DIR / f"reversal-events-{today}-v3.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "scan_date": today,
            "version": "v0.3-sina",
            "n_total": len(enriched),
            "n_reversal": sum(1 for e in enriched if e["outcome"] == "reversal"),
            "events": enriched,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {out}", flush=True)


if __name__ == "__main__":
    main()
