"""探索特征非线性 + 交互效应 - 找 LR 没学到的模式"""
import json

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json') as f:
    events = json.load(f)['events']

print(f"事件总数: {len(events)}, 反转 {sum(1 for e in events if e['outcome']=='reversal')}\n")

# 1. callback_pct × cb5_main_avg
print("=== callback × cb5_main 二维表 (反转率) ===")
print(f"{'cb (回调%)':<15}", end='')
cb5_bins = [(-99, -0.5), (-0.5, 0), (0, 0.5), (0.5, 2), (2, 99)]
cb5_labels = ["<-0.5", "-0.5~0", "0~0.5", "0.5~2", ">=2"]
for lbl in cb5_labels: print(f"{lbl:>14}", end='')
print()
print("-"*85)
cb_bins = [(0, 2), (2, 5), (5, 10), (10, 99)]
cb_labels = ["0~2", "2~5", "5~10", "≥10"]
for cb_lo, cb_hi in cb_bins:
    print(f"{cb_labels[cb_bins.index((cb_lo, cb_hi))]:<15}", end='')
    for cb5_lo, cb5_hi in cb5_bins:
        sub = [e for e in events if cb_lo <= (e.get('callback_pct',0) or 0) < cb_hi and cb5_lo <= (e.get('cb5_main_avg',0) or 0) < cb5_hi]
        if not sub: print(f"{'-':>14}", end=''); continue
        rev = sum(1 for e in sub if e['outcome']=='reversal')
        print(f"{rev/len(sub)*100:>5.0f}%(n{len(sub):>3})", end='   ')
    print()

# 2. lbc × callback
print("\n=== lbc × callback 二维表 ===")
print(f"{'lbc':<10}", end='')
for lbl in cb_labels: print(f"{lbl:>14}", end='')
print()
print("-"*70)
for lbc_label, lbc_cond in [("lbc=1", lambda x: x==1), ("lbc=2", lambda x: x==2), ("lbc=3+", lambda x: x>=3)]:
    print(f"{lbc_label:<10}", end='')
    for cb_lo, cb_hi in cb_bins:
        sub = [e for e in events if lbc_cond(e.get('d0_lbc',1) or 1) and cb_lo <= (e.get('callback_pct',0) or 0) < cb_hi]
        if len(sub) < 3: print(f"{'-':>14}", end=''); continue
        rev = sum(1 for e in sub if e['outcome']=='reversal')
        print(f"{rev/len(sub)*100:>5.0f}%(n{len(sub):>3})", end='   ')
    print()

# 3. d0_chg × callback (主板 10cm vs 20cm 不同)
print("\n=== d0_chg × callback (D0涨幅 × 回调) ===")
chg_bins = [("9.5~12", lambda x: 9.5<=x<12), ("12~16", lambda x: 12<=x<16), ("16~21", lambda x: 16<=x<21), ("≥21", lambda x: x>=21)]
print(f"{'d0_chg':<15}", end='')
for lbl in cb_labels: print(f"{lbl:>14}", end='')
print()
print("-"*70)
for chg_label, chg_cond in chg_bins:
    print(f"{chg_label:<15}", end='')
    for cb_lo, cb_hi in cb_bins:
        sub = [e for e in events if chg_cond(e.get('d0_chg',0) or 0) and cb_lo <= (e.get('callback_pct',0) or 0) < cb_hi]
        if len(sub) < 3: print(f"{'-':>14}", end=''); continue
        rev = sum(1 for e in sub if e['outcome']=='reversal')
        print(f"{rev/len(sub)*100:>5.0f}%(n{len(sub):>3})", end='   ')
    print()

# 4. broke_ma5/ma10
print("\n=== broke_ma5 × broke_ma10 ===")
combos = [(False, False), (True, False), (True, True)]
for ma5, ma10 in combos:
    sub = [e for e in events if e.get('broke_ma5')==ma5 and e.get('broke_ma10')==ma10]
    if not sub: continue
    rev = sum(1 for e in sub if e['outcome']=='reversal')
    print(f"  broke_ma5={ma5}, broke_ma10={ma10}: n={len(sub)}, 反转 {rev/len(sub)*100:.1f}%")

# 5. vol_callback_ratio
print("\n=== vol_callback_ratio (回调期 vs D0 量比) ===")
vol_bins = [("<0.3", lambda x: x<0.3), ("0.3~0.5", lambda x: 0.3<=x<0.5), ("0.5~0.7", lambda x: 0.5<=x<0.7),
            ("0.7~1.0", lambda x: 0.7<=x<1.0), ("1.0~1.5", lambda x: 1.0<=x<1.5), (">=1.5", lambda x: x>=1.5)]
for label, cond in vol_bins:
    sub = [e for e in events if cond(e.get('vol_callback_ratio',0) or 0)]
    if len(sub) < 5: continue
    rev = sum(1 for e in sub if e['outcome']=='reversal')
    print(f"  量比 {label:<10}: n={len(sub):>4}, 反转 {rev/len(sub)*100:.1f}%")

# 6. callback × cb1_main (D-1 主力流入 是 关键末端信号)
print("\n=== cb1_main_avg (D-1 主力流入) 反转率 ===")
cb1_bins = [("<-1亿", lambda x: x<-1), ("-1~-0.3", lambda x: -1<=x<-0.3), ("-0.3~0.3", lambda x: -0.3<=x<0.3),
            ("0.3~1", lambda x: 0.3<=x<1), ("1~3", lambda x: 1<=x<3), (">=3亿", lambda x: x>=3)]
for label, cond in cb1_bins:
    sub = [e for e in events if cond(e.get('cb1_main_avg',0) or 0)]
    if len(sub) < 5: continue
    rev = sum(1 for e in sub if e['outcome']=='reversal')
    print(f"  cb1 {label:<12}: n={len(sub):>4}, 反转 {rev/len(sub)*100:.1f}%")

# 7. cb1_main 跟 cb5_main 比, 是末日信号还是噪声
print("\n=== cb1 (末日) 反向 vs cb5 (整体) 趋势 ===")
# cb5 强 (>=1亿) 但 cb1 弱 (<0): 整体好但末日跑了
sub1 = [e for e in events if (e.get('cb5_main_avg',0) or 0) >= 1 and (e.get('cb1_main_avg',0) or 0) < 0]
rev1 = sum(1 for e in sub1 if e['outcome']=='reversal')
print(f"  cb5>=1亿 + cb1<0 (好票末日跑路): n={len(sub1)}, 反转 {rev1/max(1,len(sub1))*100:.1f}%")
# cb5 强 + cb1 强
sub2 = [e for e in events if (e.get('cb5_main_avg',0) or 0) >= 1 and (e.get('cb1_main_avg',0) or 0) >= 1]
rev2 = sum(1 for e in sub2 if e['outcome']=='reversal')
print(f"  cb5>=1亿 + cb1>=1 (好票末日仍流入): n={len(sub2)}, 反转 {rev2/max(1,len(sub2))*100:.1f}%")
# cb5 弱 (<0) + cb1 强 (>=1)
sub3 = [e for e in events if (e.get('cb5_main_avg',0) or 0) < 0 and (e.get('cb1_main_avg',0) or 0) >= 1]
rev3 = sum(1 for e in sub3 if e['outcome']=='reversal')
print(f"  cb5<0 + cb1>=1 (整体差但末日翻红): n={len(sub3)}, 反转 {rev3/max(1,len(sub3))*100:.1f}%")
