"""更细粒度市场状态探索 - 看 1d 涨跌相关性 + 5 天动量"""
import json
from collections import Counter, defaultdict

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]
with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json") as f:
    idx_data = json.load(f)

idx_by_date = {}
sorted_dates = []
for code, info in idx_data.items():
    for r in info["rows"]:
        idx_by_date.setdefault(r["date"], {})[code] = r["chg_pct"]
sorted_dates = sorted(idx_by_date.keys())

def get_eval_date(e):
    if e.get("d_t_date"): return e["d_t_date"]
    d0 = e["d0_date"]
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]

def get_5d_chg(date, code):
    if date not in sorted_dates: return None
    i = sorted_dates.index(date)
    if i < 5: return None
    five_d_ago = sorted_dates[i-5]
    chgs = []
    for j in range(i-4, i+1):
        c = idx_by_date.get(sorted_dates[j], {}).get(code)
        if c is None: return None
        chgs.append(c)
    return sum(chgs)

# 添加 5d 信息
results = []
for e in events:
    eval_d = get_eval_date(e)
    if not eval_d or eval_d not in idx_by_date: continue
    d = idx_by_date[eval_d]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    
    # 5 天累计
    sh5 = get_5d_chg(eval_d, "sh000001")
    sz5 = get_5d_chg(eval_d, "sz399006")
    kc5 = get_5d_chg(eval_d, "sh000688")
    
    results.append({
        "sh": sh, "sz": sz, "kc": kc,
        "sh5": sh5, "sz5": sz5, "kc5": kc5,
        "lbc": e.get("d0_lbc", 1) or 1,
        "is_rev": e["outcome"] == "reversal",
        "callback": e.get("callback_pct", 0) or 0,
        "cb5_main": e.get("cb5_main_avg", 0) or 0,
    })

print(f"事件 {len(results)} (其中含 5d 数据 {sum(1 for r in results if r['sh5'] is not None)})\n")

# 切片: kc - sh diff (5d 累计)
def slice_stats(label, condition):
    sub = [r for r in results if condition(r)]
    if not sub: 
        print(f"{label:<55} n=0  -")
        return
    rev_n = sum(1 for r in sub if r["is_rev"])
    rev_lbc1 = sum(1 for r in sub if r["is_rev"] and r["lbc"]==1)
    n_lbc1 = sum(1 for r in sub if r["lbc"]==1)
    print(f"{label:<55} n={len(sub):>4}  反转 {rev_n:>3}  反转率 {rev_n/len(sub)*100:>5.1f}%   lbc=1: {rev_lbc1}/{n_lbc1}")

# 1. 以 5 天动量看 - 创业板/科创 5天表现
print("=== 5 天动量切片 ===")
slice_stats("kc5 >= 5% (科创近一周强势)", lambda r: r["kc5"] is not None and r["kc5"] >= 5)
slice_stats("kc5 <= -5% (科创近一周弱势)", lambda r: r["kc5"] is not None and r["kc5"] <= -5)
slice_stats("sh5 >= 3 (主板近一周走强)", lambda r: r["sh5"] is not None and r["sh5"] >= 3)
slice_stats("sh5 <= -3 (主板近一周走弱)", lambda r: r["sh5"] is not None and r["sh5"] <= -3)
slice_stats("sz5 >= 3 (创业近一周走强)", lambda r: r["sz5"] is not None and r["sz5"] >= 3)
slice_stats("sz5 <= -3 (创业近一周走弱)", lambda r: r["sz5"] is not None and r["sz5"] <= -3)

# 2. 跷跷板 (主板+创业反向)
print("\n=== 跷跷板模式 ===")
slice_stats("sh5 - sz5 >= 5 (主板暴强 vs 创业弱)", lambda r: r["sh5"] is not None and r["sz5"] is not None and r["sh5"] - r["sz5"] >= 5)
slice_stats("sz5 - sh5 >= 5 (创业暴强 vs 主板弱)", lambda r: r["sh5"] is not None and r["sz5"] is not None and r["sz5"] - r["sh5"] >= 5)

# 3. 1 日方向 + 5 日方向组合
print("\n=== 1日 vs 5日 一致性 ===")
slice_stats("1日上涨 + 5日累计上涨 (持续向上)", lambda r: r["sh"] > 0.3 and (r["sh5"] or 0) > 1)
slice_stats("1日下跌 + 5日累计下跌 (持续向下)", lambda r: r["sh"] < -0.3 and (r["sh5"] or 0) < -1)
slice_stats("1日上涨 但 5日累计下跌 (反弹)", lambda r: r["sh"] > 0.3 and (r["sh5"] or 0) < -1)
slice_stats("1日下跌 但 5日累计上涨 (调整)", lambda r: r["sh"] < -0.3 and (r["sh5"] or 0) > 1)

# 4. 三大指数齐涨 vs 齐跌
print("\n=== 同向程度 ===")
slice_stats("三大齐涨 (全 > 0.5)", lambda r: r["sh"] > 0.5 and r["sz"] > 0.5 and r["kc"] > 0.5)
slice_stats("三大齐跌 (全 < -0.5)", lambda r: r["sh"] < -0.5 and r["sz"] < -0.5 and r["kc"] < -0.5)
slice_stats("三大齐红 (全 >= 0)", lambda r: r["sh"] >= 0 and r["sz"] >= 0 and r["kc"] >= 0)
slice_stats("三大齐绿 (全 <= 0)", lambda r: r["sh"] <= 0 and r["sz"] <= 0 and r["kc"] <= 0)

# 5. 大涨大跌
print("\n=== 极端事件 ===")
slice_stats("大盘暴涨 (avg > 2)", lambda r: (r["sh"]+r["sz"]+r["kc"])/3 > 2)
slice_stats("大盘暴跌 (avg < -2)", lambda r: (r["sh"]+r["sz"]+r["kc"])/3 < -2)
slice_stats("大盘暴跌 + lbc=1", lambda r: (r["sh"]+r["sz"]+r["kc"])/3 < -2 and r["lbc"]==1)

# 6. 探索: D0 + cb 期间的累计大盘涨幅
print("\n=== cb 期间累计涨幅探索 ===")
# 反转股 vs 失败股的 5d 大盘均值
rev_sh5 = [r["sh5"] for r in results if r["is_rev"] and r["sh5"] is not None]
fail_sh5 = [r["sh5"] for r in results if not r["is_rev"] and r["sh5"] is not None]
rev_sz5 = [r["sz5"] for r in results if r["is_rev"] and r["sz5"] is not None]
fail_sz5 = [r["sz5"] for r in results if not r["is_rev"] and r["sz5"] is not None]

import statistics
print(f"反转股 n={len(rev_sh5)}: sh5 中位 {statistics.median(rev_sh5):+.2f}%, sz5 中位 {statistics.median(rev_sz5):+.2f}%")
print(f"失败股 n={len(fail_sh5)}: sh5 中位 {statistics.median(fail_sh5):+.2f}%, sz5 中位 {statistics.median(fail_sz5):+.2f}%")
