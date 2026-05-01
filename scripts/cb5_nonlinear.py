"""探索 cb5_main_avg 跟反转率的非线性关系"""
import json

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json') as f:
    events = json.load(f)['events']

# 按 cb5_main 分桶
buckets = [
    ("<-1", lambda x: x < -1),
    ("-1~-0.3", lambda x: -1 <= x < -0.3),
    ("-0.3~0", lambda x: -0.3 <= x < 0),
    ("0~0.3", lambda x: 0 <= x < 0.3),
    ("0.3~1", lambda x: 0.3 <= x < 1),
    ("1~2", lambda x: 1 <= x < 2),
    ("2~3", lambda x: 2 <= x < 3),
    ("3~5", lambda x: 3 <= x < 5),
    (">=5", lambda x: x >= 5),
]

print("=== cb5_main_avg 全样本 反转率 ===")
print(f"{'桶':<10}{'n':>6}{'反转率':>8}")
for name, cond in buckets:
    sub = [e for e in events if cond(e.get('cb5_main_avg', 0) or 0)]
    rev = sum(1 for e in sub if e['outcome']=='reversal')
    if sub:
        print(f"{name:<10}{len(sub):>6}{rev/len(sub)*100:>7.1f}%")

# 按 callback_pct + cb5_main 双桶
print("\n=== callback_pct × cb5_main_avg 反转率热图 ===")
print(f"{'cb5':<10}{'cb=0~3':>12}{'cb=3~6':>12}{'cb=6~10':>12}{'cb>=10':>12}")
cb_bins = [(0,3), (3,6), (6,10), (10,99)]
cb5_bins = [("<0", lambda x: x<0), ("0~1", lambda x: 0<=x<1), ("1~3", lambda x: 1<=x<3), (">=3", lambda x: x>=3)]
for cb5_name, cb5_cond in cb5_bins:
    row = [cb5_name]
    for clo, chi in cb_bins:
        sub = [e for e in events if cb5_cond(e.get('cb5_main_avg', 0) or 0) and clo <= (e.get('callback_pct', 0) or 0) < chi]
        if sub:
            rev = sum(1 for e in sub if e['outcome']=='reversal')
            row.append(f"{rev/len(sub)*100:.0f}%(n{len(sub)})")
        else:
            row.append("-")
    print(f"{row[0]:<10}{row[1]:>12}{row[2]:>12}{row[3]:>12}{row[4]:>12}")

# 关键: cb5 大 + callback 浅 (3% 内) 的样本表现
print("\n=== '大流入 + 浅回调' (高 P 但要查) ===")
sub = [e for e in events if (e.get('cb5_main_avg', 0) or 0) >= 3 and (e.get('callback_pct', 0) or 0) < 3]
rev = sum(1 for e in sub if e['outcome']=='reversal')
print(f"  cb5>=3亿 + cb<3%: n={len(sub)}, 反转率 {rev/max(1,len(sub))*100:.1f}%")

# 找 cb5 极大 (>5) 的反转率
sub_big = [e for e in events if (e.get('cb5_main_avg', 0) or 0) >= 5]
rev_big = sum(1 for e in sub_big if e['outcome']=='reversal')
print(f"  cb5>=5亿 (极端流入): n={len(sub_big)}, 反转率 {rev_big/max(1,len(sub_big))*100:.1f}%")

# cb5>=5 + lbc=1
sub2 = [e for e in events if (e.get('cb5_main_avg', 0) or 0) >= 5 and (e.get('d0_lbc', 1) or 1) == 1]
rev2 = sum(1 for e in sub2 if e['outcome']=='reversal')
print(f"  cb5>=5亿 + lbc=1: n={len(sub2)}, 反转率 {rev2/max(1,len(sub2))*100:.1f}%")

# 是否有 'cb5 适中 (0.5-2亿)' 反而最好?
sub_mid = [e for e in events if 0.5 <= (e.get('cb5_main_avg', 0) or 0) < 2]
rev_mid = sum(1 for e in sub_mid if e['outcome']=='reversal')
print(f"\n  cb5 0.5-2亿 (温和流入): n={len(sub_mid)}, 反转率 {rev_mid/max(1,len(sub_mid))*100:.1f}%")

sub_neg = [e for e in events if (e.get('cb5_main_avg', 0) or 0) < 0]
rev_neg = sum(1 for e in sub_neg if e['outcome']=='reversal')
print(f"  cb5 <0 (净流出): n={len(sub_neg)}, 反转率 {rev_neg/max(1,len(sub_neg))*100:.1f}%")

# 与 callback 交互: cb5<0 + cb深 (>=5%)
sub3 = [e for e in events if (e.get('cb5_main_avg', 0) or 0) < 0 and (e.get('callback_pct', 0) or 0) >= 5]
rev3 = sum(1 for e in sub3 if e['outcome']=='reversal')
print(f"  cb5<0 (流出) + cb>=5% (深回调): n={len(sub3)}, 反转率 {rev3/max(1,len(sub3))*100:.1f}%")

sub4 = [e for e in events if (e.get('cb5_main_avg', 0) or 0) >= 1 and (e.get('callback_pct', 0) or 0) >= 5]
rev4 = sum(1 for e in sub4 if e['outcome']=='reversal')
print(f"  cb5>=1 (流入) + cb>=5% (深回调 = 强势整理): n={len(sub4)}, 反转率 {rev4/max(1,len(sub4))*100:.1f}%")

# 加上 lbc 维度
print("\n=== lbc × cb5 ===")
for lbc_label, lbc_cond in [("lbc=1", lambda x: x==1), ("lbc=2", lambda x: x==2), ("lbc=3+", lambda x: x>=3)]:
    print(f"\n{lbc_label}:")
    for name, cond in buckets:
        sub = [e for e in events if cond(e.get('cb5_main_avg', 0) or 0) and lbc_cond(e.get('d0_lbc', 1) or 1)]
        if len(sub) >= 5:
            rev = sum(1 for e in sub if e['outcome']=='reversal')
            print(f"  cb5 {name:<10} n={len(sub):>4}  反转率 {rev/len(sub)*100:.1f}%")
