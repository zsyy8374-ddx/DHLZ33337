#!/usr/bin/env python3
"""
reversal_lr.py — 回马枪 LR 模型 v0.1

输入: backtest/reversal-events-2026-04-30.json (1151 个涨停事件)
训练: 用 D0 涨停日 + 回调期数据预测"再涨停"
输出: backtest/reversal-lr-{date}.json (权重 + 阈值 + 时序 AUC)
"""
import json, math, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))


def sigmoid(z):
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def extract_features(e):
    """从 reversal event 提取特征"""
    callback = e.get("callback_pct", 0) or 0
    min_close = e.get("min_close_pct", 0) or 0
    vol_ratio = e.get("vol_callback_ratio", 0) or 0
    d0_chg = e.get("d0_chg", 10) or 10
    
    return {
        # 连续: 回调强度
        "callback_pct": callback,
        "min_close_pct": min_close,
        # 二值: MA 击穿
        "broke_ma5": 1.0 if e.get("broke_ma5") else 0.0,
        "broke_ma10": 1.0 if e.get("broke_ma10") else 0.0,
        # 二值: 浅回调 (强信号)
        "shallow": 1.0 if callback < 3 else 0.0,
        "no_close_break": 1.0 if min_close < 3 else 0.0,
        # 量能 dummy (U 型: 深缩量 + 爆量都是好的)
        "vol_compress": 1.0 if 0 < vol_ratio < 0.5 else 0.0,
        "vol_dead": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,  # 反指!
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,
        # 创业板/科创板/北交所反指
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
    }


def normalize(features, cont_keys):
    means, stds = {}, {}
    for k in cont_keys:
        vals = [f[k] for f in features]
        m = sum(vals) / len(vals)
        v = sum((x-m)**2 for x in vals) / len(vals)
        s = math.sqrt(v) if v > 0 else 1.0
        means[k] = m; stds[k] = s
    out = []
    for f in features:
        nf = {}
        for k, v in f.items():
            if k in cont_keys:
                nf[k] = (v - means[k]) / stds[k]
            else:
                nf[k] = v
        out.append(nf)
    return out, means, stds


def train_lr(X, y, lr=0.2, iters=500, l2=0.01):
    keys = list(X[0].keys())
    n = len(X)
    weights = {k: 0.0 for k in keys}
    bias = 0.0
    for _ in range(iters):
        gw = {k: 0.0 for k in keys}
        gb = 0.0
        for i in range(n):
            z = bias + sum(weights[k] * X[i][k] for k in keys)
            err = sigmoid(z) - y[i]
            for k in keys:
                gw[k] += err * X[i][k]
            gb += err
        for k in keys:
            gw[k] = gw[k] / n + l2 * weights[k]
            weights[k] -= lr * gw[k]
        bias -= lr * gb / n
    return weights, bias


def predict(X, weights, bias):
    keys = list(weights.keys())
    return [sigmoid(bias + sum(weights[k] * x[k] for k in keys)) for x in X]


def auc(y_true, y_pred):
    paired = sorted(zip(y_pred, y_true), reverse=True)
    n_pos = sum(y_true); n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0: return 0.5
    tp = fp = 0; auc_val = 0.0
    prev_score = None; prev_tp = prev_fp = 0
    for score, label in paired:
        if score != prev_score:
            auc_val += (fp - prev_fp) * (tp + prev_tp) / 2
            prev_score = score; prev_tp = tp; prev_fp = fp
        if label == 1: tp += 1
        else: fp += 1
    auc_val += (fp - prev_fp) * (tp + prev_tp) / 2
    return auc_val / (n_pos * n_neg)


def kfold_cv(X, y, k=5):
    n = len(X)
    indices = list(range(n))
    random.seed(42); random.shuffle(indices)
    fold_size = n // k
    aucs = []
    for fold in range(k):
        test_idx = set(indices[fold*fold_size:(fold+1)*fold_size])
        Xtr = [X[i] for i in range(n) if i not in test_idx]
        ytr = [y[i] for i in range(n) if i not in test_idx]
        Xte = [X[i] for i in range(n) if i in test_idx]
        yte = [y[i] for i in range(n) if i in test_idx]
        w, b = train_lr(Xtr, ytr, lr=0.2, iters=300, l2=0.01)
        aucs.append(auc(yte, predict(Xte, w, b)))
    return aucs


def time_series_cv(events, X, y, n_splits=5):
    """按 d0_date 排序的时序 CV"""
    indexed = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
    n = len(indexed)
    fold_size = n // (n_splits + 1)
    aucs = []
    top_n_hit = []  # Top N 命中 (按各折大小动态)
    for k in range(n_splits):
        train_end = fold_size * (k + 1)
        test_start = train_end
        test_end = train_end + fold_size
        train_idx = indexed[:train_end]
        test_idx = indexed[test_start:test_end]
        if len(train_idx) < 50 or len(test_idx) < 5: continue
        Xtr = [X[i] for i in train_idx]
        ytr = [y[i] for i in train_idx]
        Xte = [X[i] for i in test_idx]
        yte = [y[i] for i in test_idx]
        w, b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
        preds = predict(Xte, w, b)
        aucs.append(auc(yte, preds))
        # Top 10% 命中
        top_n = max(5, len(preds) // 10)
        ranked = sorted(zip(preds, yte), reverse=True)[:top_n]
        if ranked:
            top_n_hit.append(sum(yi for _, yi in ranked) / len(ranked))
    return aucs, top_n_hit


def calibrate_thresholds(X, y, w, b):
    preds = predict(X, w, b)
    paired = sorted(zip(preds, y), reverse=True)
    P_high = 0.7; P_mid = 0.55
    n_pos = 0
    for i, (p, yi) in enumerate(paired):
        n_pos += yi
        rate = n_pos / (i + 1)
        if i + 1 >= 5 and rate >= 0.80 and P_high == 0.7:
            P_high = round(p, 3)
        if i + 1 >= 10 and rate >= 0.65:
            P_mid = round(p, 3)
    if P_high < P_mid: P_high = P_mid + 0.05
    return P_high, P_mid


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    src = BACKTEST_DIR / "reversal-events-2026-04-30.json"
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 加载 {len(events)} 个涨停事件 | 回马枪率 {sum(1 for e in events if e['outcome']=='reversal')/len(events)*100:.1f}%\n", flush=True)
    
    features = [extract_features(e) for e in events]
    labels = [1 if e["outcome"] == "reversal" else 0 for e in events]
    cont_keys = ["callback_pct", "min_close_pct"]
    X_norm, means, stds = normalize(features, cont_keys)
    
    # 随机 5 折 CV
    rand_aucs = kfold_cv(X_norm, labels, k=5)
    rand_avg = sum(rand_aucs) / len(rand_aucs)
    print(f"🎯 随机 5 折 AUC: {rand_avg:.4f} (虚高基线)", flush=True)
    
    # 时序滚动
    ts_aucs, top10 = time_series_cv(events, X_norm, labels, n_splits=5)
    ts_avg = sum(ts_aucs) / len(ts_aucs)
    top10_avg = sum(top10) / len(top10) if top10 else 0
    print(f"📅 时序 AUC: {ts_avg:.4f} (真实指标)", flush=True)
    print(f"📅 Top 10% 命中: {top10_avg*100:.1f}%", flush=True)
    
    # 全数据训练
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)
    
    # Top 权重
    print(f"\n📊 Top 权重:", flush=True)
    weighted = sorted(weights.items(), key=lambda x: -abs(x[1]))
    for k, w in weighted[:10]:
        eff = "↑" if w > 0 else "↓"
        print(f"   {k:<20} {w:+.4f} {eff}", flush=True)
    
    # 阈值校准
    P_high, P_mid = calibrate_thresholds(X_norm, labels, weights, bias)
    print(f"\n🎚️ 阈值校准:", flush=True)
    print(f"   P_high (≥80% 胜率): {P_high}", flush=True)
    print(f"   P_mid  (≥65% 胜率): {P_mid}", flush=True)
    
    # 落档
    out = {
        "version": "reversal-lr-v0.1",
        "trained_at": today,
        "n_samples": len(events),
        "n_pos": sum(labels),
        "rand_auc": rand_avg,
        "ts_auc": ts_avg,
        "top10_hit": top10_avg,
        "weights": weights,
        "bias": bias,
        "feature_means": means,
        "feature_stds": stds,
        "cont_keys": cont_keys,
        "P_high": P_high,
        "P_mid": P_mid,
    }
    save_path = BACKTEST_DIR / f"reversal-lr-{today}.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {save_path}", flush=True)


if __name__ == "__main__":
    main()
