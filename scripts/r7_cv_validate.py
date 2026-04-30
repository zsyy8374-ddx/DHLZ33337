"""5 折 CV 中验证 R7 调权效果

在每个 fold 测试集上:
- 计算原 LR 概率
- 算每个事件的 d_t 是否 R7 触发日
- 对触发日的事件做 R7 调权
- 比 AUC + Top N
"""
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
    if e.get("d_t_date"):
        return e["d_t_date"]
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

# R7 信息
event_r7 = []  # bool 数组
for e in events:
    eval_d = get_eval_date(e)
    event_r7.append(bool(eval_d and is_r7_day(eval_d)))
print(f"R7 触发事件 {sum(event_r7)}/{len(events)} = {sum(event_r7)/len(events)*100:.1f}%")

def r7_adjust(p, lbc, r7_on):
    if not r7_on: return p
    if (lbc or 1) >= 3: return max(0.0, p - 0.35)
    if (lbc or 1) >= 2: return max(0.0, p - 0.25)
    return max(0.0, p - 0.10)

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
orig_aucs, adj_aucs = [], []
orig_t10s, adj_t10s = [], []
orig_t20s, adj_t20s = [], []
orig_t30s, adj_t30s = [], []

print(f"\n{'Fold':<6}{'orig AUC':>10}{'adj AUC':>10}{'ΔAUC':>10}{'orig T10':>10}{'adj T10':>10}{'orig T20':>10}{'adj T20':>10}{'orig T30':>10}{'adj T30':>10}")
print("-"*96)

for k in range(K):
    test_start = k * fold_size
    test_end = test_start + fold_size if k < K-1 else len(events)
    test_idx_set = set(sorted_idx[test_start:test_end])
    train_idx = [i for i in sorted_idx if i not in test_idx_set]
    test_idx = list(test_idx_set)
    
    Xtr = [X[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [X[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    w, b = train_lr(Xtr, ytr, lr=0.1, iters=300, l2=0.01)
    pre_orig = predict(Xte, w, b)
    
    # R7 调权
    pre_adj = []
    for j, p in zip(test_idx, pre_orig):
        lbc = events[j].get("d0_lbc", 1) or 1
        r7 = event_r7[j]
        pre_adj.append(r7_adjust(p, lbc, r7))
    
    a_o = auc_simple(pre_orig, yte); a_a = auc_simple(pre_adj, yte)
    o10 = topn_hit(pre_orig, yte, 10); a10 = topn_hit(pre_adj, yte, 10)
    o20 = topn_hit(pre_orig, yte, 20); a20 = topn_hit(pre_adj, yte, 20)
    o30 = topn_hit(pre_orig, yte, 30); a30 = topn_hit(pre_adj, yte, 30)
    orig_aucs.append(a_o); adj_aucs.append(a_a)
    orig_t10s.append(o10); adj_t10s.append(a10)
    orig_t20s.append(o20); adj_t20s.append(a20)
    orig_t30s.append(o30); adj_t30s.append(a30)
    
    n_r7_in_test = sum(1 for j in test_idx if event_r7[j])
    print(f"{k+1:<6}{a_o:>10.4f}{a_a:>10.4f}{a_a-a_o:>+10.4f}{int(o10*100):>9}%{int(a10*100):>9}%{int(o20*100):>9}%{int(a20*100):>9}%{int(o30*100):>9}%{int(a30*100):>9}%   R7事件={n_r7_in_test}")

avg = lambda l: sum(l)/len(l)
print(f"\n  原 LR 平均: AUC {avg(orig_aucs):.4f}, T10 {avg(orig_t10s)*100:.1f}%, T20 {avg(orig_t20s)*100:.1f}%, T30 {avg(orig_t30s)*100:.1f}%")
print(f"  R7 调权后 :  AUC {avg(adj_aucs):.4f}, T10 {avg(adj_t10s)*100:.1f}%, T20 {avg(adj_t20s)*100:.1f}%, T30 {avg(adj_t30s)*100:.1f}%")
print(f"  Δ:           AUC {avg(adj_aucs)-avg(orig_aucs):+.4f}, T10 {(avg(adj_t10s)-avg(orig_t10s))*100:+.1f}pp, T20 {(avg(adj_t20s)-avg(orig_t20s))*100:+.1f}pp, T30 {(avg(adj_t30s)-avg(orig_t30s))*100:+.1f}pp")
