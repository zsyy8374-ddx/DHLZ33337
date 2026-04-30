#!/usr/bin/env python3
"""
reversal_recalibrate.py — 用 OOS calibration 重新校准 P_high/P_mid

原校准 bug:
  - calibrate_thresholds 是在训练集上跑, 严重 in-sample 偏差
  - 训练集上 0.97 看似 85% 命中, OOS 实际 0.8 才是 85% 命中
  - 推送时用了 0.97 阈值, 导致 "极强档 0 只" + 模型实际有 90% 命中区被埋没

修复:
  1. 时序 80/20 split → 在 OOS 测试集 calibrate
  2. 找 OOS 真实命中率 ≥ 85% 的最低 P 阈值 (P_high_oos)
  3. 找 OOS 真实命中率 ≥ 70% 的最低 P 阈值 (P_mid_oos)
  4. 用 Top N 也算一份, 保留备用
"""
import json, sys, math
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"

sys.path.insert(0, str(WORKSPACE / "scripts"))
from reversal_lr_v4 import extract_v4, normalize, train_lr, predict


def calibrate_oos(test_preds, test_labels, hit_target=0.85, min_n=5):
    """找 OOS 上滚动命中率达到 hit_target 的最低 P"""
    paired = sorted(zip(test_preds, test_labels), reverse=True)
    n_pos = 0
    last_p = paired[0][0]
    for i, (p, y) in enumerate(paired):
        n_pos += y
        n = i + 1
        rate = n_pos / n
        if n >= min_n and rate >= hit_target:
            last_p = p
        elif n >= min_n and rate < hit_target and last_p < paired[0][0]:
            return last_p, n
    return last_p, len(paired)


def main():
    # 找最新 v4 events
    src = sorted(BACKTEST_DIR.glob("reversal-events-*-v4.json"), reverse=True)[0]
    with open(src) as f:
        events = json.load(f)["events"]
    print(f"📊 加载: {src.name}, {len(events)} 事件\n", flush=True)
    
    features = [extract_v4(e) for e in events]
    labels = [1 if e["outcome"] == "reversal" else 0 for e in events]
    cont_keys = ["callback_pct", "min_close_pct", "lbc_num", "cb5_main_avg",
                 "cb3_main_avg", "cb1_main_avg", "d0_main_flow", "pre_d0_5d_main_avg"]
    X_norm, means, stds = normalize(features, cont_keys)
    
    # 时序 80/20
    sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
    n = len(sorted_idx); split = int(n * 0.8)
    train_idx = sorted_idx[:split]; test_idx = sorted_idx[split:]
    
    Xtr = [X_norm[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [X_norm[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    w, b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
    
    # 用 OOS 测试集校准
    test_preds = predict(Xte, w, b)
    
    # 用全量训练 (推送用) 重训, 但 calibration 用 OOS 拿到的阈值
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)
    
    # OOS 阈值
    P_high_oos, n_high = calibrate_oos(test_preds, yte, hit_target=0.85, min_n=10)
    P_mid_oos, n_mid = calibrate_oos(test_preds, yte, hit_target=0.70, min_n=15)
    
    print(f"📊 OOS calibration:", flush=True)
    print(f"   P_high (≥85% 命中, n≥10): {P_high_oos:.3f}", flush=True)
    print(f"   P_mid  (≥70% 命中, n≥15): {P_mid_oos:.3f}", flush=True)
    
    # OOS Top N 命中
    ranked = sorted(zip(test_preds, yte), reverse=True)
    top_metrics = {}
    for top_n in [10, 15, 20, 25, 30]:
        if top_n > len(ranked): break
        hit = sum(y for _, y in ranked[:top_n]) / top_n
        top_metrics[top_n] = hit
        print(f"   Top {top_n:>2}: 命中 {hit*100:.1f}% (P>={ranked[top_n-1][0]:.3f})", flush=True)
    
    # 用全量模型预测看分布
    full_preds = predict(X_norm, weights, bias)
    print(f"\n📊 全量训练后预测分布 (训练集):", flush=True)
    bins = [(0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    for lo, hi in bins:
        sub = [(p, y) for p, y in zip(full_preds, labels) if lo <= p < hi]
        if not sub: continue
        rate = sum(y for _, y in sub) / len(sub)
        print(f"   [{lo:.1f}-{hi:.1f})  n={len(sub):>4} 命中={rate*100:5.1f}%", flush=True)
    
    # 更新最新 v4 模型 JSON 的 P_high/P_mid
    model_path = sorted(BACKTEST_DIR.glob("reversal-lr-*-v4.json"), reverse=True)[0]
    with open(model_path) as f:
        model = json.load(f)
    
    old_high = model["P_high"]; old_mid = model["P_mid"]
    model["P_high"] = round(P_high_oos, 3)
    model["P_mid"] = round(P_mid_oos, 3)
    model["P_high_method"] = "OOS_calibration_85pct"
    model["P_mid_method"] = "OOS_calibration_70pct"
    model["P_old_high_in_sample"] = old_high
    model["P_old_mid_in_sample"] = old_mid
    model["oos_top_n_hits"] = top_metrics
    
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 已更新模型 {model_path.name}:", flush=True)
    print(f"   P_high: {old_high} → {model['P_high']}", flush=True)
    print(f"   P_mid: {old_mid} → {model['P_mid']}", flush=True)


if __name__ == "__main__":
    main()
