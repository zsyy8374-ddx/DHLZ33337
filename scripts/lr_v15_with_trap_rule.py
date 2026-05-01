"""v1.5 = v1.1 LR + GBDT 学到的"高位陷阱" post-hoc penalty
- 触发条件 (取自 GBDT 拉低 Top 50 的共同特征):
  * lbc_num >= 3 (高连板)
  * vol_callback_ratio >= 5.0 (回调期超大量)
  * cb1_main_avg < -1.0 (D-1 主力大流出) OR cb3_main_avg < -0.3
- penalty: -0.20 (在原 LR 输出上 减)
- 目标: 用规则形式获得部分集成模型的优势, 不增加部署复杂度

也试:
- v1.5b: lbc>=3 + vol>=3 (放宽条件)
- v1.5c: 多档 penalty 按强度
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from reversal_lr_v4 import train_lr, predict, normalize
from lr_v11_with_recent_rev_rate import extract_v11
from mini_gbdt import auc

with open('/Users/openclaw/.openclaw/workspace-dengxian/backtest/reversal-events-2026-05-01-v8-enriched.json') as f:
    events = json.load(f)['events']

features = [extract_v11(e) for e in events]
labels = [1 if e['outcome'] == 'reversal' else 0 for e in events]
cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg",
             "d0_main_flow","pre_d0_5d_main_avg","lbc_num","vol_callback_ratio",
             "recent_5d_rev_rate","recent_10d_rev_rate","recent_20d_rev_rate"]


def trap_penalty_v1(f):
    """v1: 严格规则 (lbc>=3 + vol>=5 + (cb1<-1 或 cb3<-0.3))"""
    lbc = f.get('lbc_num', 1)
    vol = f.get('vol_callback_ratio', 0)
    cb1 = f.get('cb1_main_avg', 0)
    cb3 = f.get('cb3_main_avg', 0)
    if lbc >= 3 and vol >= 5.0 and (cb1 < -1.0 or cb3 < -0.3):
        return -0.20
    return 0.0


def trap_penalty_v2(f):
    """v2: 分档"""
    lbc = f.get('lbc_num', 1)
    vol = f.get('vol_callback_ratio', 0)
    cb1 = f.get('cb1_main_avg', 0)
    cb3 = f.get('cb3_main_avg', 0)
    cb_pct = f.get('callback_pct', 0)
    
    p = 0.0
    # 死陷阱: 高连板 + 巨量 + 资金流出
    if lbc >= 3 and vol >= 5.0 and (cb1 < -1.0 or cb3 < -0.3):
        p -= 0.20
    # 弱陷阱: 高连板 + 巨量 (没流出), 仍然要警惕
    elif lbc >= 4 and vol >= 3.0:
        p -= 0.10
    # 高位 + 回调过深 + 资金流出
    elif lbc >= 3 and cb_pct >= 15 and cb1 < -0.5:
        p -= 0.10
    return p


def trap_penalty_v3(f):
    """v3: 加强信号"""
    lbc = f.get('lbc_num', 1)
    vol = f.get('vol_callback_ratio', 0)
    cb1 = f.get('cb1_main_avg', 0)
    cb3 = f.get('cb3_main_avg', 0)
    cb_pct = f.get('callback_pct', 0)
    cb5 = f.get('cb5_main_avg', 0)
    
    p = 0.0
    # 死陷阱: 高连板 + 巨量 + 资金流出
    if lbc >= 3 and vol >= 5.0 and (cb1 < -1.0 or cb3 < -0.3):
        p -= 0.20
    # 弱陷阱
    elif lbc >= 4 and vol >= 3.0:
        p -= 0.10
    elif lbc >= 3 and cb_pct >= 15 and cb1 < -0.5:
        p -= 0.10
    
    # 加强 信号 (GBDT 推高 Top 也是 cb1>3.7 但反转率才 46% — 不能全推高, 谨慎处理)
    # 但其实, GBDT 推高反转率 46% 说明这是个弱正信号, 不加分
    return p


# 滚动 OOS 测试
def auc_local(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)


months = sorted(set(e['d0_date'][:7] for e in events))
results = {name: {"auc": [], "t20": [], "high_hit": [], "high_n": []} 
           for name in ["v1.1 (基线)", "v1.5a (严格)", "v1.5b (分档)"]}

for m in months[6:]:
    tr_i = [i for i, e in enumerate(events) if e['d0_date'][:7] < m]
    te_i = [i for i, e in enumerate(events) if e['d0_date'][:7] == m]
    if len(tr_i) < 100 or len(te_i) < 30: continue
    
    Xtr_r = [features[i] for i in tr_i]
    y_tr = [labels[i] for i in tr_i]
    Xte_r = [features[i] for i in te_i]
    y_te = [labels[i] for i in te_i]
    
    Xtr_n, mu_m, sd_m = normalize(Xtr_r, cont_keys)
    w_m, b_m = train_lr(Xtr_n, y_tr, lr=0.1, iters=300, l2=0.01)
    Xte_n = [{k: ((v-mu_m[k])/sd_m[k] if k in cont_keys else v) for k,v in f.items()} for f in Xte_r]
    p_lr_base = predict(Xte_n, w_m, b_m)
    
    # 应用 trap penalty (基于 raw features, 不是 normalized)
    p_v1 = [max(0.001, min(0.999, p + trap_penalty_v1(Xte_r[k]))) for k, p in enumerate(p_lr_base)]
    p_v2 = [max(0.001, min(0.999, p + trap_penalty_v2(Xte_r[k]))) for k, p in enumerate(p_lr_base)]
    
    for name, pval in [("v1.1 (基线)", p_lr_base), ("v1.5a (严格)", p_v1), ("v1.5b (分档)", p_v2)]:
        paired = sorted(zip(pval, y_te), reverse=True)
        results[name]["auc"].append(auc_local(pval, y_te))
        results[name]["t20"].append(sum(y for _,y in paired[:20]) / min(20, len(paired)))
        nh = sum(1 for x,_ in paired if x>=0.7)
        hh = sum(y for x,y in paired if x>=0.7) / max(1, nh)
        results[name]["high_hit"].append(hh)
        results[name]["high_n"].append(nh)

print("=== 滚动 OOS 平均 ===")
for name, s in results.items():
    if not s["auc"]: continue
    print(f"  {name:18}  AUC={sum(s['auc'])/len(s['auc']):.3f}  T20={sum(s['t20'])/len(s['t20'])*100:.1f}%  P>=0.7命中={sum(s['high_hit'])/len(s['high_hit'])*100:.1f}%  n={sum(s['high_n'])/len(s['high_n']):.1f}")

# 看下 trap_v1 触发了多少
trap_count = sum(1 for f in features if trap_penalty_v1(f) < 0)
trap_revs = sum(labels[i] for i, f in enumerate(features) if trap_penalty_v1(f) < 0)
print(f"\n  trap_v1 触发: {trap_count} 个事件 ({trap_count/len(features)*100:.1f}%)")
print(f"  其中反转: {trap_revs}, 反转率 {trap_revs/max(1,trap_count)*100:.1f}% (vs 全样本 36.8%)")

trap_count2 = sum(1 for f in features if trap_penalty_v2(f) < 0)
trap_revs2 = sum(labels[i] for i, f in enumerate(features) if trap_penalty_v2(f) < 0)
print(f"\n  trap_v2 触发: {trap_count2} 个事件 ({trap_count2/len(features)*100:.1f}%)")
print(f"  其中反转: {trap_revs2}, 反转率 {trap_revs2/max(1,trap_count2)*100:.1f}%")
