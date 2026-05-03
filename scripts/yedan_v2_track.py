#!/usr/bin/env python3
"""
战法 B v2 实盘命中追踪
- D+1 9:30 后, 把 D 的推荐 (yedan_v2_picks_*.txt) 和 D+1 实际开盘价对比
- 算出 T+1 收益, 写入命中记录
- 累计胜率/收益, 看实盘 vs 历史是否一致

用法: 周一-周五 北京 9:35 跑 (D+1 开盘后)
"""
import warnings; warnings.filterwarnings('ignore')

import sys, re, time, json, argparse
from pathlib import Path
from datetime import datetime, timedelta
import pywencai
import pandas as pd

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
TRACK = Path("/Users/openclaw/.openclaw/workspace-dengxian/picks/yedan_v2")
TRACK.mkdir(parents=True, exist_ok=True)

def parse_picks(path):
    """解析 yedan_v2_picks_YYYYMMDD.txt"""
    txt = path.read_text(encoding='utf-8')
    bucket = None
    rows = []
    for line in txt.splitlines():
        line = line.strip()
        if "软封+早封" in line: bucket = "gold"
        elif "软封其他" in line: bucket = "soft"
        elif "避雷" in line: bucket = "bait"
        elif bucket and re.match(r"^\d{6}\.\w+", line):
            m = re.match(r"^(\d{6}\.\w+)\s+(\S+):\s+封流\s+([\d.]+)", line)
            if m:
                rows.append({"bucket":bucket, "code":m.group(1), "name":m.group(2), "fl":float(m.group(3))})
    return rows

def fetch_open_price(date_str, codes):
    """拉这些股的当日开盘价"""
    code_short = [c.split(".")[0] for c in codes]
    query = f"{date_str} 开盘价 大于0 排名前6000"
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    p_open_col = None
    for c in df.columns:
        if "开盘价:不复权" in c: p_open_col = c; break
    if p_open_col is None: return None
    df["p_open"] = pd.to_numeric(df[p_open_col], errors="coerce")
    df["code_s"] = df["股票代码"].astype(str).str.split(".").str[0]
    out = {}
    for cs in code_short:
        m = df[df["code_s"]==cs]
        if len(m)>0:
            out[cs] = float(m["p_open"].iloc[0])
    return out

def fetch_close_price(date_str, codes):
    """D 的收盘价 (= 涨停价, 买入价)"""
    code_short = [c.split(".")[0] for c in codes]
    query = f"{date_str} 收盘价 大于0 排名前6000"
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    p_close_col = None
    for c in df.columns:
        if "收盘价:不复权" in c and "排名" not in c: p_close_col = c; break
    if p_close_col is None: return None
    df["p_close"] = pd.to_numeric(df[p_close_col], errors="coerce")
    df["code_s"] = df["股票代码"].astype(str).str.split(".").str[0]
    out = {}
    for cs in code_short:
        m = df[df["code_s"]==cs]
        if len(m)>0:
            out[cs] = float(m["p_close"].iloc[0])
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--d", help="D (推送日) YYYYMMDD")
    p.add_argument("--d1", help="D+1 (验证日) YYYYMMDD")
    args = p.parse_args()
    
    # 默认: D = 上个交易日, D+1 = 今天
    today = datetime.now().strftime("%Y%m%d") if not args.d1 else args.d1
    if not args.d:
        # 找最近的 picks 文件
        cands = sorted(DATA.glob("yedan_v2_picks_*.txt"), reverse=True)
        if not cands:
            print("没找到 picks 文件"); return
        d = cands[0].stem.replace("yedan_v2_picks_","")
    else:
        d = args.d
    
    pick_file = DATA / f"yedan_v2_picks_{d}.txt"
    if not pick_file.exists():
        print(f"无 {pick_file}"); return
    
    rows = parse_picks(pick_file)
    print(f"[{d} → {today}] {len(rows)} 只候选")
    
    if len(rows) == 0: return
    codes = [r["code"] for r in rows]
    
    # D 收盘价 + D+1 开盘价
    d_close = fetch_close_price(d, codes)
    d1_open = fetch_open_price(today, codes)
    
    if d_close is None or d1_open is None:
        print("拉价格失败"); return
    
    results = []
    for r in rows:
        cs = r["code"].split(".")[0]
        pb = d_close.get(cs); ps = d1_open.get(cs)
        if pb is None or ps is None or pb<=0 or ps<=0:
            continue
        ret = (ps-pb)/pb*100
        results.append({**r, "p_buy":pb, "p_sell":ps, "ret_pct":ret})
    
    if len(results)==0:
        print("无有效价格数据"); return
    
    df = pd.DataFrame(results)
    
    print()
    print(f"{'类别':<8} {'代码':<10} {'名称':<10} {'封流':>5} {'买入':>8} {'卖出':>8} {'T+1 收益':>9}")
    for _, r in df.iterrows():
        print(f"{r['bucket']:<8} {r['code']:<10} {r['name']:<10} {r['fl']:>5.2f} {r['p_buy']:>8.2f} {r['p_sell']:>8.2f} {r['ret_pct']:>8.2f}%")
    
    # 各档统计
    print()
    print("=== 实盘命中统计 ===")
    for b, lbl in [("gold","⭐⭐⭐ 软封+早封"),("soft","⭐⭐ 软封其他"),("bait","⛔ 避雷区 (没买)")]:
        s = df[df["bucket"]==b]
        if len(s)==0: continue
        avg = s["ret_pct"].mean()
        win = (s["ret_pct"]>0).mean()*100
        print(f"  {lbl}: n={len(s)}, 均 {avg:.2f}%, 胜率 {win:.0f}%")
    
    # 写入累计追踪
    track_file = TRACK / "track_v2.csv"
    df["date_d"] = d
    df["date_d1"] = today
    if track_file.exists():
        old = pd.read_csv(track_file)
        df_all = pd.concat([old, df], ignore_index=True)
        df_all = df_all.drop_duplicates(subset=["date_d","code"], keep="last")
    else:
        df_all = df
    df_all.to_csv(track_file, index=False, encoding='utf-8-sig')
    
    print()
    print(f"=== 累计追踪 ({len(df_all)} 行 / {df_all['date_d'].nunique()} 天) ===")
    for b, lbl in [("gold","⭐⭐⭐ 软封+早封")]:
        s = df_all[df_all["bucket"]==b]
        if len(s)>0:
            print(f"  {lbl} 累计: n={len(s)}, 均 {s['ret_pct'].mean():.2f}%, 胜率 {(s['ret_pct']>0).mean()*100:.0f}%")

if __name__ == "__main__":
    main()
