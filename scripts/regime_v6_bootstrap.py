"""Bootstrap 200 次: v0.6 8 类 regime 调权稳定性"""
import json, random, math, time, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import train_lr, predict, normalize, extract_v4

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

event_regime = [detect_v6(get_eval_date(e) or "") for e in events]

def boost(c, regime):
    lbc = c.get("d0_lbc", 1) or 1
    if regime in ("kc_only_red", "spread_high_up"):
        if lbc >= 3: return -0.40
        if lbc >= 2: return -0.30
        return -0.15
    if regime == "sh_only_red":
        if lbc >= 3: return -0.30
        if lbc >= 2: return -0.20
        return -0.08
    if regime == "all_green_strong": return -0.10
    if regime == "all_green_weak": return -0.05
    if regime == "all_red_strong": return +0.05
    if regime == "all_red_weak": return 0
    if regime == "sz_only_red": return +0.05
    return 0

features = [extract_v4(e) for e in events]
labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
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

random.seed(42)
N = len(events)
n_trials = 200
deltas = []
print(f"Bootstrap {n_trials} trials, n={N}", flush=True)
t0 = time.time()
for trial in range(n_trials):
    perm = list(range(N))
    random.shuffle(perm)
    test_idx = perm[:int(N*0.2)]; train_idx = perm[int(N*0.2):]
    Xtr_raw = [features[i] for i in train_idx]; Xte_raw = [features[i] for i in test_idx]
    Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
    Xte = [{kk: ((v - mu[kk])/sd[kk] if kk in cont_keys else v) for kk, v in f.items()} for f in Xte_raw]
    yt = [labels[i] for i in train_idx]; yv = [labels[i] for i in test_idx]
    w, b = train_lr(Xtr, yt, lr=0.1, iters=200, l2=0.01)
    p_o = predict(Xte, w, b)
    p_a = [max(0, min(1, p + boost(events[j], event_regime[j]))) for j, p in zip(test_idx, p_o)]
    deltas.append(auc(p_a, yv) - auc(p_o, yv))
    if (trial+1) % 50 == 0:
        print(f"  trial {trial+1}/{n_trials}, 用时 {time.time()-t0:.0f}s", flush=True)

def percentile(lst, p):
    s = sorted(lst); return s[int(len(s)*p)]

print(f"\n📊 v6 (8类 regime) AUC 改善 ({n_trials} trials):")
print(f"  平均: {sum(deltas)/len(deltas):+.4f}")
print(f"  中位: {percentile(deltas, 0.5):+.4f}")
print(f"  5% 分位: {percentile(deltas, 0.05):+.4f}")
print(f"  95% 分位: {percentile(deltas, 0.95):+.4f}")
print(f"  正向比例: {sum(1 for d in deltas if d>0)}/{len(deltas)} = {sum(1 for d in deltas if d>0)/len(deltas)*100:.1f}%")
