"""5 折 CV 验证 R7 + R8 联合调权"""
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

def is_r7_day(date):
    if date not in idx_by_date: return False
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    return spread > 3 and sh < 0.5

event_r7 = [bool(is_r7_day(get_eval_date(e) or "")) for e in events]
print(f"R7 触发 {sum(event_r7)}/{len(events)}")

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

def adjust_r7_only(p, e, r7_on):
    if not r7_on: return p
    lbc = e.get("d0_lbc", 1) or 1
    if lbc >= 3: return max(0.0, p - 0.35)
    if lbc >= 2: return max(0.0, p - 0.25)
    return max(0.0, p - 0.10)

def adjust_r78(p, e, r7_on):
    if not r7_on: return p
    lbc = e.get("d0_lbc", 1) or 1
    if lbc >= 3: p2 = p - 0.35
    elif lbc >= 2: p2 = p - 0.25
    else: p2 = p - 0.10
    # R8: 强势整理 + 主力流入 加分
    min_close = e.get("min_close_pct", 0) or 0
    cb5 = e.get("cb5_main_avg", 0) or 0
    if min_close == 0 and cb5 >= 1.0:
        p2 += 0.20
    return max(0.0, min(1.0, p2))

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

stats = {"orig": {"auc":[], "t10":[], "t20":[], "t30":[]},
         "r7":   {"auc":[], "t10":[], "t20":[], "t30":[]},
         "r78":  {"auc":[], "t10":[], "t20":[], "t30":[]}}

print(f"\n{'Fold':<5}{'AUC orig':>10}{'AUC r7':>10}{'AUC r78':>10}{'T20 orig':>10}{'T20 r7':>10}{'T20 r78':>10}")
print("-"*65)

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
    pre_r7 = [adjust_r7_only(p, events[j], event_r7[j]) for j, p in zip(test_idx, pre_o)]
    pre_r78 = [adjust_r78(p, events[j], event_r7[j]) for j, p in zip(test_idx, pre_o)]
    
    for name, pre in [("orig", pre_o), ("r7", pre_r7), ("r78", pre_r78)]:
        stats[name]["auc"].append(auc_simple(pre, yte))
        stats[name]["t10"].append(topn_hit(pre, yte, 10))
        stats[name]["t20"].append(topn_hit(pre, yte, 20))
        stats[name]["t30"].append(topn_hit(pre, yte, 30))
    
    print(f"{k+1:<5}{stats['orig']['auc'][-1]:>10.4f}{stats['r7']['auc'][-1]:>10.4f}{stats['r78']['auc'][-1]:>10.4f}{int(stats['orig']['t20'][-1]*100):>9}%{int(stats['r7']['t20'][-1]*100):>9}%{int(stats['r78']['t20'][-1]*100):>9}%")

avg = lambda l: sum(l)/len(l)
print(f"\n{'指标':<8}{'原 LR':>12}{'+ R7':>12}{'+ R7+R8':>12}{'R7 vs orig':>14}{'R78 vs orig':>14}")
for m in ["auc","t10","t20","t30"]:
    o = avg(stats["orig"][m]); r7 = avg(stats["r7"][m]); r78 = avg(stats["r78"][m])
    if m == "auc":
        print(f"{m:<8}{o:>12.4f}{r7:>12.4f}{r78:>12.4f}{r7-o:>+14.4f}{r78-o:>+14.4f}")
    else:
        print(f"{m:<8}{o*100:>11.1f}%{r7*100:>11.1f}%{r78*100:>11.1f}%{(r7-o)*100:>+13.1f}pp{(r78-o)*100:>+13.1f}pp")
