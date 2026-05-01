"""v1.2 实验: D0 涨停成色
- d0_chg ≈ 9.94 ~ 10.06 (含 ST = 5.0%) 的"标准涨停"
- d0_chg > 10.5 的"放量超涨停" (含创业板/科创板 20%)
- d0 涨停 + 高换手 / 低换手 区分
- d0_chg 中位数 vs 反转率
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

# 1. 看 d0_chg 分桶
buckets = [
    ('5% 涨停 (ST/B股)',   lambda c: 4.5 <= c < 5.5),
    ('10%整 干净一字',      lambda c: 9.85 <= c <= 10.15),
    ('10-20% (科创/创业 部分弱)',  lambda c: 10.15 < c < 19.5),
    ('20% 一字 (科创/创业)', lambda c: 19.5 <= c <= 20.5),
    ('20%+ 异常',         lambda c: c > 20.5),
]

print("=== D0 涨幅分桶反转率 ===")
print(f"{'桶':<35}{'n':>6}{'反转':>6}{'反转率':>10}{'cb5avg':>10}")
for name, fn in buckets:
    sub = [e for e in events if fn(e.get('d0_chg', 0))]
    if not sub: 
        print(f"{name:<35}{'(空)':>6}")
        continue
    n = len(sub)
    rev = sum(1 for e in sub if e['outcome'] == 'reversal')
    cb5avg = sum(e.get('cb5_main_avg', 0) for e in sub) / n
    print(f"{name:<35}{n:>6}{rev:>6}{rev/n*100:>9.1f}%{cb5avg:>10.2f}")

# 2. 干净 10% 涨停 + 不同 lbc 反转率
print("\n=== 干净 10% 涨停 (9.85-10.15) × lbc ===")
clean10 = [e for e in events if 9.85 <= e.get('d0_chg', 0) <= 10.15]
for lbc in [1, 2, 3, 4, 5]:
    sub = [e for e in clean10 if e.get('d0_lbc') == lbc]
    if len(sub) < 20: continue
    n = len(sub)
    rev = sum(1 for e in sub if e['outcome'] == 'reversal')
    print(f"  lbc={lbc}, n={n}, 反转率={rev/n*100:.1f}%")

# 3. 干净 10% lbc=1 vs 不那么干净 (10.15-12%) lbc=1
print("\n=== lbc=1 子分桶 ===")
lbc1 = [e for e in events if e.get('d0_lbc') == 1]
for name, fn in [
    ('clean10  (9.85-10.15)', lambda c: 9.85 <= c <= 10.15),
    ('soft11   (10.15-12)',   lambda c: 10.15 < c < 12),
    ('mid12-15',              lambda c: 12 <= c < 15),
    ('hard15-20',             lambda c: 15 <= c < 19.5),
    ('20% one  (19.5-20.5)',  lambda c: 19.5 <= c <= 20.5),
]:
    sub = [e for e in lbc1 if fn(e.get('d0_chg', 0))]
    if len(sub) < 20: continue
    n = len(sub)
    rev = sum(1 for e in sub if e['outcome'] == 'reversal')
    cb5 = sum(e.get('cb5_main_avg', 0) for e in sub) / n
    print(f"  {name:<25} n={n:>4}, 反转率={rev/n*100:>5.1f}%, cb5avg={cb5:+.2f}")

# 4. 量比 (vol_callback_ratio) 与 d0_chg 交叉
print("\n=== d0_chg 干净 vs vol_callback_ratio 强弱 ===")
for chg_name, chg_fn in [('clean10', lambda c: 9.85<=c<=10.15), ('soft20+', lambda c: c>15)]:
    print(f'\n  D0 = {chg_name}')
    for v_name, v_fn in [
        ('量比死亡 0.5-0.7', lambda v: 0.5<=v<=0.7),
        ('量比正常 0.7-1.5', lambda v: 0.7<v<1.5),
        ('量比偏大 1.5+',     lambda v: v>=1.5),
    ]:
        sub = [e for e in events if chg_fn(e.get('d0_chg',0)) and v_fn(e.get('vol_callback_ratio',0))]
        if len(sub) < 20: continue
        n = len(sub)
        rev = sum(1 for e in sub if e['outcome']=='reversal')
        print(f'    {v_name:<20} n={n:>4}, 反转={rev/n*100:>5.1f}%')

# 5. 干净 10% lbc=1 cb5 大 (≥1) vs 小: 4 月失败那 5 只是不是这种?
print("\n=== 高位风险 (clean10 lbc=1 cb5≥1亿) ===")
risky = [e for e in events if 9.85<=e.get('d0_chg',0)<=10.15 and e.get('d0_lbc')==1 and e.get('cb5_main_avg',0)>=1]
n = len(risky); rev = sum(1 for e in risky if e['outcome']=='reversal')
print(f"  n={n}, 反转率={rev/n*100:.1f}%  (vs 平均 36.8%)")
risky2 = [e for e in events if 9.85<=e.get('d0_chg',0)<=10.15 and e.get('d0_lbc')==1 and 0.3<=e.get('cb5_main_avg',0)<1]
n2 = len(risky2); rev2 = sum(1 for e in risky2 if e['outcome']=='reversal')
print(f"  对照 cb5 0.3-1 lbc=1 clean10: n={n2}, 反转率={rev2/n2*100:.1f}%")
