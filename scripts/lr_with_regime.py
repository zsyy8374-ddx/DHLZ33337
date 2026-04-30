"""把 regime 当 dummy 特征喂进 LR, 看是否比 post-hoc 调权更好

对比:
  v0.4 base (无 regime)
  v0.4 + regime dummy (训练时已知)
  v0.4 base + regime 后处理调权
"""
import json, math, sys, random
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import train_lr, predict, sigmoid, extract_v4, normalize

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

# 构造特征
def extract_with_regime(e, regime):
    f = extract_v4(e)
    # regime dummies (one-hot)
    f["reg_kc_red"] = 1.0 if regime == "kc_only_red" else 0.0
    f["reg_sh_red"] = 1.0 if regime == "sh_only_red" else 0.0
    f["reg_sz_red"] = 1.0 if regime == "sz_only_red" else 0.0
    f["reg_spread_up"] = 1.0 if regime == "spread_high_up" else 0.0
    f["reg_weak_res"] = 1.0 if regime == "weak_resonant" else 0.0
    f["reg_strong_res"] = 1.0 if regime == "strong_resonant" else 0.0
    # interaction: regime × lbc
    lbc = e.get("d0_lbc", 1) or 1
    f["reg_kc_lianban"] = 1.0 if regime == "kc_only_red" and lbc >= 2 else 0.0
    f["reg_spread_lianban"] = 1.0 if regime == "spread_high_up" and lbc >= 2 else 0.0
    f["reg_sz_lianban"] = 1.0 if regime == "sz_only_red" and lbc >= 2 else 0.0  # sz 红 + 连板 = 双倍利好?
    return f

# 不带 regime 的版本
features_base = [extract_v4(e) for e in events]
features_reg = [extract_with_regime(e, event_regime[i]) for i, e in enumerate(events)]

cont_keys_base = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]
cont_keys_reg = cont_keys_base  # regime 是 dummy

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

def topn_hit(scores, ys, n):
    paired = sorted(zip(scores, ys), reverse=True)[:n]
    return sum(y for _, y in paired)/max(1,len(paired))

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

# 5 fold CV
sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
K = 5
fold_size = len(events) // K

base_aucs, base_t30 = [], []
post_aucs, post_t30 = [], []
embed_aucs, embed_t30 = [], []
combined_aucs, combined_t30 = [], []

print(f"{'Fold':<5}{'base AUC':>10}{'post AUC':>10}{'embed AUC':>11}{'comb AUC':>10}{'base T30':>10}{'post T30':>10}{'embed T30':>11}{'comb T30':>10}")
print("-"*87)

for k in range(K):
    test_start = k * fold_size
    test_end = test_start + fold_size if k < K-1 else len(events)
    test_set = set(sorted_idx[test_start:test_end])
    train_idx = [i for i in sorted_idx if i not in test_set]
    test_idx = list(test_set)
    
    # Base
    Xb_tr_raw = [features_base[i] for i in train_idx]
    Xb_te_raw = [features_base[i] for i in test_idx]
    Xb_tr, mu_b, sd_b = normalize(Xb_tr_raw, cont_keys_base)
    Xb_te = []
    for f in Xb_te_raw:
        nf = {}
        for kk, v in f.items():
            nf[kk] = (v - mu_b[kk])/sd_b[kk] if kk in cont_keys_base else v
        Xb_te.append(nf)
    yt = [labels[i] for i in train_idx]
    yv = [labels[i] for i in test_idx]
    wb, bb = train_lr(Xb_tr, yt, lr=0.1, iters=300, l2=0.01)
    pre_base = predict(Xb_te, wb, bb)
    
    # Post-hoc
    pre_post = [adjust_post(p, events[j], event_regime[j]) for j, p in zip(test_idx, pre_base)]
    
    # Embed (regime as feature)
    Xr_tr_raw = [features_reg[i] for i in train_idx]
    Xr_te_raw = [features_reg[i] for i in test_idx]
    Xr_tr, mu_r, sd_r = normalize(Xr_tr_raw, cont_keys_reg)
    Xr_te = []
    for f in Xr_te_raw:
        nf = {}
        for kk, v in f.items():
            nf[kk] = (v - mu_r[kk])/sd_r[kk] if kk in cont_keys_reg else v
        Xr_te.append(nf)
    wr, br = train_lr(Xr_tr, yt, lr=0.1, iters=300, l2=0.01)
    pre_embed = predict(Xr_te, wr, br)
    
    # Combined: embed + post-hoc
    pre_combined = [adjust_post(p, events[j], event_regime[j]) for j, p in zip(test_idx, pre_embed)]
    
    bA = auc_simple(pre_base, yv); pA = auc_simple(pre_post, yv); eA = auc_simple(pre_embed, yv); cA = auc_simple(pre_combined, yv)
    bT = topn_hit(pre_base, yv, 30); pT = topn_hit(pre_post, yv, 30); eT = topn_hit(pre_embed, yv, 30); cT = topn_hit(pre_combined, yv, 30)
    base_aucs.append(bA); post_aucs.append(pA); embed_aucs.append(eA); combined_aucs.append(cA)
    base_t30.append(bT); post_t30.append(pT); embed_t30.append(eT); combined_t30.append(cT)
    
    print(f"{k+1:<5}{bA:>10.4f}{pA:>10.4f}{eA:>11.4f}{cA:>10.4f}{int(bT*100):>9}%{int(pT*100):>9}%{int(eT*100):>10}%{int(cT*100):>9}%")

avg = lambda l: sum(l)/len(l)
print(f"\n{'Method':<30}{'Avg AUC':>10}{'Avg T30':>10}{'ΔAUC vs base':>15}{'ΔT30 vs base':>15}")
print("-"*80)
print(f"{'base (v0.4 无 regime)':<30}{avg(base_aucs):>10.4f}{avg(base_t30)*100:>9.1f}%")
print(f"{'+ post-hoc 调权':<30}{avg(post_aucs):>10.4f}{avg(post_t30)*100:>9.1f}%{avg(post_aucs)-avg(base_aucs):>+15.4f}{(avg(post_t30)-avg(base_t30))*100:>+13.1f}pp")
print(f"{'+ regime embed':<30}{avg(embed_aucs):>10.4f}{avg(embed_t30)*100:>9.1f}%{avg(embed_aucs)-avg(base_aucs):>+15.4f}{(avg(embed_t30)-avg(base_t30))*100:>+13.1f}pp")
print(f"{'+ embed + post-hoc 联合':<30}{avg(combined_aucs):>10.4f}{avg(combined_t30)*100:>9.1f}%{avg(combined_aucs)-avg(base_aucs):>+15.4f}{(avg(combined_t30)-avg(base_t30))*100:>+13.1f}pp")
