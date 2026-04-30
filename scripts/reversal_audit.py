#!/usr/bin/env python3
"""
reversal_audit.py — v0.3 数据泄漏审查

逻辑:
  v0.3 的资金流字段是 D0 当天 + 回调期 (D0+1 ... D_target-1)
  D_target 是评估日 (回马枪日 / 失败时的最后一天)
  所有特征都应该是 "知道 D_target 之前能算的", 不能用 D_target 当天数据

审查项:
  1. callback_main_flow_avg 的窗口 [D0+1, D_target-1] 还是 [D0+1, D_target]?
     → 必须是前者, 不然偷看了 D_target
  2. callback_in_days_ratio 同上
  3. 时序严格 split: 用前 80% 训练, 后 20% 测试 (vs 当前 5-fold CV)
  4. 把 D_target 数据 mask 掉, 重新算特征, 看 AUC 还能保持吗?

如果 mask 后 AUC 暴跌 → 说明有泄漏
如果 mask 后 AUC 持平 → 干净
"""
import json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
BJT = timezone(timedelta(hours=8))


def main():
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    src = BACKTEST_DIR / f"reversal-events-{today}-v3.json"
    
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    events = d["events"]
    print(f"📊 审查 v0.3 数据 ({len(events)} 个事件)\n", flush=True)
    
    # 检查 1: 窗口范围是否包含 D_target
    print("=" * 60, flush=True)
    print("【审查 1】回调期窗口 [D0+1, D_target-1] 还是 [D0+1, D_target]?", flush=True)
    print("=" * 60, flush=True)
    
    # 看 reversal_mine_v3_sina.py 怎么算的 cb_main_avg
    mine_path = WORKSPACE / "scripts" / "reversal_mine_v3_sina.py"
    if mine_path.exists():
        text = mine_path.read_text()
        # 找回调期统计逻辑
        import re
        # 找 callback_dates 或类似变量的赋值
        for kw in ["callback_dates", "cb_dates", "callback_period", "回调期"]:
            for m in re.finditer(rf".{{0,80}}{kw}.{{0,150}}", text):
                print(f"  匹配 '{kw}': {m.group(0).strip()[:200]}", flush=True)
                break
    print("", flush=True)
    
    # 检查 2: outcome=='reversal' 的样本里, D_target 当天是否在回调期窗口里?
    print("=" * 60, flush=True)
    print("【审查 2】outcome=reversal 时, callback_main_flow_avg 是否含 D_target?", flush=True)
    print("=" * 60, flush=True)
    
    # 检查事件结构
    e0 = events[0]
    print(f"事件字段: {list(e0.keys())}", flush=True)
    print(f"\n样本事件 (outcome=reversal):", flush=True)
    rev_sample = next(e for e in events if e.get("outcome") == "reversal")
    for k, v in rev_sample.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            print(f"  {k}: {v}", flush=True)
    print(f"\n样本事件 (outcome=fail):", flush=True)
    fail_sample = next(e for e in events if e.get("outcome") != "reversal")
    for k, v in fail_sample.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            print(f"  {k}: {v}", flush=True)
    print("", flush=True)
    
    # 🚨 关键审查: callback_window 是不是泄漏了 outcome
    print("=" * 60, flush=True)
    print("【审查 2.5】callback_window 是否泄漏 outcome?", flush=True)
    print("=" * 60, flush=True)
    from collections import Counter
    rev_w = Counter(e.get("callback_window") for e in events if e.get("outcome") == "reversal")
    fail_w = Counter(e.get("callback_window") for e in events if e.get("outcome") != "reversal")
    print(f"reversal callback_window: {dict(rev_w.most_common(5))}", flush=True)
    print(f"failed   callback_window: {dict(fail_w.most_common(5))}", flush=True)
    if len(set(fail_w.keys())) == 1:
        only_w = list(fail_w.keys())[0]
        print(f"\n🚨 严重泄漏: failed 全部 callback_window={only_w} (因为 mining 截断到 10 天)", flush=True)
        print(f"   reversal 的 cb 平均是 1-9 天, failed 是 10 天 → cb_main_flow_avg 间接编码了 outcome", flush=True)
        print(f"   修复方案: 用统一固定窗口 D0+1 到 D0+10 算所有事件的资金流", flush=True)
    
    # 检查 3: callback_dates 的最后一天 vs target_date
    print("=" * 60, flush=True)
    print("【审查 3】统计 callback 期的天数分布", flush=True)
    print("=" * 60, flush=True)
    
    days_total = []
    days_used_in_avg = []
    for e in events:
        if "d0_date" in e and "target_date" in e:
            d0 = datetime.strptime(e["d0_date"], "%Y-%m-%d")
            tgt = datetime.strptime(e["target_date"], "%Y-%m-%d")
            days_diff = (tgt - d0).days
            days_total.append(days_diff)
    
    if days_total:
        from collections import Counter
        c = Counter(days_total)
        print(f"D0 到 target_date 间隔天数分布 (前 12):", flush=True)
        for k in sorted(c.keys())[:12]:
            print(f"  {k} 天: n={c[k]}", flush=True)
    print("", flush=True)
    
    # 检查 4: 时序严格 split
    print("=" * 60, flush=True)
    print("【审查 4】严格时序 split (前 80% 训练, 后 20% 测试)", flush=True)
    print("=" * 60, flush=True)
    
    # 引用 reversal_lr_v3 的训练函数
    sys.path.insert(0, str(WORKSPACE / "scripts"))
    from reversal_lr_v3 import extract_v3, normalize, train_lr, predict, auc
    
    features = [extract_v3(e) for e in events]
    labels = [1 if e["outcome"] == "reversal" else 0 for e in events]
    cont_keys = ["callback_pct", "min_close_pct", "lbc_num", "cb_main_avg", "pre_d0_5d_main_avg"]
    X_norm, _, _ = normalize(features, cont_keys)
    
    # 按 d0_date 排序
    sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get("d0_date", ""))
    n = len(sorted_idx)
    split = int(n * 0.8)
    train_idx = sorted_idx[:split]
    test_idx = sorted_idx[split:]
    
    Xtr = [X_norm[i] for i in train_idx]
    ytr = [labels[i] for i in train_idx]
    Xte = [X_norm[i] for i in test_idx]
    yte = [labels[i] for i in test_idx]
    
    print(f"训练集: {len(Xtr)} 样本 (D0 {events[train_idx[0]].get('d0_date')} ~ {events[train_idx[-1]].get('d0_date')})", flush=True)
    print(f"测试集: {len(Xte)} 样本 (D0 {events[test_idx[0]].get('d0_date')} ~ {events[test_idx[-1]].get('d0_date')})", flush=True)
    print(f"训练正例率: {sum(ytr)/len(ytr)*100:.1f}%", flush=True)
    print(f"测试正例率: {sum(yte)/len(yte)*100:.1f}%", flush=True)
    
    # 训练
    w, b = train_lr(Xtr, ytr, lr=0.2, iters=500, l2=0.01)
    
    # 训练集 AUC
    train_preds = predict(Xtr, w, b)
    train_auc = auc(ytr, train_preds)
    
    # 测试集 AUC
    test_preds = predict(Xte, w, b)
    test_auc = auc(yte, test_preds)
    
    # 测试集 Top 10% 命中
    n_top = max(5, len(test_preds) // 10)
    ranked = sorted(zip(test_preds, yte), reverse=True)[:n_top]
    test_top10 = sum(yi for _, yi in ranked) / len(ranked) if ranked else 0
    
    print(f"\n训练集 AUC: {train_auc:.4f}", flush=True)
    print(f"测试集 AUC: {test_auc:.4f}  ⚠️ 这是真实样本外性能", flush=True)
    print(f"测试集 Top {n_top} 命中: {test_top10*100:.1f}%", flush=True)
    print(f"过拟合幅度: {train_auc - test_auc:+.4f}", flush=True)
    
    # 看 OOS 分档
    print(f"\n测试集分档表现:", flush=True)
    bins = [(0.97, 1.01, "极强"), (0.7, 0.97, "强"), (0.55, 0.7, "中"),
            (0.4, 0.55, "弱"), (0, 0.4, "差")]
    for lo, hi, name in bins:
        bin_yi = [yi for p, yi in zip(test_preds, yte) if lo <= p < hi]
        if bin_yi:
            print(f"  {name:<4} P=[{lo:.2f},{hi:.2f}) n={len(bin_yi)} 命中={sum(bin_yi)/len(bin_yi)*100:.1f}%", flush=True)
    
    # 检查 5: 把 D_target 数据 mask 掉重训
    print("\n" + "=" * 60, flush=True)
    print("【审查 5】每个特征在测试集上的真实增量价值", flush=True)
    print("=" * 60, flush=True)
    
    base_keys = list(X_norm[0].keys())
    full_test_auc = test_auc
    print(f"全特征 OOS AUC: {full_test_auc:.4f}\n", flush=True)
    
    # 关掉某类特征看 OOS 影响
    feature_groups = {
        "形态(callback_pct, min_close_pct, broke_ma5/10, shallow, no_close_break)":
            ["callback_pct", "min_close_pct", "broke_ma5", "broke_ma10", "shallow", "no_close_break"],
        "量能(vol_dead, vol_explode)":
            ["vol_dead", "vol_explode"],
        "连板(is_20cm, lbc_num, is_lianban)":
            ["is_20cm", "lbc_num", "is_lianban"],
        "资金流-回调期(cb_*)":
            [k for k in base_keys if k.startswith("cb_")],
        "资金流-D0(d0_*)":
            [k for k in base_keys if k.startswith("d0_")],
        "资金流-D0前5天(pre_*)":
            [k for k in base_keys if k.startswith("pre_")],
    }
    
    for group_name, keys in feature_groups.items():
        Xtr_m = [{k: v for k, v in x.items() if k not in keys} for x in Xtr]
        Xte_m = [{k: v for k, v in x.items() if k not in keys} for x in Xte]
        if not Xtr_m[0]:  # 全砍光了
            continue
        wm, bm = train_lr(Xtr_m, ytr, lr=0.2, iters=500, l2=0.01)
        preds_m = predict(Xte_m, wm, bm)
        a_m = auc(yte, preds_m)
        delta = full_test_auc - a_m
        eff = "🔥 关键" if delta > 0.01 else ("✅ 有价值" if delta > 0.003 else ("· 一般" if delta > -0.001 else "⚠️ 反作用"))
        print(f"  {eff} 砍 {group_name}", flush=True)
        print(f"     OOS AUC: {a_m:.4f}  Δ={delta:+.4f}", flush=True)
    
    print("\n" + "=" * 60, flush=True)
    print("✅ 审查完成", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
