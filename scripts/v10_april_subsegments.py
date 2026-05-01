"""分析 2026-04 (T20 仅 75%) 的真涨停股共性 - 不在 Top 20 的票如何"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from reversal_lr_v10 import extract_v10

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

features = [extract_v10(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
cont_keys = ['callback_pct','min_close_pct','cb5_main_avg','cb3_main_avg','cb1_main_avg','d0_main_flow','pre_d0_5d_main_avg','lbc_num','vol_callback_ratio']

# 用 ≤2026-03 训, 测 2026-04
train_idx = [i for i, e in enumerate(events) if e['d0_date'] < '2026-04']
test_idx = [i for i, e in enumerate(events) if e['d0_date'].startswith('2026-04')]

Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=200, l2=0.01)

Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p = predict(Xte, w, b)

paired = sorted(zip(p, yv, test_idx), reverse=True)

# Top 20 失败的 vs Top 21-100 成功的
print("=== 2026-04 Top 20 (T20 75%) ===")
print(f"{'#':<4}{'P':<7}{'代码':<8}{'lbc':<5}{'cb%':<7}{'cb5':<8}{'反转':<5}{'D0'}")
for i, (pv, yvi, evi) in enumerate(paired[:20]):
    e = events[evi]
    is_rev = "✅" if yvi else "❌"
    print(f"{i+1:<4}{pv:<7.3f}{e['code']:<8}{e.get('d0_lbc',1):<5}{e.get('callback_pct',0):<7.1f}{e.get('cb5_main_avg',0):<8.2f}{is_rev:<5}{e['d0_date']}")

# Top 20 失败的 5 只 共性
top20_fail = [(pv, yvi, evi) for pv, yvi, evi in paired[:20] if not yvi]
print(f"\n### Top 20 失败 {len(top20_fail)} 只 ###")
for pv, _, evi in top20_fail:
    e = events[evi]
    print(f"  {e['code']} {e.get('name','')[:6]:<8} P={pv:.3f} lbc={e.get('d0_lbc',1)} cb={e.get('callback_pct',0):.1f}% cb5={e.get('cb5_main_avg',0):+.2f} d0_chg={e.get('d0_chg',0):.1f}% D0={e['d0_date']}")
print(f"  平均 lbc: {sum(events[evi].get('d0_lbc',1) for _,_,evi in top20_fail)/len(top20_fail):.2f}")
print(f"  平均 cb5: {sum(events[evi].get('cb5_main_avg',0) for _,_,evi in top20_fail)/len(top20_fail):+.2f}")

# Top 21-100 成功的
top21_100_success = [(pv, yvi, evi) for pv, yvi, evi in paired[20:100] if yvi]
print(f"\n### Top 21-100 成功 {len(top21_100_success)} 只 (从 80 只里) ###")
print(f"  平均 lbc: {sum(events[evi].get('d0_lbc',1) for _,_,evi in top21_100_success)/max(1,len(top21_100_success)):.2f}")
print(f"  平均 cb5: {sum(events[evi].get('cb5_main_avg',0) for _,_,evi in top21_100_success)/max(1,len(top21_100_success)):+.2f}")
print(f"  平均 cb%: {sum(events[evi].get('callback_pct',0) for _,_,evi in top21_100_success)/max(1,len(top21_100_success)):.1f}")
