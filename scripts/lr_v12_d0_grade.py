"""v1.2: 加 D0 涨停成色 + 量比交叉
新特征:
- d0_clean_lbc1_cb5big: D0 干净10% + 1 板 + cb5≥1亿 (反转率 76.7%) 强信号
- d0_clean_vol_explode: D0 干净10% + 量比≥1.5 (反转率 60%) 强信号
- d0_20cm_vol_dead: D0 20% 一字 + 量比死亡 0.5-0.7 (反转率 6.4%) 反指
- d0_20cm_lbc1: D0 20% 一字板 lbc=1 (反转率 10.5%) 反指 (v1.1 已有 is_20cm)
- d0_lianban_clean: D0 干净10% + lbc≥3 (反转率 53%+) 强连板信号

要求: 时序 OOS AUC + 滚动 OOS Top 20 / P≥0.7 命中率全部不退步
"""
import json, sys
from collections import defaultdict
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from reversal_lr_v10 import extract_v10, get_dminus1, detect_v6, idx_by_date
from lr_v11_with_recent_rev_rate import extract_v11, date_events, all_dates, date_to_idx, get_recent_rev_rate

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']


def extract_v12(e):
    f = extract_v11(e)
    d0_chg = e.get("d0_chg", 10) or 10
    lbc = e.get("d0_lbc", 1) or 1
    cb5 = e.get("cb5_main_avg", 0) or 0
    vol_ratio = e.get("vol_callback_ratio", 0) or 0
    
    # clean10 = D0 干净涨停板 (9.85-10.15)
    is_clean10 = 9.85 <= d0_chg <= 10.15
    is_20cm_one = 19.5 <= d0_chg <= 20.5  # 20% 一字
    
    # 强信号 +
    f["d0_clean_lbc1_cb5big"] = 1.0 if is_clean10 and lbc == 1 and cb5 >= 1.0 else 0.0
    f["d0_clean_vol_explode"] = 1.0 if is_clean10 and vol_ratio >= 1.5 else 0.0
    f["d0_clean_lianban_3p"] = 1.0 if is_clean10 and lbc >= 3 else 0.0
    
    # 反指 -
    f["d0_20cm_vol_dead"] = 1.0 if is_20cm_one and 0.5 <= vol_ratio <= 0.7 else 0.0
    f["d0_20cm_lbc1"] = 1.0 if is_20cm_one and lbc == 1 else 0.0
    f["d0_soft_overshoot"] = 1.0 if 10.15 < d0_chg < 12 and lbc == 1 else 0.0  # 26.9% 反转, 弱信号
    
    return f


cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]

features = [extract_v12(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]

print(f"📊 v1.2 数据: {len(events)} 事件, 特征 {len(features[0])} 维")

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

# 时序 80/20 OOS
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
test_idx = sorted_idx[int(N*0.8):]
train_idx = sorted_idx[:int(N*0.8)]

Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)

Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p_te = predict(Xte, w, b)
ts_auc = auc(p_te, yv)
print(f"\n时序 OOS AUC: {ts_auc:.4f} (v1.1 是 0.7296)")

# 看新特征权重
print("\n新特征权重:")
for k in ["d0_clean_lbc1_cb5big", "d0_clean_vol_explode", "d0_clean_lianban_3p", 
          "d0_20cm_vol_dead", "d0_20cm_lbc1", "d0_soft_overshoot"]:
    if k in w:
        print(f"  {k:30s} {w[k]:+.4f}")

# Top 20 命中
paired = sorted(zip(p_te, yv), reverse=True)
hit20 = sum(y for _, y in paired[:20])
hit50 = sum(y for _, y in paired[:50])
print(f"\n时序 OOS Top 20 命中: {hit20}/20 = {hit20*5}%")
print(f"时序 OOS Top 50 命中: {hit50}/50 = {hit50*2}%")

# 全月份滚动 OOS (用 N-1 月训, 测当月)
print("\n=== 滚动 OOS (按月) ===")
months = sorted(set(e['d0_date'][:7] for e in events))
all_aucs = []
all_t20 = []
all_p_high_hit = []
all_p_high_n = []

for m in months[6:]:  # 跳过头几个月样本不足
    tr_i = [i for i, e in enumerate(events) if e['d0_date'][:7] < m]
    te_i = [i for i, e in enumerate(events) if e['d0_date'][:7] == m]
    if len(tr_i) < 100 or len(te_i) < 30: continue
    Xtr_r = [features[i] for i in tr_i]
    Xtr_n, mu_m, sd_m = normalize(Xtr_r, cont_keys)
    y_tr = [labels[i] for i in tr_i]
    w_m, b_m = train_lr(Xtr_n, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_r = [features[i] for i in te_i]
    Xte_n = [{k: ((v - mu_m[k])/sd_m[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r]
    y_te = [labels[i] for i in te_i]
    p_m = predict(Xte_n, w_m, b_m)
    auc_m = auc(p_m, y_te)
    paired_m = sorted(zip(p_m, y_te), reverse=True)
    t20_m = sum(y for _,y in paired_m[:20]) / min(20, len(paired_m))
    high_n = sum(1 for p,_ in paired_m if p >= 0.7)
    high_hit = sum(y for p,y in paired_m if p >= 0.7) / max(1, high_n)
    all_aucs.append(auc_m); all_t20.append(t20_m); all_p_high_hit.append(high_hit); all_p_high_n.append(high_n)
    print(f"  {m}  n={len(te_i):>4}  AUC={auc_m:.3f}  T20={t20_m*100:>3.0f}%  P≥0.7  n={high_n:>3}  hit={high_hit*100:>4.0f}%")

if all_aucs:
    print(f"\n  平均: AUC={sum(all_aucs)/len(all_aucs):.3f}  T20={sum(all_t20)/len(all_t20)*100:.1f}%  P≥0.7命中={sum(all_p_high_hit)/len(all_p_high_hit)*100:.1f}%  候选数={sum(all_p_high_n)/len(all_p_high_n):.1f}")
print(f"\n  v1.1 基线: AUC=0.771 T20=88.9% P≥0.7 命中=92.1% 候选=22.2")
