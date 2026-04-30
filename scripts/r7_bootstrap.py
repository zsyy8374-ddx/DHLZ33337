"""Bootstrap 1000 次重采样: 验证 R7 改善 AUC 的置信区间

每次:
- 随机分 train/test (80/20)
- 训 LR, 算 test 上 AUC orig 与 R7 调权后的 AUC
- 累积 1000 次, 看 R7 改善的分布
"""
import json, random, math
import sys
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

def adjust_r7(p, e, r7_on):
    if not r7_on: return p
    lbc = e.get("d0_lbc", 1) or 1
    if lbc >= 3: return max(0.0, p - 0.35)
    if lbc >= 2: return max(0.0, p - 0.25)
    return max(0.0, p - 0.10)

labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
features = [extract(e) for e in events]
keys = list(features[0].keys())
X, _, _ = normalize_dicts(features, keys)

def auc_simple(scores, ys):
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
n_trials = 200  # 1000 太慢, 200 够
deltas = []
deltas_with_r7 = []

print(f"Bootstrap {n_trials} trials, n={N}", flush=True)

import time
t0 = time.time()
for trial in range(n_trials):
    # 随机划 80/20 (按事件随机, 不按时间)
    perm = list(range(N))
    random.shuffle(perm)
    test_size = int(N * 0.2)
    test_idx = perm[:test_size]
    train_idx = perm[test_size:]
    
    Xtr = [X[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [X[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    w, b = train_lr(Xtr, ytr, lr=0.1, iters=200, l2=0.01)
    pre_o = predict(Xte, w, b)
    pre_r7 = [adjust_r7(p, events[j], event_r7[j]) for j, p in zip(test_idx, pre_o)]
    
    a_o = auc_simple(pre_o, yte)
    a_r7 = auc_simple(pre_r7, yte)
    delta = a_r7 - a_o
    deltas.append(delta)
    
    n_r7_test = sum(1 for j in test_idx if event_r7[j])
    if n_r7_test >= 8:  # 至少 8 个 R7 事件才统计
        deltas_with_r7.append(delta)
    
    if (trial+1) % 50 == 0:
        elapsed = time.time() - t0
        print(f"  trial {trial+1}/{n_trials}, 用时 {elapsed:.0f}s, 预计剩余 {elapsed*(n_trials/(trial+1)-1):.0f}s", flush=True)

# 统计
def percentile(lst, p):
    s = sorted(lst)
    return s[int(len(s)*p)]

print(f"\n📊 全 {n_trials} trials AUC 改善 (R7 - orig):")
print(f"  平均: {sum(deltas)/len(deltas):+.4f}")
print(f"  中位: {percentile(deltas, 0.5):+.4f}")
print(f"  5% 分位: {percentile(deltas, 0.05):+.4f}")
print(f"  95% 分位: {percentile(deltas, 0.95):+.4f}")
n_pos = sum(1 for d in deltas if d > 0)
print(f"  正向比例: {n_pos}/{len(deltas)} = {n_pos/len(deltas)*100:.1f}%")

if deltas_with_r7:
    print(f"\n📊 仅 trials 含 ≥8 个 R7 事件 ({len(deltas_with_r7)} 个):")
    print(f"  平均: {sum(deltas_with_r7)/len(deltas_with_r7):+.4f}")
    print(f"  中位: {percentile(deltas_with_r7, 0.5):+.4f}")
    print(f"  5%: {percentile(deltas_with_r7, 0.05):+.4f}")
    print(f"  95%: {percentile(deltas_with_r7, 0.95):+.4f}")
    n_pos2 = sum(1 for d in deltas_with_r7 if d > 0)
    print(f"  正向比例: {n_pos2}/{len(deltas_with_r7)} = {n_pos2/len(deltas_with_r7)*100:.1f}%")
