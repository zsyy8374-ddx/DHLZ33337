"""用 v1.4 集成模型重新打分 4-29 推送, 对比 v1.1 在 4-30 实战的命中
- 加载 reversal_hits_full.jsonl 里的 results (216 只 P>=0.4 候选, 已含 4-30 实战)
- 用 v1.4 重新打分
- 比 v1.1 / v1.4 哪个 Top 20/50 涨停数 多
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from predict_v14 import load_v14_model, predict_v14
from lr_v11_with_recent_rev_rate import extract_v11
from reversal_lr_v10 import detect_v6, get_dminus1
from collections import defaultdict
from pathlib import Path

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

# 拉 4-29 推送的候选 + 4-30 实战
hits_path = WORKSPACE / 'picks' / 'reversal_hits_full.jsonl'
data = None
with open(hits_path) as f:
    for line in f:
        row = json.loads(line)
        if row.get('pick_date') == '2026-04-29':
            data = row; break

if not data:
    print("❌ 找不到 4-29 实战")
    sys.exit(1)
results = data['results']
print(f"✅ 4-29 推送: {len(results)} 候选, 4-30 涨停 {data['n_zt']}")

# 加载完整 candidates (才有 features)
with open(WORKSPACE / 'picks' / 'reversal-v4-2026-04-29.json') as f:
    full = json.load(f)
cand_by_code = {c['code']: c for c in full['candidates']}

# 拉 reversal-events-2026-05-01-v8-enriched 当作 base 算 recent_rev_rate
with open(WORKSPACE / 'backtest' / 'reversal-events-2026-05-01-v8-enriched.json') as f:
    hist_events = json.load(f)['events']

date_evs = defaultdict(list)
for e in hist_events:
    if e.get('d0_lbc', 1) == 1:
        date_evs[e['d0_date']].append(e)
all_dates_hist = sorted(date_evs.keys())
target_date = '2026-04-29'
prev_dates = [d for d in all_dates_hist if d < target_date]
def get_rate(n):
    sub = prev_dates[-n:]
    related = []
    for d in sub:
        related.extend(date_evs[d])
    if not related: return 0.5
    return sum(1 for e in related if e['outcome']=='reversal') / len(related)
recent_5d = get_rate(5)
recent_10d = get_rate(10)
recent_20d = get_rate(20)
print(f"   近期反转率: 5d={recent_5d*100:.0f}%, 10d={recent_10d*100:.0f}%, 20d={recent_20d*100:.0f}%")

# v1.4 模型
model_v14 = load_v14_model()

# 给每个 result 算 v1.4 P
v14_scored = []
for r in results:
    code = r['code']
    cand = cand_by_code.get(code)
    if not cand: continue
    # 把 cand 转成 event-like dict
    e_like = {
        'code': code,
        'd0_date': cand.get('d0_date', target_date),
        'd0_chg': cand.get('d0_chg', 10),
        'd0_lbc': cand.get('d0_lbc', 1),
        'callback_pct': cand.get('callback_pct', 0),
        'min_close_pct': cand.get('min_close_pct', 0),
        'broke_ma5': cand.get('broke_ma5', False),
        'broke_ma10': cand.get('broke_ma10', False),
        'vol_callback_ratio': cand.get('vol_callback_ratio', 0),
        'cb5_main_avg': cand.get('cb5_main_avg', 0),
        'cb3_main_avg': cand.get('cb3_main_avg', 0),
        'cb1_main_avg': cand.get('cb1_main_avg', 0),
        'cb5_in_ratio': cand.get('cb5_in_ratio', 0),
        'd0_main_flow': cand.get('d0_main_flow', 0),
        'pre_d0_5d_main_avg': cand.get('pre_d0_5d_main_avg', 0),
        'outcome': 'na'
    }
    f = extract_v11(e_like)
    # 注: extract_v11 调 detect_v6(d-1), 在 4-29 推送时只能用 4-28 regime, 这部分跟 picks_v4 处理一样
    # 把 recent_rev_rate 注入
    f['recent_5d_rev_rate'] = recent_5d
    f['recent_10d_rev_rate'] = recent_10d
    f['recent_20d_rev_rate'] = recent_20d
    
    # v1.4 预测
    p_ens, p_lr_v14, p_gb = predict_v14(f, model_v14)
    
    v14_scored.append({
        **r,
        'p_v14_ens': p_ens,
        'p_v14_lr': p_lr_v14,
        'p_v14_gb': p_gb,
    })

print(f"   重打分: {len(v14_scored)} 只\n")

# 按 v1.1 排序
sorted_v11 = sorted(v14_scored, key=lambda x: x['lr_prob'], reverse=True)
sorted_v14 = sorted(v14_scored, key=lambda x: x['p_v14_ens'], reverse=True)

# 比较 Top N
print("=== Top N 对比 (实战 4-30 涨停命中) ===")
print(f"{'N':<6}{'v1.1 涨停':<12}{'v1.4 涨停':<12}{'v1.1 平均涨幅':<16}{'v1.4 平均涨幅'}")
for n in [10, 20, 30, 50, 80]:
    if n > len(v14_scored): continue
    top11 = sorted_v11[:n]
    top14 = sorted_v14[:n]
    zt11 = sum(1 for r in top11 if r.get('is_zt'))
    zt14 = sum(1 for r in top14 if r.get('is_zt'))
    chg11 = sum(r.get('today_chg',0) for r in top11)/n
    chg14 = sum(r.get('today_chg',0) for r in top14)/n
    print(f"Top{n:<3} {zt11:>3} ({zt11/n*100:>4.1f}%)   {zt14:>3} ({zt14/n*100:>4.1f}%)   {chg11:+.2f}%       {chg14:+.2f}%")

# 看 v1.4 Top 20 是哪些, 跟 v1.1 Top 20 重叠多少
top_v11_codes = set(r['code'] for r in sorted_v11[:20])
top_v14_codes = set(r['code'] for r in sorted_v14[:20])
overlap = top_v11_codes & top_v14_codes
print(f"\nTop 20 重叠: {len(overlap)}/20")
print(f"v1.1 独有: {top_v11_codes - top_v14_codes}")
print(f"v1.4 独有: {top_v14_codes - top_v11_codes}")

# 看 v1.4 加进来 (替掉 v1.1) 的 票表现
print("\n=== v1.4 Top 20 中 v1.1 未选的票 ===")
print(f"{'代码':<8}{'名称':<10}{'v1.1':<8}{'v1.4':<8}{'今日涨幅':<10}{'是否涨停':<10}{'lbc':<4}{'cb%':<6}{'cb5亿':<8}")
for r in sorted_v14[:20]:
    if r['code'] in (top_v11_codes - top_v14_codes): continue  # 这是 v1.1 没选 v1.4 选的
    if r['code'] not in (top_v14_codes - top_v11_codes): continue
    cand = cand_by_code.get(r['code'], {})
    flag = "✅涨停" if r.get('is_zt') else f"{r.get('today_chg',0):+.1f}%"
    print(f"{r['code']:<8}{r.get('name','')[:8]:<10}{r['lr_prob']:<8.3f}{r['p_v14_ens']:<8.3f}{r.get('today_chg',0):+.2f}%   {flag:<10}{cand.get('d0_lbc','?'):<4}{cand.get('callback_pct',0):<6.1f}{cand.get('cb5_main_avg',0):<+8.2f}")
