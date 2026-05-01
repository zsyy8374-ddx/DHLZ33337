"""v1.0 LR: 用 3262 enriched events (含资金流) 训
- 数据: 2025-02 至 2026-04
- 真实反转率 36.8%
- 含 D-1 regime + 全 v0.8 交互特征
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']
with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json') as f:
    idx_data = json.load(f)

idx_by_date = {}
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

def get_dminus1(e):
    if e.get('d_t_date'):
        d_t = e['d_t_date']
    else:
        d0 = e['d0_date']
        if d0 not in sorted_dates: return None
        i = sorted_dates.index(d0)
        if i + 10 >= len(sorted_dates): return None
        d_t = sorted_dates[i + 10]
    if d_t not in sorted_dates: return None
    i = sorted_dates.index(d_t)
    if i == 0: return None
    return sorted_dates[i - 1]


def extract_v10(e):
    callback = e.get("callback_pct", 0) or 0
    min_close = e.get("min_close_pct", 0) or 0
    vol_ratio = e.get("vol_callback_ratio", 0) or 0
    d0_chg = e.get("d0_chg", 10) or 10
    lbc = e.get("d0_lbc", 1) or 1
    cb5 = e.get("cb5_main_avg", 0) or 0
    cb3 = e.get("cb3_main_avg", 0) or 0
    cb1 = e.get("cb1_main_avg", 0) or 0
    d0_main = e.get("d0_main_flow", 0) or 0
    pre_avg = e.get("pre_d0_5d_main_avg", 0) or 0
    cb5_in = e.get("cb5_in_ratio", 0) or 0
    
    dm1 = get_dminus1(e)
    regime = detect_v6(dm1 or "")
    
    return {
        # K 线
        "callback_pct": callback,
        "min_close_pct": min_close,
        "broke_ma5": 1.0 if e.get("broke_ma5") else 0.0,
        "double_break": 1.0 if e.get("broke_ma5") and e.get("broke_ma10") else 0.0,
        "shallow": 1.0 if callback < 3 else 0.0,
        "deep": 1.0 if callback >= 10 else 0.0,
        "no_close_break": 1.0 if min_close < 3 else 0.0,
        # 量比 U 型
        "vol_extreme_low": 1.0 if vol_ratio < 0.3 else 0.0,
        "vol_dead_zone": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,
        "vol_callback_ratio": vol_ratio,
        # 板块
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
        "lbc_num": lbc,
        "is_lianban": 1.0 if lbc >= 2 else 0.0,
        "lianban_shallow": 1.0 if lbc >= 2 and 2 <= callback < 5 else 0.0,
        # 资金流 (3262 数据展现新真相)
        "cb5_main_avg": cb5,
        "cb3_main_avg": cb3,
        "cb1_main_avg": cb1,
        "d0_main_flow": d0_main,
        "pre_d0_5d_main_avg": pre_avg,
        # 真实死亡区: cb5 -0.3~0 (反转 20.3%)
        "cb5_dead_zone": 1.0 if -0.3 <= cb5 < 0 else 0.0,
        "cb5_main_strong_pos": 1.0 if cb5 >= 2 else 0.0,
        "cb5_main_pos": 1.0 if 0.3 <= cb5 < 2 else 0.0,
        "cb5_main_neg_strong": 1.0 if cb5 < -1 else 0.0,
        "cb5_in_high": 1.0 if cb5_in >= 0.6 else 0.0,
        "cb5_in_low": 1.0 if cb5_in < 0.4 else 0.0,
        # 末日反差 (好票被洗 92% 反转)
        "shake_signal": 1.0 if cb5 >= 1 and cb1 < 0 else 0.0,
        # D-1 regime
        "reg_kc_red": 1.0 if regime == "kc_only_red" else 0.0,
        "reg_sh_red": 1.0 if regime == "sh_only_red" else 0.0,
        "reg_sz_red": 1.0 if regime == "sz_only_red" else 0.0,
        "reg_spread_high_up": 1.0 if regime == "spread_high_up" else 0.0,
        "reg_all_red_strong": 1.0 if regime == "all_red_strong" else 0.0,
        "reg_all_red_weak": 1.0 if regime == "all_red_weak" else 0.0,
        "reg_all_green_strong": 1.0 if regime == "all_green_strong" else 0.0,
        "reg_all_green_weak": 1.0 if regime == "all_green_weak" else 0.0,
    }


features = [extract_v10(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
print(f"📊 数据: {len(events)}, 反转 {sum(labels)} ({sum(labels)/len(labels)*100:.1f}%)")

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio"]

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

# 时序 80/20
sorted_evs = sorted(enumerate(events), key=lambda x: x[1]['d0_date'])
sorted_idx = [i for i, _ in sorted_evs]
N = len(events)
test_idx = sorted_idx[int(N*0.8):]
train_idx = sorted_idx[:int(N*0.8)]

# 训
Xtr_raw = [features[i] for i in train_idx]
Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
yt = [labels[i] for i in train_idx]
w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)

# 测
Xte_raw = [features[i] for i in test_idx]
Xte = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte_raw]
yv = [labels[i] for i in test_idx]
p_te = predict(Xte, w, b)
ts_auc = auc(p_te, yv)
print(f"\n时序 OOS AUC: {ts_auc:.4f}")

# Top N 命中
sorted_pte = sorted(zip(p_te, yv), reverse=True)
print("\nTop N 命中:")
for n in [10, 20, 30, 50, 100, 150, 200]:
    if len(sorted_pte) < n: continue
    sub = sorted_pte[:n]
    hit = sum(y for _, y in sub) / n
    p_thr = sub[-1][0]
    print(f"   Top {n:>3}: 命中 {hit*100:.1f}%, P 阈值 {p_thr:.3f}")

# 阈值校准 (累积命中)
P_high = 0.85; P_mid = 0.70
for n in [10, 20, 30, 50, 80]:
    cumhit = 0
    for i, (p, y) in enumerate(sorted_pte[:n]):
        cumhit += y
        if cumhit / (i+1) >= 0.85:
            P_high = p
P_high = max(0.6, P_high)  # 最低 0.6

for n in [50, 100, 150]:
    cumhit = 0
    for i, (p, y) in enumerate(sorted_pte[:n]):
        cumhit += y
        if cumhit / (i+1) >= 0.70:
            P_mid = p
P_mid = max(0.5, P_mid)

# 全量重训
X_all, mu_all, sd_all = normalize(features, cont_keys)
w_all, b_all = train_lr(X_all, labels, lr=0.1, iters=300, l2=0.01)

print(f"\n🎚️ 阈值: P_high={P_high:.3f}, P_mid={P_mid:.3f}")
print(f"\n📊 v1.0 全量权重 (Top 25):")
for k, v in sorted(w_all.items(), key=lambda x: -abs(x[1]))[:25]:
    sign = "↑" if v > 0 else "↓"
    print(f"   {k:<26} {v:+.4f} {sign}")

# 落档
out = {
    "version": "v1.0",
    "data_basis": "3262 enriched events (含资金流, 2025-02 至 2026-04)",
    "regime_basis": "D-1 (推送日, 不泄漏)",
    "features": list(features[0].keys()),
    "cont_keys": cont_keys,
    "feature_means": mu_all,
    "feature_stds": sd_all,
    "weights": w_all,
    "bias": b_all,
    "ts_auc": ts_auc,
    "P_high": P_high,
    "P_mid": P_mid,
    "n_events": N,
    "reversal_rate": sum(labels)/N,
    "calibration_method": "OOS_top_N (cumulative ≥85%)",
}

with open('/Users/openclaw/.openclaw/workspace-dengxian/picks/lr_v10_model.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n📁 落档: lr_v10_model.json")
