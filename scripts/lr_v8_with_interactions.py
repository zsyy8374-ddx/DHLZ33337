"""v0.8 LR: 加非线性 + 交互特征
新加的:
1. vol_dead_zone: 量比 0.5~0.7 (反转 18%, 极差)
2. vol_extreme_low: 量比 <0.3 (反转 100%, 极强)
3. shake_signal: cb5>=1 + cb1<0 (好票末日跑路, 反转 93%)
4. double_break: broke_ma5 + broke_ma10 (反转 29%, 极差)
5. lbc_with_shallow_cb: lbc>=2 + cb 2-5% (反转 94%, 强)
"""
import json, sys, random, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize, sigmoid

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

def get_dminus1_date(e):
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

def extract_v8(e):
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
    
    # D-1 regime
    dm1 = get_dminus1_date(e)
    regime = detect_v6(dm1 or "")
    
    return {
        "callback_pct": callback,
        "min_close_pct": min_close,
        "broke_ma5": 1.0 if e.get("broke_ma5") else 0.0,
        # ⭐ 新: 双破特征
        "double_break": 1.0 if e.get("broke_ma5") and e.get("broke_ma10") else 0.0,
        "shallow": 1.0 if callback < 3 else 0.0,
        "no_close_break": 1.0 if min_close < 3 else 0.0,
        # ⭐ 量比新增 (替代旧的 vol_dead/vol_explode 单一 dummy)
        "vol_extreme_low": 1.0 if vol_ratio < 0.3 else 0.0,    # 反转 100%
        "vol_dead_zone": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,  # 反转 18%
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,        # 反转 69%
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
        "lbc_num": lbc,
        "is_lianban": 1.0 if lbc >= 2 else 0.0,
        # ⭐ 新: 连板 + 浅回调 (94% 反转)
        "lianban_shallow": 1.0 if lbc >= 2 and 2 <= callback < 5 else 0.0,
        # ⭐ 新: 末日洗盘信号 (93% 反转)
        "shake_signal": 1.0 if cb5 >= 1 and cb1 < 0 else 0.0,
        # 资金流
        "cb5_main_strong_pos": 1.0 if cb5 >= 2 else 0.0,
        "cb5_main_pos": 1.0 if 0.5 <= cb5 < 2 else 0.0,
        "cb5_main_neg": 1.0 if cb5 < -0.5 else 0.0,
        "cb5_in_high": 1.0 if cb5_in >= 0.6 else 0.0,
        "cb5_in_low": 1.0 if cb5_in < 0.4 else 0.0,
        "cb5_main_avg": cb5,
        "cb3_main_avg": cb3,
        "cb1_main_avg": cb1,
        "d0_main_flow": d0_main,
        "pre_d0_5d_main_avg": pre_avg,
        # regime dummies (D-1, 不泄漏)
        "reg_kc_red": 1.0 if regime == "kc_only_red" else 0.0,
        "reg_sh_red": 1.0 if regime == "sh_only_red" else 0.0,
        "reg_sz_red": 1.0 if regime == "sz_only_red" else 0.0,
        "reg_spread_high_up": 1.0 if regime == "spread_high_up" else 0.0,
        "reg_all_red_strong": 1.0 if regime == "all_red_strong" else 0.0,
        "reg_all_red_weak": 1.0 if regime == "all_red_weak" else 0.0,
        "reg_all_green_strong": 1.0 if regime == "all_green_strong" else 0.0,
        "reg_all_green_weak": 1.0 if regime == "all_green_weak" else 0.0,
    }

cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

# Bootstrap 比较 v0.7 vs v0.8
from reversal_lr_v4 import extract_v4
features_v7 = []
features_v8 = []
for e in events:
    f7 = extract_v4(e)
    # v7 加 D-1 regime
    dm1 = get_dminus1_date(e)
    regime = detect_v6(dm1 or "")
    for r in ["kc_red","sh_red","sz_red","spread_high_up","all_red_strong","all_red_weak","all_green_strong","all_green_weak"]:
        f7[f"reg_{r}"] = 1.0 if regime == ({"kc_red":"kc_only_red","sh_red":"sh_only_red","sz_red":"sz_only_red"}.get(r, r)) else 0.0
    features_v7.append(f7)
    features_v8.append(extract_v8(e))

labels = [1 if e["outcome"]=="reversal" else 0 for e in events]

random.seed(42)
N = len(events)
n_trials = 100
delta_v8_vs_v7 = []
delta_v8_vs_base = []
print(f"Bootstrap {n_trials} trials, n={N}", flush=True)
t0 = time.time()
for trial in range(n_trials):
    perm = list(range(N))
    random.shuffle(perm)
    test_idx = perm[:int(N*0.2)]; train_idx = perm[int(N*0.2):]
    
    # v0.7
    Xtr = [features_v7[i] for i in train_idx]; Xte = [features_v7[i] for i in test_idx]
    Xtr_n, mu, sd = normalize(Xtr, cont_keys)
    Xte_n = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte]
    yt = [labels[i] for i in train_idx]; yv = [labels[i] for i in test_idx]
    w7, b7 = train_lr(Xtr_n, yt, lr=0.1, iters=200, l2=0.01)
    p7 = predict(Xte_n, w7, b7)
    auc7 = auc(p7, yv)
    
    # v0.8
    Xtr = [features_v8[i] for i in train_idx]; Xte = [features_v8[i] for i in test_idx]
    Xtr_n, mu, sd = normalize(Xtr, cont_keys)
    Xte_n = [{k: ((v - mu[k])/sd[k] if k in cont_keys else v) for k, v in f.items()} for f in Xte]
    w8, b8 = train_lr(Xtr_n, yt, lr=0.1, iters=200, l2=0.01)
    p8 = predict(Xte_n, w8, b8)
    auc8 = auc(p8, yv)
    
    # base v0.4 (无 regime)
    base_keys = [k for k in features_v8[0] if not k.startswith("reg_") and k not in ["double_break","vol_extreme_low","vol_dead_zone","lianban_shallow","shake_signal"]]
    Xtr_b = [{k: features_v7[i][k] for k in base_keys if k in features_v7[i]} for i in train_idx]
    Xte_b = [{k: features_v7[i][k] for k in base_keys if k in features_v7[i]} for i in test_idx]
    Xtr_bn, mu_b, sd_b = normalize(Xtr_b, [k for k in cont_keys if k in base_keys])
    Xte_bn = [{k: ((v - mu_b[k])/sd_b[k] if k in cont_keys and k in mu_b else v) for k, v in f.items()} for f in Xte_b]
    wb, bb = train_lr(Xtr_bn, yt, lr=0.1, iters=200, l2=0.01)
    pb = predict(Xte_bn, wb, bb)
    aucb = auc(pb, yv)
    
    delta_v8_vs_v7.append(auc8 - auc7)
    delta_v8_vs_base.append(auc8 - aucb)
    if (trial+1) % 25 == 0:
        print(f"  {trial+1}/{n_trials}, 用时 {time.time()-t0:.0f}s", flush=True)

def percentile(lst, p):
    s = sorted(lst); return s[int(len(s)*p)]

print(f"\n📊 v0.8 vs v0.7 (D-1 regime):")
print(f"  平均 ΔAUC: {sum(delta_v8_vs_v7)/len(delta_v8_vs_v7):+.4f}")
print(f"  5%~95%: [{percentile(delta_v8_vs_v7, 0.05):+.4f}, {percentile(delta_v8_vs_v7, 0.95):+.4f}]")
print(f"  正向: {sum(1 for d in delta_v8_vs_v7 if d>0)}/{len(delta_v8_vs_v7)}")

print(f"\n📊 v0.8 vs base v0.4 (无任何 regime):")
print(f"  平均 ΔAUC: {sum(delta_v8_vs_base)/len(delta_v8_vs_base):+.4f}")
print(f"  5%~95%: [{percentile(delta_v8_vs_base, 0.05):+.4f}, {percentile(delta_v8_vs_base, 0.95):+.4f}]")
print(f"  正向: {sum(1 for d in delta_v8_vs_base if d>0)}/{len(delta_v8_vs_base)}")

# 看 v0.8 全量学到的权重
all_X, mu, sd = normalize(features_v8, cont_keys)
w_all, b_all = train_lr(all_X, labels, lr=0.1, iters=300, l2=0.01)
print(f"\n📊 v0.8 全量权重 (Top 25):")
for k, v in sorted(w_all.items(), key=lambda x: -abs(x[1]))[:25]:
    sign = "↑" if v > 0 else "↓"
    print(f"   {k:<26} {v:+.4f} {sign}")
