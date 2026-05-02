#!/usr/bin/env python3
"""v1.8 训练: 用 v1.7 的 57 维 + 新增 12 维 9:25 集合竞价 = 69 维
- LR + GBDT 集成 (lr_weight=0.6, gbdt_weight=0.4 跟 v14 一样)
- 时序 OOS: 训练集用前 80%, OOS 用后 20%
- 严格防泄漏: 所有特征都是 D_t 9:25 之前的, label 是 outcome (reversal/failed)
"""
import json, math, random
from pathlib import Path
import collections

random.seed(42)

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
SRC = WS / 'backtest' / 'v18_events_enriched.json'
OUT_MODEL = WS / 'picks' / 'lr_v18_ensemble_model.json'
OUT_REPORT = WS / 'backtest' / 'reversal-v18-train-2026-05-02.md'


# ============ 特征工程 ============
# v1.7 已有的 d0 / pre10 / cb / pm 特征 (从 events 字段取)
# v1.8 新增 9:25 集合竞价 12 维

# v1.7 实际可用特征 (删除泄漏字段):
# 泄漏字段 (窗口长度依赖 outcome): days_between, callback_pct, min_close_pct,
# broke_ma5, broke_ma10, vol_callback_ratio
V17_FEATURES = [
    'd0_chg', 'd0_vol', 'd0_lbc', 'd0_main_flow', 'pre_d0_5d_main_avg',
    # cb1/cb3/cb5: 固定窗口 D0+1/3/5 主力资金 (SAFE)
    'cb1_main_avg', 'cb3_main_avg', 'cb5_main_avg', 'cb5_in_ratio',
    # pre10_*: D0 之前 10 天 (SAFE)
    'pre10_n', 'pre10_days_in', 'pre10_in_ratio', 'pre10_max_streak',
    'pre10_main_total', 'pre10_main_avg', 'pre10_strong_days',
]

V18_NEW_FEATURES = [
    'auc_buy', 'auc_sell', 'auc_diff', 'auc_ratio',
    'auc_match_close', 'auc_amt', 'auc_vol', 'auc_turn',
    'auc_chg', 'auc_amp',
    'auc_buy_to_float', 'auc_sell_to_float', 'auc_amt_to_mcap',
    'auc_strong_open', 'auc_zt_open',
]

ALL_FEATURES = V17_FEATURES + V18_NEW_FEATURES


def safe_float(x, default=0.0):
    if x is None: return default
    try: return float(x)
    except (TypeError, ValueError): return default


def build_x(e):
    """从 event 提取 X 向量"""
    x = []
    for f in V17_FEATURES:
        x.append(safe_float(e.get(f)))
    for f in V18_NEW_FEATURES:
        v = e.get(f)
        x.append(safe_float(v))
    return x


def build_y(e):
    return 1 if e['outcome'] == 'reversal' else 0


def standardize(X, mu=None, sigma=None):
    if mu is None:
        n = len(X); m = len(X[0])
        mu = [sum(row[j] for row in X)/n for j in range(m)]
        sigma = []
        for j in range(m):
            v = sum((row[j]-mu[j])**2 for row in X)/n
            sigma.append(math.sqrt(v) if v > 0 else 1.0)
    Xn = [[(row[j]-mu[j])/sigma[j] for j in range(len(row))] for row in X]
    return Xn, mu, sigma


def lr_train(X, y, lr=0.01, epochs=300, l2=0.01):
    """简单逻辑回归 (gradient descent)"""
    n = len(X); m = len(X[0])
    w = [0.0]*m; b = 0.0
    for ep in range(epochs):
        # forward
        z = [sum(X[i][j]*w[j] for j in range(m)) + b for i in range(n)]
        p = [1/(1+math.exp(-min(max(zz,-30),30))) for zz in z]
        # gradient
        dw = [0.0]*m; db = 0.0
        for i in range(n):
            err = p[i] - y[i]
            for j in range(m):
                dw[j] += err * X[i][j]
            db += err
        for j in range(m):
            dw[j] = dw[j]/n + l2*w[j]
            w[j] -= lr*dw[j]
        b -= lr*db/n
    return w, b


def lr_predict(X, w, b):
    return [1/(1+math.exp(-min(max(sum(row[j]*w[j] for j in range(len(row)))+b, -30), 30))) for row in X]


# ============ GBDT (简单实现, 借鉴 v14) ============

class TreeNode:
    __slots__ = ['feat', 'thr', 'left', 'right', 'val']
    def __init__(self):
        self.feat = None; self.thr = None; self.left = None; self.right = None; self.val = None


def fit_tree(X, residuals, max_depth=5, min_samples=20):
    """单棵回归树, 拟合 residuals"""
    def build(idx, depth):
        node = TreeNode()
        if depth >= max_depth or len(idx) < min_samples:
            node.val = sum(residuals[i] for i in idx) / len(idx) if idx else 0
            return node
        # 找最佳分裂
        best_gain = 0; best_feat = None; best_thr = None
        n_features = len(X[0])
        # 抽 sqrt 个特征
        feat_pool = random.sample(range(n_features), max(3, int(math.sqrt(n_features))))
        for f in feat_pool:
            vals = sorted(set(X[i][f] for i in idx))
            if len(vals) < 2: continue
            for k in range(0, len(vals)-1, max(1, len(vals)//10)):
                thr = (vals[k] + vals[k+1]) / 2
                left_idx = [i for i in idx if X[i][f] <= thr]
                right_idx = [i for i in idx if X[i][f] > thr]
                if len(left_idx) < min_samples or len(right_idx) < min_samples: continue
                # gain (variance reduction)
                m_l = sum(residuals[i] for i in left_idx) / len(left_idx)
                m_r = sum(residuals[i] for i in right_idx) / len(right_idx)
                m_all = sum(residuals[i] for i in idx) / len(idx)
                gain = (sum((residuals[i]-m_all)**2 for i in idx)
                        - sum((residuals[i]-m_l)**2 for i in left_idx)
                        - sum((residuals[i]-m_r)**2 for i in right_idx))
                if gain > best_gain:
                    best_gain = gain; best_feat = f; best_thr = thr
        if best_feat is None:
            node.val = sum(residuals[i] for i in idx) / len(idx) if idx else 0
            return node
        node.feat = best_feat; node.thr = best_thr
        left_idx = [i for i in idx if X[i][best_feat] <= best_thr]
        right_idx = [i for i in idx if X[i][best_feat] > best_thr]
        node.left = build(left_idx, depth+1)
        node.right = build(right_idx, depth+1)
        return node
    return build(list(range(len(X))), 0)


def tree_predict_one(node, x):
    while node.val is None:
        if x[node.feat] <= node.thr: node = node.left
        else: node = node.right
    return node.val


def tree_to_dict(node):
    if node.val is not None:
        return {'val': node.val}
    return {'feat': node.feat, 'thr': node.thr,
            'left': tree_to_dict(node.left), 'right': tree_to_dict(node.right)}


def gbdt_train(X, y, n_trees=30, lr=0.05, max_depth=5):
    """简单 GBDT (logistic gradient)"""
    n = len(X)
    # 初始化: log(p/(1-p)) = log(p_pos/p_neg)
    p_pos = sum(y) / n
    p_neg = 1 - p_pos
    init = math.log(p_pos / p_neg) if p_pos > 0 and p_neg > 0 else 0
    F = [init] * n
    trees = []
    for t in range(n_trees):
        # 残差 (logistic)
        p = [1/(1+math.exp(-min(max(f,-30),30))) for f in F]
        residuals = [y[i] - p[i] for i in range(n)]
        tree = fit_tree(X, residuals, max_depth=max_depth)
        for i in range(n):
            F[i] += lr * tree_predict_one(tree, X[i])
        trees.append(tree)
    return init, lr, trees


def gbdt_predict(X, init, lr, trees):
    F = [init] * len(X)
    for tree in trees:
        for i, x in enumerate(X):
            F[i] += lr * tree_predict_one(tree, x)
    return [1/(1+math.exp(-min(max(f,-30),30))) for f in F]


# ============ 评估 ============

def auc(y, p):
    """简单 AUC: trapezoidal"""
    pairs = sorted(zip(p, y), key=lambda x: -x[0])
    pos_total = sum(y)
    neg_total = len(y) - pos_total
    if pos_total == 0 or neg_total == 0: return 0.5
    cum_pos = 0; auc_sum = 0
    for pp, yy in pairs:
        if yy == 1: cum_pos += 1
        else: auc_sum += cum_pos
    return auc_sum / (pos_total * neg_total)


def topk_hit(y, p, k=20):
    pairs = sorted(zip(p, y), key=lambda x: -x[0])
    top = pairs[:k]
    return sum(yy for _, yy in top) / max(1, len(top))


# ============ 主 ============

def main():
    print('📥 加载 enriched events...', flush=True)
    with open(SRC) as f:
        data = json.load(f)
    events = data['events']
    
    # 只保留有 9:25 数据的 (1470 件)
    enriched = [e for e in events if e.get('auc_buy') is not None]
    print(f'  enriched events: {len(enriched)}')
    
    # 按 d_t_strict 排序 (时序 OOS)
    enriched.sort(key=lambda e: e.get('d_t_strict', '0'))
    
    # 构建 X / y
    X = [build_x(e) for e in enriched]
    y = [build_y(e) for e in enriched]
    n_pos = sum(y); n_neg = len(y) - n_pos
    print(f'  positive (reversal): {n_pos}, negative (failed): {n_neg}')
    
    # 时序 OOS: 前 80% 训练, 后 20% OOS
    split = int(len(X) * 0.8)
    X_tr, y_tr = X[:split], y[:split]
    X_oos, y_oos = X[split:], y[split:]
    print(f'  训练: {len(X_tr)} (pos={sum(y_tr)}), OOS: {len(X_oos)} (pos={sum(y_oos)})')
    
    # 标准化
    X_tr_n, mu, sigma = standardize(X_tr)
    X_oos_n = [[(row[j]-mu[j])/sigma[j] for j in range(len(row))] for row in X_oos]
    
    # 训 LR
    print('\n🔧 训 LR...', flush=True)
    w, b = lr_train(X_tr_n, y_tr, lr=0.01, epochs=300, l2=0.01)
    p_tr_lr = lr_predict(X_tr_n, w, b)
    p_oos_lr = lr_predict(X_oos_n, w, b)
    auc_lr_tr = auc(y_tr, p_tr_lr)
    auc_lr_oos = auc(y_oos, p_oos_lr)
    print(f'  LR AUC: 训练 {auc_lr_tr:.4f}, OOS {auc_lr_oos:.4f}')
    
    # 训 GBDT
    print('\n🔧 训 GBDT (30 棵, depth=5)...', flush=True)
    init, glr, trees = gbdt_train(X_tr_n, y_tr, n_trees=30, lr=0.05, max_depth=5)
    p_tr_gb = gbdt_predict(X_tr_n, init, glr, trees)
    p_oos_gb = gbdt_predict(X_oos_n, init, glr, trees)
    auc_gb_tr = auc(y_tr, p_tr_gb)
    auc_gb_oos = auc(y_oos, p_oos_gb)
    print(f'  GBDT AUC: 训练 {auc_gb_tr:.4f}, OOS {auc_gb_oos:.4f}')
    
    # 集成: 0.6 LR + 0.4 GBDT
    lr_w = 0.6; gb_w = 0.4
    p_oos_ens = [lr_w*p_oos_lr[i] + gb_w*p_oos_gb[i] for i in range(len(p_oos_lr))]
    auc_ens_oos = auc(y_oos, p_oos_ens)
    
    print(f'\n🎯 集成 (0.6 LR + 0.4 GBDT) OOS AUC: {auc_ens_oos:.4f}')
    
    # Top K 命中率
    for k in [5, 10, 20, 30, 50]:
        h = topk_hit(y_oos, p_oos_ens, k=k)
        print(f'  Top {k:>3} 命中率: {h*100:.1f}%')
    
    # 阈值校准 (OOS)
    print('\n📊 OOS 阈值校准:')
    pairs_oos = sorted(zip(p_oos_ens, y_oos), key=lambda x: -x[0])
    thr_table = []
    for p_thr in [0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5]:
        sub = [yy for pp, yy in pairs_oos if pp >= p_thr]
        if sub:
            print(f'  P≥{p_thr}: n={len(sub)}, 命中率 {sum(sub)/len(sub)*100:.1f}%')
            thr_table.append({'p_thr': p_thr, 'n': len(sub), 'hit': sum(sub)/len(sub)})
    
    # 落档 model
    model = {
        'version': 'v1.8-ensemble-9:25',
        'features': ALL_FEATURES,
        'mu': mu, 'sigma': sigma,
        'lr_weights': w, 'lr_bias': b,
        'gbdt_init': init, 'gbdt_lr': glr,
        'gbdt_trees': [tree_to_dict(t) for t in trees],
        'lr_weight': lr_w, 'gbdt_weight': gb_w,
        'oos_auc': auc_ens_oos,
        'oos_threshold_table': thr_table,
        'oos_topk': {f'top{k}': topk_hit(y_oos, p_oos_ens, k=k) for k in [5,10,20,30,50]},
        'train_size': len(X_tr), 'oos_size': len(X_oos),
        'note': 'v1.8: v1.7 21 维 + 9:25 集合竞价 15 维 = 36 维, 时序 OOS, 严格防泄漏',
    }
    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MODEL, 'w') as f:
        json.dump(model, f, ensure_ascii=False)
    print(f'\n💾 model 落档: {OUT_MODEL}')


if __name__ == '__main__':
    main()
