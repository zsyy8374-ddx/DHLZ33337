#!/usr/bin/env python3
"""
reversal_picks.py — 涨停回马枪每日候选股推送 (REVERSAL DAILY)

逻辑:
  1. 找出最近 2-10 个交易日内涨停过的所有股票 (D0)
  2. 对每只票算回调期数据: callback_pct, min_close_pct, broke_ma5/10, vol_callback_ratio
  3. 用 reversal-lr 模型预测"明天再涨停"概率
  4. 按 P_high/P_mid 分档输出, 推送微信+邮件

用法:
  python3 reversal_picks.py            # 用今日数据
  python3 reversal_picks.py 2026-04-29 # 历史日期
  python3 reversal_picks.py dry        # 不推送只打印
"""
import json, time, sys, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
PICKS_DIR = WORKSPACE / "picks"
PICKS_DIR.mkdir(exist_ok=True)
BJT = timezone(timedelta(hours=8))


def http_get(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", errors="ignore")
            if data.startswith("v="):
                data = data[2:].rstrip(";")
            return json.loads(data) if data.strip().startswith("{") else None
    except Exception:
        return None


def is_zt(code, chg):
    if code.startswith(('300', '688')): return chg >= 19.5
    if code.startswith(('8', '4', '9')): return chg >= 29.5
    return chg >= 9.7


def fetch_kline(code, beg, end, lookback=130):
    sym = ("sh" if code.startswith('6') else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},{lookback},qfq"
    d = http_get(url)
    if not d: return [], None
    sd = d.get("data", {}).get(sym, {})
    klines = sd.get("qfqday") or sd.get("day") or []
    name = None
    qt = sd.get("qt")
    if qt and isinstance(qt, dict):
        info = qt.get(sym)
        if info and isinstance(info, list) and len(info) > 1:
            name = info[1]
    return klines, name


def fetch_zt_pool_daily(date):
    """东财涨停池"""
    url = f"http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt%3Aasc&date={date.replace('-','')}"
    d = http_get(url)
    if not d: return []
    items = d.get("data", {}).get("pool", [])
    return [{"code": it.get("c"), "name": it.get("n"), "date": date} for it in items]


def calc_ma(klines, idx, period):
    if idx < period - 1: return None
    return sum(float(klines[i][2]) for i in range(idx-period+1, idx+1)) / period


def get_d0_features(code, end_date):
    """对一只票, 找其 D0 (最近 2-10 天前的涨停日), 计算回调期特征
    返回: 最适合的一个 D0 候选 (距今最近的, 且 D0+1 ~ today 区间在 2-10 天内)
    """
    beg = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=130)).strftime("%Y-%m-%d")
    klines, name = fetch_kline(code, beg, end_date, lookback=130)
    if not klines or len(klines) < 30:
        return None, None
    
    # 找 today_idx (end_date 在 K 线里的位置)
    today_idx = None
    for i, k in enumerate(klines):
        if k[0] == end_date:
            today_idx = i; break
    if today_idx is None:
        # end_date 不在 K 线 (今日还未收盘), 用最后一条
        today_idx = len(klines) - 1
        end_date = klines[-1][0]
    
    # 从 today 倒推 2-10 天找 D0 涨停 (优先距今较近的)
    best = None
    for back in range(2, 11):
        d0_idx = today_idx - back
        if d0_idx < 20: continue  # 留 20 天给 MA
        k = klines[d0_idx]
        if len(k) < 6: continue
        c = float(k[2]); pc = float(klines[d0_idx-1][2])
        if pc <= 0: continue
        chg = (c - pc) / pc * 100
        if not is_zt(code, chg): continue
        
        # 找到 D0 了, 计算回调期特征
        d0_close = c
        d0_vol = float(k[5])
        ma5_d0 = calc_ma(klines, d0_idx, 5)
        ma10_d0 = calc_ma(klines, d0_idx, 10)
        
        callback_pct = 0; min_close = d0_close
        broke_ma5 = False; broke_ma10 = False
        vols = []
        for j in range(d0_idx + 1, today_idx + 1):
            jk = klines[j]
            if len(jk) < 6: continue
            j_l = float(jk[4]); j_c = float(jk[2]); j_v = float(jk[5])
            if d0_close > 0:
                drop = (d0_close - j_l) / d0_close * 100
                if drop > callback_pct: callback_pct = drop
            if j_c < min_close: min_close = j_c
            if ma5_d0 and j_c < ma5_d0: broke_ma5 = True
            if ma10_d0 and j_c < ma10_d0: broke_ma10 = True
            vols.append(j_v)
        
        # 排除已经在期间又涨停过的 (已是回马枪后的, 不是候选)
        already_zt_again = False
        for j in range(d0_idx + 1, today_idx + 1):
            jk = klines[j]
            j_c = float(jk[2]); j_pc = float(klines[j-1][2])
            if j_pc > 0 and is_zt(code, (j_c - j_pc) / j_pc * 100):
                already_zt_again = True; break
        if already_zt_again: continue
        
        # 排除已破 MA10 跌幅过大的票 (低胜率, 不浪费推荐)
        # min_close_pct 不超过 15% 才推
        min_close_pct = (d0_close - min_close) / d0_close * 100
        if min_close_pct > 18: continue  # 跌太狠了, 不算回马枪候选
        
        candidate = {
            "code": code,
            "name": name or "?",
            "d0_date": k[0],
            "d0_close": round(d0_close, 3),
            "d0_chg": round(chg, 2),
            "days_since_d0": back,
            "today_close": round(float(klines[today_idx][2]), 3),
            "callback_pct": round(callback_pct, 2),
            "min_close_pct": round(min_close_pct, 2),
            "broke_ma5": broke_ma5,
            "broke_ma10": broke_ma10,
            "vol_callback_ratio": round(sum(vols) / len(vols) / d0_vol, 3) if vols and d0_vol > 0 else 0,
        }
        if best is None or back < best["days_since_d0"]:
            best = candidate
    
    return best, name


def extract_features(c):
    callback = c.get("callback_pct", 0) or 0
    min_close = c.get("min_close_pct", 0) or 0
    vol_ratio = c.get("vol_callback_ratio", 0) or 0
    d0_chg = c.get("d0_chg", 10) or 10
    return {
        "callback_pct": callback,
        "min_close_pct": min_close,
        "broke_ma5": 1.0 if c.get("broke_ma5") else 0.0,
        "broke_ma10": 1.0 if c.get("broke_ma10") else 0.0,
        "shallow": 1.0 if callback < 3 else 0.0,
        "no_close_break": 1.0 if min_close < 3 else 0.0,
        "vol_compress": 1.0 if 0 < vol_ratio < 0.5 else 0.0,
        "vol_dead": 1.0 if 0.5 <= vol_ratio < 0.7 else 0.0,
        "vol_explode": 1.0 if vol_ratio >= 1.5 else 0.0,
        "is_20cm": 1.0 if d0_chg >= 19.5 and d0_chg < 25 else 0.0,
    }


def predict_lr(c, model):
    f = extract_features(c)
    means = model["feature_means"]; stds = model["feature_stds"]
    cont_keys = model["cont_keys"]
    fn = {}
    for k, v in f.items():
        if k in cont_keys:
            fn[k] = (v - means.get(k, 0)) / stds.get(k, 1)
        else:
            fn[k] = v
    z = model["bias"] + sum(model["weights"][k] * fn[k] for k in model["weights"])
    return 1.0 / (1.0 + (2.71828 ** -z)) if -700 < z < 700 else (0.0 if z < 0 else 1.0)


def get_candidates(end_date):
    """找出近 2-10 天涨停过的所有 unique 股票, 计算每只的回调期特征"""
    print(f"📊 扫描近 2-10 天涨停过的股票 (基准日 {end_date})...", flush=True)
    
    # 先抓近 12 个交易日的涨停池, 收集 unique codes
    codes_set = set()
    for back in range(0, 14):
        d_str = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=back)).strftime("%Y-%m-%d")
        zt_pool = fetch_zt_pool_daily(d_str)
        for it in zt_pool:
            codes_set.add(it["code"])
        time.sleep(0.05)
    
    codes = sorted(codes_set)
    print(f"   候选池: {len(codes)} 只 (近 14 天涨停过的)", flush=True)
    
    candidates = []
    for i, code in enumerate(codes):
        cand, name = get_d0_features(code, end_date)
        if cand:
            candidates.append(cand)
        if (i + 1) % 50 == 0:
            print(f"   [{i+1}/{len(codes)}] 候选 {len(candidates)}", flush=True)
        time.sleep(0.05)
    
    print(f"   通过初筛: {len(candidates)} 只 (近 2-10 天有 D0 涨停, 跌幅<18%, 期间没再涨停)", flush=True)
    return candidates


def format_msg(candidates, model, date):
    P_high = model["P_high"]; P_mid = model["P_mid"]
    
    if not candidates:
        return f"⚔️ {date} 涨停回马枪推荐\n❌ 无候选"
    
    # 排序 by lr_prob
    candidates.sort(key=lambda x: -x["lr_prob"])
    
    tier_a = [c for c in candidates if c["lr_prob"] >= P_high]
    tier_b = [c for c in candidates if P_mid <= c["lr_prob"] < P_high]
    tier_c = [c for c in candidates if 0.55 <= c["lr_prob"] < P_mid]
    
    lines = []
    lines.append(f"⚔️ {date} 涨停回马枪推荐 (REVERSAL v0.1)")
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append(f"候选池: {len(candidates)} | 极强 {len(tier_a)} | 强 {len(tier_b)} | 关注 {len(tier_c)}")
    lines.append(f"模型: 时序 AUC {model['ts_auc']:.2f}, Top10% 命中 {model['top10_hit']*100:.0f}%")
    lines.append("")
    
    def render(c):
        out = [f"{c['code']} {c['name']} 📊{c['lr_prob']:.2f}"]
        d_info = f"D0={c['d0_date']}({c['days_since_d0']}天前) {c['d0_chg']:.1f}%"
        out.append(f"   {d_info}")
        feat = []
        feat.append(f"回调{c['callback_pct']:.1f}%")
        feat.append(f"跌{c['min_close_pct']:.1f}%")
        if c['broke_ma5']: feat.append("破MA5")
        else: feat.append("守MA5")
        if c['broke_ma10']: feat.append("破MA10")
        feat.append(f"量比{c['vol_callback_ratio']:.2f}")
        out.append(f"   {' | '.join(feat)}")
        return out
    
    if tier_a:
        lines.append(f"🔥🔥 极强档 (P≥{P_high:.2f}, 历史胜率≥80%)")
        for c in tier_a[:8]:
            lines.extend(render(c))
        lines.append("")
    
    if tier_b:
        lines.append(f"🔥 强档 (P≥{P_mid:.2f}, 历史胜率≥65%)")
        for c in tier_b[:8]:
            lines.extend(render(c))
        lines.append("")
    
    if tier_c and not tier_a and not tier_b:
        lines.append(f"🟡 关注档 (P≥0.55)")
        for c in tier_c[:8]:
            lines.extend(render(c))
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append(f"💡 模型: 1151 样本时序训练, 真实 AUC 0.73")
    lines.append(f"⚠️ 不构成投资建议, 自行二次确认")
    return "\n".join(lines)


def send_wechat(msg):
    """复用 daily_picks 的参数格式"""
    cmd = ["openclaw", "message", "send",
           "--channel", "openclaw-weixin",
           "--account", "ba28cc3242ca-im-bot",
           "--target", "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat",
           "--message", msg,
           "--json"]
    import re
    for retry in range(3):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            mid = None
            if r.returncode == 0:
                m = re.search(r'\{[\s\S]*\}', r.stdout)
                if m:
                    try:
                        d = json.loads(m.group(0))
                        mid = d.get("payload", {}).get("result", {}).get("messageId")
                    except Exception:
                        pass
            if mid:
                print(f"✅ 微信推送成功 (第{retry+1}次) mid={mid}", flush=True)
                return True
            print(f"⚠️ 微信推送 #{retry+1} 未得 messageId, stderr={r.stderr[-200:]}", flush=True)
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ 微信异常 #{retry+1}: {e}", flush=True)
            time.sleep(2)
    return False


def send_email(msg, date):
    body_path = f"/tmp/reversal-{date}.txt"
    with open(body_path, "w", encoding="utf-8") as f:
        f.write(msg)
    try:
        r = subprocess.run(
            ["node", str(WORKSPACE / "qq-send.js"),
             "--to", "1628354330@qq.com",
             "--subject", f"⚔️ 回马枪候选 {date}",
             "--bodyFile", body_path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            print(f"📧 邮件推送成功", flush=True)
            return True
    except Exception as e:
        print(f"⚠️ 邮件失败: {e}", flush=True)
    return False


def main():
    target_date = None; dry_run = False
    for a in sys.argv[1:]:
        if a == "dry": dry_run = True
        elif a.startswith("20"): target_date = a
    
    if not target_date:
        target_date = datetime.now(BJT).strftime("%Y-%m-%d")
    
    # 加载模型
    model_path = BACKTEST_DIR / "reversal-lr-2026-04-30.json"
    if not model_path.exists():
        # fallback: 找最新的
        cands = sorted(BACKTEST_DIR.glob("reversal-lr-*.json"), reverse=True)
        if not cands:
            print("❌ 没有找到 reversal-lr 模型, 请先跑 reversal_lr.py", flush=True)
            sys.exit(1)
        model_path = cands[0]
    
    with open(model_path, encoding="utf-8") as f:
        model = json.load(f)
    print(f"📦 加载模型: {model_path.name}", flush=True)
    print(f"   时序 AUC: {model['ts_auc']:.4f}, Top10%: {model['top10_hit']*100:.1f}%", flush=True)
    print(f"   阈值: P_high={model['P_high']}, P_mid={model['P_mid']}", flush=True)
    
    # 抓候选股
    candidates = get_candidates(target_date)
    if not candidates:
        print("❌ 无候选", flush=True)
        sys.exit(1)
    
    # LR 预测
    for c in candidates:
        c["lr_prob"] = round(predict_lr(c, model), 4)
    
    # 落档
    save_path = PICKS_DIR / f"reversal-{target_date}.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump({"date": target_date, "model_version": model["version"],
                   "candidates": candidates}, f, ensure_ascii=False, indent=2)
    print(f"\n📁 候选股落档: {save_path}", flush=True)
    
    msg = format_msg(candidates, model, target_date)
    print("\n" + "="*60, flush=True)
    print(msg, flush=True)
    print("="*60 + "\n", flush=True)
    
    if dry_run:
        print("📭 dry-run, 跳过推送", flush=True)
        return
    
    wx_ok = send_wechat(msg)
    if wx_ok:
        send_email(msg, target_date)
    if not wx_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
