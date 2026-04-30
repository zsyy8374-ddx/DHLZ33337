"""Bootstrap 200 trials: 验证 embed+post-hoc 联合方案的稳定性"""
import json, random, math, time, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import train_lr, predict, extract_v4, normalize

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]
with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json") as f:
    idx_data = json.load(f)

idx_by_date = {}
sorted_dates = []
for code, info in idx_data.items():
    for r in info["rows"]:
        idx_by_date.setdefault(r["date"], {})[code] = r["chg_pct"]
sorted_dates = sorted(idx_by_date.keys())

def get_eval_date(e):
    if e.get("d_t_date"): return e["d_t_date"]
    d0 = e["d0_date"]
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]

def detect_regime(date):
    if date not in idx_by_date: return "normal"
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    avg = (sh + sz + kc) / 3
    if kc > 2 and sh < 0.5: return "kc_only_red"
    if sh > 0.5 and sz < -0.3 and kc < -0.3: return "sh_only_red"
    if sz > 2 and sh < 0.5: return "sz_only_red"
    if spread > 4 and avg > 0: return "spread_high_up"
    if spread < 1 and avg <= -0.5: return "weak_resonant"
    if spread < 1 and avg >= 0.5: return "strong_resonant"
    return "normal"

event_regime = [detect_regime(get_eval_date(e) or "") for e in events]

def extract_with_regime(e, regime):
    f = extract_v4(e)
    f["reg_kc_red"] = 1.0 if regime == "kc_only_red" else 0.0
    f["reg_sh_red"] = 1.0 if regime == "sh_only_red" else 0.0
    f["reg_sz_red"] = 1.0 if regime == "sz_only_red" else 0.0
    f["reg_spread_up"] = 1.0 if regime == "spread_high_up" else 0.0
    f["reg_weak_res"] = 1.0 if regime == "weak_resonant" else 0.0
    f["reg_strong_res"] = 1.0 if regime == "strong_resonant" else 0.0
    lbc = e.get("d0_lbc", 1) or 1
    f["reg_kc_lianban"] = 1.0 if regime == "kc_only_red" and lbc >= 2 else 0.0
    f["reg_spread_lianban"] = 1.0 if regime == "spread_high_up" and lbc >= 2 else 0.0
    f["reg_sz_lianban"] = 1.0 if regime == "sz_only_red" and lbc >= 2 else 0.0
    return f

features_reg = [extract_with_regime(e, event_regime[i]) for i, e in enumerate(events)]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]
labels = [1 if e["outcome"]=="reversal" else 0 for e in events]

def auc_simple(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

def adjust_post(p, e, regime):
    lbc = e.get("d0_lbc", 1) or 1
    boost = 0
    if regime in ("kc_only_red", "spread_high_up"):
        if lbc >= 3: boost = -0.40
        elif lbc >= 2: boost = -0.30
        else: boost = -0.15
    elif regime == "sh_only_red":
        if lbc >= 3: boost = -0.30
        elif lbc >= 2: boost = -0.20
        else: boost = -0.08
    elif regime == "weak_resonant": boost = -0.05
    elif regime == "sz_only_red": boost = 0.05
    elif regime == "strong_resonant": boost = 0.02
    return max(0.0, min(1.0, p + boost))

random.seed(42)
N = len(events)
n_trials = 200

deltas_post = []
deltas_combined = []
print(f"Bootstrap {n_trials} trials, n={N}", flush=True)
t0 = time.time()
for trial in range(n_trials):
    perm = list(range(N))
    random.shuffle(perm)
    test_size = int(N * 0.2)
    test_idx = perm[:test_size]
    train_idx = perm[test_size:]
    
    yt = [labels[i] for i in train_idx]
    yv = [labels[i] for i in test_idx]
    
    # Base (v0.4 无 regime)
    Xb_tr_raw = [extract_v4(events[i]) for i in train_idx]
    Xb_te_raw = [extract_v4(events[i]) for i in test_idx]
    Xb_tr, mu_b, sd_b = normalize(Xb_tr_raw, cont_keys)
    Xb_te = []
    for f in Xb_te_raw:
        nf = {kk: ((v - mu_b[kk])/sd_b[kk] if kk in cont_keys else v) for kk, v in f.items()}
        Xb_te.append(nf)
    wb, bb = train_lr(Xb_tr, yt, lr=0.1, iters=200, l2=0.01)
    pre_base = predict(Xb_te, wb, bb)
    
    # Post-hoc only
    pre_post = [adjust_post(p, events[j], event_regime[j]) for j, p in zip(test_idx, pre_base)]
    
    # Embed + post-hoc
    Xr_tr_raw = [features_reg[i] for i in train_idx]
    Xr_te_raw = [features_reg[i] for i in test_idx]
    Xr_tr, mu_r, sd_r = normalize(Xr_tr_raw, cont_keys)
    Xr_te = []
    for f in Xr_te_raw:
        nf = {kk: ((v - mu_r[kk])/sd_r[kk] if kk in cont_keys else v) for kk, v in f.items()}
        Xr_te.append(nf)
    wr, br = train_lr(Xr_tr, yt, lr=0.1, iters=200, l2=0.01)
    pre_embed = predict(Xr_te, wr, br)
    pre_combined = [adjust_post(p, events[j], event_regime[j]) for j, p in zip(test_idx, pre_embed)]
    
    a_base = auc_simple(pre_base, yv)
    a_post = auc_simple(pre_post, yv)
    a_combined = auc_simple(pre_combined, yv)
    deltas_post.append(a_post - a_base)
    deltas_combined.append(a_combined - a_base)
    
    if (trial+1) % 50 == 0:
        elapsed = time.time() - t0
        print(f"  trial {trial+1}/{n_trials}, 用时 {elapsed:.0f}s", flush=True)

def percentile(lst, p):
    s = sorted(lst); return s[int(len(s)*p)]

print(f"\n📊 Post-hoc only ({n_trials} trials):")
print(f"  平均 ΔAUC: {sum(deltas_post)/len(deltas_post):+.4f}")
print(f"  5%~95%: [{percentile(deltas_post, 0.05):+.4f}, {percentile(deltas_post, 0.95):+.4f}]")
print(f"  正向: {sum(1 for d in deltas_post if d>0)}/{len(deltas_post)}")

print(f"\n📊 Embed + Post-hoc ({n_trials} trials):")
print(f"  平均 ΔAUC: {sum(deltas_combined)/len(deltas_combined):+.4f}")
print(f"  5%~95%: [{percentile(deltas_combined, 0.05):+.4f}, {percentile(deltas_combined, 0.95):+.4f}]")
print(f"  正向: {sum(1 for d in deltas_combined if d>0)}/{len(deltas_combined)}")

# 联合 vs post-hoc 直接比
diffs = [c - p for c, p in zip(deltas_combined, deltas_post)]
print(f"\n📊 联合 vs post-hoc 单独 直接比 ({n_trials} trials):")
print(f"  联合平均 - post-hoc 平均 = {sum(diffs)/len(diffs):+.4f}")
print(f"  联合更优 trials: {sum(1 for d in diffs if d>0)}/{len(diffs)}")
