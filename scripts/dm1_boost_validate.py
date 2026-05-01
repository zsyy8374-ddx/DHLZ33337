"""使用 D-1 regime boost (基于真实 D-1 → D_t 反转率) 重新验证"""
import json, math, sys, random, time
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize, extract_v4

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

def get_eval_date(e):
    if e.get('d_t_date'): return e['d_t_date']
    d0 = e['d0_date']
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]

# 计算每个事件的 D-1 regime
event_dm1_regime = []
for e in events:
    d_t = get_eval_date(e)
    if not d_t or d_t not in sorted_dates:
        event_dm1_regime.append("normal")
        continue
    i = sorted_dates.index(d_t)
    if i == 0:
        event_dm1_regime.append("normal")
        continue
    d_minus_1 = sorted_dates[i-1]
    event_dm1_regime.append(detect_v6(d_minus_1))

# 同样计算 D_t regime (旧 v0.6)
event_dt_regime = []
for e in events:
    d_t = get_eval_date(e)
    event_dt_regime.append(detect_v6(d_t or ""))

# v0.6 旧 boost (用 D_t)
def boost_old(c, regime):
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

# v0.7 新 boost (用 D-1, 基于真实反转率)
# 数据: kc 0%, sh 15%, sz 42%, all_green 58%, all_red 58%, normal 50%, 整体 53%
def boost_dm1(c, regime):
    lbc = c.get("d0_lbc", 1) or 1
    # 基于 D-1 实际反转率
    base_boost_map = {
        "kc_only_red": -0.50,      # 反转 0%, 直接彻底降权
        "sh_only_red": -0.30,      # 15%
        "sz_only_red": -0.10,      # 42% (低于平均)
        "spread_high_up": -0.30,   # 类似 kc_only
        "all_red_strong": +0.03,   # 58%
        "all_green_strong": +0.04, # 58% (跟 all_red 一样!)
        "all_red_weak": 0,
        "all_green_weak": -0.05,
        "normal": -0.02,           # 50%
    }
    base = base_boost_map.get(regime, 0)
    # lbc 越高在危险 regime 内越压
    if regime in ("kc_only_red", "sh_only_red", "spread_high_up"):
        if lbc >= 3: base -= 0.10
        elif lbc >= 2: base -= 0.05
    return base

# CV 测
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

def topn(scores, ys, n):
    paired = sorted(zip(scores, ys), reverse=True)[:n]
    return sum(y for _, y in paired)/max(1,len(paired))

random.seed(42)
N = len(events)
n_trials = 200
deltas_old = []   # 旧 D_t boost
deltas_new = []   # 新 D-1 boost
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
    p_old = [max(0, min(1, p + boost_old(events[j], event_dt_regime[j]))) for j, p in zip(test_idx, p_o)]
    p_new = [max(0, min(1, p + boost_dm1(events[j], event_dm1_regime[j]))) for j, p in zip(test_idx, p_o)]
    deltas_old.append(auc(p_old, yv) - auc(p_o, yv))
    deltas_new.append(auc(p_new, yv) - auc(p_o, yv))
    if (trial+1) % 50 == 0:
        print(f"  trial {trial+1}/{n_trials}, 用时 {time.time()-t0:.0f}s", flush=True)

def percentile(lst, p):
    s = sorted(lst); return s[int(len(s)*p)]

print(f"\n📊 v0.6 旧 boost (D_t regime, 信息泄漏):")
print(f"  平均 ΔAUC: {sum(deltas_old)/len(deltas_old):+.4f}")
print(f"  5%~95%: [{percentile(deltas_old, 0.05):+.4f}, {percentile(deltas_old, 0.95):+.4f}]")
print(f"  正向: {sum(1 for d in deltas_old if d>0)}/{len(deltas_old)}")

print(f"\n📊 v0.7 新 boost (D-1 regime, 真实可推):")
print(f"  平均 ΔAUC: {sum(deltas_new)/len(deltas_new):+.4f}")
print(f"  5%~95%: [{percentile(deltas_new, 0.05):+.4f}, {percentile(deltas_new, 0.95):+.4f}]")
print(f"  正向: {sum(1 for d in deltas_new if d>0)}/{len(deltas_new)}")
