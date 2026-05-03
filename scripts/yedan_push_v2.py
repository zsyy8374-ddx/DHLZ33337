#!/usr/bin/env python3
"""
战法 B v2 推送 (T+1 真实信号)
基于 1123 行 19 天回测, 排除一字板后真信号:
- ⭐⭐⭐ 软封+早封 (封流 3-5 + 首封 9:30-10:00 + 非一字板) — 真实 +2.00%/69%
- ⭐⭐ 软封整体 (封流 3-5, 非一字板) — 真实 +1.59%/63%
- ⛔ 避雷: 封流≥5 (硬封) — 真实 -2.69%/32%

用法: 周一 5-5 北京 15:05 收盘后跑
"""
import warnings
warnings.filterwarnings('ignore')

import sys, argparse, time
from pathlib import Path
import pywencai
import pandas as pd
from datetime import datetime

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
DATA.mkdir(parents=True, exist_ok=True)

def fetch_fenglu(date_str):
    """拉当日涨停股 + 封流比 (涨停封单量*100/自由流通股) + 首封时间 + 价格 (一字板判定)"""
    query = (f"{date_str} 涨停封单量*100/自由流通股 大于0 "
             f"开盘价 收盘价 最高价 最低价 排名前1500")
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    rename = {}
    for c in df.columns:
        cs = str(c)
        # 问财返回的计算列: {(}{(}涨停封单量{*}100.0{)}{/}自由流通股{)}
        if "涨停封单量" in cs and "自由流通股" in cs:
            rename[c] = "fenglu_ratio"
        elif ("首次涨停时间" in cs or "首次封板时间" in cs) and "排名" not in cs:
            rename[c] = "zt_first_time"
        elif "开盘价:不复权" in cs and "排名" not in cs: rename[c] = "p_open"
        elif "收盘价:不复权" in cs and "排名" not in cs: rename[c] = "p_close"
        elif "最高价:不复权" in cs and "排名" not in cs: rename[c] = "p_high"
        elif "最低价:不复权" in cs and "排名" not in cs: rename[c] = "p_low"
    df = df.rename(columns=rename)
    # 处理重复列名 (只保留首个)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def t2min(s):
    if s is None or pd.isna(s): return None
    parts = str(s).strip().split(":")
    if len(parts)<2: return None
    try: return int(parts[0])*60+int(parts[1])
    except: return None

def is_yi_zi_ban(row):
    """一字板判定: 开盘=收盘=最高=最低 (差异 < 0.5%)"""
    try:
        po = float(row.get("p_open", 0))
        pc = float(row.get("p_close", 0))
        ph = float(row.get("p_high", 0))
        pl = float(row.get("p_low", 0))
        if min(po,pc,ph,pl) <= 0: return False
        if abs(po-pc)/pc < 0.005 and abs(ph-pl)/pc < 0.005:
            return True
    except: pass
    return False

def calc_fenglu_ratio(row):
    """只用问财直接给的 fenglu_ratio (= 涨停封单量*100/自由流通股)"""
    try:
        if "fenglu_ratio" in row and pd.notna(row["fenglu_ratio"]):
            v = float(row["fenglu_ratio"])
            if v > 0: return v
    except: pass
    return None

def render(df, date_str):
    df = df[~df["股票简称"].astype(str).str.contains("ST", na=False)].copy()
    df["fenglu_ratio"] = df.apply(calc_fenglu_ratio, axis=1)
    df["first_min"] = df["zt_first_time"].apply(t2min) if "zt_first_time" in df.columns else None
    df["is_yzb"] = df.apply(is_yi_zi_ban, axis=1)
    
    # 排除一字板
    real = df[~df["is_yzb"].fillna(False)].copy()
    
    # ⭐⭐⭐ 软封+早封: 封流 3-5 + 9:30-10:00
    gold = real[(real["fenglu_ratio"]>=3) & (real["fenglu_ratio"]<5) & 
                (real["first_min"]>=540) & (real["first_min"]<600)
                ].sort_values("fenglu_ratio", ascending=False)
    
    # ⭐⭐ 软封 (3-5) 其他时段
    soft_other = real[(real["fenglu_ratio"]>=3) & (real["fenglu_ratio"]<5) & 
                      ~real.index.isin(gold.index)
                     ].sort_values("fenglu_ratio", ascending=False)
    
    # ⛔ 避雷区 (38 天验证: 封流≥5 不论时间都亏)
    bait = real[real["fenglu_ratio"]>=5].sort_values("fenglu_ratio", ascending=False)
    
    lines = [f"📊 战法B v2 — 隔夜持仓 ({date_str})", ""]
    lines.append(f"基于 1123 行 19 天 T+1 真实回测 (已排除一字板)")
    lines.append("")
    lines.append(f"⭐⭐⭐ 软封+早封 (封流 3-5 + 9:30-10:00, 历史 +2.00%/69%, n=42)")
    if len(gold)==0:
        lines.append("  无")
    for _, r in gold.head(8).iterrows():
        fl = r["fenglu_ratio"]; fm = r["first_min"]
        time_str = r.get("zt_first_time","")
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 封流 {fl:.2f}, 首封 {time_str}")
    
    lines.append("")
    lines.append(f"⭐⭐ 软封其他 (封流 3-5 其他时段, 历史 +1.5%/60%, 备选)")
    for _, r in soft_other.head(5).iterrows():
        fl = r["fenglu_ratio"]
        time_str = r.get("zt_first_time","")
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 封流 {fl:.2f}, 首封 {time_str}")
    
    lines.append("")
    lines.append(f"⛔ 避雷区 (封流≥5 任何时间, 历史 -2.98%/44%, 不要碰)")
    for _, r in bait.head(8).iterrows():
        fl = r["fenglu_ratio"]
        time_str = r.get("zt_first_time","")
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 封流 {fl:.2f}, 首封 {time_str}")
    
    lines.append("")
    lines.append("💡 操作:")
    lines.append("  • 14:55 买入金信号档, 单只 ≤15%, 总仓 ≤50%")
    lines.append("  • D+1 (次日) 9:30 开盘卖出")
    lines.append("  • 避雷区绝对不买 (T+1 历史亏 2.69%)")
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    args = p.parse_args()
    
    print(f"拉 {args.date} 涨停股数据...")
    df = fetch_fenglu(args.date)
    if df is None or len(df) == 0:
        print(f"无数据 (节假日?)")
        return
    print(f"涨停股 {len(df)} 只")
    
    out = DATA / f"fenglu_{args.date}.csv"
    df.to_csv(out, index=False, encoding='utf-8-sig')
    
    msg = render(df, args.date)
    print(msg)
    
    # 同时写到候选文件
    out2 = DATA / f"yedan_v2_picks_{args.date}.txt"
    out2.write_text(msg, encoding='utf-8')
    print(f"\n已写入 {out2}")

if __name__ == "__main__":
    main()
