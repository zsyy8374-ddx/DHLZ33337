"""核心问题: 推送时 (D-1) 的 regime 跟 D_t 的 regime 一致吗?
如果不一致, 那 post-hoc boost 用 D-1 的 regime 完全不对"""
import json

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json') as f:
    events = json.load(f)['events']

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json') as f:
    idx_data = json.load(f)

idx_by_date = {}
sorted_dates = []
for code, info in idx_data.items():
    for r in info['rows']:
        idx_by_date.setdefault(r['date'], {})[code] = r['chg_pct']
sorted_dates = sorted(idx_by_date.keys())

def detect_v6(date):
    if date not in idx_by_date: return "normal"
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    avg = (sh + sz + kc) / 3
    if kc > 2 and sh < 0.5: return "kc_only_red"
    if sh > 0.5 and sz < -0.3 and kc < -0.3: return "sh_only_red"
    if sz > 2 and sh < 0.5: return "sz_only_red"
    if spread > 4 and avg > 0: return "spread_high_up"
    if sh <= 0 and sz <= 0 and kc <= 0:
        return "all_green_strong" if avg <= -0.5 else "all_green_weak"
    if sh >= 0 and sz >= 0 and kc >= 0:
        return "all_red_strong" if avg >= 0.5 else "all_red_weak"
    return "normal"

# 对每个事件, 拿到 D_t (事件评估日) 和 D-1 的 regime
# 反转事件: D_t = d_t_date
# 失败事件: D_t = D0 + 10 交易日
matches = 0; total = 0
mismatch_table = {}

def get_eval_date(e):
    if e.get('d_t_date'): return e['d_t_date']
    d0 = e['d0_date']
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]

for e in events:
    d_t = get_eval_date(e)
    if not d_t or d_t not in sorted_dates: continue
    i = sorted_dates.index(d_t)
    if i == 0: continue
    d_minus_1 = sorted_dates[i-1]
    
    r_dm1 = detect_v6(d_minus_1)
    r_dt = detect_v6(d_t)
    total += 1
    if r_dm1 == r_dt: matches += 1
    
    key = (r_dm1, r_dt)
    mismatch_table[key] = mismatch_table.get(key, 0) + 1

print(f"📊 D-1 regime == D_t regime: {matches}/{total} = {matches/total*100:.1f}%\n")

# 表格
all_regimes = sorted(set([k[0] for k in mismatch_table] + [k[1] for k in mismatch_table]))
print(f"{'D-1 →':<20}", end='')
for r in all_regimes: print(f"{r:>14}", end='')
print()
print("-" * (20 + 14 * len(all_regimes)))
for r1 in all_regimes:
    print(f"{r1:<20}", end='')
    total_row = sum(mismatch_table.get((r1, r2), 0) for r2 in all_regimes)
    for r2 in all_regimes:
        n = mismatch_table.get((r1, r2), 0)
        if total_row > 0:
            pct = n/total_row*100
            print(f"{n:>4} ({pct:>4.0f}%)", end='   ')
        else:
            print(f"  -      ", end='   ')
    print()

# 实际 D_t 反转率 vs D-1 模型期望反转率
print("\n=== 关键: D-1 regime 实际 D_t 反转率 ===")
d1_to_outcomes = {}
for e in events:
    d_t = get_eval_date(e)
    if not d_t or d_t not in sorted_dates: continue
    i = sorted_dates.index(d_t)
    if i == 0: continue
    d_minus_1 = sorted_dates[i-1]
    r_dm1 = detect_v6(d_minus_1)
    d1_to_outcomes.setdefault(r_dm1, []).append(e['outcome'] == 'reversal')

print(f"\n{'D-1 regime':<25}{'n':>6}{'实际反转率':>10}{'模型期望':>12}")
print("-"*55)

# 模型期望 (D_t 的反转率, 即原来的 8 类 regime 反转率)
expected = {
    'kc_only_red': 2.6, 'sh_only_red': 12.5, 'sz_only_red': 80.0,
    'spread_high_up': 2.6, 'all_green_strong': 37.8, 'all_green_weak': 50.0,
    'all_red_weak': 55.6, 'all_red_strong': 62.9, 'normal': 61.6
}

for r in sorted(d1_to_outcomes.keys()):
    arr = d1_to_outcomes[r]
    rev = sum(arr)
    exp = expected.get(r, 0)
    print(f"{r:<25}{len(arr):>6}{rev/len(arr)*100:>9.1f}%{exp:>11.1f}%")
