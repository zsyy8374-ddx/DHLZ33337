"""实验 11 (v0.9): 加"市场风向"特征 (无泄漏版)

关键设计:
- 不用 d_t 日的指数 (这是 outcome 决定的, 会泄漏)
- 用 D0 → "今天" (推断时为今天, 训练时为 d_t 或 D0+10) 这段窗口的 *最近 3 天* 大盘平均
- 推断时知道: 今天的最近 3 天就是真实的过去 3 天, 不依赖未来

为了训练 + 推断对称, 训练时对 reversal 事件用 d_t 日的"过去3天均值", 对失败事件用 D0+10
但这样还是会泄漏 (reversal 在弱市才会出现 = 弱市变量与 outcome 关联)
更稳的做法: 用 D0 当天起 +3, +5, +10 天的市场指数 (这样训练和推断都能定义)

但推断时的"今天"距 D0 已经过了 cb_days 天 (2-10), 所以应该用 D0 到 D0+cb_days 这段
- 训练: 用 callback_window (即事件持续 cb_days)
- 推断: 用 D0 到今天 (今天 - D0 = cb_days)

更好: 把窗口固定为 "D0 到 D0 + 5天", 推断用 cb_days = min(实际, 5)
"""
import json, sys, math
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import train_lr, predict, sigmoid
from datetime import datetime, timedelta

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/index_daily.json") as f:
    idx_data = json.load(f)

# 建索引
idx_by_date = {}
sorted_trade_dates = []
for code, info in idx_data.items():
    for r in info["rows"]:
        idx_by_date.setdefault(r["date"], {})[code] = r["chg_pct"]
sorted_trade_dates = sorted(idx_by_date.keys())

def get_market_window(d0_date, n_after=5):
    """从 d0_date 之后取 n_after 个交易日的指数涨跌均值"""
    if d0_date not in idx_by_date:
        return None
    i0 = sorted_trade_dates.index(d0_date)
    after = sorted_trade_dates[i0+1:i0+1+n_after]
    if len(after) < 2:
        return None
    sh_avg = sum(idx_by_date[d].get("sh000001", 0) for d in after) / len(after)
    sz_avg = sum(idx_by_date[d].get("sz399006", 0) for d in after) / len(after)
    kc_avg = sum(idx_by_date[d].get("sh000688", 0) for d in after) / len(after)
    return {
        "mkt_sh_avg": sh_avg,
        "mkt_sz_avg": sz_avg,
        "mkt_kc_avg": kc_avg,
        "mkt_avg": (sh_avg + sz_avg + kc_avg) / 3,
        "mkt_kc_lead": kc_avg - (sh_avg + sz_avg) / 2,  # 科创相对主板的领先
    }

# 看覆盖
covered = 0
mkt_features = []
for e in events:
    mw = get_market_window(e["d0_date"], 5)
    mkt_features.append(mw)
    if mw is not None:
        covered += 1
print(f"覆盖率 {covered}/{len(events)} = {covered/len(events)*100:.1f}%")

# 过滤
keep = [(i, e, mf) for i, (e, mf) in enumerate(zip(events, mkt_features)) if mf is not None]
print(f"保留事件 {len(keep)}")

def normalize_dicts(features, keys):
    n = len(features)
    mu = {}; sd = {}
    for k in keys:
        vals = [f[k] for f in features]
        mu[k] = sum(vals) / n
        sd[k] = math.sqrt(sum((v-mu[k])**2 for v in vals)/n) or 1.0
    out = []
    for f in features:
        d = dict(f)
        for k in keys:
            d[k] = (f[k]-mu[k])/sd[k]
        out.append(d)
    return out, mu, sd

def extract_v4(e):
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

def extract_v9(e, mw):
    f = extract_v4(e)
    f["mkt_avg"] = mw["mkt_avg"]
    f["mkt_kc_lead"] = mw["mkt_kc_lead"]
    return f

events_keep = [e for _, e, _ in keep]
mws = [mw for _, _, mw in keep]
labels = [1 if e["outcome"]=="reversal" else 0 for e in events_keep]

features_v4 = [extract_v4(e) for e in events_keep]
features_v9 = [extract_v9(e, mw) for e, mw in zip(events_keep, mws)]
v4_keys = list(features_v4[0].keys())
v9_keys = list(features_v9[0].keys())

X_v4, _, _ = normalize_dicts(features_v4, v4_keys)
X_v9, _, _ = normalize_dicts(features_v9, v9_keys)

sorted_idx = sorted(range(len(events_keep)), key=lambda i: events_keep[i].get("d0_date", ""))

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
    return sum(y for _, y in paired) / max(1, len(paired))

K = 5
fold_size = len(events_keep) // K
v4_aucs, v9_aucs = [], []
v4_t10s, v9_t10s = [], []
v4_t20s, v9_t20s = [], []

print(f"\n📊 5 折 CV (v0.4 vs v0.9 +市场风向):")
print(f"{'Fold':<6}{'v4 AUC':>10}{'v9 AUC':>10}{'ΔAUC':>10}{'v4 T10':>9}{'v9 T10':>9}{'v4 T20':>9}{'v9 T20':>9}")
print("-"*75)

for k in range(K):
    test_start = k * fold_size
    test_end = test_start + fold_size if k < K-1 else len(events_keep)
    test_set = set(sorted_idx[test_start:test_end])
    train_idx = [i for i in sorted_idx if i not in test_set]
    test_idx = list(test_set)
    
    Xtr4 = [X_v4[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte4 = [X_v4[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    Xtr9 = [X_v9[i] for i in train_idx]; Xte9 = [X_v9[i] for i in test_idx]
    
    w4, b4 = train_lr(Xtr4, ytr, lr=0.1, iters=300, l2=0.01)
    w9, b9 = train_lr(Xtr9, ytr, lr=0.1, iters=300, l2=0.01)
    
    pre4 = predict(Xte4, w4, b4)
    pre9 = predict(Xte9, w9, b9)
    
    a4 = auc_simple(pre4, yte); a9 = auc_simple(pre9, yte)
    t4_10 = topn_hit(pre4, yte, 10); t9_10 = topn_hit(pre9, yte, 10)
    t4_20 = topn_hit(pre4, yte, 20); t9_20 = topn_hit(pre9, yte, 20)
    v4_aucs.append(a4); v9_aucs.append(a9)
    v4_t10s.append(t4_10); v9_t10s.append(t9_10)
    v4_t20s.append(t4_20); v9_t20s.append(t9_20)
    print(f"{k+1:<6}{a4:>10.4f}{a9:>10.4f}{a9-a4:>+10.4f}{int(t4_10*100):>8}%{int(t9_10*100):>8}%{int(t4_20*100):>8}%{int(t9_20*100):>8}%")

avg = lambda l: sum(l)/len(l)
print(f"\n  v4 平均: AUC {avg(v4_aucs):.4f}, T10 {avg(v4_t10s)*100:.1f}%, T20 {avg(v4_t20s)*100:.1f}%")
print(f"  v9 平均: AUC {avg(v9_aucs):.4f}, T10 {avg(v9_t10s)*100:.1f}%, T20 {avg(v9_t20s)*100:.1f}%")
print(f"  Δ:       AUC {avg(v9_aucs)-avg(v4_aucs):+.4f}, T10 {(avg(v9_t10s)-avg(v4_t10s))*100:+.1f}pp, T20 {(avg(v9_t20s)-avg(v4_t20s))*100:+.1f}pp")

w_full, b_full = train_lr(X_v9, labels, lr=0.1, iters=500, l2=0.01)
print(f"\n📊 v0.9 全样本系数:")
for k in v9_keys:
    arrow = "↑" if w_full[k] > 0 else "↓"
    print(f"   {k:<28} {w_full[k]:+.4f} {arrow}")
print(f"   bias                         {b_full:+.4f}")
