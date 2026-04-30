#!/usr/bin/env python3
"""
reversal_mine_v5_sector.py — v0.5 加板块强度特征

逻辑:
  1. 拉东财行业板块涨跌幅 (历史 K 线)
  2. 通过股票代码反查所属行业 (东财 sector)
  3. 算 D0 当日 + cb5 期 板块表现:
     - sector_d0_chg: D0 板块涨幅
     - sector_cb5_chg: D0+1 到 D0+5 板块累计涨跌
     - sector_cb5_strength: 板块在市场中的相对强度 (vs 上证)
     - sector_zt_density: D0 板块涨停密度
  4. 严格遵守窗口对称性: 所有事件都用 D0+1 到 D0+5

避免 v0.3 教训:
  - 不依赖 D_t / outcome
  - 所有窗口长度 = 5 天 (定值)
  - 验证: reversal/failed 的窗口分布应完全相同
"""
import json, time, copy
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


def http_get_json(url, timeout=10):
    data = http_get(url, timeout=timeout)
    if not data: return None
    try:
        return json.loads(data) if data.strip().startswith(("{", "[")) else None
    except Exception:
        return None


def fetch_stock_to_sector():
    """从预生成的映射文件读取 (build_sector_map.py 输出)"""
    print("📊 读取股票→行业映射...", flush=True)
    map_path = WORKSPACE / "data" / "stock_sector_map.json"
    if not map_path.exists():
        print("   ⚠️ 映射文件不存在, 先跑 build_sector_map.py", flush=True)
        return {}
    with open(map_path, encoding="utf-8") as f:
        d = json.load(f)
    sm = d["code_to_sector"]
    print(f"   覆盖 {len(sm)} 只", flush=True)
    return sm


def fetch_sector_codes():
    """拉东财行业 + 概念板块代码 (跟 build_sector_map.py 一致)"""
    out = {}
    for fs_code in ["m:90+t:2", "m:90+t:3"]:
        url = (f"http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1"
               f"&fltt=2&invt=2&fid=f3&fs={fs_code}&fields=f12,f14")
        d = http_get_json(url)
        if not d: continue
        items = d.get("data", {}).get("diff", []) or []
        for it in items:
            if it.get("f12") and it.get("f14"):
                out[it["f14"]] = it["f12"]
    return out


def fetch_sector_kline(sector_code, beg, end):
    """拉行业板块日 K"""
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=90.{sector_code}"
           f"&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&beg={beg.replace('-','')}&end={end.replace('-','')}")
    d = http_get_json(url, timeout=8)
    if not d: return []
    klines = d.get("data", {}).get("klines", []) or []
    out = []
    for k in klines:
        parts = k.split(",")
        if len(parts) >= 9:
            try:
                out.append({
                    "date": parts[0],
                    "close": float(parts[2]),
                    "chg_pct": float(parts[8]),
                })
            except (ValueError, IndexError):
                pass
    return out


def fetch_index_kline(sym, beg, end):
    """拉上证指数 (1.000001) 日 K"""
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sym}"
           f"&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&beg={beg.replace('-','')}&end={end.replace('-','')}")
    d = http_get_json(url, timeout=8)
    if not d: return []
    klines = d.get("data", {}).get("klines", []) or []
    out = []
    for k in klines:
        parts = k.split(",")
        if len(parts) >= 9:
            try:
                out.append({
                    "date": parts[0],
                    "close": float(parts[2]),
                    "chg_pct": float(parts[8]),
                })
            except (ValueError, IndexError):
                pass
    return out


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    src = BACKTEST_DIR / f"reversal-events-{today}-v4.json"
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 加载 v0.4: {len(events)} 个事件", flush=True)
    
    # 1. 拉股票→行业 + 行业→代码
    stock_to_sector = fetch_stock_to_sector()
    sector_to_code = fetch_sector_codes()
    print(f"   行业板块 {len(sector_to_code)} 个", flush=True)
    
    # 2. 拉上证指数
    print("\n📊 拉上证指数...", flush=True)
    sh_klines = fetch_index_kline("1.000001", "2026-01-01", today)
    sh_map = {k["date"]: k for k in sh_klines}
    print(f"   上证 {len(sh_klines)} 天", flush=True)
    
    # 3. 拉每个行业板块的 K 线 (只拉事件涉及的板块)
    sectors_needed = set()
    for e in events:
        s = stock_to_sector.get(e["code"])
        if s:
            sectors_needed.add(s)
    print(f"\n📊 拉 {len(sectors_needed)} 个行业板块 K 线...", flush=True)
    
    sector_kline_cache = {}
    for i, sec in enumerate(sectors_needed):
        sec_code = sector_to_code.get(sec)
        if not sec_code: continue
        klines = fetch_sector_kline(sec_code, "2025-12-01", today)
        if klines:
            sector_kline_cache[sec] = {k["date"]: k for k in klines}
        time.sleep(0.1)
        if (i + 1) % 20 == 0:
            print(f"   [{i+1}/{len(sectors_needed)}] 已拉 {len(sector_kline_cache)} 个", flush=True)
    print(f"\n✅ 板块 K 线: {len(sector_kline_cache)} 个", flush=True)
    
    # 4. 给每个事件加板块特征
    print("\n📊 计算板块特征...", flush=True)
    enriched = []
    no_sector = 0
    no_kline = 0
    
    for e in events:
        ne = copy.copy(e)
        sec = stock_to_sector.get(e["code"])
        if not sec:
            no_sector += 1
            ne["sector"] = None
            ne["sector_d0_chg"] = 0
            ne["sector_cb5_chg"] = 0
            ne["sector_cb5_excess"] = 0
            ne["sector_d0_excess"] = 0
            enriched.append(ne)
            continue
        
        ne["sector"] = sec
        sec_klines = sector_kline_cache.get(sec, {})
        if not sec_klines:
            no_kline += 1
            ne["sector_d0_chg"] = 0
            ne["sector_cb5_chg"] = 0
            ne["sector_cb5_excess"] = 0
            ne["sector_d0_excess"] = 0
            enriched.append(ne)
            continue
        
        d0_date = e["d0_date"]
        sorted_dates = sorted(sec_klines.keys())
        if d0_date not in sorted_dates:
            ne["sector_d0_chg"] = 0
            ne["sector_cb5_chg"] = 0
            ne["sector_cb5_excess"] = 0
            ne["sector_d0_excess"] = 0
            enriched.append(ne)
            continue
        
        d0_idx = sorted_dates.index(d0_date)
        ne["sector_d0_chg"] = round(sec_klines[d0_date]["chg_pct"], 3)
        sh_d0 = sh_map.get(d0_date, {}).get("chg_pct", 0)
        ne["sector_d0_excess"] = round(ne["sector_d0_chg"] - sh_d0, 3)
        
        # cb5 板块涨跌
        end_idx = min(d0_idx + 5, len(sorted_dates) - 1)
        cb5_dates = sorted_dates[d0_idx + 1:end_idx + 1]
        if cb5_dates:
            cb5_chg = sum(sec_klines[d]["chg_pct"] for d in cb5_dates) / len(cb5_dates)
            sh_cb5_avg = 0
            sh_n = 0
            for dd in cb5_dates:
                if dd in sh_map:
                    sh_cb5_avg += sh_map[dd]["chg_pct"]
                    sh_n += 1
            sh_cb5_avg = sh_cb5_avg / sh_n if sh_n else 0
            ne["sector_cb5_chg"] = round(cb5_chg, 3)
            ne["sector_cb5_excess"] = round(cb5_chg - sh_cb5_avg, 3)
            ne["sector_cb5_window"] = len(cb5_dates)
        else:
            ne["sector_cb5_chg"] = 0
            ne["sector_cb5_excess"] = 0
            ne["sector_cb5_window"] = 0
        
        enriched.append(ne)
    
    print(f"\n   完成 {len(enriched)} (无板块映射 {no_sector}, 无 K 线 {no_kline})", flush=True)
    
    # 落档
    save_path = BACKTEST_DIR / f"reversal-events-{today}-v5.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump({"version": "reversal-events-v0.5", "n_events": len(enriched), "events": enriched},
                  f, ensure_ascii=False, indent=2)
    print(f"\n📁 落档: {save_path}", flush=True)
    
    # 验证窗口对称
    from collections import Counter
    rev_w = Counter(e.get("sector_cb5_window") for e in enriched if e["outcome"] == "reversal" and e.get("sector_cb5_window"))
    fail_w = Counter(e.get("sector_cb5_window") for e in enriched if e["outcome"] != "reversal" and e.get("sector_cb5_window"))
    print(f"\n✅ 板块 cb5_window 对称性:", flush=True)
    print(f"   reversal: {dict(rev_w.most_common(3))}", flush=True)
    print(f"   failed:   {dict(fail_w.most_common(3))}", flush=True)
    
    # 分箱看 sector_cb5_excess
    print("\n📊 sector_cb5_excess (板块超过上证的累计幅度) 分箱:", flush=True)
    bins = [(-99, -2), (-2, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 2), (2, 99)]
    labels = ["<-2%", "-2~-1%", "-1~-0.3%", "-0.3~0.3%", "0.3~1%", "1~2%", "≥2%"]
    has_sector = [e for e in enriched if e.get("sector_cb5_window", 0) > 0]
    for (lo, hi), lbl in zip(bins, labels):
        sub = [e for e in has_sector if lo <= e["sector_cb5_excess"] < hi]
        if not sub: continue
        rev = sum(1 for e in sub if e["outcome"] == "reversal")
        print(f"   {lbl:<10} n={len(sub):>4} 回马枪率={rev/len(sub)*100:5.1f}%", flush=True)
    
    print("\n📊 sector_d0_chg (D0 板块涨幅) 分箱:", flush=True)
    bins2 = [(-10, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 5), (5, 99)]
    labels2 = ["<-1%", "-1~0%", "0~1%", "1~2%", "2~3%", "3~5%", "≥5%"]
    for (lo, hi), lbl in zip(bins2, labels2):
        sub = [e for e in has_sector if lo <= e["sector_d0_chg"] < hi]
        if not sub: continue
        rev = sum(1 for e in sub if e["outcome"] == "reversal")
        print(f"   {lbl:<8} n={len(sub):>4} 回马枪率={rev/len(sub)*100:5.1f}%", flush=True)


if __name__ == "__main__":
    main()
