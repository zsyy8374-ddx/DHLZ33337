"""任务 #2 改: 回填 4-25 和 4-23 的 picks 用于多日追踪
但回填需要重跑 reversal_picks_v4.py 全流程, 太耗时
更聪明: 直接从 v6 events 取 D0 = 4-23~4-29 的事件, 复算 LR P, 当成"模拟 picks"
然后用 4-30 实际涨跌看 D0+1 / D0+5 命中率"""
import json, sys
sys.path.insert(0, "/Users/openclaw/.openclaw/workspace-dengxian/scripts")
from reversal_lr_v4 import extract_v4, normalize, train_lr, predict
from urllib.request import urlopen, Request
from datetime import datetime, timedelta
import time

with open("/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-04-30-v6.json") as f:
    events = json.load(f)["events"]

# 模拟"如果在 D0+1 时给每个事件打分, 它在 D0+1 ~ D0+10 各天的命中率"
# 这是 v0.4 模型的"长窗口效用"测试

# 训练 LR 用 D0 ≤ 4-15 的事件 (避免泄漏)
labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
features = [extract_v4(e) for e in events]
cont_keys = ["callback_pct","min_close_pct","lbc_num","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg"]

# 用早期 70% 训练, 测试后期
sorted_events = sorted(enumerate(events), key=lambda x: x[1].get("d0_date", ""))
n = len(events)
train_idx = [i for i, _ in sorted_events[:int(n*0.7)]]
test_idx = [i for i, _ in sorted_events[int(n*0.7):]]

X_all, _, _ = normalize(features, cont_keys)
Xtr = [X_all[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
Xte = [X_all[i] for i in test_idx]; yte = [labels[i] for i in test_idx]

w, b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
test_preds = predict(Xte, w, b)

# 给 test 事件加 P
for i, idx in enumerate(test_idx):
    events[idx]["lr_p_simulated"] = test_preds[i]

# 看 D0 距 4-30 的天数对应的命中
test_events = [events[i] for i in test_idx]
test_events.sort(key=lambda x: -x.get("lr_p_simulated", 0))

# D0 距 4-30 天数分箱
end = datetime(2026, 4, 30)
print("\n📊 v0.4 模拟 picks 在不同 D0 距今天数的 outcome:")
print(f"{'D0 距今':<10} {'n':>6} {'Top 30 命中':>14} {'整体命中':>10}")
print("-" * 50)
from collections import defaultdict
bins = defaultdict(list)
for e in test_events:
    d0 = e.get("d0_date")
    if not d0: continue
    days = (end - datetime.strptime(d0, "%Y-%m-%d")).days
    bins[days].append(e)

for days in sorted(bins.keys()):
    sub = bins[days]
    sub.sort(key=lambda x: -x.get("lr_p_simulated", 0))
    n_total = len(sub)
    overall = sum(1 for e in sub if e["outcome"]=="reversal")/n_total if n_total > 0 else 0
    top30 = sub[:min(30, n_total)]
    t30 = sum(1 for e in top30 if e["outcome"]=="reversal")/len(top30) if top30 else 0
    print(f"  {days:>3} 天    {n_total:>6}  {t30*100:>10.1f}%   {overall*100:>8.1f}%")

# 对每个 D0 测看 d_t_after_d0 (如果命中) 分布
print(f"\n📊 d_t 距 D0 天数分布 (回马枪发生在 D0+几):")
gaps = []
for e in test_events:
    if e["outcome"] != "reversal": continue
    d0 = e.get("d0_date")
    dt = e.get("d_t_date")
    if d0 and dt:
        gap = (datetime.strptime(dt, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days
        gaps.append(gap)

if gaps:
    from collections import Counter
    cnt = Counter(gaps)
    for g in sorted(cnt.keys())[:15]:
        print(f"   D0+{g:>2}: {cnt[g]:>4} 次")
