"""R8: R7 触发日的'强势整理'加分规则

历史 R7 日的 winner 共同特征:
  days_below_d0 == 0 (从未跌破 D0)
  first_red_at == 0 (从未阴线)
  min_close_pct == 0 (没回调)
  cb5_main_avg > 0 (主力净流入)

设计 R8:
  R7 触发日, 满足 days_below_d0==0 且 cb5≥0.5 → +0.15
"""
import json
from collections import defaultdict

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

def is_r7_day(date):
    if date not in idx_by_date: return False
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    return spread > 3 and sh < 0.5

# R7 日 + 满足 R8 加分条件
r7_events = []
for e in events:
    eval_d = get_eval_date(e)
    if not eval_d or not is_r7_day(eval_d): continue
    r7_events.append(e)

print(f"R7 总事件: {len(r7_events)}")
print(f"  反转 (winner): {sum(1 for e in r7_events if e['outcome']=='reversal')}")

# R8 候选: days_below_d0 == 0 且 cb5 >= 0.5
def r8_passes(e):
    return (e.get("days_below_d0", 0) or 0) == 0 and (e.get("cb5_main_avg", 0) or 0) >= 0.5

r8_subset = [e for e in r7_events if r8_passes(e)]
print(f"\nR8 候选 (R7 + days_below=0 + cb5>=0.5): {len(r8_subset)}")
print(f"  反转: {sum(1 for e in r8_subset if e['outcome']=='reversal')}")
print(f"  反转率: {sum(1 for e in r8_subset if e['outcome']=='reversal')/max(1,len(r8_subset))*100:.1f}%")

# 严格点: cb5 >= 1
def r8_strict(e):
    return (e.get("days_below_d0", 0) or 0) == 0 and (e.get("cb5_main_avg", 0) or 0) >= 1.0

r8s = [e for e in r7_events if r8_strict(e)]
print(f"\nR8 严格 (cb5>=1.0): {len(r8s)}")
print(f"  反转: {sum(1 for e in r8s if e['outcome']=='reversal')}")
print(f"  反转率: {sum(1 for e in r8s if e['outcome']=='reversal')/max(1,len(r8s))*100:.1f}%")

# 在非 R7 日也试试这个规则 - 看是否反而是好规则
non_r7 = [e for e in events if e not in r7_events]
nr_r8 = [e for e in non_r7 if r8_strict(e)]
print(f"\n非 R7 日 R8 严格: {len(nr_r8)}")
print(f"  反转: {sum(1 for e in nr_r8 if e['outcome']=='reversal')}")
print(f"  反转率: {sum(1 for e in nr_r8 if e['outcome']=='reversal')/max(1,len(nr_r8))*100:.1f}%")

# 想清楚: 这是不是个真规则? 看全样本
print(f"\n=== 全样本 R8 (无 R7 限制) ===")
all_r8 = [e for e in events if r8_strict(e)]
print(f"全样本 R8: {len(all_r8)}, 反转 {sum(1 for e in all_r8 if e['outcome']=='reversal')}, 反转率 {sum(1 for e in all_r8 if e['outcome']=='reversal')/max(1,len(all_r8))*100:.1f}%")

# 尝试更精细: callback_pct < 3 (基本不回调) + cb3 >= 1
def r8_v2(e):
    return (e.get("callback_pct", 0) or 0) < 3 and (e.get("cb3_main_avg", 0) or 0) >= 1.0

print(f"\n=== R8 v2: callback<3% + cb3>=1亿 ===")
r8v2 = [e for e in events if r8_v2(e)]
print(f"全样本: {len(r8v2)}, 反转 {sum(1 for e in r8v2 if e['outcome']=='reversal')}, 反转率 {sum(1 for e in r8v2 if e['outcome']=='reversal')/max(1,len(r8v2))*100:.1f}%")
r8v2_r7 = [e for e in r8v2 if e in r7_events]
print(f"R7 日内: {len(r8v2_r7)}, 反转 {sum(1 for e in r8v2_r7 if e['outcome']=='reversal')}, 反转率 {sum(1 for e in r8v2_r7 if e['outcome']=='reversal')/max(1,len(r8v2_r7))*100:.1f}%" if r8v2_r7 else "R7 日内: 0")

# 终极规则 R8 final: 在 R7 日, 给"days_below=0 + first_red=0 + cb5≥0" 的票加 +0.20
def r8_final(e):
    return (e.get("days_below_d0", 0) or 0) == 0 and (e.get("first_red_at", 0) or 0) == 0 and (e.get("cb5_main_avg", 0) or 0) >= 0

r8f_r7 = [e for e in r7_events if r8_final(e)]
r8f_r7_rev = sum(1 for e in r8f_r7 if e["outcome"]=="reversal")
r8f_all = [e for e in events if r8_final(e)]
r8f_all_rev = sum(1 for e in r8f_all if e["outcome"]=="reversal")
print(f"\n=== R8 final: days_below=0 + first_red=0 + cb5>=0 ===")
print(f"R7 日内: {len(r8f_r7)}, 反转 {r8f_r7_rev}, 反转率 {r8f_r7_rev/max(1,len(r8f_r7))*100:.1f}%")
print(f"全样本: {len(r8f_all)}, 反转 {r8f_all_rev}, 反转率 {r8f_all_rev/max(1,len(r8f_all))*100:.1f}%")
