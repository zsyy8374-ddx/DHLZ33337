"""R7 规则的历史回测验证

逻辑:
  - 对每个历史事件, 找到它的 d_t (反转日, 失败用 D0+10)
  - 用 d_t 当天的三大指数判断是不是极端分化日
  - 看 R7 触发 vs 不触发, 在不同 lbc 下的 reversal 率
"""
import json
from collections import defaultdict

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json") as f:
    idx_data = json.load(f)

# 按日期索引
idx_by_date = {}
sorted_dates = []
for code, info in idx_data.items():
    for r in info["rows"]:
        idx_by_date.setdefault(r["date"], {})[code] = r["chg_pct"]
sorted_dates = sorted(idx_by_date.keys())

def get_eval_date(e):
    """事件评估日 = d_t 或 D0 + 10 个交易日"""
    if e.get("d_t_date"):
        return e["d_t_date"]
    d0 = e["d0_date"]
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]

def is_r7_day(date):
    if date not in idx_by_date: return None
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    return spread > 3 and sh < 0.5

# 分类
r7_pos_lbc1 = []; r7_pos_lbc23 = []; r7_pos_lbc4plus = []
r7_neg_lbc1 = []; r7_neg_lbc23 = []; r7_neg_lbc4plus = []
unknown = 0

for e in events:
    eval_date = get_eval_date(e)
    if not eval_date or eval_date not in idx_by_date:
        unknown += 1
        continue
    r7 = is_r7_day(eval_date)
    lbc = e.get("d0_lbc", 1) or 1
    is_rev = e["outcome"] == "reversal"
    
    if r7:
        if lbc == 1: r7_pos_lbc1.append(is_rev)
        elif lbc <= 3: r7_pos_lbc23.append(is_rev)
        else: r7_pos_lbc4plus.append(is_rev)
    else:
        if lbc == 1: r7_neg_lbc1.append(is_rev)
        elif lbc <= 3: r7_neg_lbc23.append(is_rev)
        else: r7_neg_lbc4plus.append(is_rev)

def stats(label, rev_list):
    n = len(rev_list)
    rate = sum(rev_list)/n*100 if n else 0
    return f"{label:<25} n={n:>4}  反转 {sum(rev_list):>3}  反转率 {rate:>5.1f}%"

print("📊 R7 规则的历史回测\n")
print(f"覆盖事件: {len(events) - unknown}/{len(events)} (不能定位评估日的: {unknown})\n")

print("==== R7 触发日 (极端分化, sh<0.5 + spread>3) ====")
print(stats("lbc=1", r7_pos_lbc1))
print(stats("lbc=2-3", r7_pos_lbc23))
print(stats("lbc>=4", r7_pos_lbc4plus))

print("\n==== R7 未触发日 (普通行情) ====")
print(stats("lbc=1", r7_neg_lbc1))
print(stats("lbc=2-3", r7_neg_lbc23))
print(stats("lbc>=4", r7_neg_lbc4plus))

# R7 触发日的 ≥2 板事件实际命中率 vs 非触发日
r7_pos_high = r7_pos_lbc23 + r7_pos_lbc4plus
r7_neg_high = r7_neg_lbc23 + r7_neg_lbc4plus
print(f"\n=== R7 规则有效性验证 ===")
print(f"  R7 触发日 (lbc>=2): n={len(r7_pos_high)}, 反转率 {sum(r7_pos_high)/max(1,len(r7_pos_high))*100:.1f}%")
print(f"  R7 未触发日 (lbc>=2): n={len(r7_neg_high)}, 反转率 {sum(r7_neg_high)/max(1,len(r7_neg_high))*100:.1f}%")

# 列出 R7 触发的所有日期
print("\n📅 历史 R7 触发日 (sh<0.5 + spread>3):")
r7_dates = [d for d in sorted_dates if is_r7_day(d)]
for d in r7_dates:
    info = idx_by_date[d]
    sh = info.get("sh000001", 0); sz = info.get("sz399006", 0); kc = info.get("sh000688", 0)
    print(f"  {d}: 上证 {sh:+.2f}%, 创业板 {sz:+.2f}%, 科创 {kc:+.2f}%")
