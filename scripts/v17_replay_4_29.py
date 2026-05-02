"""v1.7 在 4-29 推送上的 replay (用 4-30 早盘 + D0 涨停板特征)
- 4-29 推送 216 候选 → 4-30 实战 11 涨停
- v1.7 用 4-30 早盘的 pm + 4-29 当天的 d0zt 重排
- 看比 v1.4 多多少命中
"""
import json, sys, math
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from pathlib import Path
from reversal_lr_v4 import normalize, predict
from lr_v17_with_pm_d0zt import extract_v17
from mini_gbdt import predict_gbdt

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

# 加载 v1.7 模型
with open(WORKSPACE / 'picks' / 'lr_v17_ensemble_model.json') as f:
    model = json.load(f)
print(f"📦 模型: {model['version']}, AUC={model['ts_auc']}, P_high={model['P_high']}")

# 加载 4-29 推送 + 4-30 实战
with open(WORKSPACE / 'picks' / 'reversal_hits_full.jsonl') as f:
    for line in f:
        row = json.loads(line)
        if row.get('pick_date') == '2026-04-29':
            data = row; break

# 加载 v12 (含 pm + d0zt) 数据 — 但注意 v12 是按 (code, d0_date) 索引的, 4-29 推送的事件 d0 不一定在 v12
with open(WORKSPACE / 'backtest' / 'reversal-events-2026-05-01-v12-with-pm-d0zt.json') as f:
    v12_events = json.load(f)['events']
v12_by_key = {(e['code'], e['d0_date']): e for e in v12_events}

with open(WORKSPACE / 'picks' / 'reversal-v4-2026-04-29.json') as f:
    full = json.load(f)
cand_by_code = {c['code']: c for c in full['candidates']}

cont_keys = model['cont_keys']
mu = model['feature_means']; sd = model['feature_stds']
w = model['weights']; b = model['bias']
gbdt = model['gbdt']  # [base, trees, lr] but list


def predict_v17_lr(features):
    f_norm = {k:((v-mu[k])/sd[k] if k in cont_keys else v) for k,v in features.items()}
    z = b
    for k, v in f_norm.items(): z += w.get(k, 0) * v
    return 1 / (1 + math.exp(-z))


def predict_v17_gbdt(features):
    base, trees, lr = gbdt[0], gbdt[1], gbdt[2]
    z = base
    for tree in trees:
        # 走树
        node = tree
        while node[0] == 'node':
            _, feat, thr, lc, rc = node
            v = features.get(feat, 0)
            node = lc if v < thr else rc
        z += lr * node[1]  # leaf value
    return 1 / (1 + math.exp(-z))


def predict_v17(features):
    p_lr = predict_v17_lr(features)
    p_gb = predict_v17_gbdt(features)
    return 0.6 * p_lr + 0.4 * p_gb, p_lr, p_gb


# 给 4-29 推送的每个候选打 v1.7 分
recent_5d, recent_10d, recent_20d = 0.28, 0.39, 0.45

scored = []
for r in data['results']:
    cand = cand_by_code.get(r['code'])
    if not cand: continue
    # 构造事件: 用候选的基础特征 + 从 v12 找 pm + d0zt
    e = {
        'd0_chg': cand.get('d0_chg', 10), 'd0_lbc': cand.get('d0_lbc', 1),
        'callback_pct': cand.get('callback_pct', 0), 'min_close_pct': cand.get('min_close_pct', 0),
        'broke_ma5': cand.get('broke_ma5', False), 'broke_ma10': cand.get('broke_ma10', False),
        'vol_callback_ratio': cand.get('vol_callback_ratio', 0),
        'cb5_main_avg': cand.get('cb5_main_avg', 0), 'cb3_main_avg': cand.get('cb3_main_avg', 0),
        'cb1_main_avg': cand.get('cb1_main_avg', 0), 'cb5_in_ratio': cand.get('cb5_in_ratio', 0),
        'd0_main_flow': cand.get('d0_main_flow', 0), 'pre_d0_5d_main_avg': cand.get('pre_d0_5d_main_avg', 0),
        'd0_date': cand.get('d0_date', ''),
        'outcome': 'na'
    }
    # 从 v12 拿 pm + d0zt
    key = (r['code'], cand.get('d0_date', ''))
    if key in v12_by_key:
        v12 = v12_by_key[key]
        for k in ['pm_open_pct','pm_5m_high_pct','pm_5m_close_pct','pm_10m_high_pct','pm_5m_amt_yi','pm_strong_open','pm_weak_open','pm_open_red_5m']:
            if k in v12: e[k] = v12[k]
        for k in ['d0_zt_lock_pct','d0_zt_after_amt_yi','d0_zt_after_amt_pct','d0_zt_lock_strength','d0_strong_lock','d0_weak_lock','d0_unsealed']:
            if k in v12: e[k] = v12[k]
    
    f = extract_v17(e)
    f['recent_5d_rev_rate'] = recent_5d
    f['recent_10d_rev_rate'] = recent_10d
    f['recent_20d_rev_rate'] = recent_20d
    
    p_ens, p_lr, p_gb = predict_v17(f)
    
    scored.append({
        'code': r['code'],
        'name': r.get('name', ''),
        'p_v11': r['lr_prob'],  # v1.1 输出
        'p_v17': p_ens,
        'p_v17_lr': p_lr,
        'p_v17_gb': p_gb,
        'is_zt': r.get('is_zt', False),
        'today_chg': r.get('today_chg', 0),
        'today_high': r.get('today_high', 0),
        'has_pm': 'pm_open_pct' in e,
        'has_d0zt': 'd0_zt_lock_pct' in e,
        'pm_open_pct': e.get('pm_open_pct'),
        'pm_10m_high_pct': e.get('pm_10m_high_pct'),
    })

with_pm = sum(1 for s in scored if s['has_pm'])
print(f"\n📊 4-29 推送 {len(scored)} 只, 有 pm: {with_pm}, 4-30 涨停 {sum(1 for s in scored if s['is_zt'])}")

# 分档
P_high = model['P_high']  # 0.85
P_mid = model['P_mid']    # 0.7

scored.sort(key=lambda x: -x['p_v17'])

tier_a = [s for s in scored if s['p_v17'] >= P_high]
tier_b = [s for s in scored if P_mid <= s['p_v17'] < P_high]
tier_c = [s for s in scored if 0.55 <= s['p_v17'] < P_mid]

print(f"\n=== v1.7 分档 ===")
print(f"  极强 (P≥{P_high}): {len(tier_a)} 只, 涨停 {sum(1 for s in tier_a if s['is_zt'])}")
print(f"  强档 ({P_mid}~{P_high}): {len(tier_b)} 只, 涨停 {sum(1 for s in tier_b if s['is_zt'])}")
print(f"  关注 (0.55~{P_mid}): {len(tier_c)} 只, 涨停 {sum(1 for s in tier_c if s['is_zt'])}")

print(f"\n=== v1.7 极强档详情 ===")
for s in sorted(tier_a, key=lambda x: -x['p_v17']):
    flag = "✅" if s['is_zt'] else "❌"
    pm_info = f"pm_open={s.get('pm_open_pct',0):+.1f}% pm_10m_high={s.get('pm_10m_high_pct',0):+.1f}%" if s['has_pm'] else "无pm"
    print(f"  {s['code']} {s['name']:8s} v1.7={s['p_v17']:.3f} (LR={s['p_v17_lr']:.2f},GB={s['p_v17_gb']:.2f}) {flag} {s['today_chg']:+5.2f}% | {pm_info}")

print(f"\n=== v1.7 强档详情 (Top 15) ===")
for s in sorted(tier_b, key=lambda x: -x['p_v17'])[:15]:
    flag = "✅" if s['is_zt'] else "❌"
    pm_info = f"pm_open={s.get('pm_open_pct',0):+.1f}% pm_10m={s.get('pm_10m_high_pct',0):+.1f}%" if s['has_pm'] else "无pm"
    print(f"  {s['code']} {s['name']:8s} v1.7={s['p_v17']:.3f} {flag} {s['today_chg']:+5.2f}% | {pm_info}")

# Top N 分析
print(f"\n=== Top N 涨停 (vs v1.1) ===")
print(f"{'N':<6}{'v1.1 涨停':>12}{'v1.7 涨停':>12}{'v1.1 平均':>12}{'v1.7 平均':>12}")
v11_sorted = sorted(scored, key=lambda x: -x['p_v11'])
for n in [10, 20, 30, 50, 80]:
    v11 = v11_sorted[:n]
    v17 = scored[:n]
    v11_zt = sum(1 for s in v11 if s['is_zt'])
    v17_zt = sum(1 for s in v17 if s['is_zt'])
    v11_avg = sum(s['today_chg'] for s in v11) / max(1, len(v11))
    v17_avg = sum(s['today_chg'] for s in v17) / max(1, len(v17))
    print(f"  Top {n:<3}{v11_zt:>4}/{n:<3}{v17_zt:>4}/{n:<3}  {v11_avg:>+8.2f}%   {v17_avg:>+8.2f}%")

# 推送 P>=0.7 比较
v17_pushed = [s for s in scored if s['p_v17'] >= P_mid]
v11_pushed = [s for s in scored if s['p_v11'] >= 0.6]  # v1.1 阈值
print(f"\n=== 推送阈值对比 ===")
print(f"  v1.1 P≥0.6: 推送 {len(v11_pushed)} 只, 涨停 {sum(1 for s in v11_pushed if s['is_zt'])} ({sum(1 for s in v11_pushed if s['is_zt'])/max(1,len(v11_pushed))*100:.1f}%), 平均 {sum(s['today_chg'] for s in v11_pushed)/max(1,len(v11_pushed)):+.2f}%")
print(f"  v1.7 P≥0.7: 推送 {len(v17_pushed)} 只, 涨停 {sum(1 for s in v17_pushed if s['is_zt'])} ({sum(1 for s in v17_pushed if s['is_zt'])/max(1,len(v17_pushed))*100:.1f}%), 平均 {sum(s['today_chg'] for s in v17_pushed)/max(1,len(v17_pushed)):+.2f}%")
