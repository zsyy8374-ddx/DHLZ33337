#!/usr/bin/env python3
"""V2.1 概念强度因子: 用 D-1 板块涨幅作为新特征

逻辑:
  1. 给每只股票打概念标签 (静态, 从 concepts_data.json)
  2. 对 events 的每个 D_t 日:
     a. 找到 D_t-1 当天市场所有票的涨幅 (从 v12 raw 或腾讯)
     b. 算每个概念的"D_t-1 平均涨幅"
     c. 取该股所属概念中 D_t-1 平均涨幅最强的 Top3 平均
  3. 跟 outcome 看相关性

简化版: 先看 4-30 这天, 4-29 哪些概念最强, 跟 4-30 涨停的关系
"""
import json
import collections
import urllib.request, time
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WS / 'backtest' / 'concepts_data.json') as f:
    concepts = json.load(f)

with open(WS / 'backtest' / 'v18_test_4_30_real.json') as f:
    results_4_30 = json.load(f)['results']

# 给每个 4-29 v1.4 候选股加概念
for r in results_4_30:
    info = concepts.get(r['code'], {})
    r['concepts'] = info.get('concepts', [])
    r['industry'] = info.get('industry', '').split('-')[0] if info.get('industry') else ''

# 4-30 涨停 18 只的概念集合
zt_concept_count = collections.Counter()
for r in results_4_30:
    if r['is_zt']:
        for c in r['concepts']:
            zt_concept_count[c] += 1

# 候选 332 只的概念分布
all_concept_count = collections.Counter()
for r in results_4_30:
    for c in r['concepts']:
        all_concept_count[c] += 1

print('=== 4-30 涨停 18 只 vs 候选 332 只 概念分布对比 ===')
print(f'{"概念":20} | 涨停占比 | 候选占比 | lift')
print('-'*60)
ranked = []
for c, zt_n in zt_concept_count.most_common(50):
    all_n = all_concept_count.get(c, 0)
    if all_n < 3: continue  # 噪音, 至少 3 只候选
    zt_rate = zt_n / 18
    pop_rate = all_n / 332
    lift = zt_rate / max(0.001, pop_rate)
    ranked.append((c, zt_n, all_n, lift))

ranked.sort(key=lambda x: -x[3])
for c, zt_n, all_n, lift in ranked[:30]:
    print(f'{c:20} | {zt_n}/18 ({zt_n/18*100:.0f}%) | {all_n}/332 ({all_n/332*100:.0f}%) | lift {lift:.2f}')

# 实验: 选"高 lift" 概念集 (lift ≥ 2)
HOT = {c for c, _, _, lift in ranked if lift >= 2.0}
print(f'\n🔥 强势概念 (lift≥2): {sorted(HOT)[:15]}...')

# 给每只候选打"hot_concept_count"
for r in results_4_30:
    r['hot_concept_n'] = sum(1 for c in r['concepts'] if c in HOT)

# 测试: hot_concept_n 对涨停的预测力
print('\n=== hot_concept_n 分布 ===')
zt_hot_dist = collections.Counter(r['hot_concept_n'] for r in results_4_30 if r['is_zt'])
no_zt_hot_dist = collections.Counter(r['hot_concept_n'] for r in results_4_30 if not r['is_zt'])
for n in sorted(set(list(zt_hot_dist.keys())+list(no_zt_hot_dist.keys()))):
    zt = zt_hot_dist.get(n, 0); no = no_zt_hot_dist.get(n, 0)
    print(f'  hot_n={n}: 涨停 {zt}, 没涨停 {no}, 涨停率 {zt/max(1,zt+no)*100:.1f}%')

# 阈值
print('\n=== hot_concept_n ≥ N 的命中率 ===')
for thr in [1, 2, 3, 4, 5]:
    sub = [r for r in results_4_30 if r['hot_concept_n'] >= thr]
    zt = sum(1 for r in sub if r['is_zt'])
    if sub:
        print(f'  hot ≥ {thr}: n={len(sub)}, 涨停 {zt} ({zt/len(sub)*100:.1f}%)')

# 跟 v1.8 结合
print('\n=== v1.8 + hot_concept 联动 ===')
combos = [
    (0.7, 1, 'P≥0.7 + hot≥1'),
    (0.7, 2, 'P≥0.7 + hot≥2'),
    (0.65, 2, 'P≥0.65 + hot≥2'),
    (0.6, 3, 'P≥0.6 + hot≥3'),
    (0.5, 3, 'P≥0.5 + hot≥3'),
    (0.5, 4, 'P≥0.5 + hot≥4'),
    (0.4, 5, 'P≥0.4 + hot≥5'),
]
for p_thr, h_thr, label in combos:
    sub = [r for r in results_4_30 if r.get('p_v18', 0) >= p_thr and r['hot_concept_n'] >= h_thr]
    zt = sum(1 for r in sub if r['is_zt'])
    if sub:
        print(f'  {label}: n={len(sub)}, 涨停 {zt} ({zt/len(sub)*100:.0f}%)')

# v1.8 排序加权重
print('\n=== v1.8 + 0.05 * hot_n 重排 Top 20 ===')
results_4_30.sort(key=lambda x: -(x.get('p_v18', 0) + 0.04 * x['hot_concept_n']))
for i, r in enumerate(results_4_30[:20], 1):
    zt = '✅' if r['is_zt'] else '❌'
    print(f'  {i:>2}. {r["code"]} {r["name"][:8]:8} P={r["p_v18"]:.3f} hot={r["hot_concept_n"]:>2} {zt}')

# 落档
out = WS / 'backtest' / 'v21_concept_test.json'
with open(out, 'w') as f:
    json.dump({'hot_concepts': sorted(HOT), 'results': results_4_30}, f, ensure_ascii=False, indent=2)
print(f'\n💾 落档: {out}')
