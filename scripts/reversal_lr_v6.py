#!/usr/bin/env python3
"""reversal_lr_v6.py — 加 D0 前 10 日主力持续性特征"""
import json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))


def sigmoid(z):
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def extract_v6(e):
    callback = e.get("callback_pct", 0) or 0
    min_close = e.get("min_close_pct", 0) or 0
    vol_ratio = e.get("vol_callback_ratio", 0) or 0
    d0_chg = e.get("d0_chg", 10) or 10
    lbc = e.get("d0_lbc", 1) or 1
    cb5_main = e.get("cb5_main_avg", 0) or 0
    cb5_in = e.get("cb5_in_ratio", 0) or 0
    cb3_main = e.get("cb3_main_avg", 0) or 0
    cb1_main = e.get("cb1_main_avg", 0) or 0
    d0_main = e.get("d0_main_flow", 0) or 0
    pre_avg = e.get("pre_d0_5d_main_avg", 0) or 0
    # v0.6 新增: D0 前 10 日持续性 (490/1151 有, 缺失填 0)
    pre10_total = e.get("pre10_main_total", 0) or 0
    pre10_in = e.get("pre10_days_in", 0) or 0
    pre10_strong = e.get("pre10_strong_days", 0) or 0
    pre10_n = e.get("pre10_n", 0) or 0
    has_pre10 = 1.0 if pre10_n >= 5 else 0.0
    
    return {
        "callback_pct": callback,
        "min_close_pct": min_close,
        "broke_ma5": 1.0 if e.get("broke_ma5") else 0.0,
        "broke_ma10": 1.0 if e.get("broke_ma10") else 0.0,
        "shallow": 1.0 if callback < 3 else 0.0,
        "no_close_break": 1.0 if min_close < 3 else 0.0,
        "vol_dead": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
        "lbc_num": lbc,
        "is_lianban": 1.0 if lbc >= 2 else 0.0,
        "cb5_main_strong_pos": 1.0 if cb5_main >= 2 else 0.0,
        "cb5_main_pos": 1.0 if 0.5 <= cb5_main < 2 else 0.0,
        "cb5_main_neg": 1.0 if cb5_main < -0.5 else 0.0,
        # 去掉 cb5_in_high 共线性垃圾特征 (原本是 -0.30 反指)
        "cb5_in_low": 1.0 if cb5_in < 0.4 else 0.0,
        # 连续值
        "cb5_main_avg": cb5_main,
        "cb3_main_avg": cb3_main,
        "cb1_main_avg": cb1_main,
        "d0_main_flow": d0_main,
        "pre_d0_5d_main_avg": pre_avg,
        # v0.6 持续性
        "has_pre10": has_pre10,
        "pre10_main_total": pre10_total * has_pre10,  # 缺失会被 has_pre10=0 抵消
        "pre10_strong_days": pre10_strong * has_pre10,
        # dummies (坚鲁)
        "pre10_total_strong": 1.0 if (has_pre10 and pre10_total >= 1) else 0.0,
        "pre10_total_neg": 1.0 if (has_pre10 and pre10_total < -1) else 0.0,
        "pre10_strong_3plus": 1.0 if (has_pre10 and pre10_strong >= 3) else 0.0,
        "pre10_in_extreme": 1.0 if (has_pre10 and pre10_in >= 8) else 0.0,
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
            nf[k] = (v - means[k]) / stds[k] if k in cont_keys else v
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


def time_series_cv(events, X, y, n_splits=5):
    indexed = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
    n = len(indexed)
    fold_size = n // (n_splits + 1)
    aucs = []; top10 = []
    for k in range(n_splits):
        train_end = fold_size * (k + 1)
        test_start = train_end; test_end = train_end + fold_size
        train_idx = indexed[:train_end]
        test_idx = indexed[test_start:test_end]
        if len(train_idx) < 50 or len(test_idx) < 5: continue
        Xtr = [X[i] for i in train_idx]; ytr = [y[i] for i in train_idx]
        Xte = [X[i] for i in test_idx]; yte = [y[i] for i in test_idx]
        w, b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
        preds = predict(Xte, w, b)
        aucs.append(auc(yte, preds))
        top_n = max(5, len(preds) // 10)
        ranked = sorted(zip(preds, yte), reverse=True)[:top_n]
        if ranked:
            top10.append(sum(yi for _, yi in ranked) / len(ranked))
    return aucs, top10


def calibrate_thresholds(X, y, w, b):
    preds = predict(X, w, b)
    paired = sorted(zip(preds, y), reverse=True)
    P_high = 0.7; P_mid = 0.55
    n_pos = 0
    for i, (p, yi) in enumerate(paired):
        n_pos += yi
        rate = n_pos / (i + 1)
        if i + 1 >= 5 and rate >= 0.85 and P_high == 0.7:
            P_high = round(p, 3)
        if i + 1 >= 10 and rate >= 0.7:
            P_mid = round(p, 3)
    if P_high < P_mid: P_high = P_mid + 0.05
    return P_high, P_mid


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    src = BACKTEST_DIR / f"reversal-events-{today}-v6.json"
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 v0.6: {len(events)} 个事件 (基础胜率 {sum(1 for e in events if e['outcome']=='reversal')/len(events)*100:.1f}%)\n", flush=True)
    
    features = [extract_v6(e) for e in events]
    labels = [1 if e["outcome"] == "reversal" else 0 for e in events]
    cont_keys = ["callback_pct", "min_close_pct", "lbc_num", "cb5_main_avg",
                 "cb3_main_avg", "cb1_main_avg", "d0_main_flow", "pre_d0_5d_main_avg",
                 "pre10_main_total", "pre10_strong_days"]
    X_norm, means, stds = normalize(features, cont_keys)
    
    # 时序 CV
    ts_aucs, top10 = time_series_cv(events, X_norm, labels, n_splits=5)
    ts_avg = sum(ts_aucs) / len(ts_aucs)
    top10_avg = sum(top10) / len(top10) if top10 else 0
    print(f"📅 v0.6 时序 AUC: {ts_avg:.4f} (vs v0.4 0.7698, v0.5 0.7695)", flush=True)
    print(f"📅 v0.6 Top 10% 命中: {top10_avg*100:.1f}%", flush=True)
    
    # 时序 80/20 split (更严)
    sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
    n = len(sorted_idx); split = int(n * 0.8)
    train_idx = sorted_idx[:split]; test_idx = sorted_idx[split:]
    Xtr = [X_norm[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [X_norm[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    w_split, b_split = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
    test_preds = predict(Xte, w_split, b_split)
    train_preds = predict(Xtr, w_split, b_split)
    test_auc = auc(yte, test_preds); train_auc = auc(ytr, train_preds)
    n_top = max(5, len(test_preds) // 10)
    test_top10 = sum(yi for _, yi in sorted(zip(test_preds, yte), reverse=True)[:n_top]) / n_top
    
    print(f"\n📊 严格 80/20 split:", flush=True)
    print(f"   训练 AUC: {train_auc:.4f}", flush=True)
    print(f"   测试 AUC: {test_auc:.4f}", flush=True)
    print(f"   测试 Top {n_top} 命中: {test_top10*100:.1f}%", flush=True)
    print(f"   过拟合: {train_auc - test_auc:+.4f}", flush=True)
    
    # 全量训练
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)
    print(f"\n📊 全量训练 Top 权重:", flush=True)
    weighted = sorted(weights.items(), key=lambda x: -abs(x[1]))
    for k, w in weighted[:18]:
        eff = "↑" if w > 0 else "↓"
        print(f"   {k:<25} {w:+.4f} {eff}", flush=True)
    
    P_high, P_mid = calibrate_thresholds(X_norm, labels, weights, bias)
    print(f"\n🎚️ 阈值: P_high={P_high}, P_mid={P_mid}", flush=True)
    
    # 落档
    out = {
        "version": "reversal-lr-v0.6",
        "trained_at": today, "n_samples": len(events), "n_pos": sum(labels),
        "ts_auc": ts_avg, "top10_hit": top10_avg,
        "test_auc_oos": test_auc, "test_top10_oos": test_top10,
        "weights": weights, "bias": bias,
        "feature_means": means, "feature_stds": stds,
        "cont_keys": cont_keys, "P_high": P_high, "P_mid": P_mid,
    }
    save_path = BACKTEST_DIR / f"reversal-lr-{today}-v6.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {save_path}", flush=True)


if __name__ == "__main__":
    main()
