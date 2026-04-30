"""5 折 CV: 验证 6 类 regime 调权的整体效果"""
import json, sys, math
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import train_lr, predict, sigmoid

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
    if date not in idx_by_date: return "unknown"
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
from collections import Counter
print(f"Regime 分布:")
for k, v in Counter(event_regime).most_common():
    rev_rate = sum(1 for j, e in enumerate(events) if event_regime[j]==k and e['outcome']=='reversal') / max(1,v) * 100
    print(f"  {k:<20} n={v:>4}  反转率 {rev_rate:.1f}%")

def normalize_dicts(features, keys):
    n = len(features); mu = {}; sd = {}
    for k in keys:
        vals = [f[k] for f in features]
        mu[k] = sum(vals)/n
        sd[k] = math.sqrt(sum((v-mu[k])**2 for v in vals)/n) or 1.0
    out = []
    for f in features:
        d = dict(f)
        for k in keys:
            d[k] = (f[k]-mu[k])/sd[k]
        out.append(d)
    return out, mu, sd

def extract(e):
    return {
        "callback_pct": e.get("callback_pct", 0) or 0,
        "min_close_pct": e.get("min_close_pct", 0) or 0,
        "lbc_num": e.get("d0_lbc", 1) or 1,
        "cb5_main_avg": e.get("cb5_main_avg", 0) or 0,
        "cb3_main_avg": e.get("cb3_main_avg", 0) or 0,
        "cb1_main_avg": e.get("cb1_main_avg", 0) or 0,
        "d0_main_flow": e.get("d0_main_flow", 0) or 0,
        "pre_d0_5d_main_avg": e.get("pre_d0_5d_main_avg", 0) or 0,
    }

def adjust(p, e, regime):
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
    elif regime == "weak_resonant":
        boost = -0.05
    elif regime == "sz_only_red":
        boost = 0.05
    elif regime == "strong_resonant":
        boost = 0.02
    return max(0.0, min(1.0, p + boost))

labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
features = [extract(e) for e in events]
keys = list(features[0].keys())
X, _, _ = normalize_dicts(features, keys)

sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))

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

K = 5
fold_size = len(events) // K

print(f"\n{'Fold':<5}{'AUC orig':>10}{'AUC reg':>10}{'ΔAUC':>10}{'T20 orig':>10}{'T20 reg':>10}{'T30 orig':>10}{'T30 reg':>10}")
print("-"*70)

orig_aucs = []; reg_aucs = []
orig_t20s = []; reg_t20s = []
orig_t30s = []; reg_t30s = []

for k in range(K):
    test_start = k * fold_size
    test_end = test_start + fold_size if k < K-1 else len(events)
    test_set = set(sorted_idx[test_start:test_end])
    train_idx = [i for i in sorted_idx if i not in test_set]
    test_idx = list(test_set)
    
    Xtr = [X[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [X[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    w, b = train_lr(Xtr, ytr, lr=0.1, iters=300, l2=0.01)
    pre_o = predict(Xte, w, b)
    pre_r = [adjust(p, events[j], event_regime[j]) for j, p in zip(test_idx, pre_o)]
    
    a_o = auc_simple(pre_o, yte); a_r = auc_simple(pre_r, yte)
    o20 = topn_hit(pre_o, yte, 20); r20 = topn_hit(pre_r, yte, 20)
    o30 = topn_hit(pre_o, yte, 30); r30 = topn_hit(pre_r, yte, 30)
    orig_aucs.append(a_o); reg_aucs.append(a_r)
    orig_t20s.append(o20); reg_t20s.append(r20)
    orig_t30s.append(o30); reg_t30s.append(r30)
    print(f"{k+1:<5}{a_o:>10.4f}{a_r:>10.4f}{a_r-a_o:>+10.4f}{int(o20*100):>9}%{int(r20*100):>9}%{int(o30*100):>9}%{int(r30*100):>9}%")

avg = lambda l: sum(l)/len(l)
print(f"\n   平均: orig AUC {avg(orig_aucs):.4f}, regime AUC {avg(reg_aucs):.4f}, Δ {avg(reg_aucs)-avg(orig_aucs):+.4f}")
print(f"         T20 orig {avg(orig_t20s)*100:.1f}% → regime {avg(reg_t20s)*100:.1f}% (Δ {(avg(reg_t20s)-avg(orig_t20s))*100:+.1f}pp)")
print(f"         T30 orig {avg(orig_t30s)*100:.1f}% → regime {avg(reg_t30s)*100:.1f}% (Δ {(avg(reg_t30s)-avg(orig_t30s))*100:+.1f}pp)")
