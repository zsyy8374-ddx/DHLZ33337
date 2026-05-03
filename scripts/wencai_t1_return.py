#!/usr/bin/env python3
"""
T+1 真实收益回测:
- D 9:30 买入 (战法 A 候选)
- D 涨停封死
- D+1 9:30 卖出 (开盘价)
- 真实收益 = (D+1 开盘 - D 买入) / D 买入

数据缺口: 我现有数据没有 D 买入价 + D+1 开盘价
但可以用问财补:
- D+1 9:25 撮合价 (近似 D+1 开盘价)
- D 涨停价 = D-1 收盘 × 1.1 (买入价上限)
"""
import warnings
warnings.filterwarnings('ignore')

import pywencai
import pandas as pd
from pathlib import Path
import time

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def fetch_d1_open(date_str):
    """拉 date 当天 9:25 撮合价 + 9:30 开盘价 + 当日收盘"""
    query = (f"{date_str} 9点25分集合竞价 大于0 "
             f"开盘价 收盘价 "
             f"涨跌幅 排名前1500")
    try:
        df = pywencai.get(query=query, loop=True)
        return df
    except Exception as e:
        print(f"  err: {e}")
        return None

# 检查能不能拉 5-1 之后日期 (5-1~5-3 假期, 5-5 周一才开盘, 5-6 才有 D+1 数据可看)
# 现在能用: 4-2 ~ 4-30 D / 4-3 ~ 5-5 D+1 (但 5-5 数据未出)

# 先跑一个 D=4-29, D+1=4-30 的小测试
print("测试: 拉 4-30 (D+1 视角) 开盘价 + 收盘价")
df = fetch_d1_open("20260430")
if df is not None:
    print(f"返回 {len(df)} 行, 列名:")
    print(list(df.columns)[:15])
    print()
    print(df.head(3))
