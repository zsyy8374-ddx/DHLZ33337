#!/usr/bin/env python3
"""
reversal_mine_v3.py — 涨停回马枪 v0.3 (主力资金流)

新增特征 (vs v0.2):
- d0_main_flow: D0 涨停日主力净流入额 (亿)
- d0_main_flow_pct: D0 主力净流入占成交额 % (近似)
- d0_super_flow: D0 超大单净流入 (亿) - 真正的"主力"
- callback_main_flow_sum: 回调期主力净流入累计 (亿) ⭐ 核心特征
- callback_main_flow_avg_pct: 回调期日均主力流入占比 %
- callback_super_in_days: 回调期超大单净流入>0 的天数
- pre_d0_5d_flow: D0 之前 5 天主力净流入累计 (吸筹信号?)

关键: 严格按"信息可知顺序"提取 - 推荐时已知 today 之前所有数据,
       但训练时的"回调期"对 reversal 样本必须是 D0+1 ~ D_t-1 (不含 D_t)
       为避免窗口长度泄漏, 这次用比例 (sum / window_size) 做主特征

输入: backtest/reversal-events-2026-04-30-v2.json
输出: backtest/reversal-events-2026-04-30-v3.json
"""
import json, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))


def http_get(url, timeout=15):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
        with urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", errors="ignore")
            if data.startswith("jQuery"):
                start = data.index("(") + 1; end = data.rindex(")")
                data = data[start:end]
            return json.loads(data)
    except Exception as e:
        return None


def get_secid(code):
    return f"1.{code}" if code.startswith('6') else f"0.{code}"


def fetch_fflow(code, lmt=130):
    """拉个股资金流 K 线 (近 lmt 个交易日)"""
    secid = get_secid(code)
    url = (f"http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
           f"?lmt={lmt}&klt=101&secid={secid}"
           f"&fields1=f1,f2,f3,f7"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
           f"&_=1")
    d = http_get(url)
    if not d or not d.get("data"):
        return {}
    klines = d["data"].get("klines", [])
    # 解析: 返回 dict[date -> {main_flow, super_flow, main_pct, close, chg}]
    out = {}
    for line in klines:
        parts = line.split(",")
        if len(parts) < 13: continue
        try:
            date = parts[0]
            out[date] = {
                "main_flow": float(parts[1]),       # 主力净流入额
                "small_flow": float(parts[2]),
                "mid_flow": float(parts[3]),
                "big_flow": float(parts[4]),        # 大单净流入
                "super_flow": float(parts[5]),      # 超大单净流入
                "main_pct": float(parts[6]),        # 主力净流入占比 %
                "super_pct": float(parts[10]),      # 超大单占比
                "close": float(parts[11]),
                "chg": float(parts[12]),
            }
        except (ValueError, IndexError):
            continue
    return out


def extract_v3_features(fflow, e):
    """从资金流数据提取特征"""
    d0_date = e["d0_date"]
    d_t_date = e.get("d_t_date")
    days_between = e.get("days_between")
    
    out = {}
    
    # --- 1. D0 当天 ---
    d0 = fflow.get(d0_date)
    if not d0:
        return None  # 没数据, 跳过
    
    out["d0_main_flow"] = round(d0["main_flow"] / 1e8, 4)        # 亿
    out["d0_super_flow"] = round(d0["super_flow"] / 1e8, 4)
    out["d0_main_pct"] = round(d0["main_pct"], 2)
    out["d0_super_pct"] = round(d0["super_pct"], 2)
    
    # --- 2. 回调期 (D0+1 ~ D_t-1, 不含 D_t) ---
    # 找到 D0 在按日期排序的 fflow 中的位置
    sorted_dates = sorted(fflow.keys())
    if d0_date not in sorted_dates:
        return None
    d0_idx = sorted_dates.index(d0_date)
    
    if d_t_date and d_t_date in sorted_dates:
        end_idx = sorted_dates.index(d_t_date) - 1  # 不含 D_t
    else:
        # failed 样本: 用 D0+10 作为窗口 (与 v2 一致)
        end_idx = min(d0_idx + 10, len(sorted_dates) - 1)
    
    callback_dates = sorted_dates[d0_idx + 1:end_idx + 1]
    
    if not callback_dates:
        out["callback_main_flow_sum"] = 0
        out["callback_main_flow_avg"] = 0
        out["callback_main_pct_avg"] = 0
        out["callback_super_in_days"] = 0
        out["callback_super_in_ratio"] = 0
        out["callback_window"] = 0
    else:
        main_flows = [fflow[d]["main_flow"] for d in callback_dates if d in fflow]
        super_flows = [fflow[d]["super_flow"] for d in callback_dates if d in fflow]
        main_pcts = [fflow[d]["main_pct"] for d in callback_dates if d in fflow]
        n = len(main_flows)
        out["callback_window"] = n
        out["callback_main_flow_sum"] = round(sum(main_flows) / 1e8, 4)
        # ⚠️ 用平均, 避免窗口长度泄漏
        out["callback_main_flow_avg"] = round(sum(main_flows) / n / 1e8, 4) if n else 0
        out["callback_main_pct_avg"] = round(sum(main_pcts) / n, 2) if n else 0
        out["callback_super_in_days"] = sum(1 for v in super_flows if v > 0)
        out["callback_super_in_ratio"] = round(out["callback_super_in_days"] / n, 3) if n else 0
    
    # --- 3. D0 之前 5 天 (吸筹信号) ---
    pre5 = sorted_dates[max(0, d0_idx - 5):d0_idx]
    if pre5:
        main_flows_pre = [fflow[d]["main_flow"] for d in pre5 if d in fflow]
        if main_flows_pre:
            out["pre_d0_5d_main_avg"] = round(sum(main_flows_pre) / len(main_flows_pre) / 1e8, 4)
            out["pre_d0_5d_super_in_days"] = sum(1 for d in pre5 if d in fflow and fflow[d]["super_flow"] > 0)
        else:
            out["pre_d0_5d_main_avg"] = 0
            out["pre_d0_5d_super_in_days"] = 0
    else:
        out["pre_d0_5d_main_avg"] = 0
        out["pre_d0_5d_super_in_days"] = 0
    
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
    no_fflow = 0
    
    for i, (code, code_events) in enumerate(code_to_events.items()):
        fflow = fetch_fflow(code, lmt=160)
        if not fflow:
            no_fflow += len(code_events)
            time.sleep(0.1)
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
            print(f"   [{i+1}/{len(code_to_events)}] 累计 {len(enriched)} | 缺资金流 {no_fflow} | 失败 {failed}", flush=True)
        time.sleep(0.08)  # 避免限流
    
    print(f"\n📈 v0.3 enriched: {len(enriched)} (无资金流 {no_fflow}, 提取失败 {failed})", flush=True)
    
    # 简单分箱看信号
    if enriched:
        # 主力净流入分箱
        print(f"\n   D0 主力净流入分箱:", flush=True)
        bins = [(-100, -2, "<-2亿"), (-2, -0.5, "-2~-0.5亿"), (-0.5, 0, "-0.5~0亿"),
                (0, 0.5, "0~0.5亿"), (0.5, 2, "0.5~2亿"), (2, 100, "≥2亿")]
        for lo, hi, lab in bins:
            sub = [e for e in enriched if lo <= e["d0_main_flow"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
        
        # 回调期主力日均
        print(f"\n   回调期主力日均净流入分箱:", flush=True)
        for lo, hi, lab in bins:
            sub = [e for e in enriched if lo <= e["callback_main_flow_avg"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
        
        # 回调期超大单净流入天数比例
        print(f"\n   回调期超大单净流入天数比例:", flush=True)
        for lo, hi, lab in [(0, 0.2, "<20%"), (0.2, 0.4, "20-40%"), (0.4, 0.6, "40-60%"),
                             (0.6, 0.8, "60-80%"), (0.8, 1.01, "≥80%")]:
            sub = [e for e in enriched if lo <= e["callback_super_in_ratio"] < hi]
            if sub:
                success = sum(1 for e in sub if e["outcome"] == "reversal")
                print(f"     {lab:<15} n={len(sub):4} 回马枪率={success/len(sub)*100:.1f}%", flush=True)
    
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    out = BACKTEST_DIR / f"reversal-events-{today}-v3.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "scan_date": today,
            "version": "v0.3",
            "n_total": len(enriched),
            "n_reversal": sum(1 for e in enriched if e["outcome"] == "reversal"),
            "events": enriched,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {out}", flush=True)


if __name__ == "__main__":
    main()
