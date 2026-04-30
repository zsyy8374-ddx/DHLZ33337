#!/usr/bin/env python3
"""reversal_lr_v3.py — v0.3 LR (含主力资金流特征)"""
import json, math, random
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))


def sigmoid(z):
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def extract_v3(e):
    callback = e.get("callback_pct", 0) or 0
    min_close = e.get("min_close_pct", 0) or 0
    vol_ratio = e.get("vol_callback_ratio", 0) or 0
    d0_chg = e.get("d0_chg", 10) or 10
    lbc = e.get("d0_lbc", 1) or 1
    
    # v0.3 资金流特征
    cb_main_avg = e.get("callback_main_flow_avg", 0) or 0
    cb_in_ratio = e.get("callback_in_days_ratio", 0) or 0
    d0_main = e.get("d0_main_flow", 0) or 0
    d0_main_pct = e.get("d0_main_ratio", 0) or 0
    pre_avg = e.get("pre_d0_5d_main_avg", 0) or 0
    
    return {
        # v0.1/0.2 base
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
        # v0.3 资金流: 关键 U 型, 用 dummies 而非连续值
        "cb_main_outflow_big": 1.0 if cb_main_avg < -0.5 else 0.0,    # 回调大流出
        "cb_main_inflow_big": 1.0 if cb_main_avg >= 0.5 else 0.0,     # 回调流入
        "cb_main_inflow_huge": 1.0 if cb_main_avg >= 2 else 0.0,      # 回调大幅流入
        "cb_main_dead": 1.0 if -0.5 <= cb_main_avg < 0.5 else 0.0,   # 中间状态 (反指)
        "cb_in_low": 1.0 if cb_in_ratio < 0.2 else 0.0,               # 极少流入天数
        "cb_in_high": 1.0 if cb_in_ratio >= 0.8 else 0.0,             # 大量流入天数
        "d0_main_neg_strong": 1.0 if d0_main_pct < -10 else 0.0,      # D0 主力大幅流出
        # 连续: 资金流量 (非 U 型部分)
        "cb_main_avg": cb_main_avg,
        "pre_d0_5d_main_avg": pre_avg,
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


def ablation_full_retrain(X, y, base_auc):
    """逐个删除特征 + 重训, 看时序 AUC 变化"""
    print(f"\n📉 Ablation (重训, 基础 AUC={base_auc:.4f}):", flush=True)
    keys = list(X[0].keys())
    results = []
    for k in keys:
        Xm = [{kk: v for kk, v in x.items() if kk != k} for x in X]
        wm, bm = train_lr(Xm, y, lr=0.2, iters=300, l2=0.01)
        preds = predict(Xm, wm, bm)
        a_m = auc(y, preds)
        delta = base_auc - a_m
        results.append((k, delta))
    for k, delta in sorted(results, key=lambda x: -x[1])[:25]:
        eff = "🔥" if delta > 0.005 else ("⚠️" if delta < -0.001 else "·")
        print(f"   {eff} {k:<25} Δ={delta:+.4f}", flush=True)


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    src = BACKTEST_DIR / f"reversal-events-{today}-v3.json"
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 v0.3: {len(events)} 个事件 (基础胜率 {sum(1 for e in events if e['outcome']=='reversal')/len(events)*100:.1f}%)\n", flush=True)
    
    features = [extract_v3(e) for e in events]
    labels = [1 if e["outcome"] == "reversal" else 0 for e in events]
    cont_keys = ["callback_pct", "min_close_pct", "lbc_num", "cb_main_avg", "pre_d0_5d_main_avg"]
    X_norm, means, stds = normalize(features, cont_keys)
    
    # 时序 CV
    ts_aucs, top10 = time_series_cv(events, X_norm, labels, n_splits=5)
    ts_avg = sum(ts_aucs) / len(ts_aucs)
    top10_avg = sum(top10) / len(top10) if top10 else 0
    print(f"📅 v0.3 时序 AUC: {ts_avg:.4f} (vs v0.1 0.7321, v0.2 0.7431)", flush=True)
    print(f"📅 v0.3 Top 10% 命中: {top10_avg*100:.1f}% (vs v0.1 82.1%, v0.2 88.4%)", flush=True)
    
    # 全量训练
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)
    
    print(f"\n📊 Top 权重:", flush=True)
    weighted = sorted(weights.items(), key=lambda x: -abs(x[1]))
    for k, w in weighted[:20]:
        eff = "↑" if w > 0 else "↓"
        print(f"   {k:<25} {w:+.4f} {eff}", flush=True)
    
    P_high, P_mid = calibrate_thresholds(X_norm, labels, weights, bias)
    print(f"\n🎚️ 阈值: P_high={P_high} (>=85% 历史胜率), P_mid={P_mid} (>=70%)", flush=True)
    
    # Ablation 重训版
    base_auc = auc(labels, predict(X_norm, weights, bias))
    ablation_full_retrain(X_norm, labels, base_auc)
    
    # 落档
    out = {
        "version": "reversal-lr-v0.3",
        "trained_at": today,
        "n_samples": len(events),
        "n_pos": sum(labels),
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
    save_path = BACKTEST_DIR / f"reversal-lr-{today}-v3.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已落档: {save_path}", flush=True)


if __name__ == "__main__":
    main()
