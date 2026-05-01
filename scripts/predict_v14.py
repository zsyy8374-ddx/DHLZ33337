"""v1.4 集成模型预测器
- 加载 lr_v14_ensemble_model.json
- 预测: p_ens = 0.6 * p_lr + 0.4 * p_gbdt
- 接口兼容 reversal_picks_v4.py 的 predict_lr
"""
import json, math
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")


def sigmoid(z):
    if z > 30: return 1.0
    if z < -30: return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def load_v14_model(path=None):
    if path is None:
        path = WORKSPACE / "picks" / "lr_v14_ensemble_model.json"
    with open(path) as f:
        return json.load(f)


def _predict_tree(tree, x):
    if tree[0] == "leaf": return tree[1]
    _, feat, thr, left, right = tree
    v = x.get(feat, 0)
    if v <= thr: return _predict_tree(left, x)
    return _predict_tree(right, x)


def predict_v14(features, model):
    """features: dict (feature_name -> value)
    返回 集成概率"""
    # LR 部分
    cont_keys = model["lr_cont_keys"]
    mu = model["lr_feature_means"]
    sd = model["lr_feature_stds"]
    w = model["lr_weights"]
    b = model["lr_bias"]
    
    z = b
    for k in model["lr_features"]:
        v = features.get(k, 0) or 0
        if k in cont_keys:
            v = (v - mu.get(k, 0)) / max(sd.get(k, 1), 1e-9)
        z += w.get(k, 0) * v
    p_lr = sigmoid(z)
    
    # GBDT 部分
    base = model["gbdt_base"]
    lr_step = model["gbdt_lr"]
    trees = model["gbdt_trees"]
    
    z_gb = base
    for tree in trees:
        z_gb += lr_step * _predict_tree(tree, features)
    p_gb = sigmoid(z_gb)
    
    # 集成
    w_lr = model.get("lr_weight", 0.6)
    w_gb = model.get("gbdt_weight", 0.4)
    p_ens = w_lr * p_lr + w_gb * p_gb
    
    return p_ens, p_lr, p_gb


def predict_v14_simple(features, model):
    """只返回集成概率"""
    p_ens, _, _ = predict_v14(features, model)
    return p_ens


if __name__ == "__main__":
    # 自测: 装载并跑一个事件
    import sys
    sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
    from lr_v11_with_recent_rev_rate import extract_v11
    
    with open(WORKSPACE / "backtest" / "reversal-events-2026-05-01-v8-enriched.json") as f:
        events = json.load(f)["events"]
    
    model = load_v14_model()
    print(f"✅ 加载: {model['version']}, 集成 {model['lr_weight']} LR + {model['gbdt_weight']} GBDT")
    print(f"   特征: {len(model['lr_features'])} 维")
    print(f"   GBDT 树: {len(model['gbdt_trees'])} 棵")
    print(f"   阈值: P_high={model['P_high']}, P_mid={model['P_mid']}")
    
    # 测一个反转事件
    e = next(ev for ev in events if ev['outcome'] == 'reversal' and ev['d0_lbc'] == 2)
    f = extract_v11(e)
    p_ens, p_lr, p_gb = predict_v14(f, model)
    print(f"\n样例 (lbc=2 反转): {e['code']} D0={e['d0_date']}")
    print(f"  P_LR  = {p_lr:.4f}")
    print(f"  P_GBDT = {p_gb:.4f}")
    print(f"  P_ENS  = {p_ens:.4f}")
