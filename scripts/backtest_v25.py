#!/usr/bin/env python3
"""
backtest_v25.py — v2.5: 用 logistic regression 学习维度权重

策略:
  1. 加载 v2.4 跑出来的 786 样本 (backtest/v24-results-2026-04-28.json)
  2. 提取原始特征 (lbc, fbt_bucket, fund_pct, vol_ratio, cap_yi, hs, zbc, in_lhb 等)
  3. 训练 logistic regression (纯 Python, 不依赖 sklearn)
  4. 输出: 每个特征的权重 + 5 折交叉验证 AUC + Top 票预测概率

不用 numpy: 用纯 Python list, 数据量 786 完全够用
"""
import json, math, random, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
OUT_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))


def sigmoid(z):
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def load_v24_samples(path):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d["samples"]


def extract_features(s):
    """从 v2.4 sample 提取原始特征 (而不是评分桶)"""
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
    
    # 工程特征
    fbt_early = 1.0 if 0 < fbt <= 93000 else 0.0  # 9:30 前封板
    fbt_premium = 1.0 if 0 < fbt <= 92500 else 0.0  # 集合竞价/一字
    fbt_late = 1.0 if fbt > 130000 else 0.0  # 下午弱势
    
    cap_golden = 1.0 if 30 <= ltsz_yi <= 80 else 0.0
    cap_huge = 1.0 if ltsz_yi > 150 else 0.0
    
    seal_strong = 1.0 if seal_pct >= 3 else 0.0
    seal_weak = 1.0 if 0 < seal_pct < 0.5 else 0.0
    
    vol_compress = 1.0 if 0 < vol_ratio < 0.7 else 0.0  # 缩量
    vol_explode = 1.0 if vol_ratio > 3 else 0.0  # 天量
    
    has_zb = 1.0 if zbc > 0 else 0.0  # 有炸板
    
    # v2.8.1 换手率分桶 (发现是 U 型, 不能单调)
    hs_lock = 1.0 if hs < 1 else 0.0          # 一字板 封死: 60% 胜率!
    hs_low = 1.0 if 1 <= hs < 3 else 0.0      # 冷货 25%
    hs_dead = 1.0 if 3 <= hs < 10 else 0.0    # 死亡区 12-15%
    hs_mid = 1.0 if 10 <= hs < 15 else 0.0    # 中性 19%
    hs_active = 1.0 if 15 <= hs < 20 else 0.0 # 换手高但危险 12%
    hs_high = 1.0 if hs >= 20 else 0.0        # 活跃 21-27%
    
    # v2.8.1 交互特征 (v2.9 加多交互反而退步, 已回滚)
    early_big_seal = 1.0 if (0 < fbt <= 93000 and seal_pct >= 3) else 0.0  # 早盘 + 大封单
    small_cap_active = 1.0 if (ltsz_yi <= 80 and 5 <= hs <= 20) else 0.0  # 中小盘 + 活跃
    
    # v2.8.3: 通过 Ablation 分析删了 12 个噪音特征 (AUC 0.66 → 0.69)
    # 删除原因: market_strength/sector_zt/hs_mid/vol_ratio/seal_weak/small_cap_active/zbc/
    #          vol_explode/cap_golden/seal_strong/hs_low/fbt_premium/in_lhb (LR 学不到信号)
    return {
        # 原始连续特征 (还在的, 会做归一化)
        "lbc": lbc,
        "seal_pct": seal_pct,
        "hs": hs,
        # 二值特征 (还在的, 12 个)
        "is_yizi": is_yizi,
        "fbt_early": fbt_early,
        "fbt_late": fbt_late,
        "cap_huge": cap_huge,
        "vol_compress": vol_compress,
        "has_zb": has_zb,
        "hs_lock": hs_lock,
        "hs_dead": hs_dead,
        "hs_active": hs_active,
        "hs_high": hs_high,
        "early_big_seal": early_big_seal,
    }


def normalize(samples_features, continuous_keys):
    """对连续特征做 z-score 归一化"""
    means = {}; stds = {}
    for k in continuous_keys:
        vals = [s[k] for s in samples_features]
        m = sum(vals) / len(vals)
        v = sum((x-m)**2 for x in vals) / len(vals)
        s = math.sqrt(v) if v > 0 else 1.0
        means[k] = m; stds[k] = s
    out = []
    for f in samples_features:
        nf = {}
        for k, v in f.items():
            if k in continuous_keys:
                nf[k] = (v - means[k]) / stds[k]
            else:
                nf[k] = v  # 二值不动
        out.append(nf)
    return out, means, stds


def train_lr(X, y, lr=0.1, iters=500, l2=0.01):
    """简单 logistic regression with L2"""
    keys = list(X[0].keys())
    n = len(X)
    weights = {k: 0.0 for k in keys}
    bias = 0.0
    
    for it in range(iters):
        grad_w = {k: 0.0 for k in keys}
        grad_b = 0.0
        loss = 0.0
        for i in range(n):
            z = bias + sum(weights[k] * X[i][k] for k in keys)
            p = sigmoid(z)
            err = p - y[i]
            for k in keys:
                grad_w[k] += err * X[i][k]
            grad_b += err
            # cross entropy
            loss += -(y[i] * math.log(max(p, 1e-9)) + (1-y[i]) * math.log(max(1-p, 1e-9)))
        # L2 正则化
        for k in keys:
            grad_w[k] = grad_w[k] / n + l2 * weights[k]
            weights[k] -= lr * grad_w[k]
        bias -= lr * grad_b / n
        if (it+1) % 100 == 0:
            print(f"   iter {it+1}: loss={loss/n:.4f}", flush=True)
    
    return weights, bias


def predict(X, weights, bias):
    keys = list(weights.keys())
    return [sigmoid(bias + sum(weights[k] * x[k] for k in keys)) for x in X]


def auc(y_true, y_pred):
    """计算 ROC AUC"""
    paired = sorted(zip(y_pred, y_true), reverse=True)
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0: return 0.5
    tp = 0; fp = 0
    auc_val = 0.0
    prev_score = None
    prev_tp = 0; prev_fp = 0
    for score, label in paired:
        if score != prev_score:
            auc_val += (fp - prev_fp) * (tp + prev_tp) / 2
            prev_score = score
            prev_tp = tp; prev_fp = fp
        if label == 1: tp += 1
        else: fp += 1
    auc_val += (fp - prev_fp) * (tp + prev_tp) / 2
    return auc_val / (n_pos * n_neg)


def kfold_cv(X, y, k=5):
    """K 折交叉验证"""
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
        
        w, b = train_lr(X_train, y_train, lr=0.2, iters=500, l2=0.01)  # v2.8.2 调参
        y_pred = predict(X_test, w, b)
        a = auc(y_test, y_pred)
        aucs.append(a)
        print(f"   Fold {fold+1}: AUC={a:.4f}", flush=True)
    
    return aucs


def precision_at_k(y_true, y_pred, k):
    """前 k 个预测中真正涨的比例"""
    paired = sorted(zip(y_pred, y_true), reverse=True)
    top_k = paired[:k]
    if not top_k: return 0.0
    return sum(label for _, label in top_k) / len(top_k)


def threshold_analysis(y_true, y_pred):
    """不同概率阈值的命中率"""
    out = []
    for t in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70]:
        n = sum(1 for p in y_pred if p >= t)
        if n == 0: continue
        hits = sum(1 for p, y in zip(y_pred, y_true) if p >= t and y == 1)
        out.append({"thr": t, "n": n, "hits": hits, "rate": round(hits/n*100, 1)})
    return out


def main():
    src = OUT_DIR / "v24-results-2026-04-28.json"
    print(f"📂 加载 v2.4 样本: {src}", flush=True)
    samples = load_v24_samples(src)
    print(f"   样本数: {len(samples)}", flush=True)
    
    print(f"\n🔧 特征工程...", flush=True)
    features = [extract_features(s) for s in samples]
    labels = [1 if s["promoted"] else 0 for s in samples]
    
    pos = sum(labels)
    print(f"   正样本: {pos}/{len(labels)} ({pos/len(labels)*100:.2f}%)", flush=True)
    
    # 归一化连续特征
    cont_keys = ["lbc", "seal_pct", "hs"]  # v2.8.3 仅保留 3 个连续特征
    X_norm, means, stds = normalize(features, cont_keys)
    print(f"   归一化均值: { {k: round(means[k], 2) for k in cont_keys} }", flush=True)
    
    # K 折交叉验证
    print(f"\n🎯 5 折交叉验证...", flush=True)
    aucs = kfold_cv(X_norm, labels, k=5)
    avg_auc = sum(aucs) / len(aucs)
    print(f"   平均 AUC: {avg_auc:.4f}", flush=True)
    
    # 全数据训练最终模型
    print(f"\n🏋️ 全数据训练最终模型...", flush=True)
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)  # v2.8.2 调参
    
    # 预测全部
    y_pred = predict(X_norm, weights, bias)
    
    # 权重排序
    print(f"\n📊 特征权重 (排序):", flush=True)
    weighted = sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)
    print(f"   {'feature':<20} {'weight':>10} {'effect':>8}")
    for k, w in weighted:
        eff = "↑晋级" if w > 0 else "↓晋级" if w < 0 else "无关"
        if abs(w) < 0.05: eff = "弱相关"
        print(f"   {k:<20} {w:>+10.4f} {eff:>8}")
    print(f"   {'BIAS':<20} {bias:>+10.4f}", flush=True)
    
    # 阈值分析
    print(f"\n🎯 概率阈值分析:", flush=True)
    thr_table = threshold_analysis(labels, y_pred)
    print(f"   {'阈值':>6} {'样本':>6} {'命中':>6} {'胜率':>8}")
    for t in thr_table:
        print(f"   ≥{t['thr']:>5.2f} {t['n']:>6} {t['hits']:>6} {t['rate']:>7.1f}%")
    
    # Top K 命中
    print(f"\n📈 Top K 票命中率 (按预测概率排序):", flush=True)
    for k in [5, 10, 20, 30, 50]:
        p = precision_at_k(labels, y_pred, k)
        print(f"   Top {k}: 命中率 {p*100:.1f}%")
    
    # Top 25 票详情
    print(f"\n💎 Top 25 票预测概率:", flush=True)
    paired = sorted(zip(samples, y_pred), key=lambda x: -x[1])
    print(f"   {'日期':<12} {'代码':<8} {'名称':<12} {'概率':>6} {'真实':>6} {'板':>3} {'板块':<10}")
    for s, p in paired[:25]:
        ft = s["features"]
        actual = "✅晋" if s["promoted"] else "❌炸"
        print(f"   {s['date']:<12} {s['code']:<8} {s['name']:<12} {p:>5.3f} {actual:>6} {ft.get('lbc','-'):>3} {ft.get('hybk','-')[:10]:<10}")
    
    # 落档
    out_p = OUT_DIR / f"v25-lr-results-2026-04-28.json"
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v2.5-lr",
            "n_samples": len(samples),
            "n_pos": pos,
            "cv_aucs": aucs,
            "avg_auc": avg_auc,
            "weights": weights,
            "bias": bias,
            "feature_means": means,
            "feature_stds": stds,
            "threshold_analysis": thr_table,
            "predictions": [{"code": s["code"], "name": s["name"], "date": s["date"],
                             "predicted_prob": round(p, 4),
                             "actual_promoted": s["promoted"],
                             "v24_score": s["total"]}
                            for s, p in paired],
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n   ✅ 模型落档: {out_p}", flush=True)
    
    # 写报告
    write_report(weights, bias, aucs, avg_auc, thr_table, paired, len(samples), pos)


def write_report(weights, bias, aucs, avg_auc, thr_table, paired, n, pos):
    p = OUT_DIR / f"v25-lr-results-2026-04-28.md"
    md = []
    md.append(f"# v2.5 Logistic Regression 学习权重\n")
    md.append(f"_截止 2026-04-28 (北京) | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 数据\n")
    md.append(f"- 样本: {n} (来自 v2.4 跑出的 30 天涨停池)")
    md.append(f"- 正样本: {pos} ({pos/n*100:.2f}%)\n")
    
    md.append(f"## 🎯 模型表现\n")
    md.append(f"- 5 折 CV AUC: " + ", ".join(f"{a:.4f}" for a in aucs))
    md.append(f"- **平均 AUC: {avg_auc:.4f}**")
    md.append(f"  - AUC 0.5 = 随机, 0.7 = 弱预测, 0.8 = 强预测, 0.9 = 极强\n")
    
    md.append(f"## 🔬 特征权重 (LR 自动学的)\n")
    md.append(f"| 特征 | 权重 | 效应 |")
    md.append(f"|---|---:|---|")
    weighted = sorted(weights.items(), key=lambda x: -abs(x[1]))
    for k, w in weighted:
        if abs(w) < 0.01: continue
        eff = "↑晋级率" if w > 0.05 else ("↓晋级率" if w < -0.05 else "弱影响")
        md.append(f"| {k} | {w:+.4f} | {eff} |")
    md.append(f"| BIAS | {bias:+.4f} | 基线 |\n")
    
    md.append(f"## 🎯 概率阈值表现\n")
    md.append(f"| 阈值 | 样本 | 命中 | 晋级率 |")
    md.append(f"|---:|---:|---:|---:|")
    for t in thr_table:
        md.append(f"| ≥{t['thr']:.2f} | {t['n']} | {t['hits']} | {t['rate']}% |")
    md.append("")
    
    md.append(f"## 💎 Top 25 票预测 (LR 概率)\n")
    md.append(f"| 日期 | 代码 | 名称 | 概率 | 真实 | v2.4分 | 连板 | 板块 |")
    md.append(f"|---|---|---|---:|:---:|---:|---:|---|")
    for s, prob in paired[:25]:
        ft = s["features"]
        actual = "✅" if s["promoted"] else "❌"
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | {prob:.3f} | {actual} | {s['total']} | {ft.get('lbc','-')} | {ft.get('hybk','-')[:8]} |")
    
    md.append(f"\n---\n")
    md.append(f"## 🚀 v2.5 优势\n")
    md.append(f"1. 权重不再手拍, 数据驱动")
    md.append(f"2. 输出概率 (0-1), 比分数更直观")
    md.append(f"3. 可量化每个特征贡献")
    md.append(f"4. 容易迭代: 加新特征只需 retrain\n")
    
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"   ✅ 报告: {p}", flush=True)


if __name__ == "__main__":
    main()
