#!/usr/bin/env python3
"""
backtest_v27.py — v2.7: Random Forest (纯 Python 实现)

目标: 看 RF 能否比 LR (AUC 0.64) 抓到 LR 漏的非线性组合
  - 例: "封单大 AND 盘子小 AND 早盘封" 这种交互效应, LR 是线性的, 抓不到
  - RF 可以自然处理交互特征

输入: backtest/v24-results-2026-04-28.json (与 LR 同样 786 样本)
输出: backtest/v27-rf-results-2026-04-28.{md,json}

实现策略:
  - 不依赖 sklearn (Mac Studio 红线)
  - 自己写 Decision Tree + Bagging
  - 100 棵树, 每棵随机抽 80% 样本 + sqrt(n_features) 特征
  - 用 Gini 不纯度
"""
import json, math, random, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
OUT_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))

random.seed(42)


# ─── 特征工程 (与 v2.5 LR 同步, 但加交互特征 & 不归一化) ───
def extract_features(s):
    ft = s["features"]
    in_lhb = 1.0 if s.get("in_lhb") else 0.0
    lbc = float(ft.get("lbc", 1))
    fbt = float(ft.get("fbt", 0))
    fund_yi = float(ft.get("fund_yi", 0))
    ltsz_yi = float(ft.get("ltsz_yi", 0))
    seal_pct = (fund_yi / ltsz_yi * 100) if ltsz_yi > 0 else 0.0
    hs = float(ft.get("hs", 0))
    zbc = float(ft.get("zbc", 0))
    vol_ratio = float(ft.get("vol_ratio", 1.0))
    sector_zt = float(ft.get("sector_zt", 1))
    market_strength = float(ft.get("market_strength", 1.0))
    is_yizi = 1.0 if ft.get("is_yizi") else 0.0
    
    return {
        # 原始连续 (RF 不需要归一化)
        "lbc": lbc,
        "fbt": fbt,
        "fund_yi": fund_yi,
        "ltsz_yi": ltsz_yi,
        "seal_pct": seal_pct,
        "hs": hs,
        "zbc": zbc,
        "vol_ratio": min(vol_ratio, 5.0),
        "sector_zt": sector_zt,
        "market_strength": market_strength,
        # 二值
        "in_lhb": in_lhb,
        "is_yizi": is_yizi,
    }


def load_v24_samples(path):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d["samples"]


# ─── Decision Tree (Gini) ───
class Node:
    __slots__ = ("feature", "threshold", "left", "right", "value")
    def __init__(self, feature=None, threshold=None, left=None, right=None, value=None):
        self.feature = feature      # 用哪个特征切
        self.threshold = threshold  # 切分阈值
        self.left = left
        self.right = right
        self.value = value          # 叶节点: P(y=1)


def gini(labels):
    n = len(labels)
    if n == 0: return 0.0
    p1 = sum(labels) / n
    return 1 - p1*p1 - (1-p1)*(1-p1)


def best_split(X, y, feat_subset):
    """找最佳切分: 遍历所有 (feature, threshold)"""
    best_gain = 0.0
    best_feat = None
    best_thr = None
    n = len(y)
    base_gini = gini(y)
    
    for f in feat_subset:
        vals = sorted(set(x[f] for x in X))
        if len(vals) <= 1: continue
        # 候选阈值: 用相邻值中点 (减少候选数)
        candidates = []
        for i in range(len(vals)-1):
            candidates.append((vals[i] + vals[i+1]) / 2)
        # 限制候选数 (大数据集太慢)
        if len(candidates) > 20:
            step = len(candidates) // 20
            candidates = candidates[::step]
        
        for thr in candidates:
            left_y = [y[i] for i in range(n) if X[i][f] <= thr]
            right_y = [y[i] for i in range(n) if X[i][f] > thr]
            if not left_y or not right_y: continue
            g_left = gini(left_y)
            g_right = gini(right_y)
            weighted = (len(left_y) * g_left + len(right_y) * g_right) / n
            gain = base_gini - weighted
            if gain > best_gain:
                best_gain = gain
                best_feat = f
                best_thr = thr
    
    return best_feat, best_thr, best_gain


def build_tree(X, y, feat_keys, max_depth=8, min_samples=10, depth=0, max_features=None):
    """递归建树"""
    n = len(y)
    if n < min_samples or depth >= max_depth or sum(y) == 0 or sum(y) == n:
        return Node(value=sum(y) / n if n > 0 else 0.5)
    
    # 随机选特征子集 (RF 关键: max_features = sqrt(总特征数))
    if max_features and max_features < len(feat_keys):
        feat_subset = random.sample(feat_keys, max_features)
    else:
        feat_subset = feat_keys
    
    best_feat, best_thr, gain = best_split(X, y, feat_subset)
    if best_feat is None or gain < 0.001:
        return Node(value=sum(y) / n)
    
    left_idx = [i for i in range(n) if X[i][best_feat] <= best_thr]
    right_idx = [i for i in range(n) if X[i][best_feat] > best_thr]
    
    left = build_tree([X[i] for i in left_idx], [y[i] for i in left_idx],
                     feat_keys, max_depth, min_samples, depth+1, max_features)
    right = build_tree([X[i] for i in right_idx], [y[i] for i in right_idx],
                      feat_keys, max_depth, min_samples, depth+1, max_features)
    
    return Node(feature=best_feat, threshold=best_thr, left=left, right=right)


def predict_tree(tree, x):
    if tree.value is not None:
        return tree.value
    if x[tree.feature] <= tree.threshold:
        return predict_tree(tree.left, x)
    return predict_tree(tree.right, x)


# ─── Random Forest ───
def train_rf(X, y, n_trees=80, max_depth=8, min_samples=10):
    feat_keys = list(X[0].keys())
    max_features = max(1, int(math.sqrt(len(feat_keys))))
    n = len(y)
    trees = []
    for t in range(n_trees):
        # bagging: 随机抽 80% 样本
        sample_size = int(n * 0.8)
        idx = [random.randint(0, n-1) for _ in range(sample_size)]
        X_sub = [X[i] for i in idx]
        y_sub = [y[i] for i in idx]
        tree = build_tree(X_sub, y_sub, feat_keys, max_depth, min_samples, 0, max_features)
        trees.append(tree)
        if (t+1) % 20 == 0:
            print(f"   树 [{t+1}/{n_trees}]", flush=True)
    return trees


def predict_rf(trees, X):
    return [sum(predict_tree(t, x) for t in trees) / len(trees) for x in X]


# ─── 评估 ───
def auc(y_true, y_pred):
    paired = sorted(zip(y_pred, y_true), reverse=True)
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0: return 0.5
    tp = 0; fp = 0; auc_val = 0.0
    prev_score = None; prev_tp = 0; prev_fp = 0
    for score, label in paired:
        if score != prev_score:
            auc_val += (fp - prev_fp) * (tp + prev_tp) / 2
            prev_score = score; prev_tp = tp; prev_fp = fp
        if label == 1: tp += 1
        else: fp += 1
    auc_val += (fp - prev_fp) * (tp + prev_tp) / 2
    return auc_val / (n_pos * n_neg)


def kfold_cv(X, y, k=5, n_trees=80):
    n = len(X)
    indices = list(range(n))
    random.seed(42)
    random.shuffle(indices)
    fold_size = n // k
    aucs = []
    for fold in range(k):
        test_idx = set(indices[fold*fold_size:(fold+1)*fold_size])
        X_train = [X[i] for i in range(n) if i not in test_idx]
        y_train = [y[i] for i in range(n) if i not in test_idx]
        X_test = [X[i] for i in range(n) if i in test_idx]
        y_test = [y[i] for i in range(n) if i in test_idx]
        trees = train_rf(X_train, y_train, n_trees=n_trees)
        pred = predict_rf(trees, X_test)
        a = auc(y_test, pred)
        aucs.append(a)
        print(f"   Fold {fold+1}: AUC={a:.4f}", flush=True)
    return aucs


def feature_importance(trees, feat_keys):
    """统计每个特征被作为分裂节点的次数 (近似重要性)"""
    counts = {f: 0 for f in feat_keys}
    def walk(node):
        if node.feature is not None:
            counts[node.feature] = counts.get(node.feature, 0) + 1
            walk(node.left)
            walk(node.right)
    for t in trees:
        walk(t)
    total = sum(counts.values())
    if total == 0: return counts
    return {k: v/total for k, v in counts.items()}


def threshold_analysis(y_true, y_pred):
    out = []
    for t in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]:
        n = sum(1 for p in y_pred if p >= t)
        if n == 0: continue
        hits = sum(1 for p, y in zip(y_pred, y_true) if p >= t and y == 1)
        out.append({"thr": t, "n": n, "hits": hits, "rate": round(hits/n*100, 1)})
    return out


def main():
    src = OUT_DIR / "v24-results-2026-04-28.json"
    print(f"📂 加载样本: {src}", flush=True)
    samples = load_v24_samples(src)
    print(f"   样本数: {len(samples)}", flush=True)
    
    print(f"\n🔧 特征工程...", flush=True)
    X = [extract_features(s) for s in samples]
    y = [1 if s["promoted"] else 0 for s in samples]
    feat_keys = list(X[0].keys())
    print(f"   特征数: {len(feat_keys)}", flush=True)
    print(f"   正样本率: {sum(y)/len(y)*100:.2f}%", flush=True)
    
    print(f"\n🎯 5折交叉验证 (RF: 80 棵树, max_depth=8)...", flush=True)
    aucs = kfold_cv(X, y, k=5, n_trees=80)
    avg_auc = sum(aucs) / len(aucs)
    print(f"   平均 AUC: {avg_auc:.4f}", flush=True)
    
    # vs LR
    lr_auc = 0.6375
    print(f"\n📊 vs LR: {lr_auc:.4f}, RF: {avg_auc:.4f}, 差异: {avg_auc-lr_auc:+.4f}", flush=True)
    
    print(f"\n🏋️ 全数据训练最终 RF (100 棵树)...", flush=True)
    trees = train_rf(X, y, n_trees=100, max_depth=10)
    
    # 特征重要性
    fi = feature_importance(trees, feat_keys)
    fi_sorted = sorted(fi.items(), key=lambda x: -x[1])
    print(f"\n📊 特征重要性 (Top 12):", flush=True)
    for k, v in fi_sorted:
        print(f"   {k:<20} {v:.4f} {'█'*int(v*100)}", flush=True)
    
    # 预测
    y_pred = predict_rf(trees, X)
    thr_table = threshold_analysis(y, y_pred)
    
    print(f"\n🎯 RF 概率阈值分析:", flush=True)
    print(f"   {'阈值':>6} {'样本':>6} {'命中':>6} {'胜率':>8}")
    for t in thr_table:
        print(f"   ≥{t['thr']:>5.2f} {t['n']:>6} {t['hits']:>6} {t['rate']:>7.1f}%")
    
    # Top K
    paired = sorted(zip(samples, y_pred), key=lambda x: -x[1])
    print(f"\n📈 Top K 命中率:", flush=True)
    for k in [5, 10, 20, 30, 50]:
        hits = sum(s["promoted"] for s, _ in paired[:k])
        print(f"   Top {k}: {hits}/{k} = {hits/k*100:.1f}%")
    
    print(f"\n💎 RF Top 20 票:", flush=True)
    for s, p in paired[:20]:
        ft = s["features"]
        actual = "✅晋" if s["promoted"] else "❌炸"
        print(f"   {s['date']} {s['code']} {s['name']:<10} P={p:.3f} {actual} v24={s['total']:>3} 板={ft.get('lbc','-')} {ft.get('hybk','-')[:8]}")
    
    # 落档
    out = {
        "version": "v2.7-rf",
        "n_trees": 100,
        "max_depth": 10,
        "n_samples": len(samples),
        "n_pos": sum(y),
        "cv_aucs": aucs,
        "avg_auc": avg_auc,
        "lr_auc_baseline": lr_auc,
        "auc_delta_vs_lr": avg_auc - lr_auc,
        "feature_importance": fi,
        "threshold_analysis": thr_table,
        "predictions": [{"code": s["code"], "name": s["name"], "date": s["date"],
                         "rf_prob": round(p, 4), "actual_promoted": s["promoted"],
                         "v24_score": s["total"]} for s, p in paired],
    }
    p_json = OUT_DIR / "v27-rf-results-2026-04-28.json"
    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n   ✅ JSON: {p_json}", flush=True)
    
    write_md(samples, aucs, avg_auc, lr_auc, fi_sorted, thr_table, paired, len(samples), sum(y))


def write_md(samples, aucs, avg_auc, lr_auc, fi_sorted, thr_table, paired, n, pos):
    p = OUT_DIR / "v27-rf-results-2026-04-28.md"
    md = []
    md.append(f"# v2.7 Random Forest 回测\n")
    md.append(f"_截止 2026-04-28 | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 模型\n")
    md.append(f"- 样本: {n} | 正样本: {pos} ({pos/n*100:.2f}%)")
    md.append(f"- RF: 100 棵树, max_depth=10, max_features=sqrt(12)≈3\n")
    
    md.append(f"## 🎯 表现\n")
    md.append(f"- 5 折 CV AUC: {[round(a,4) for a in aucs]}")
    md.append(f"- **平均 AUC: {avg_auc:.4f}**")
    md.append(f"- LR baseline: {lr_auc:.4f}")
    delta = avg_auc - lr_auc
    sym = "✅ 提升" if delta > 0.01 else "⚠️ 持平" if abs(delta) < 0.01 else "❌ 下降"
    md.append(f"- **Δ AUC: {delta:+.4f}** {sym}\n")
    
    md.append(f"## 📊 特征重要性\n")
    md.append(f"| 特征 | 重要性 |")
    md.append(f"|---|---:|")
    for k, v in fi_sorted:
        md.append(f"| {k} | {v:.4f} |")
    md.append("")
    
    md.append(f"## 🎯 阈值表现\n")
    md.append(f"| 阈值 | 样本 | 命中 | 胜率 |")
    md.append(f"|---:|---:|---:|---:|")
    for t in thr_table:
        md.append(f"| ≥{t['thr']:.2f} | {t['n']} | {t['hits']} | {t['rate']}% |")
    md.append("")
    
    md.append(f"## 💎 RF Top 25 预测\n")
    md.append(f"| 日期 | 代码 | 名称 | RF概率 | 真实 | v2.4分 | 板 | 板块 |")
    md.append(f"|---|---|---|---:|:---:|---:|---:|---|")
    for s, prob in paired[:25]:
        ft = s["features"]
        actual = "✅" if s["promoted"] else "❌"
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | {prob:.3f} | {actual} | {s['total']} | {ft.get('lbc','-')} | {ft.get('hybk','-')[:8]} |")
    
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"   ✅ MD: {p}", flush=True)


if __name__ == "__main__":
    main()
