#!/usr/bin/env python3
"""
双战法推送脚本 (节后 5-5 周一上线)

战法 A — 9:26 当日抢板:
  - 拉问财: 9:15 买二/流通 + 9:25 买一/流通 (大于0)
  - 信号: 隔夜≥10% 或 开盘≥3% 或 双高(≥5%+≥1%)
  - 命中率 (D 当日涨停): 94-100%
  - 推送时间: 9:26 (撮合后立即)

战法 B — 15:05 收盘隔夜持仓:
  - 拉问财: 涨停封单量/流通 (大于0)  
  - 信号: 封流比 ≥5
  - 命中率 (D+1 再涨停): 53-60%
  - 推送时间: 15:05 (收盘后)

调用:
  python3 yedan_dual_push.py --mode A   # 战法 A
  python3 yedan_dual_push.py --mode B   # 战法 B
  python3 yedan_dual_push.py --mode B --date 20260430  # 指定日期 (回测)
"""
import warnings
warnings.filterwarnings('ignore')

import sys, argparse, datetime
import pywencai
import pandas as pd

def fetch_A(date_str):
    """战法 A: 9:15+9:25 双信号"""
    query = (f"{date_str} 9点15分买二*100/自由流通股 大于0 "
             f"9点25分买一*100/自由流通股 "
             f"涨跌幅 排名前500")
    df = pywencai.get(query=query, loop=True)
    if df is None or len(df)==0: return None
    rename = {}
    for c in df.columns:
        if "分时买二量" in c and "/" in c and "自由流通股" in c:
            rename[c] = "yedan_pct"
        elif "分时买一量" in c and "/" in c and "自由流通股" in c:
            rename[c] = "open_seal_pct"
        elif c == "最新涨跌幅":
            rename[c] = "chg_pct"
    df = df.rename(columns=rename)
    for c in ["yedan_pct","open_seal_pct","chg_pct"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def fetch_B(date_str):
    """战法 B: 涨停股封流比"""
    query = (f"{date_str} 涨停封单量*100/自由流通股 大于0 "
             f"涨停时间 涨停原因 排名前500")
    df = pywencai.get(query=query, loop=True)
    if df is None or len(df)==0: return None
    rename = {}
    for c in df.columns:
        if "涨停封单量" in c and "/" in c and "自由流通股" in c:
            rename[c] = "fenglu_ratio"
        elif "首次涨停时间" in c:
            rename[c] = "zt_first_time"
    df = df.rename(columns=rename)
    if "fenglu_ratio" in df.columns:
        df["fenglu_ratio"] = pd.to_numeric(df["fenglu_ratio"], errors="coerce")
    return df

def render_A(df, date_str):
    """战法 A 选股 + 渲染 v1.1 (5-3 深挖后升级)"""
    df = df[~df["股票简称"].astype(str).str.contains("ST", na=False)].copy()
    
    # 极强档: 双高 (隔夜≥20% + 开盘≥5%)
    super_strong = df[(df["yedan_pct"]>=20) & (df["open_seal_pct"]>=5)].sort_values("yedan_pct", ascending=False)
    
    # 强档 v1.1: 隔夜≥10% 或 开盘≥3% (不限隔夜) — 5-3 深挖发现开盘≥3% 是 100% 涨停金线
    strong = df[((df["yedan_pct"]>=10)|(df["open_seal_pct"]>=3)) & 
                ~df.index.isin(super_strong.index)].sort_values(
                    ["open_seal_pct","yedan_pct"], ascending=False)
    
    # 中档新逻辑 v1.1: 隔夜 1-10% + 开盘≥0.1% (历史 100% 涨停, 之前被漏)
    rescued = df[(df["yedan_pct"]>=1) & (df["yedan_pct"]<10) & 
                 (df["open_seal_pct"]>=0.1) & (df["open_seal_pct"]<3) &
                 ~df.index.isin(super_strong.index) & ~df.index.isin(strong.index)
                 ].sort_values("open_seal_pct", ascending=False)
    
    # 观察: 隔夜 5-10% + 开盘低
    medium = df[(df["yedan_pct"]>=5) & (df["yedan_pct"]<10) & (df["open_seal_pct"]<0.1)
               ].sort_values("yedan_pct", ascending=False)
    
    lines = [f"📊 战法A — 当日抢板 v1.1 ({date_str})", ""]
    lines.append("⭐⭐⭐ 极强档 (隔夜≥20% + 开盘≥5%, 历史 100% 涨停, n=28)")
    if len(super_strong)==0:
        lines.append("  无")
    for _, r in super_strong.head(10).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 隔夜{r['yedan_pct']:.1f}%, 开盘{r['open_seal_pct']:.1f}%")
    
    lines.append("")
    lines.append("⭐⭐ 强档 (隔夜≥10% 或 开盘≥3%, 历史 94-100% 涨停)")
    if len(strong)==0:
        lines.append("  无")
    for _, r in strong.head(15).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 隔夜{r['yedan_pct']:.1f}%, 开盘{r['open_seal_pct']:.1f}%")
    
    lines.append("")
    lines.append("⭐⭐ 拾漏档 v1.1 (隔夜 1-10% + 开盘≥0.1%, 历史 100% 涨停, n=29)")
    if len(rescued)==0:
        lines.append("  无")
    for _, r in rescued.head(10).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 隔夜{r['yedan_pct']:.1f}%, 开盘{r['open_seal_pct']:.2f}%")
    
    lines.append("")
    lines.append("⭐ 观察 (隔夜 5-10% 但开盘未封, 历史 ~38% 涨停)")
    for _, r in medium.head(5).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 隔夜{r['yedan_pct']:.1f}%, 开盘{r['open_seal_pct']:.2f}%")
    
    lines.append("")
    lines.append("💡 操作: 9:30 开盘抢入极强/强/拾漏档, 涨停后封死持有")
    lines.append("✅ 重要: 开盘封单 (9:25 买一) 是错事 1 位, 隔夜单只是辅助")
    return "\n".join(lines)

def t2min(s):
    if s is None or pd.isna(s): return None
    parts = str(s).strip().split(":")
    if len(parts)<2: return None
    try: return int(parts[0])*60+int(parts[1])
    except: return None

def render_B(df, date_str):
    """战法 B 选股 + 渲染 v1.1 (加首封时间细分)"""
    df = df[~df["股票简称"].astype(str).str.contains("ST", na=False)].copy()
    df["first_min"] = df["zt_first_time"].apply(t2min)
    
    # 极宝档: 封流≥5 + 早封 (9:30-10:00) — D+1 62.5%
    super_zhao = df[(df["fenglu_ratio"]>=5) & (df["first_min"]>=540) & (df["first_min"]<600)
                   ].sort_values("fenglu_ratio", ascending=False)
    # 硬封中档: 封流≥5, 不是早封
    other_hard = df[(df["fenglu_ratio"]>=5) & ~df.index.isin(super_zhao.index)
                   ].sort_values("fenglu_ratio", ascending=False)
    # 软件档: 3-5
    soft = df[(df["fenglu_ratio"]>=3) & (df["fenglu_ratio"]<5)
             ].sort_values("fenglu_ratio", ascending=False)
    
    lines = [f"📊 战法B — 隔夜持仓 v1.1 ({date_str})", ""]
    lines.append("⭐⭐⭐ 极宝档 (封流≥5 + 首封 9:30-10:00, D+1 62.5% 再封) ⚡")
    if len(super_zhao)==0:
        lines.append("  无")
    for _, r in super_zhao.head(8).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 封流 {r['fenglu_ratio']:.2f}, 首封 {r.get('zt_first_time','')}")
    
    lines.append("")
    lines.append("⭐⭐ 硬封中档 (封流≥5, 不是早封, D+1 ~45% 再封)")
    for _, r in other_hard.head(8).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 封流 {r['fenglu_ratio']:.2f}, 首封 {r.get('zt_first_time','')}")
    
    lines.append("")
    lines.append("⭐ 软封 (封流 3-5, D+1 ~30% 再封)")
    for _, r in soft.head(5).iterrows():
        lines.append(f"  {r['股票代码']} {r['股票简称']}: 封流 {r['fenglu_ratio']:.2f}, 首封 {r.get('zt_first_time','')}")
    
    lines.append("")
    lines.append("💡 操作: 14:55 买入极宝/硬封, 持仓过夜, 次日 9:30 视开盘卖出")
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["A","B"], required=True)
    p.add_argument("--date", default=None, help="YYYYMMDD; 默认今日")
    args = p.parse_args()
    
    date_str = args.date or datetime.datetime.now().strftime("%Y%m%d")
    
    if args.mode == "A":
        df = fetch_A(date_str)
        if df is None:
            print(f"❌ {date_str} 无数据")
            return
        print(render_A(df, date_str))
    else:
        df = fetch_B(date_str)
        if df is None:
            print(f"❌ {date_str} 无数据")
            return
        print(render_B(df, date_str))

if __name__ == "__main__":
    main()
