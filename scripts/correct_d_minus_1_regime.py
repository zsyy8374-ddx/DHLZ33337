"""用 D-1 regime → 实际反转率 来纠正 boost"""
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

def get_eval_date(e):
    if e.get('d_t_date'): return e['d_t_date']
    d0 = e['d0_date']
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]

# 把 D-1 regime 进一步细分: D-1 regime + D_t lbc 维度
# 其实更重要: D-1 regime 跟 D_t actual 反转率
event_dm1 = []
for e in events:
    d_t = get_eval_date(e)
    if not d_t or d_t not in sorted_dates: continue
    i = sorted_dates.index(d_t)
    if i == 0: continue
    d_minus_1 = sorted_dates[i-1]
    r_dm1 = detect_v6(d_minus_1)
    event_dm1.append({
        "regime_dm1": r_dm1,
        "lbc": e.get("d0_lbc", 1) or 1,
        "is_rev": e["outcome"] == "reversal",
    })

# D-1 regime × lbc 反转率
print("=== D-1 regime × lbc 反转率 ===")
print(f"{'D-1 regime':<22}{'lbc=1':>10}{'lbc=2':>10}{'lbc>=3':>10}{'all':>10}")
print("-"*62)

regimes = sorted(set(e['regime_dm1'] for e in event_dm1))
for r in regimes:
    sub = [e for e in event_dm1 if e['regime_dm1']==r]
    if len(sub) < 5: continue
    row = [r]
    for lbc_cond in [lambda x: x==1, lambda x: x==2, lambda x: x>=3]:
        sub2 = [e for e in sub if lbc_cond(e['lbc'])]
        if sub2:
            rev = sum(1 for e in sub2 if e['is_rev'])
            row.append(f"{rev/len(sub2)*100:.0f}%(n{len(sub2)})")
        else:
            row.append("-")
    rev_all = sum(1 for e in sub if e['is_rev'])
    row.append(f"{rev_all/len(sub)*100:.0f}%(n{len(sub)})")
    print(f"{row[0]:<22}{row[1]:>10}{row[2]:>10}{row[3]:>10}{row[4]:>10}")

# 4-29 是 all_red_strong, 看那天 lbc=1 的实际反转率 应该是多少
all_avg = sum(1 for e in event_dm1 if e['is_rev']) / len(event_dm1)
print(f"\n基线整体反转率: {all_avg*100:.1f}%")

# 推荐 boost (基于 D-1 regime → 实际反转率)
print(f"\n=== 推荐 D-1 regime boost (基于实际数据) ===")
for r in regimes:
    sub = [e for e in event_dm1 if e['regime_dm1']==r]
    if len(sub) < 5: continue
    rev = sum(1 for e in sub if e['is_rev'])
    rate = rev/len(sub)
    # boost = (rate - all_avg) * 系数 0.5 (避免过度调权)
    boost = (rate - all_avg) * 0.5
    print(f"  {r:<22} n={len(sub):>4}, 实际反转 {rate*100:.1f}%  → 推荐 boost {boost:+.3f}")
