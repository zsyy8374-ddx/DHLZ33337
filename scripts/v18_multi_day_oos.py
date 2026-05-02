#!/usr/bin/env python3
"""v1.8 多日 OOS — 不只看 4-30 一天, 看 events 最后 N 天的稳定性"""
import json, pickle
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

with open(WS / 'picks' / 'v18_sklearn_model.pkl', 'rb') as f:
    m = pickle.load(f)
lr = m['lr']; gb = m['gb']; scaler = m['scaler']
features = m['features']

with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
    events = json.load(f)['events']

# 只看有 9:25 数据的 events
enriched = [e for e in events if e.get('auc_buy') is not None]
enriched.sort(key=lambda e: e.get('d_t_strict', '0'))

# 按 D_t 分组
by_dt = defaultdict(list)
for e in enriched:
    by_dt[e.get('d_t_strict', 'unknown')].append(e)

# 取最后 30 个不同的 D_t (按时间最新的)
unique_dts = sorted(by_dt.keys(), reverse=True)[:30]
unique_dts.reverse()  # 按时间正序展示

def safe_float(v, d=0.0):
    if v is None: return d
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return d
        return f
    except: return d

print(f'=== v1.8 最后 30 天 OOS 表现 ===\n')
print(f'{"日期":12} | n  | rev | Top10 | Top5 | P≥0.85')
print('-' * 65)

cumulative_top10 = []; cumulative_top5 = []; cumulative_p085 = []

for dt in unique_dts:
    day_events = by_dt[dt]
    if len(day_events) < 5: continue
    
    X = np.array([[safe_float(e.get(f)) for f in features] for e in day_events])
    y = np.array([1 if e['outcome']=='reversal' else 0 for e in day_events])
    
    X_n = scaler.transform(X)
    p_lr = lr.predict_proba(X_n)[:, 1]
    p_gb = gb.predict_proba(X_n)[:, 1]
    p_ens = 0.4 * p_lr + 0.6 * p_gb
    
    n = len(y); rev = int(y.sum())
    
    # Top K
    if n >= 10:
        idx10 = np.argsort(-p_ens)[:10]
        t10 = float(y[idx10].mean()) * 100
    else: t10 = None
    if n >= 5:
        idx5 = np.argsort(-p_ens)[:5]
        t5 = float(y[idx5].mean()) * 100
    else: t5 = None
    
    p085_mask = p_ens >= 0.85
    p085 = float(y[p085_mask].mean()) * 100 if p085_mask.sum() > 0 else None
    p085_n = int(p085_mask.sum())
    
    print(f'{dt:12} | {n:>2} | {rev:>3} | '
          f'{f"{t10:>4.0f}%" if t10 is not None else "N/A":>5} | '
          f'{f"{t5:>4.0f}%" if t5 is not None else "N/A":>4} | '
          f'{f"{p085:>3.0f}%({p085_n})" if p085 is not None else "N/A":>10}')
    
    if t10 is not None: cumulative_top10.append(t10)
    if t5 is not None: cumulative_top5.append(t5)
    if p085 is not None: cumulative_p085.append((p085, p085_n))

print(f'\n=== 30 天平均 ===')
if cumulative_top10:
    print(f'  Top 10 平均: {np.mean(cumulative_top10):.0f}% (std {np.std(cumulative_top10):.0f}%, max {max(cumulative_top10):.0f}, min {min(cumulative_top10):.0f})')
if cumulative_top5:
    print(f'  Top 5 平均: {np.mean(cumulative_top5):.0f}% (std {np.std(cumulative_top5):.0f}%)')
if cumulative_p085:
    avg_n = np.mean([n for _, n in cumulative_p085])
    avg_pct = np.mean([p for p, _ in cumulative_p085])
    print(f'  P≥0.85 平均: {avg_pct:.0f}% (avg n={avg_n:.1f} 只/天)')

# 这是 events 内 OOS, 但 events 已经被 训练时见过 80%
# 真正测试需要排除训练集
print(f'\n=== 严格 OOS (剔除训练 80%, 仅最后 20%) ===')
total_n = len(enriched)
split = int(total_n * 0.8)
oos_events = enriched[split:]
oos_dts = sorted(set(e.get('d_t_strict','x') for e in oos_events))
print(f'OOS 时间段: {oos_dts[0] if oos_dts else "?"} ~ {oos_dts[-1] if oos_dts else "?"}')
print(f'OOS 事件数: {len(oos_events)}, OOS 日期数: {len(oos_dts)}')

oos_top10 = []; oos_p085 = []
for dt in oos_dts:
    day_e = [e for e in oos_events if e.get('d_t_strict')==dt]
    if len(day_e) < 3: continue
    X = np.array([[safe_float(e.get(f)) for f in features] for e in day_e])
    y = np.array([1 if e['outcome']=='reversal' else 0 for e in day_e])
    X_n = scaler.transform(X)
    p_ens = 0.4*lr.predict_proba(X_n)[:,1] + 0.6*gb.predict_proba(X_n)[:,1]
    n = len(y)
    if n >= 10:
        oos_top10.append(float(y[np.argsort(-p_ens)[:10]].mean())*100)
    p085 = p_ens >= 0.85
    if p085.sum() > 0:
        oos_p085.append((float(y[p085].mean())*100, int(p085.sum())))

if oos_top10:
    print(f'  严格 OOS Top 10 平均: {np.mean(oos_top10):.0f}% (n_days={len(oos_top10)})')
if oos_p085:
    avg_pct = np.mean([p for p,_ in oos_p085])
    avg_n = np.mean([n for _,n in oos_p085])
    print(f'  严格 OOS P≥0.85 平均: {avg_pct:.0f}% (avg n={avg_n:.1f} 只/天, 共 {len(oos_p085)} 天有信号)')
