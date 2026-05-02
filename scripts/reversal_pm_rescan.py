"""涨停回马枪 9:40 二次扫描 (D_t 当天早盘 pm 模型重排)
逻辑:
  1. 读最近一次 17:30 推送候选 (picks/reversal-v4-YYYY-MM-DD.json)
  2. 用腾讯/新浪 5m K 拿 D_t 早盘 9:30-9:40 数据 (今天)
  3. 用 pm_v1 模型重新打分
  4. 推送"早盘加强档" 微信
  
触发时间: 北京 09:40-09:42 (= 美西 17:40-17:42 PDT 夏令时, 18:40-18:42 PST)
"""
import json, sys, math, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')
BJT = timezone(timedelta(hours=8))


def http_get(url, timeout=12, retries=2):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(1.5)
    return None


def get_5m_first2(code):
    """拉今天 D_t 的 5m K 前 2 根 (9:35 + 9:40)"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=5&ma=no&datalen=10'
    data = http_get(url)
    if not data: return None, None, None
    try:
        klines = json.loads(data)
    except Exception:
        return None, None, None
    today_str = datetime.now(BJT).strftime('%Y-%m-%d')
    today_bars = [k for k in klines if k['day'].startswith(today_str)]
    
    # 拉前收
    url2 = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,3,qfq'
    daily_data = http_get(url2)
    prev_close = None
    if daily_data:
        try:
            d = json.loads(daily_data)
            bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
            for b in reversed(bars):
                if b[0] < today_str:
                    prev_close = float(b[2])
                    break
        except Exception:
            pass
    
    return today_bars, prev_close, today_str


def compute_pm_features(today_bars, prev_close):
    if not today_bars or not prev_close or prev_close <= 0:
        return None
    if len(today_bars) < 1:
        return None
    
    bar_930 = today_bars[0]  # 9:35:00 = 9:30-9:35
    open_p = float(bar_930['open'])
    high_5m = float(bar_930['high'])
    low_5m = float(bar_930['low'])
    close_5m = float(bar_930['close'])
    vol_5m = float(bar_930.get('volume', 0))
    amt_5m_yi = vol_5m * close_5m / 1e8
    
    open_pct = (open_p / prev_close - 1) * 100
    high_5m_pct = (high_5m / open_p - 1) * 100
    close_5m_pct = (close_5m / open_p - 1) * 100
    
    # 9:35-9:40 (如果有)
    if len(today_bars) >= 2:
        bar_935 = today_bars[1]
        high_10m = max(high_5m, float(bar_935['high']))
    else:
        high_10m = high_5m
    high_10m_pct = (high_10m / open_p - 1) * 100
    
    return {
        "pm_open_pct": round(open_pct, 3),
        "pm_5m_high_pct": round(high_5m_pct, 3),
        "pm_5m_close_pct": round(close_5m_pct, 3),
        "pm_10m_high_pct": round(high_10m_pct, 3),
        "pm_5m_amt_yi": round(amt_5m_yi, 4),
        "pm_strong_open": 1 if open_pct >= 0.3 and high_10m_pct >= 3 else 0,
        "pm_weak_open": 1 if open_pct < 0 else 0,
        "pm_open_red_5m": 1 if open_pct >= 0.5 and close_5m < open_p else 0,
    }


def predict_pm(features, model):
    """用 pm 模型 LR 预测"""
    cont_keys = model['cont_keys']
    mu = model['feature_means']
    sd = model['feature_stds']
    w = model['weights']
    b = model['bias']
    
    # normalize
    f_norm = {}
    for k, v in features.items():
        if k in cont_keys:
            f_norm[k] = (v - mu.get(k, 0)) / max(sd.get(k, 1), 1e-9)
        else:
            f_norm[k] = v
    
    # logit
    z = b
    for k, v in f_norm.items():
        z += w.get(k, 0) * v
    return 1 / (1 + math.exp(-z))


def main():
    # 读 pm 模型
    pm_model_path = WORKSPACE / 'picks' / 'pm_v1_model.json'
    if not pm_model_path.exists():
        print("❌ pm 模型未找到")
        return
    with open(pm_model_path) as f:
        pm_model = json.load(f)
    print(f"📦 pm 模型: {pm_model['version']}, AUC={pm_model['ts_auc']}, P_high={pm_model['P_high']}, P_mid={pm_model['P_mid']}")
    
    # 找最近的推送候选 (前一天 17:30 跑的)
    today = datetime.now(BJT).strftime('%Y-%m-%d')
    yesterday = (datetime.now(BJT) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    pick_files = sorted((WORKSPACE / 'picks').glob('reversal-v4-*.json'), reverse=True)
    pick_path = None
    for p in pick_files:
        # 跳过 reversal_hits 等
        if 'reversal-v4-' in p.name and len(p.stem.split('-')) == 5:
            pick_path = p; break
    if not pick_path:
        print("❌ 找不到 17:30 推送")
        return
    print(f"📂 推送源: {pick_path.name}")
    with open(pick_path) as f:
        full = json.load(f)
    candidates = full.get('candidates', [])
    print(f"   候选 {len(candidates)}")
    
    # 只对 P>=0.4 的二次扫描 (省时间)
    cands_to_scan = [c for c in candidates if c.get('lr_prob', 0) >= 0.4]
    print(f"   待扫描 (lr_prob>=0.4): {len(cands_to_scan)}")
    
    scored = []
    for i, c in enumerate(cands_to_scan):
        bars, prev_close, today_d = get_5m_first2(c['code'])
        if not bars:
            continue
        pm_feat = compute_pm_features(bars, prev_close)
        if not pm_feat:
            continue
        p_pm = predict_pm(pm_feat, pm_model)
        c2 = dict(c)
        c2.update(pm_feat)
        c2['p_pm'] = round(p_pm, 4)
        c2['p_combined'] = round(0.5 * c.get('lr_prob', 0) + 0.5 * p_pm, 4)
        scored.append(c2)
        time.sleep(0.4)
        if (i+1) % 20 == 0:
            print(f"   扫描进度 {i+1}/{len(cands_to_scan)}")
    
    print(f"\n✅ 扫到 pm 数据: {len(scored)}")
    
    # 输出
    P_high = pm_model['P_high']
    P_mid = pm_model['P_mid']
    
    scored.sort(key=lambda x: -x['p_pm'])
    
    tier_a = [s for s in scored if s['p_pm'] >= P_high]
    tier_b = [s for s in scored if P_mid <= s['p_pm'] < P_high]
    tier_c = [s for s in scored if 0.5 <= s['p_pm'] < P_mid]
    
    lines = []
    lines.append(f"⚔️ {today} 早盘加强档 (9:40 二次扫描)")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"昨晚推送 {len(candidates)} | 早盘扫到 {len(scored)} | 极强 {len(tier_a)} | 强 {len(tier_b)} | 关注 {len(tier_c)}")
    lines.append(f"模型: pm v1.0 (8维 LR), AUC 0.841, T20 98.3%")
    lines.append("")
    
    if tier_a:
        lines.append(f"🔥🔥🔥 极强档 (P_pm≥{P_high}, 历史命中 ≥91%)")
        for s in tier_a:
            lines.append(f"  {s['code']} {s.get('name', ''):8s} P_pm={s['p_pm']:.2f} P_v14={s.get('lr_prob',0):.2f}")
            lines.append(f"     开盘 {s.get('pm_open_pct',0):+.1f}% | 10m高点 {s.get('pm_10m_high_pct',0):+.1f}% | 5m成交 {s.get('pm_5m_amt_yi',0):.1f}亿")
        lines.append("")
    
    if tier_b:
        lines.append(f"🔥 强档 (P_pm≥{P_mid}, 历史命中 ≥86%)")
        for s in tier_b:
            lines.append(f"  {s['code']} {s.get('name', ''):8s} P_pm={s['p_pm']:.2f}")
            lines.append(f"     开盘 {s.get('pm_open_pct',0):+.1f}% | 10m高点 {s.get('pm_10m_high_pct',0):+.1f}%")
        lines.append("")
    
    if tier_c:
        lines.append(f"👀 关注档 (P_pm 0.5-{P_mid})")
        for s in tier_c[:10]:
            lines.append(f"  {s['code']} {s.get('name', ''):8s} P_pm={s['p_pm']:.2f}")
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ 早盘 5m 高点≥5%且开盘高开 → 历史 99-100% 涨停")
    lines.append("⚠️ 不构成投资建议")
    
    msg = '\n'.join(lines)
    print()
    print(msg)
    
    # 落档
    out = WORKSPACE / 'picks' / f'reversal-pm-{today}.json'
    with open(out, 'w') as f:
        json.dump({"date": today, "n_scored": len(scored), "scored": scored, "msg": msg}, f, ensure_ascii=False)
    print(f"\n✅ 落档: {out.name}")


if __name__ == "__main__":
    main()
