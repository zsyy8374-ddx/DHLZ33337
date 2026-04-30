"""R7 触发日的成功反转股 vs 失败股 - 找它们的差异

历史 5 个 R7 日, lbc=1 共 48 个事件, 其中 6 个反转
能不能找到一个特征区分这 6 vs 42?
"""
import json, statistics

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

# R7 日的 lbc=1 事件
r7_lbc1 = []
for e in events:
    if (e.get("d0_lbc", 1) or 1) != 1: continue
    eval_d = get_eval_date(e)
    if not eval_d or not is_r7_day(eval_d): continue
    r7_lbc1.append(e)

print(f"R7 触发日 lbc=1 事件: {len(r7_lbc1)}")
winners = [e for e in r7_lbc1 if e["outcome"] == "reversal"]
losers = [e for e in r7_lbc1 if e["outcome"] != "reversal"]
print(f"  成功反转 (winner): {len(winners)}")
print(f"  未反转 (loser): {len(losers)}")

print("\n📊 winner 6 只详情:")
for w in winners:
    print(f"  {w['code']} {w.get('name','')[:6]:<8} D0={w['d0_date']} cb_pct={w.get('callback_pct',0):.1f}% mc={w.get('min_close_pct',0):.1f}%  cb5={w.get('cb5_main_avg',0):+.2f}  cb1={w.get('cb1_main_avg',0):+.2f}  d0={w.get('d0_main_flow',0):+.2f}  pre={w.get('pre_d0_5d_main_avg',0):+.2f}  d_t={w.get('d_t_date')}")

# 各特征对比
print(f"\n📊 winners (n={len(winners)}) vs losers (n={len(losers)}) 中位数对比:")
print(f"{'特征':<25}{'winner':>14}{'loser':>14}{'信号方向':>12}")
print("-"*70)
for k in ['callback_pct','min_close_pct','d0_main_flow','cb1_main_avg','cb3_main_avg','cb5_main_avg','cb5_in_ratio','pre_d0_5d_main_avg','d0_vol_z','vol_callback_ratio','days_below_d0','first_red_at']:
    wv = [e.get(k, 0) or 0 for e in winners]
    lv = [e.get(k, 0) or 0 for e in losers]
    if not wv or not lv: continue
    wmed = statistics.median(wv); lmed = statistics.median(lv)
    diff = wmed - lmed
    arrow = "↑ 看好" if diff > 0 else ("↓ 看空" if diff < 0 else "—")
    print(f"{k:<25}{wmed:>+14.3f}{lmed:>+14.3f}{arrow:>14}")

# 看 d_t 距 D0 天数
print(f"\n📊 days_between (d_t - D0) 分布:")
w_dbet = [e.get("days_between", 0) for e in winners if e.get("days_between") is not None]
print(f"  winners: {sorted(w_dbet)}")

# 找一个能将 winner 跟 loser 拉开的简单规则
# 假设1: cb5_main_avg <= 0 (主力洗盘到位)
def rule(e):
    return (e.get("cb5_main_avg", 0) or 0) <= 0

w_passed = sum(1 for e in winners if rule(e))
l_passed = sum(1 for e in losers if rule(e))
print(f"\n📊 规则: cb5_main_avg <= 0 (主力净流出 = 洗盘到位)")
print(f"  winners 通过: {w_passed}/{len(winners)} ({w_passed/len(winners)*100:.0f}%)")
print(f"  losers 通过: {l_passed}/{len(losers)} ({l_passed/len(losers)*100:.0f}%)")
print(f"  规则命中率: {w_passed/(w_passed+l_passed)*100:.1f}%" if (w_passed+l_passed) > 0 else "")

# 假设2: callback_pct >= 5 (深度回调 = 真洗盘)
def rule2(e):
    return (e.get("callback_pct", 0) or 0) >= 5
w2 = sum(1 for e in winners if rule2(e))
l2 = sum(1 for e in losers if rule2(e))
print(f"\n📊 规则2: callback_pct >= 5%")
print(f"  winners: {w2}/{len(winners)}, losers: {l2}/{len(losers)}, 通过命中率 {w2/max(1,w2+l2)*100:.1f}%")

# 组合
def rule3(e):
    return rule(e) and rule2(e)
w3 = sum(1 for e in winners if rule3(e))
l3 = sum(1 for e in losers if rule3(e))
print(f"\n📊 规则3: cb5≤0 且 cb_pct≥5")
print(f"  winners: {w3}/{len(winners)}, losers: {l3}/{len(losers)}, 通过命中率 {w3/max(1,w3+l3)*100:.1f}%")

# 假设4: D0 主力大爆量
def rule4(e):
    return (e.get("d0_main_flow", 0) or 0) >= 5
w4 = sum(1 for e in winners if rule4(e))
l4 = sum(1 for e in losers if rule4(e))
print(f"\n📊 规则4: d0_main_flow >= 5亿")
print(f"  winners: {w4}/{len(winners)}, losers: {l4}/{len(losers)}, 通过命中率 {w4/max(1,w4+l4)*100:.1f}%")
