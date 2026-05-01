"""分析 v1.0 在 2025-10 和 2026-04 表现差的原因"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from reversal_lr_v10 import extract_v10

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']
with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json') as f:
    idx_data = json.load(f)

idx_by_date = {}
for code, info in idx_data.items():
    for r in info['rows']:
        idx_by_date.setdefault(r['date'], {})[code] = r['chg_pct']

features = [extract_v10(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio"]

# 用 ≤2025-09 训, 测 2025-10
train_idx = [i for i, e in enumerate(events) if e['d0_date'] < '2025-10']
test_idx_oct = [i for i, e in enumerate(events) if e['d0_date'].startswith('2025-10')]
test_idx_apr = [i for i, e in enumerate(events) if e['d0_date'].startswith('2026-04')]

print(f"训练 {len(train_idx)} (≤2025-09), 测 2025-10: {len(test_idx_oct)}, 2026-04: {len(test_idx_apr)}")

Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=200, l2=0.01)

# 2025-10 Top 50 详情
def detail_test(test_idx, label):
    Xte_raw = [features[i] for i in test_idx]
    Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
    yv = [labels[i] for i in test_idx]
    p = predict(Xte, w, b)
    
    paired = sorted(zip(p, yv, test_idx), reverse=True)
    print(f"\n=== {label} Top 50 ===")
    print(f"{'#':<4}{'P':<8}{'代码':<8}{'lbc':<5}{'cb%':<7}{'cb5亿':<8}{'反转':<6}{'D0日期'}")
    print("-"*60)
    for i, (pv, yvi, evi) in enumerate(paired[:50]):
        e = events[evi]
        is_rev = "✅" if yvi else "❌"
        print(f"{i+1:<4}{pv:<8.3f}{e['code']:<8}{e.get('d0_lbc',1):<5}{e.get('callback_pct',0):<7.1f}{e.get('cb5_main_avg',0):<8.2f}{is_rev:<6}{e['d0_date']}")
    
    # 命中率
    hit50 = sum(y for _, y, _ in paired[:50])
    print(f"\nTop 50 命中: {hit50}/{50} = {hit50/50*100:.1f}%")
    
    # Top 50 失败的共同特征
    print(f"\nTop 50 失败的票 (反转=否):")
    for i, (pv, yvi, evi) in enumerate(paired[:50]):
        if not yvi:
            e = events[evi]
            print(f"  #{i+1} {e['code']} P={pv:.3f} lbc={e.get('d0_lbc',1)} cb={e.get('callback_pct',0):.1f}% cb5={e.get('cb5_main_avg',0):+.2f}亿 D0={e['d0_date']}")

detail_test(test_idx_oct, "2025-10 (T50 仅 58%)")
detail_test(test_idx_apr, "2026-04 (T20 仅 75%)")
