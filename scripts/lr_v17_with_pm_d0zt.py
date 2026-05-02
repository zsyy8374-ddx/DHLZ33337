"""v1.7: v1.4 集成 + D_t 早盘特征 + D0 涨停板成交特征
基础: v1.1 LR + GBDT (集成)
增量:
  - pm_open_pct: D_t 开盘相对前收
  - pm_5m_high_pct: D_t 9:30-9:34 高点相对开盘
  - pm_5m_close_pct: D_t 9:30-9:34 收盘相对开盘
  - pm_10m_high_pct: D_t 0-10m 最高点相对开盘
  - pm_5m_amt_yi: D_t 早盘 5m 成交 (亿)
  - pm_strong_open: dummy
  - pm_weak_open: dummy
  - pm_open_red_5m: dummy
  - d0_zt_lock_pct: D0 封板时间占比
  - d0_zt_after_amt_yi: D0 封板后成交
  - d0_zt_after_amt_pct: 封板后成交占比
  - d0_zt_lock_strength: 锁定强度
  - d0_strong_lock: dummy
  - d0_weak_lock: dummy
  - d0_unsealed: dummy

数据: backtest/reversal-events-2026-05-01-v12-with-pm-d0zt.json (合并 v10 + v11)
"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11
from mini_gbdt import train_gbdt, predict_gbdt

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')


def extract_v17(e):
    f = extract_v11(e)
    
    # pm 早盘特征
    f['pm_open_pct'] = e.get('pm_open_pct', 0) or 0
    f['pm_5m_high_pct'] = e.get('pm_5m_high_pct', 0) or 0
    f['pm_5m_close_pct'] = e.get('pm_5m_close_pct', 0) or 0
    f['pm_10m_high_pct'] = e.get('pm_10m_high_pct', 0) or 0
    f['pm_5m_amt_yi'] = e.get('pm_5m_amt_yi', 0) or 0
    f['pm_strong_open'] = e.get('pm_strong_open', 0) or 0
    f['pm_weak_open'] = e.get('pm_weak_open', 0) or 0
    f['pm_open_red_5m'] = e.get('pm_open_red_5m', 0) or 0
    f['has_pm'] = 1.0 if 'pm_open_pct' in e else 0.0  # 标志位
    
    # D0 涨停板特征
    f['d0_zt_lock_pct'] = e.get('d0_zt_lock_pct', 0.5) or 0.5  # 默认中位数 (0.5 = 中午封)
    f['d0_zt_after_amt_yi'] = e.get('d0_zt_after_amt_yi', 0) or 0
    f['d0_zt_after_amt_pct'] = e.get('d0_zt_after_amt_pct', 0.1) or 0.1
    f['d0_zt_lock_strength'] = e.get('d0_zt_lock_strength', 0.5) or 0.5
    f['d0_strong_lock'] = e.get('d0_strong_lock', 0) or 0
    f['d0_weak_lock'] = e.get('d0_weak_lock', 0) or 0
    f['d0_unsealed'] = e.get('d0_unsealed', 0) or 0
    f['has_d0zt'] = 1.0 if 'd0_zt_lock_pct' in e else 0.0
    
    return f


def auc_local(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)


def main(events_file=None):
    """如果没指定, 用 v12 (合并); 退到 v11 / v10 / v9"""
    candidates = ['v12-with-pm-d0zt', 'v11-d0zt', 'v10-with-pm', 'v9-with-pre10']
    src = None
    for tag in candidates:
        if events_file and tag in events_file: 
            src = WORKSPACE / 'backtest' / f'reversal-events-2026-05-01-{tag}.json'
            if src.exists(): break
        cand = WORKSPACE / 'backtest' / f'reversal-events-2026-05-01-{tag}.json'
        if cand.exists():
            src = cand; break
    
    if not src:
        print(f"❌ 找不到数据"); return
    print(f"📂 加载: {src.name}")
    
    with open(src) as f:
        events = json.load(f)['events']
    
    features = [extract_v17(e) for e in events]
    labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
    feat_names = list(features[0].keys())
    print(f"📊 特征 {len(feat_names)} 维, 事件 {len(events)}")
    
    # 看 has_pm / has_d0zt 覆盖率
    n_pm = sum(1 for f in features if f.get('has_pm') == 1.0)
    n_d0zt = sum(1 for f in features if f.get('has_d0zt') == 1.0)
    print(f"   has_pm: {n_pm} ({n_pm/len(events)*100:.1f}%)")
    print(f"   has_d0zt: {n_d0zt} ({n_d0zt/len(events)*100:.1f}%)")
    
    # 单 pm 特征反转率分组
    print(f"\n=== pm_strong_open 反转率 (高开+强冲) ===")
    pm_strong_evs = [i for i, f in enumerate(features) if f.get('pm_strong_open') == 1.0]
    n = len(pm_strong_evs); rev = sum(labels[i] for i in pm_strong_evs)
    print(f"   触发 {n}, 反转率 {rev/max(1,n)*100:.1f}% (vs 36.8% 基线)")
    
    pm_weak_evs = [i for i, f in enumerate(features) if f.get('pm_weak_open') == 1.0]
    n = len(pm_weak_evs); rev = sum(labels[i] for i in pm_weak_evs)
    print(f"=== pm_weak_open 反转率 (低开): 触发 {n}, 反转率 {rev/max(1,n)*100:.1f}%")
    
    pm_red_evs = [i for i, f in enumerate(features) if f.get('pm_open_red_5m') == 1.0]
    n = len(pm_red_evs); rev = sum(labels[i] for i in pm_red_evs)
    print(f"=== pm_open_red_5m 反转率 (高开低走): 触发 {n}, 反转率 {rev/max(1,n)*100:.1f}%")
    
    # D0 zt 特征
    print(f"\n=== d0_strong_lock 反转率 (早盘封 + 锁紧): ===")
    sl_evs = [i for i, f in enumerate(features) if f.get('d0_strong_lock') == 1.0]
    n = len(sl_evs); rev = sum(labels[i] for i in sl_evs)
    print(f"   触发 {n}, 反转率 {rev/max(1,n)*100:.1f}%")
    
    wl_evs = [i for i, f in enumerate(features) if f.get('d0_weak_lock') == 1.0]
    n = len(wl_evs); rev = sum(labels[i] for i in wl_evs)
    print(f"=== d0_weak_lock 反转率 (尾盘封 / 不锁): 触发 {n}, 反转率 {rev/max(1,n)*100:.1f}%")
    
    un_evs = [i for i, f in enumerate(features) if f.get('d0_unsealed') == 1.0]
    n = len(un_evs); rev = sum(labels[i] for i in un_evs)
    print(f"=== d0_unsealed (没封住涨停): 触发 {n}, 反转率 {rev/max(1,n)*100:.1f}%")
    
    # 滚动 OOS
    cont_keys = [
        "callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
        "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
        "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate",
        "pm_open_pct","pm_5m_high_pct","pm_5m_close_pct","pm_10m_high_pct","pm_5m_amt_yi",
        "d0_zt_lock_pct","d0_zt_after_amt_yi","d0_zt_after_amt_pct","d0_zt_lock_strength",
    ]
    
    # 只用 has_pm AND has_d0zt 的事件做滚动 (因为这是有效数据)
    valid_idx = [i for i, f in enumerate(features) if f.get('has_pm') == 1.0 or f.get('has_d0zt') == 1.0]
    print(f"\n📌 有 pm 或 d0zt 的事件: {len(valid_idx)}")
    
    if len(valid_idx) < 200:
        print("数据不够, 等 enrich 完")
        return
    
    valid_events = [events[i] for i in valid_idx]
    valid_features = [features[i] for i in valid_idx]
    valid_labels = [labels[i] for i in valid_idx]
    
    months = sorted(set(e['d0_date'][:7] for e in valid_events))
    print(f"   月份: {months[0]} ~ {months[-1]}")
    
    stats = {n: {"auc": [], "t20": [], "h65_hit": [], "h65_n": [], "h7_hit": [], "h7_n": []}
             for n in ["v1.4 (40维)", "v1.7 LR单", "v1.7 GBDT单", "v1.7 集成"]}
    
    # v1.4 baseline 用 v11 features
    features_v11 = [extract_v11(e) for e in valid_events]
    
    for m in months[3:]:  # 只 4+ 个月够 train
        tr_i = [i for i, e in enumerate(valid_events) if e['d0_date'][:7] < m]
        te_i = [i for i, e in enumerate(valid_events) if e['d0_date'][:7] == m]
        if len(tr_i) < 100 or len(te_i) < 30: continue
        
        y_tr = [valid_labels[i] for i in tr_i]
        y_te = [valid_labels[i] for i in te_i]
        
        # v1.4 (v11 features 集成)
        Xtr_r4 = [features_v11[i] for i in tr_i]; Xte_r4 = [features_v11[i] for i in te_i]
        cont_v4 = [k for k in cont_keys if k in features_v11[0]]
        Xtr_n4, mu4, sd4 = normalize(Xtr_r4, cont_v4)
        w4, b4 = train_lr(Xtr_n4, y_tr, lr=0.1, iters=300, l2=0.01)
        Xte_n4 = [{k:((v-mu4[k])/sd4[k] if k in cont_v4 else v) for k,v in f.items()} for f in Xte_r4]
        p_lr4 = predict(Xte_n4, w4, b4)
        feat_v4 = list(features_v11[0].keys())
        gbdt4 = train_gbdt(Xtr_r4, y_tr, feat_v4, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
        p_gb4 = predict_gbdt(gbdt4, Xte_r4)
        p_v4 = [0.6*a + 0.4*b for a,b in zip(p_lr4, p_gb4)]
        
        # v1.7
        Xtr_r7 = [valid_features[i] for i in tr_i]; Xte_r7 = [valid_features[i] for i in te_i]
        Xtr_n7, mu7, sd7 = normalize(Xtr_r7, cont_keys)
        w7, b7 = train_lr(Xtr_n7, y_tr, lr=0.1, iters=300, l2=0.01)
        Xte_n7 = [{k:((v-mu7[k])/sd7[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r7]
        p_lr7 = predict(Xte_n7, w7, b7)
        gbdt7 = train_gbdt(Xtr_r7, y_tr, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42)
        p_gb7 = predict_gbdt(gbdt7, Xte_r7)
        p_v7 = [0.6*a + 0.4*b for a,b in zip(p_lr7, p_gb7)]
        
        for name, pval in [("v1.4 (40维)", p_v4), ("v1.7 LR单", p_lr7), ("v1.7 GBDT单", p_gb7), ("v1.7 集成", p_v7)]:
            paired = sorted(zip(pval, y_te), reverse=True)
            stats[name]["auc"].append(auc_local(pval, y_te))
            stats[name]["t20"].append(sum(y for _,y in paired[:20]) / min(20, len(paired)))
            for thr_key, thr in [("h65", 0.65), ("h7", 0.7)]:
                nh = sum(1 for x,_ in paired if x>=thr)
                hh = sum(y for x,y in paired if x>=thr) / max(1, nh)
                stats[name][thr_key+"_hit"].append(hh)
                stats[name][thr_key+"_n"].append(nh)
        
        print(f"  {m} n={len(te_i):>3}: v1.4 AUC={stats['v1.4 (40维)']['auc'][-1]:.3f} | v1.7 AUC={stats['v1.7 集成']['auc'][-1]:.3f}")
    
    print(f"\n=== 平均 ===")
    for name, s in stats.items():
        if not s["auc"]: continue
        print(f"  {name:20}  AUC={sum(s['auc'])/len(s['auc']):.3f}  T20={sum(s['t20'])/len(s['t20'])*100:.1f}%  P>=0.65 {sum(s['h65_hit'])/len(s['h65_hit'])*100:.1f}%/{sum(s['h65_n'])/len(s['h65_n']):.1f}  P>=0.7 {sum(s['h7_hit'])/len(s['h7_hit'])*100:.1f}%/{sum(s['h7_n'])/len(s['h7_n']):.1f}")
    
    # 看 v1.7 LR 学到的 pm/d0zt 权重
    print(f"\n=== v1.7 全量 LR 学到的新特征权重 ===")
    X_all, mu, sd = normalize(valid_features, cont_keys)
    w, b = train_lr(X_all, valid_labels, lr=0.1, iters=300, l2=0.01)
    for k in feat_names:
        if 'pm_' in k or 'd0_zt_' in k or 'd0_strong' in k or 'd0_weak' in k or 'd0_unsealed' in k:
            arrow = "↑" if w.get(k, 0) > 0 else "↓"
            print(f"  {k:30s}  {w.get(k, 0):+.4f}  {arrow}")


if __name__ == "__main__":
    main()
