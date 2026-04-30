"""探索更多市场状态对反转率的影响

历史 1151 事件 + 三大指数 120 天, 看不同市场状态下:
  反转率分布
  哪些是最危险/最有利的状态
"""
import json

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

# 所有事件的评估日 + 当日大盘状态
results = []
for e in events:
    eval_d = get_eval_date(e)
    if not eval_d or eval_d not in idx_by_date: continue
    info = idx_by_date[eval_d]
    sh = info.get("sh000001", 0); sz = info.get("sz399006", 0); kc = info.get("sh000688", 0)
    is_rev = e["outcome"] == "reversal"
    results.append({
        "sh": sh, "sz": sz, "kc": kc,
        "spread": max(sh, sz, kc) - min(sh, sz, kc),
        "avg": (sh + sz + kc) / 3,
        "lbc": e.get("d0_lbc", 1) or 1,
        "is_rev": is_rev,
        "outcome": e["outcome"]
    })

print(f"事件总数 {len(results)}\n")

# 各种 regime 切片
def slice_stats(label, condition):
    sub = [r for r in results if condition(r)]
    if not sub: return
    rev_n = sum(1 for r in sub if r["is_rev"])
    print(f"{label:<55} n={len(sub):>4}  反转 {rev_n:>3}  反转率 {rev_n/len(sub)*100:>5.1f}%")

print("=== 大盘普涨 (avg >= 1%) ===")
slice_stats("avg >=1%", lambda r: r["avg"] >= 1)
slice_stats("avg >=1% & lbc=1", lambda r: r["avg"] >= 1 and r["lbc"] == 1)
slice_stats("avg >=1% & lbc>=2", lambda r: r["avg"] >= 1 and r["lbc"] >= 2)

print("\n=== 大盘小幅 (-0.5% < avg < 0.5%) ===")
slice_stats("|avg|<0.5", lambda r: abs(r["avg"]) < 0.5)
slice_stats("|avg|<0.5 & spread>3", lambda r: abs(r["avg"]) < 0.5 and r["spread"] > 3)
slice_stats("|avg|<0.5 & spread<=3", lambda r: abs(r["avg"]) < 0.5 and r["spread"] <= 3)

print("\n=== 大盘普跌 (avg <= -1%) ===")
slice_stats("avg <=-1", lambda r: r["avg"] <= -1)
slice_stats("avg <=-1 & lbc=1", lambda r: r["avg"] <= -1 and r["lbc"] == 1)
slice_stats("avg <=-1 & lbc>=2", lambda r: r["avg"] <= -1 and r["lbc"] >= 2)

print("\n=== 主板独苗 (sh>0.5 & cy<-0.3 & kc<-0.3) ===")
slice_stats("主板独红", lambda r: r["sh"] > 0.5 and r["sz"] < -0.3 and r["kc"] < -0.3)

print("\n=== 创业板/科创独红 ===")
slice_stats("kc 独红 (>2 & sh<0.5)", lambda r: r["kc"] > 2 and r["sh"] < 0.5)
slice_stats("sz 独红 (>2 & sh<0.5)", lambda r: r["sz"] > 2 and r["sh"] < 0.5)

print("\n=== 大幅分化 (spread > 4) ===")
slice_stats("spread > 4", lambda r: r["spread"] > 4)
slice_stats("spread > 4 & avg > 0", lambda r: r["spread"] > 4 and r["avg"] > 0)
slice_stats("spread > 4 & avg <= 0", lambda r: r["spread"] > 4 and r["avg"] <= 0)

print("\n=== 跨指数共振 (spread < 1) ===")
slice_stats("spread < 1 & avg >= 0.5", lambda r: r["spread"] < 1 and r["avg"] >= 0.5)
slice_stats("spread < 1 & avg <= -0.5", lambda r: r["spread"] < 1 and r["avg"] <= -0.5)

# 综合表
print("\n=== 综合: 不同 spread vs avg 的反转率 ===")
header = 'avg vs spread'
print(f"{header:<15}{'< 1':>10}{'1-2':>10}{'2-3':>10}{'3-4':>10}{'>= 4':>10}")
for avg_lo, avg_hi, label in [(-99, -1, "<=-1"), (-1, -0.3, "-1~-0.3"), (-0.3, 0.3, "-0.3~0.3"), (0.3, 1, "0.3~1"), (1, 99, ">=1")]:
    row = [label]
    for sp_lo, sp_hi in [(0,1), (1,2), (2,3), (3,4), (4,99)]:
        sub = [r for r in results if avg_lo <= r["avg"] < avg_hi and sp_lo <= r["spread"] < sp_hi]
        if sub:
            rev = sum(1 for r in sub if r["is_rev"])
            row.append(f"{rev/len(sub)*100:.0f}%(n{len(sub)})")
        else:
            row.append("-")
    print(f"{row[0]:<15}{row[1]:>10}{row[2]:>10}{row[3]:>10}{row[4]:>10}{row[5]:>10}")
