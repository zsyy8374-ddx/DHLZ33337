#!/usr/bin/env python3
"""
lr_retrain.py — 每日自动 retrain LR 模型 (v3.0 滚动训练版)

v3.0 升级 (2026-04-29):
  - 改为每日 retrain (而非每周), 用最近 30 天数据
  - 加上时序滚动验证 (真实 AUC, 不是随机 CV 的虚高值)
  - 加上 Ablation 自动审计 (防止噪音特征潜入, 漂移监控)
  - 加上动态阈值校准 (基于当前样本 P 分布反推 P_high/P_mid)
  - 支持 --dry-run (不覆盖 LATEST_MODEL, 只打印诊断)

流程:
  1. 跑最新 30 天 v2.4 回测, 得到样本 + 标签
  2. Ablation 审计 (每个特征逐一删除, 看 AUC 变化)
  3. 时序滚动验证 (按时间切分, 模拟真实生产)
  4. 全数据训练
  5. 阈值校准 (top1_prob 与命中率的关系)
  6. 保存为 LATEST_MODEL, 同时归档 picks/lr_history/
  7. 与上次模型对比 (AUC 漂移、权重漂移、特征健康度)
"""
import argparse, json, math, os, random, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
SCRIPTS = WORKSPACE / "scripts"
BACKTEST_DIR = WORKSPACE / "backtest"
PICKS_DIR = WORKSPACE / "picks"
LR_HIST = PICKS_DIR / "lr_history"
PICKS_DIR.mkdir(exist_ok=True)
LR_HIST.mkdir(exist_ok=True)
BJT = timezone(timedelta(hours=8))

LATEST_MODEL = WORKSPACE / "backtest" / "v25-lr-results-2026-04-28.json"  # daily_picks 引用的固定路径


def sigmoid(z):
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def extract_features(s):
    """v2.8.3 同步: 14 个特征 (Ablation 删 13 噪音, AUC 0.69)"""
    ft = s["features"]
    lbc = float(ft.get("lbc", 1))
    fbt = float(ft.get("fbt", 0))
    fund_yi = float(ft.get("fund_yi", 0))
    ltsz_yi = float(ft.get("ltsz_yi", 0))
    seal_pct = (fund_yi / ltsz_yi * 100) if ltsz_yi > 0 else 0.0
    hs = float(ft.get("hs", 0))
    is_yizi = 1.0 if ft.get("is_yizi") else 0.0
    return {
        "lbc": lbc,
        "seal_pct": seal_pct,
        "hs": hs,
        "is_yizi": is_yizi,
        "fbt_early": 1.0 if 0 < fbt <= 93000 else 0.0,
        "fbt_late": 1.0 if fbt > 130000 else 0.0,
        "cap_huge": 1.0 if ltsz_yi > 150 else 0.0,
        "vol_compress": 1.0 if 0 < float(ft.get("vol_ratio", 1.0)) < 0.7 else 0.0,
        "has_zb": 1.0 if float(ft.get("zbc", 0)) > 0 else 0.0,
        "hs_lock": 1.0 if hs < 1 else 0.0,
        "hs_dead": 1.0 if 3 <= hs < 10 else 0.0,
        "hs_active": 1.0 if 15 <= hs < 20 else 0.0,
        "hs_high": 1.0 if hs >= 20 else 0.0,
        "early_big_seal": 1.0 if (0 < fbt <= 93000 and seal_pct >= 3) else 0.0,
        # 新增 (战法 B v2 38天验证, 阈值按 wencai 3-5↔daily 1.5-2.5 映射)
        "early_soft_seal": 1.0 if (0 < fbt <= 100000 and 1.5 <= seal_pct < 2.8) else 0.0,
        "seal_pct_high": 1.0 if seal_pct >= 2.8 else 0.0,
    }


def normalize(samples_features, continuous_keys):
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
                nf[k] = v
        out.append(nf)
    return out, means, stds


def train_lr(X, y, lr=0.1, iters=500, l2=0.01):
    keys = list(X[0].keys())
    n = len(X)
    weights = {k: 0.0 for k in keys}
    bias = 0.0
    for it in range(iters):
        grad_w = {k: 0.0 for k in keys}
        grad_b = 0.0
        for i in range(n):
            z = bias + sum(weights[k] * X[i][k] for k in keys)
            p = sigmoid(z)
            err = p - y[i]
            for k in keys:
                grad_w[k] += err * X[i][k]
            grad_b += err
        for k in keys:
            grad_w[k] = grad_w[k] / n + l2 * weights[k]
            weights[k] -= lr * grad_w[k]
        bias -= lr * grad_b / n
    return weights, bias


def predict(X, weights, bias):
    keys = list(weights.keys())
    return [sigmoid(bias + sum(weights[k] * x[k] for k in keys)) for x in X]


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


def kfold_cv(X, y, k=5):
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
        w, b = train_lr(X_train, y_train, lr=0.1, iters=300, l2=0.01)
        aucs.append(auc(y_test, predict(X_test, w, b)))
    return aucs


def run_v24_backtest():
    """跑 v2.4 回测 (近 30 天) 生成训练数据"""
    today_bj = datetime.now(BJT).strftime("%Y-%m-%d")
    print(f"📊 跑 v2.4 30天回测 (截至 {today_bj})...", flush=True)
    cmd = ["python3", str(SCRIPTS / "backtest_v24.py"), "30", today_bj]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        print(f"❌ 回测失败:\n{proc.stderr[-500:]}", flush=True)
        sys.exit(1)
    print(proc.stdout[-500:], flush=True)
    
    # 找最新生成的 v24-results
    src = BACKTEST_DIR / f"v24-results-{today_bj}.json"
    if not src.exists():
        print(f"❌ 找不到回测结果: {src}", flush=True)
        sys.exit(1)
    return src, today_bj


def time_series_cv(samples, X_norm, labels, n_splits=5):
    """时序滚动验证: 按 sample_date 切分, 模拟真实生产
    返回: 平均 AUC, 各折 AUC, 各折 top5 命中率
    """
    # 按日期排序
    indexed = sorted(range(len(samples)), key=lambda i: samples[i].get("sample_date", ""))
    n = len(indexed)
    fold_size = n // (n_splits + 1)  # 第一段当 train, 后面 5 段当 test
    aucs = []
    top5_hits = []
    for k in range(n_splits):
        train_end = fold_size * (k + 1)
        test_start = train_end
        test_end = train_end + fold_size
        train_idx = indexed[:train_end]
        test_idx = indexed[test_start:test_end]
        if len(train_idx) < 50 or len(test_idx) < 5:
            continue
        Xtr = [X_norm[i] for i in train_idx]
        ytr = [labels[i] for i in train_idx]
        Xte = [X_norm[i] for i in test_idx]
        yte = [labels[i] for i in test_idx]
        w, b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
        preds = predict(Xte, w, b)
        aucs.append(auc(yte, preds))
        # Top5 命中率
        ranked = sorted(zip(preds, yte), reverse=True)
        top5 = ranked[:5]
        if top5:
            top5_hits.append(sum(y for _, y in top5) / len(top5))
    return aucs, top5_hits


def ablation_audit(samples, X_norm, labels, base_ts_auc):
    """逐个删除特征, 看时序 AUC 变化 (随机 CV 会判错, 必须用时序)
    返回: 噪音特征列表 (删掉反而时序 AUC 涨 ≥0.005 的)
    """
    if not X_norm:
        return [], []
    keys = list(X_norm[0].keys())
    noise = []
    detail = []
    for drop in keys:
        X_drop = [{k: v for k, v in x.items() if k != drop} for x in X_norm]
        ts_aucs, _ = time_series_cv(samples, X_drop, labels, n_splits=5)
        if not ts_aucs:
            continue
        a = sum(ts_aucs) / len(ts_aucs)
        delta = a - base_ts_auc
        detail.append((drop, a, delta))
        if delta > 0.005:  # 删掉这个特征时序 AUC 明显上涨 → 噪音
            noise.append((drop, delta))
    return noise, detail


def calibrate_thresholds(X_norm, labels, weights, bias):
    """基于当前样本概率分布反推阈值
    输出 P_high (强信号档), P_mid (中信号档)
    """
    preds = predict(X_norm, weights, bias)
    paired = sorted(zip(preds, labels), reverse=True)
    # 找命中率 ≥ 50% 的最低阈值 = P_mid
    # 找命中率 ≥ 60% 的最低阈值 = P_high (要求样本 ≥ 5)
    P_mid, P_high = 0.40, 0.50  # 默认
    n_pos = 0
    for i, (p, y) in enumerate(paired):
        n_pos += y
        rate = n_pos / (i + 1)
        if i + 1 >= 5 and rate >= 0.60 and P_high == 0.50:
            P_high = round(p, 3)
        if i + 1 >= 10 and rate >= 0.50:
            P_mid = round(p, 3)
    # 防止 P_high 比 P_mid 还低
    if P_high < P_mid: P_high = P_mid + 0.05
    return P_high, P_mid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="不覆盖 LATEST_MODEL, 只打印诊断")
    parser.add_argument("--skip-ablation", action="store_true", help="跳过 ablation (省时, ~1分钟)")
    parser.add_argument("--skip-backtest", action="store_true", help="跳过回测, 用今天已有的 v24-results")
    args = parser.parse_args()

    today_bj = datetime.now(BJT).strftime("%Y-%m-%d")
    
    print(f"{'='*60}", flush=True)
    print(f"🔄 LR retrain v3.0 启动 ({today_bj}){' [DRY-RUN]' if args.dry_run else ''}", flush=True)
    print(f"{'='*60}", flush=True)
    
    # 1. 跑回测
    if args.skip_backtest:
        src = BACKTEST_DIR / f"v24-results-{today_bj}.json"
        if not src.exists():
            # 回退到最新的
            cands = sorted(BACKTEST_DIR.glob("v24-results-*.json"), reverse=True)
            if not cands:
                print(f"❌ 没有找到 v24-results, 请先跑回测", flush=True)
                sys.exit(1)
            src = cands[0]
            print(f"⏭️ 跳过回测, 用已有: {src.name}", flush=True)
    else:
        src, _ = run_v24_backtest()
    
    # 2. 加载样本
    with open(src, "r", encoding="utf-8") as f:
        d = json.load(f)
    samples = d["samples"]
    print(f"\n📂 样本: {len(samples)} | 正样本率 {sum(1 for s in samples if s['promoted'])/len(samples)*100:.2f}%", flush=True)
    
    if len(samples) < 100:
        print(f"⚠️ 样本太少 (<100), 跳过 retrain", flush=True)
        sys.exit(2)
    
    # 3. 特征化
    features = [extract_features(s) for s in samples]
    labels = [1 if s["promoted"] else 0 for s in samples]
    cont_keys = ["lbc", "seal_pct", "hs"]
    X_norm, means, stds = normalize(features, cont_keys)
    
    # 4. 随机 5 折 (老指标, 看看跟时序的差距)
    print(f"\n🎯 随机 5 折 CV (虚高基线)...", flush=True)
    rand_aucs = kfold_cv(X_norm, labels, k=5)
    rand_avg = sum(rand_aucs) / len(rand_aucs)
    print(f"   随机 AUC: {rand_avg:.4f}", flush=True)
    
    # 5. 时序滚动验证 (真实生产指标)
    print(f"\n📅 时序滚动验证 (真实指标)...", flush=True)
    ts_aucs, ts_top5 = time_series_cv(samples, X_norm, labels, n_splits=5)
    ts_avg = sum(ts_aucs) / len(ts_aucs) if ts_aucs else 0
    top5_avg = sum(ts_top5) / len(ts_top5) if ts_top5 else 0
    print(f"   时序 AUC: {ts_avg:.4f} ({[round(a,3) for a in ts_aucs]})", flush=True)
    print(f"   时序 Top5 命中: {top5_avg*100:.1f}%", flush=True)
    print(f"   ⚠️ 数据泄漏 gap: {(rand_avg - ts_avg)*100:.2f}pp", flush=True)
    
    # 6. Ablation 审计 (用时序 AUC 作为基准, 随机 CV 会误判)
    noise = []
    if not args.skip_ablation:
        print(f"\n🔍 Ablation 审计 (基于时序 AUC, 阈值 +0.005)...", flush=True)
        noise, abl_detail = ablation_audit(samples, X_norm, labels, ts_avg)
        if noise:
            print(f"   ⚠️ 发现 {len(noise)} 个噪音特征:", flush=True)
            for k, delta in sorted(noise, key=lambda x: -x[1]):
                print(f"     {k:<20} 删掉时序 AUC +{delta:.4f}", flush=True)
            print(f"   建议: 下版本考虑剔除", flush=True)
        else:
            print(f"   ✅ 当前特征集干净, 无噪音 (时序 AUC 阈值)", flush=True)
    
    # 7. 全数据训练
    print(f"\n🏋️ 全数据训练...", flush=True)
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)
    
    weighted = sorted(weights.items(), key=lambda x: -abs(x[1]))
    print(f"\n📊 Top 权重:", flush=True)
    for k, w in weighted[:8]:
        eff = "↑" if w > 0 else "↓"
        print(f"   {k:<20} {w:+.4f} {eff}", flush=True)
    
    # 8. 阈值校准
    P_high, P_mid = calibrate_thresholds(X_norm, labels, weights, bias)
    print(f"\n🎚️ 动态阈值校准:", flush=True)
    print(f"   P_high (强信号 ≥60% 胜率): {P_high}", flush=True)
    print(f"   P_mid  (中信号 ≥50% 胜率): {P_mid}", flush=True)
    
    # 9. 落档
    out = {
        "version": "v3.0-lr-rolling",
        "trained_at": today_bj,
        "n_samples": len(samples),
        "n_pos": sum(labels),
        "cv_aucs": rand_aucs,         # 随机 (兼容 daily_picks 老字段)
        "avg_auc": rand_avg,           # 随机 (兼容)
        "ts_aucs": ts_aucs,            # 新: 时序
        "ts_avg_auc": ts_avg,          # 新: 时序 (真实)
        "ts_top5_hit": top5_avg,       # 新: Top5 命中率
        "weights": weights,
        "bias": bias,
        "feature_means": means,
        "feature_stds": stds,
        "P_high": P_high,              # 新: 动态阈值
        "P_mid": P_mid,                # 新: 动态阈值
        "noise_features": [k for k, _ in noise],  # 新: 审计结果
    }
    
    if args.dry_run:
        print(f"\n🚫 DRY-RUN: 不落档. 完成.", flush=True)
        return
    
    # 历史归档
    hist_path = LR_HIST / f"lr_model_{today_bj}.json"
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n📁 历史归档: {hist_path}", flush=True)
    
    with open(LATEST_MODEL, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"📁 最新模型: {LATEST_MODEL}", flush=True)
    
    # 10. 漂移对比
    hist_files = sorted(LR_HIST.glob("lr_model_*.json"), reverse=True)
    if len(hist_files) >= 2:
        prev = json.load(open(hist_files[1], encoding="utf-8"))
        prev_ts = prev.get("ts_avg_auc", prev.get("avg_auc", 0))
        delta = ts_avg - prev_ts
        sym = "↗️" if delta > 0.005 else "↘️" if delta < -0.005 else "➡️"
        print(f"\n📈 vs 上次 ({hist_files[1].stem}): 时序 AUC {prev_ts:.4f} → {ts_avg:.4f} {sym} ({delta:+.4f})", flush=True)
        # 权重漂移 Top 3
        prev_w = prev.get("weights", {})
        drifts = []
        for k, w in weights.items():
            pw = prev_w.get(k, 0)
            drifts.append((k, w - pw, pw, w))
        drifts.sort(key=lambda x: -abs(x[1]))
        print(f"   权重漂移 Top 3:", flush=True)
        for k, d, pw, w in drifts[:3]:
            print(f"     {k:<20} {pw:+.3f} → {w:+.3f} ({d:+.3f})", flush=True)
    
    print(f"\n✅ retrain 完成. daily_picks.py 下次跑会自动用新模型", flush=True)


if __name__ == "__main__":
    main()
