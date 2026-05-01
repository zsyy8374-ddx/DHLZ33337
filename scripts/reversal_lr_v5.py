#!/usr/bin/env python3
"""reversal_lr_v5.py — 加入市场 regime 特征 + 训练保存"""
import json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))

sys.path.insert(0, str(WORKSPACE / "scripts"))
from reversal_lr_v4 import sigmoid, extract_v4, normalize, train_lr, predict


def load_index_data():
    """加载三大指数日数据"""
    with open(BACKTEST_DIR / "index_daily.json") as f:
        idx_data = json.load(f)
    idx_by_date = {}
    sorted_dates = []
    for code, info in idx_data.items():
        for r in info["rows"]:
            idx_by_date.setdefault(r["date"], {})[code] = r["chg_pct"]
    sorted_dates = sorted(idx_by_date.keys())
    return idx_by_date, sorted_dates


def detect_regime(idx_by_date, date):
    """v0.6 8 类 regime"""
    if date not in idx_by_date: return "normal"
    d = idx_by_date[date]
    sh = d.get("sh000001", 0); sz = d.get("sz399006", 0); kc = d.get("sh000688", 0)
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    avg = (sh + sz + kc) / 3
    if kc > 2 and sh < 0.5: return "kc_only_red"
    if sh > 0.5 and sz < -0.3 and kc < -0.3: return "sh_only_red"
    if sz > 2 and sh < 0.5: return "sz_only_red"
    if spread > 4 and avg > 0: return "spread_high_up"
    if sh <= 0 and sz <= 0 and kc <= 0:
        return "all_green_strong" if avg <= -0.5 else "all_green_weak"
    if sh >= 0 and sz >= 0 and kc >= 0:
        return "all_red_strong" if avg >= 0.5 else "all_red_weak"
    return "normal"


def get_eval_date(e, sorted_dates):
    """事件评估日 D_t (反转日或 D0+10)"""
    if e.get("d_t_date"): return e["d_t_date"]
    d0 = e["d0_date"]
    if d0 not in sorted_dates: return None
    i = sorted_dates.index(d0)
    if i + 10 >= len(sorted_dates): return None
    return sorted_dates[i + 10]


def get_dminus1_date(e, sorted_dates):
    """v0.7: 推送日 (D_t 前 1 交易日) — 推送时可见的 regime"""
    eval_d = get_eval_date(e, sorted_dates)
    if not eval_d: return None
    if eval_d not in sorted_dates: return None
    i = sorted_dates.index(eval_d)
    if i == 0: return None
    return sorted_dates[i - 1]


def extract_v5(e, regime):
    """v0.5 特征 = v0.4 + 8 类 regime dummies + interaction (升级 v0.6 regime)"""
    f = extract_v4(e)
    f["reg_kc_red"] = 1.0 if regime == "kc_only_red" else 0.0
    f["reg_sh_red"] = 1.0 if regime == "sh_only_red" else 0.0
    f["reg_sz_red"] = 1.0 if regime == "sz_only_red" else 0.0
    f["reg_spread_up"] = 1.0 if regime == "spread_high_up" else 0.0
    f["reg_all_green_strong"] = 1.0 if regime == "all_green_strong" else 0.0
    f["reg_all_green_weak"] = 1.0 if regime == "all_green_weak" else 0.0
    f["reg_all_red_strong"] = 1.0 if regime == "all_red_strong" else 0.0
    f["reg_all_red_weak"] = 1.0 if regime == "all_red_weak" else 0.0
    lbc = e.get("d0_lbc", 1) or 1
    f["reg_kc_lianban"] = 1.0 if regime == "kc_only_red" and lbc >= 2 else 0.0
    f["reg_spread_lianban"] = 1.0 if regime == "spread_high_up" and lbc >= 2 else 0.0
    f["reg_sz_lianban"] = 1.0 if regime == "sz_only_red" and lbc >= 2 else 0.0
    f["reg_green_lianban"] = 1.0 if regime == "all_green_strong" and lbc >= 2 else 0.0
    f["reg_red_lianban"] = 1.0 if regime == "all_red_strong" and lbc >= 2 else 0.0
    return f


def auc(y_true, y_pred):
    paired = sorted(zip(y_pred, y_true), reverse=True)
    pos = sum(y_true); neg = len(y_true) - pos
    if pos == 0 or neg == 0: return 0.5
    s = 0; tp = 0
    for _, yi in paired:
        if yi == 1: tp += 1
        else: s += tp
    return s / (pos * neg)


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    
    # 找最新的 events 文件
    candidates = sorted(BACKTEST_DIR.glob("reversal-events-*-v6.json"))
    if not candidates:
        candidates = sorted(BACKTEST_DIR.glob("reversal-events-*-v4.json"))
    src = candidates[-1]
    print(f"📂 数据源: {src.name}")
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    
    idx_by_date, sorted_dates = load_index_data()
    # ⚠️ v0.7 重大修复: 用 D-1 regime 训模型, 不是 D_t (避免信息泄漏)
    event_regimes = []
    for e in events:
        dm1 = get_dminus1_date(e, sorted_dates)
        event_regimes.append(detect_regime(idx_by_date, dm1 or ""))
    
    from collections import Counter
    print(f"📊 总事件 {len(events)}, regime 分布:")
    for r, n in Counter(event_regimes).most_common():
        rev = sum(1 for i, e in enumerate(events) if event_regimes[i]==r and e["outcome"]=="reversal")
        print(f"   {r:<20} n={n:>4}  反转率 {rev/n*100:.1f}%")
    
    features = [extract_v5(e, event_regimes[i]) for i, e in enumerate(events)]
    labels = [1 if e["outcome"]=="reversal" else 0 for e in events]
    cont_keys = ["callback_pct","min_close_pct","cb5_main_avg","cb3_main_avg","cb1_main_avg","d0_main_flow","pre_d0_5d_main_avg","lbc_num"]
    
    X_norm, means, stds = normalize(features, cont_keys)
    
    # 时序 80/20
    sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
    n = len(sorted_idx); split = int(n * 0.8)
    train_idx = sorted_idx[:split]; test_idx = sorted_idx[split:]
    Xtr = [X_norm[i] for i in train_idx]; ytr = [labels[i] for i in train_idx]
    Xte = [X_norm[i] for i in test_idx]; yte = [labels[i] for i in test_idx]
    
    w_split, b_split = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
    test_preds = predict(Xte, w_split, b_split)
    test_auc = auc(yte, test_preds)
    n_top = max(5, len(test_preds) // 10)
    test_top10 = sum(yi for _, yi in sorted(zip(test_preds, yte), reverse=True)[:n_top]) / n_top
    print(f"\n📊 时序 80/20 split:")
    print(f"   测试 AUC: {test_auc:.4f}")
    print(f"   测试 Top {n_top} 命中: {test_top10*100:.1f}%")
    
    # 全量训练
    weights, bias = train_lr(X_norm, labels, lr=0.2, iters=500, l2=0.01)
    
    print(f"\n📊 全量训练 Top 权重:")
    weighted = sorted(weights.items(), key=lambda x: -abs(x[1]))
    for k, w in weighted[:20]:
        eff = "↑" if w > 0 else "↓"
        print(f"   {k:<25} {w:+.4f} {eff}")
    
    # 校准阈值
    train_preds = predict(X_norm, weights, bias)
    paired = sorted(zip(train_preds, labels), reverse=True)
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
    
    print(f"\n🎚️ 阈值: P_high={P_high}, P_mid={P_mid}")
    
    # 保存模型 (兼容 v4 格式)
    model = {
        "version": "v0.5",
        "trained_at": datetime.now(BJT).isoformat(),
        "n_samples": len(events),
        "n_pos": sum(labels),
        "ts_auc": test_auc,
        "top10_hit": test_top10,
        "test_auc_oos": test_auc,
        "test_top10_oos": test_top10,
        "weights": weights,
        "bias": bias,
        "feature_means": means,
        "feature_stds": stds,
        "cont_keys": cont_keys,
        "P_high": P_high,
        "P_mid": P_mid,
        "feature_keys": list(features[0].keys()),
        "regime_used": True,
    }
    # 保存两处 (picks/ 与 backtest/ 甚趋于 v4)
    out1 = WORKSPACE / "picks" / "lr_v5_model.json"
    out1.parent.mkdir(parents=True, exist_ok=True)
    with open(out1, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    out2 = BACKTEST_DIR / f"reversal-lr-{today}-v5.json"
    with open(out2, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    print(f"\n💾 模型已保存: {out1.name} + {out2.name}")


if __name__ == "__main__":
    main()
