"""手写 mini-GBDT (gradient boosted decision trees, depth=3 ~ 5)
- 用 logistic loss
- 不依赖 xgboost/sklearn
- 速度: 200 棵树 × 3262 样本 × depth 3 ~ 几秒
"""
import math, random


def _split_score(idx, feat_vals_list, residuals, sorted_pairs, lambda_reg=1.0):
    """对一个特征找最佳切分: 最大化 (sum_l)^2/(n_l+λ) + (sum_r)^2/(n_r+λ)
    feat_vals_list: 已经只选了 idx 子集的 feat 值列表 (与 idx 同顺序)"""
    n_total = len(idx)
    if n_total < 4: return None
    total = sum(residuals[i] for i in idx)
    # sorted by feature value
    pairs = sorted([(feat_vals_list[k], residuals[idx[k]], idx[k]) for k in range(n_total)])
    
    best_gain = 0
    best_thr = None
    left_sum = 0
    left_n = 0
    parent_score = total*total/(n_total + lambda_reg)
    
    for k in range(n_total - 1):
        v, r, i = pairs[k]
        left_sum += r
        left_n += 1
        if pairs[k+1][0] == v: continue  # 同值不切
        right_sum = total - left_sum
        right_n = n_total - left_n
        if right_n < 2: continue
        gain = (left_sum*left_sum/(left_n+lambda_reg) + right_sum*right_sum/(right_n+lambda_reg)) - parent_score
        if gain > best_gain:
            best_gain = gain
            best_thr = (v + pairs[k+1][0]) / 2
    return best_thr, best_gain


def build_tree(idx, X, residuals, feat_names, depth, max_depth=3, lambda_reg=1.0, min_leaf=10):
    """递归建树, X 是 list of dict, residuals 是 list of float"""
    n = len(idx)
    if depth >= max_depth or n < 2*min_leaf:
        # leaf: 输出 sum / (n + λ)
        return ("leaf", sum(residuals[i] for i in idx) / (n + lambda_reg))
    
    best_feat = None; best_thr = None; best_gain = 0
    for f in feat_names:
        feat_vals_list = [X[i][f] for i in idx]
        out = _split_score(idx, feat_vals_list, residuals, None, lambda_reg)
        if out is None: continue
        thr, gain = out
        if thr is None: continue
        if gain > best_gain:
            best_gain = gain
            best_feat = f
            best_thr = thr
    
    if best_feat is None:
        return ("leaf", sum(residuals[i] for i in idx) / (n + lambda_reg))
    
    left_idx = [i for i in idx if X[i][best_feat] <= best_thr]
    right_idx = [i for i in idx if X[i][best_feat] > best_thr]
    if len(left_idx) < min_leaf or len(right_idx) < min_leaf:
        return ("leaf", sum(residuals[i] for i in idx) / (n + lambda_reg))
    
    left_tree = build_tree(left_idx, X, residuals, feat_names, depth+1, max_depth, lambda_reg, min_leaf)
    right_tree = build_tree(right_idx, X, residuals, feat_names, depth+1, max_depth, lambda_reg, min_leaf)
    return ("node", best_feat, best_thr, left_tree, right_tree)


def predict_tree(tree, x):
    if tree[0] == "leaf": return tree[1]
    _, feat, thr, left, right = tree
    if x[feat] <= thr: return predict_tree(left, x)
    return predict_tree(right, x)


def sigmoid(z):
    if z > 30: return 1.0
    if z < -30: return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def train_gbdt(X, y, feat_names, n_trees=100, max_depth=3, lr=0.1, lambda_reg=1.0, min_leaf=20, subsample=0.8, seed=42):
    """gradient boosted decision trees, logistic loss, leaf weights = sum_residual / (n+λ) * lr"""
    random.seed(seed)
    n = len(X)
    # 初始预测: log odds of base rate
    pos_rate = sum(y) / n
    base = math.log(pos_rate / (1 - pos_rate))
    pred = [base] * n  # 当前对每个样本的预测 (logit)
    trees = []
    for t in range(n_trees):
        # 残差: y - p
        residuals = [y[i] - sigmoid(pred[i]) for i in range(n)]
        # 子样本
        if subsample < 1.0:
            sub = random.sample(range(n), int(n * subsample))
        else:
            sub = list(range(n))
        tree = build_tree(sub, X, residuals, feat_names, 0, max_depth, lambda_reg, min_leaf)
        trees.append(tree)
        # 更新 pred
        for i in range(n):
            pred[i] += lr * predict_tree(tree, X[i])
    return base, trees, lr


def predict_gbdt(model, X):
    base, trees, lr = model
    preds = []
    for x in X:
        z = base
        for tree in trees:
            z += lr * predict_tree(tree, x)
        preds.append(sigmoid(z))
    return preds


def auc(scores, ys):
    paired = sorted(zip(scores, ys), reverse=True)
    pos = sum(ys); neg = len(ys)-pos
    if pos==0 or neg==0: return 0.5
    s = 0; tp = 0
    for _, y in paired:
        if y==1: tp += 1
        else: s += tp
    return s/(pos*neg)


if __name__ == "__main__":
    # 自测: 玩具数据
    random.seed(0)
    X = [{"a": random.random(), "b": random.random()} for _ in range(500)]
    y = [1 if (x["a"] + x["b"]) > 1.0 else 0 for x in X]
    model = train_gbdt(X, y, ["a", "b"], n_trees=30, max_depth=3, lr=0.3)
    preds = predict_gbdt(model, X)
    print("自测 AUC:", auc(preds, y))
    # 应该 > 0.95
