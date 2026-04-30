"""测试新 regime 分类: 7 类 (加入 all_red, all_green, sz_strong)"""
import json, sys, math
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import normalize, train_lr, predict, extract_v4

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

# v0.5 (6 类)
def detect_v5(date):
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

# v0.6 (8 类) - 优先级更高的优先匹配
def detect_v6(date):
    if date not in idx_by_date: return "normal"
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    avg = (sh + sz + kc) / 3
    # 极端 (高优先)
    if kc > 2 and sh < 0.5: return "kc_only_red"
    if sh > 0.5 and sz < -0.3 and kc < -0.3: return "sh_only_red"
    if sz > 2 and sh < 0.5: return "sz_only_red"
    if spread > 4 and avg > 0: return "spread_high_up"
    # 整体方向 (中优先)
    if sh <= 0 and sz <= 0 and kc <= 0:
        if avg <= -0.5: return "all_green_strong"  # 齐跌强
        return "all_green_weak"  # 齐跌弱
    if sh >= 0 and sz >= 0 and kc >= 0:
        if avg >= 0.5: return "all_red_strong"
        return "all_red_weak"
    return "normal"  # 涨跌混合 = 正常

results = []
for e in events:
    eval_d = get_eval_date(e)
    if not eval_d: continue
    r5 = detect_v5(eval_d)
    r6 = detect_v6(eval_d)
    is_rev = e["outcome"] == "reversal"
    results.append({"v5": r5, "v6": r6, "is_rev": is_rev, "lbc": e.get("d0_lbc",1) or 1})

print("v5 6 类 vs v6 8 类:\n")
from collections import Counter
print(f"{'regime':<25}{'n':>6}{'反转率':>8}")
print("-"*45)
print("=== v5 (6 类) ===")
for k, n in Counter(r["v5"] for r in results).most_common():
    rev = sum(1 for r in results if r["v5"]==k and r["is_rev"])
    print(f"{k:<25}{n:>6}{rev/n*100:>7.1f}%")
print("\n=== v6 (8 类) ===")
for k, n in Counter(r["v6"] for r in results).most_common():
    rev = sum(1 for r in results if r["v6"]==k and r["is_rev"])
    print(f"{k:<25}{n:>6}{rev/n*100:>7.1f}%")

# 现在测 v6 的 post-hoc 调权效果
def boost_v6(c, regime):
    lbc = c.get("d0_lbc", 1) or 1
    boost = 0
    if regime in ("kc_only_red", "spread_high_up"):  # 2.6%
        if lbc >= 3: boost = -0.40
        elif lbc >= 2: boost = -0.30
        else: boost = -0.15
    elif regime == "sh_only_red":  # 12.5%
        if lbc >= 3: boost = -0.30
        elif lbc >= 2: boost = -0.20
        else: boost = -0.08
    elif regime == "all_green_strong":  # ~?%, 看历史
        boost = -0.10
    elif regime == "all_green_weak":
        boost = -0.05
    elif regime == "all_red_strong":  # 强齐红, 给加分
        boost = +0.05
    elif regime == "all_red_weak":
        boost = 0
    elif regime == "sz_only_red":  # 80%
        boost = +0.05
    return boost

# 5 fold CV
event_v5 = [r["v5"] for r in results]
event_v6 = [r["v6"] for r in results]
events_used = events[:len(results)]

features = [extract_v4(e) for e in events_used]
labels = [1 if e["outcome"]=="reversal" else 0 for e in events_used]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]

sorted_idx = sorted(range(len(events_used)), key=lambda i: events_used[i].get("d0_date", ""))
K = 5; fold_size = len(events_used) // K

def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)

def topn(scores, ys, n):
    paired = sorted(zip(scores, ys), reverse=True)[:n]
    return sum(y for _, y in paired)/max(1,len(paired))

# v5 boost
def boost_v5(c, regime):
    lbc = c.get("d0_lbc", 1) or 1
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
    return boost

aucs_o, aucs_5, aucs_6 = [], [], []
t30_o, t30_5, t30_6 = [], [], []
for k in range(K):
    test_set = set(sorted_idx[k*fold_size:(k+1)*fold_size if k < K-1 else len(events_used)])
    tr = [i for i in sorted_idx if i not in test_set]; te = list(test_set)
    Xtr_raw = [features[i] for i in tr]; Xte_raw = [features[i] for i in te]
    Xtr, mu, sd = normalize(Xtr_raw, cont_keys)
    Xte = [{kk: ((v - mu[kk])/sd[kk] if kk in cont_keys else v) for kk, v in f.items()} for f in Xte_raw]
    yt = [labels[i] for i in tr]; yv = [labels[i] for i in te]
    w, b = train_lr(Xtr, yt, lr=0.1, iters=300, l2=0.01)
    p_o = predict(Xte, w, b)
    p_5 = [max(0, min(1, p + boost_v5(events_used[j], event_v5[j]))) for j, p in zip(te, p_o)]
    p_6 = [max(0, min(1, p + boost_v6(events_used[j], event_v6[j]))) for j, p in zip(te, p_o)]
    aucs_o.append(auc(p_o, yv)); aucs_5.append(auc(p_5, yv)); aucs_6.append(auc(p_6, yv))
    t30_o.append(topn(p_o, yv, 30)); t30_5.append(topn(p_5, yv, 30)); t30_6.append(topn(p_6, yv, 30))

avg = lambda l: sum(l)/len(l)
print(f"\n=== 5 fold CV (post-hoc 调权对比) ===")
print(f"  base (无调权):   AUC {avg(aucs_o):.4f}, T30 {avg(t30_o)*100:.1f}%")
print(f"  v5 (6类 regime): AUC {avg(aucs_5):.4f} ({avg(aucs_5)-avg(aucs_o):+.4f}), T30 {avg(t30_5)*100:.1f}% ({(avg(t30_5)-avg(t30_o))*100:+.1f}pp)")
print(f"  v6 (8类 regime): AUC {avg(aucs_6):.4f} ({avg(aucs_6)-avg(aucs_o):+.4f}), T30 {avg(t30_6)*100:.1f}% ({(avg(t30_6)-avg(t30_o))*100:+.1f}pp)")
