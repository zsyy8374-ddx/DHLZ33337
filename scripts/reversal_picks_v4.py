#!/usr/bin/env python3
"""
reversal_picks_v4.py — 涨停回马枪每日推送 (v0.4 修复泄漏)

v0.4 关键修复:
  - 资金流统一用 D0+1 到 D0+5 窗口 (cb5)
  - 不依赖 D_t (避免 window-leak)

逻辑:
  1. 找出最近 2-10 个交易日内涨停过的所有股票 (D0)
  2. 用腾讯 K 线算回调期形态特征 (callback_pct, MA, vol_ratio, 连板)
  3. 用新浪资金流补主力大单数据 (D0 当日 + 回调期)
  4. v0.3 LR 预测 → 按 P_high/P_mid 分档
  5. 推送微信 + 邮件

用法:
  python3 reversal_picks_v4.py            # 今日
  python3 reversal_picks_v4.py 2026-04-29 # 历史
  python3 reversal_picks_v4.py 2026-04-29 dry  # 不推送
"""
import json, time, sys, subprocess, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
BACKTEST_DIR = WORKSPACE / "backtest"
PICKS_DIR = WORKSPACE / "picks"
PICKS_DIR.mkdir(exist_ok=True)
BJT = timezone(timedelta(hours=8))

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


def http_get(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", errors="ignore")
            if data.startswith("v="):
                data = data[2:].rstrip(";")
            return data
    except Exception:
        return None


def http_get_json(url, timeout=10):
    data = http_get(url, timeout=timeout)
    if not data: return None
    try:
        return json.loads(data) if data.strip().startswith(("{", "[")) else None
    except Exception:
        return None


def is_zt(code, chg):
    if code.startswith(('300', '688')): return chg >= 19.5
    if code.startswith(('8', '4', '9')): return chg >= 29.5
    return chg >= 9.7


def fetch_kline(code, beg, end, lookback=130):
    sym = ("sh" if code.startswith('6') else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},{lookback},qfq"
    d = http_get_json(url)
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


def fetch_zt_pool(date):
    url = (f"http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989"
           f"&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt%3Aasc&date={date.replace('-','')}")
    d = http_get_json(url)
    if not d: return []
    return [{"code": it.get("c"), "name": it.get("n"), "date": date}
            for it in d.get("data", {}).get("pool", [])]


def fetch_sina_fflow(code, num=120):
    """新浪资金流"""
    prefix = "sh" if code.startswith('6') else "sz"
    url = (f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={num}&sort=opendate&asc=0&daima={prefix}{code}")
    data = http_get(url, timeout=8)
    if not data or not data.startswith("[{"):
        return {}
    try:
        items = json.loads(data)
        out = {}
        for it in items:
            date = it.get("opendate")
            if not date: continue
            try:
                out[date] = {
                    "net": float(it.get("netamount") or 0),
                    "main_net": float(it.get("r0_net") or 0),
                    "main_ratio": float(it.get("r0_ratio") or 0),
                    "main_strength": float(it.get("r0x_ratio") or 0),
                    "chg": float(it.get("changeratio") or 0) * 100,
                }
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        return {}


def calc_ma(klines, idx, period):
    if idx < period - 1: return None
    return sum(float(klines[i][2]) for i in range(idx-period+1, idx+1)) / period


def get_d0_features(code, klines, fflow, end_date):
    """对一只票, 找最近 2-10 天前的涨停日 D0, 算所有特征"""
    if not klines or len(klines) < 30:
        return None
    
    # 找 today_idx
    today_idx = None
    for i, k in enumerate(klines):
        if k[0] == end_date:
            today_idx = i; break
    if today_idx is None:
        today_idx = len(klines) - 1
        end_date = klines[-1][0]
    
    best = None
    for back in range(2, 11):
        d0_idx = today_idx - back
        if d0_idx < 20: continue
        k = klines[d0_idx]
        if len(k) < 6: continue
        c = float(k[2]); pc = float(klines[d0_idx-1][2])
        if pc <= 0: continue
        chg = (c - pc) / pc * 100
        if not is_zt(code, chg): continue
        
        d0_close = c
        d0_vol = float(k[5])
        ma5_d0 = calc_ma(klines, d0_idx, 5)
        ma10_d0 = calc_ma(klines, d0_idx, 10)
        d0_date = k[0]
        
        # 排除期间又涨停过的
        already_zt = False
        for j in range(d0_idx + 1, today_idx + 1):
            jk = klines[j]
            j_c = float(jk[2]); j_pc = float(klines[j-1][2])
            if j_pc > 0 and is_zt(code, (j_c - j_pc) / j_pc * 100):
                already_zt = True; break
        if already_zt: continue
        
        # 回调期统计
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
        
        min_close_pct = (d0_close - min_close) / d0_close * 100 if d0_close > 0 else 0
        if min_close_pct > 18: continue  # 跌太狠
        
        # 连板数 (D0 倒数算)
        lbc = 1
        for back2 in range(1, 8):
            idx2 = d0_idx - back2
            if idx2 < 1: break
            kk = klines[idx2]
            cc = float(kk[2]); pcc = float(klines[idx2-1][2])
            if pcc <= 0: break
            chg2 = (cc - pcc) / pcc * 100
            if is_zt(code, chg2):
                lbc += 1
            else:
                break
        
            # 资金流特征 v0.4: 统一用 D0+1 到 D0+k 窗口 (不依赖 D_t)
        d0_main_flow = 0.0
        cb1_main_avg = 0.0; cb3_main_avg = 0.0
        cb5_main_avg = 0.0; cb5_in_ratio = 0.0
        pre_d0_5d_main_avg = 0.0
        if fflow:
            sorted_dates = sorted(fflow.keys())
            if d0_date in sorted_dates:
                d0_idx_f = sorted_dates.index(d0_date)
                if d0_date in fflow:
                    d0_main_flow = fflow[d0_date]["main_net"] / 1e8
                # 统一窗口 cb1 / cb3 / cb5
                for kk in [1, 3, 5]:
                    end_f_idx = min(d0_idx_f + kk, len(sorted_dates) - 1)
                    win_dates = sorted_dates[d0_idx_f + 1:end_f_idx + 1]
                    if win_dates:
                        nets = [fflow[d]["main_net"] for d in win_dates if d in fflow]
                        if nets:
                            avg = sum(nets) / len(nets) / 1e8
                            if kk == 1: cb1_main_avg = avg
                            elif kk == 3: cb3_main_avg = avg
                            else:
                                cb5_main_avg = avg
                                cb5_in_ratio = sum(1 for v in nets if v > 0) / len(nets)
                # D0 前 5 天
                pre5 = sorted_dates[max(0, d0_idx_f - 5):d0_idx_f]
                if pre5:
                    pre5_nets = [fflow[d]["main_net"] for d in pre5 if d in fflow]
                    if pre5_nets:
                        pre_d0_5d_main_avg = sum(pre5_nets) / len(pre5_nets) / 1e8
        
        candidate = {
            "code": code,
            "d0_date": d0_date,
            "d0_close": round(d0_close, 3),
            "d0_chg": round(chg, 2),
            "days_since_d0": back,
            "today_close": round(float(klines[today_idx][2]), 3),
            "callback_pct": round(callback_pct, 2),
            "min_close_pct": round(min_close_pct, 2),
            "broke_ma5": broke_ma5,
            "broke_ma10": broke_ma10,
            "vol_callback_ratio": round(sum(vols) / len(vols) / d0_vol, 3) if vols and d0_vol > 0 else 0,
            "d0_lbc": lbc,
            "d0_main_flow": round(d0_main_flow, 4),
            "cb1_main_avg": round(cb1_main_avg, 4),
            "cb3_main_avg": round(cb3_main_avg, 4),
            "cb5_main_avg": round(cb5_main_avg, 4),
            "cb5_in_ratio": round(cb5_in_ratio, 3),
            "pre_d0_5d_main_avg": round(pre_d0_5d_main_avg, 4),
        }
        if best is None or back < best["days_since_d0"]:
            best = candidate
    
    return best


def extract_v4(c):
    callback = c.get("callback_pct", 0) or 0
    min_close = c.get("min_close_pct", 0) or 0
    vol_ratio = c.get("vol_callback_ratio", 0) or 0
    d0_chg = c.get("d0_chg", 10) or 10
    lbc = c.get("d0_lbc", 1) or 1
    cb5_main = c.get("cb5_main_avg", 0) or 0
    cb5_in = c.get("cb5_in_ratio", 0) or 0
    cb3_main = c.get("cb3_main_avg", 0) or 0
    cb1_main = c.get("cb1_main_avg", 0) or 0
    d0_main = c.get("d0_main_flow", 0) or 0
    pre_avg = c.get("pre_d0_5d_main_avg", 0) or 0
    
    return {
        "callback_pct": callback,
        "min_close_pct": min_close,
        "broke_ma5": 1.0 if c.get("broke_ma5") else 0.0,
        "broke_ma10": 1.0 if c.get("broke_ma10") else 0.0,
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
        "cb5_in_high": 1.0 if cb5_in >= 0.6 else 0.0,
        "cb5_in_low": 1.0 if cb5_in < 0.4 else 0.0,
        "cb5_main_avg": cb5_main,
        "cb3_main_avg": cb3_main,
        "cb1_main_avg": cb1_main,
        "d0_main_flow": d0_main,
        "pre_d0_5d_main_avg": pre_avg,
    }


def fetch_market_style(end_date):
    """拉市场风格指标: 上证 5 日、创业板 5 日、两者差 (cy-sh)。到 end_date 为止 (不含 D0)
    + 今日三大指数单日涨跌 + 极端分化检测 (4-30 复盘新增)
    """
    style = {"sh_5d": None, "cy_5d": None, "cy_sh_diff": None,
             "sh_1d": None, "cy_1d": None, "kc_1d": None,
             "index_spread_1d": None, "extreme_split": False}
    
    def fetch_idx(sym):
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,{end_date},20,qfq"
        d = http_get_json(url)
        if not d: return []
        klines = d.get("data", {}).get(sym, {}).get("day", []) or []
        return [(k[0], float(k[2])) for k in klines if len(k) >= 3]
    
    sh = fetch_idx("sh000001")
    cy = fetch_idx("sz399006")
    kc = fetch_idx("sh000688")
    
    if len(sh) >= 6:
        style["sh_5d"] = round((sh[-1][1] - sh[-6][1]) / sh[-6][1] * 100, 3)
    if len(cy) >= 6:
        style["cy_5d"] = round((cy[-1][1] - cy[-6][1]) / cy[-6][1] * 100, 3)
    if style["sh_5d"] is not None and style["cy_5d"] is not None:
        style["cy_sh_diff"] = round(style["cy_5d"] - style["sh_5d"], 3)
    
    # 单日涨跌 (最后一根 vs 上一根)
    def last1d(rows):
        if len(rows) >= 2:
            return round((rows[-1][1] - rows[-2][1]) / rows[-2][1] * 100, 3)
        return None
    style["sh_1d"] = last1d(sh)
    style["cy_1d"] = last1d(cy)
    style["kc_1d"] = last1d(kc)
    style["market_regime"] = "normal"
    
    # 三大指数状态分类 (基于 1151 事件 + 120 天指数回测)
    sh1 = style["sh_1d"] or 0
    sz1 = style["cy_1d"] or 0
    kc1 = style["kc_1d"] or 0
    one_d = [sh1, sz1, kc1]
    if all(v is not None for v in [style["sh_1d"], style["cy_1d"], style["kc_1d"]]):
        spread = max(one_d) - min(one_d)
        style["index_spread_1d"] = round(spread, 3)
        avg = (sh1 + sz1 + kc1) / 3
        
        # 科创独红 (历史 2.6% 反转率, 极险)
        if kc1 > 2 and sh1 < 0.5:
            style["extreme_split"] = True
            style["market_regime"] = "kc_only_red"
        # 主板独红 (历史 12.5% 反转率, 险)
        elif sh1 > 0.5 and sz1 < -0.3 and kc1 < -0.3:
            style["market_regime"] = "sh_only_red"
            style["extreme_split"] = True  # 也当极端分化处理
        # 创业板独红 (历史 80% 反转率, 佳)
        elif sz1 > 2 and sh1 < 0.5:
            style["market_regime"] = "sz_only_red"
        # 大幅分化 (spread > 4) 普涨型 (历史 2.6%, 极险)
        elif spread > 4 and avg > 0:
            style["market_regime"] = "spread_high_up"
            style["extreme_split"] = True
        # 共振小跌 (spread<1 + avg<=-0.5, 历史 37.5%, 偏差)
        elif spread < 1 and avg <= -0.5:
            style["market_regime"] = "weak_resonant"
        # 共振小涨 (spread<1 + avg>=0.5, 历史 64.6%, 优)
        elif spread < 1 and avg >= 0.5:
            style["market_regime"] = "strong_resonant"
    
    return style


def style_boost(c, style):
    """根据市场风格 + 4-30 复盘发现为 P 加减分
    
    严谨 5 折验证过的规则:
    R1: 弱势市 (sh_5d ≤ -1%) + cb5 ≥2亿 → +0.10 (历史 93.5%)
    R3: 大盘风 (cy-sh ≤ -1%) + 1板 → +0.05 (59% vs 44%)
    R6 (4-30 复盘新): cb1 ≥1亿 → -0.05 (5折 AUC +0.004, 4/5 fold 正向, T10 +2pp)
         说明: cb1 = D0+1 主力日均。过高 = 主力次日快速出货信号
    """
    boost = 0.0
    
    # R1, R3 需要 style
    if style and style.get("sh_5d") is not None:
        sh_5d = style.get("sh_5d", 0)
        diff = style.get("cy_sh_diff", 0) or 0
        cb5 = c.get("cb5_main_avg", 0) or 0
        lbc = c.get("d0_lbc", 1) or 1
        
        if sh_5d <= -1 and cb5 >= 2:
            boost += 0.10
        if diff <= -1 and lbc == 1:
            boost += 0.05
    
    # R6: cb1 过大 (不需 style, 独立生效)
    cb1 = c.get("cb1_main_avg", 0) or 0
    if cb1 >= 1:
        boost -= 0.05
    
    # v0.6 8 类 regime 调权 (历史 1151 事件 + bootstrap 200 trials 验证)
    # AUC 平均改善 +0.035, 5% 分位 +0.021, 200/200 正向
    if style:
        regime = style.get("market_regime", "normal")
        lbc = c.get("d0_lbc", 1) or 1
        
        if regime in ("kc_only_red", "spread_high_up"):  # 2.6%
            if lbc >= 3: boost -= 0.40
            elif lbc >= 2: boost -= 0.30
            else: boost -= 0.15
        elif regime == "sh_only_red":  # 12.5%
            if lbc >= 3: boost -= 0.30
            elif lbc >= 2: boost -= 0.20
            else: boost -= 0.08
        elif regime == "all_green_strong":  # 37.8% 齐跌强
            boost -= 0.10
        elif regime == "all_green_weak":  # 齐跌弱, 微压
            boost -= 0.05
        elif regime == "all_red_strong":  # 62.9% 齐涨强
            boost += 0.05
        elif regime == "all_red_weak":  # 齐涨弱, 中性
            boost += 0
        elif regime == "sz_only_red":  # 80%
            boost += 0.05
    
    return boost


def detect_regime_v5(style):
    """从 market style 判断 8 类 regime (v0.6 升级)
    
    历史 1151 事件 反转率:
      kc_only_red       2.6% ⚠️极险
      spread_high_up    2.6% ⚠️极险
      sh_only_red      12.5% ⚠️险
      all_green_strong 37.8% 偏差 (n=312)
      all_green_weak   ~50%  中性
      all_red_weak     55.6% 中性 (n=18)
      normal           61.6% 正常
      all_red_strong   62.9% 优 (n=437)
      sz_only_red      80.0% ⚡佳
    """
    if not style: return "normal"
    sh = style.get("sh_1d", 0) or 0
    sz = style.get("cy_1d", 0) or 0
    kc = style.get("kc_1d", 0) or 0
    if sh == 0 and sz == 0 and kc == 0: return "normal"
    spread = max(sh, sz, kc) - min(sh, sz, kc)
    avg = (sh + sz + kc) / 3
    # 极端 (高优先)
    if kc > 2 and sh < 0.5: return "kc_only_red"
    if sh > 0.5 and sz < -0.3 and kc < -0.3: return "sh_only_red"
    if sz > 2 and sh < 0.5: return "sz_only_red"
    if spread > 4 and avg > 0: return "spread_high_up"
    # 整体方向 (中优先)
    if sh <= 0 and sz <= 0 and kc <= 0:
        return "all_green_strong" if avg <= -0.5 else "all_green_weak"
    if sh >= 0 and sz >= 0 and kc >= 0:
        return "all_red_strong" if avg >= 0.5 else "all_red_weak"
    return "normal"  # 涨跌混合 = 正常


def extract_v5(c, regime):
    """v0.5 特征 = v0.4 + 8 类 regime dummies + interaction"""
    f = extract_v4(c)
    f["reg_kc_red"] = 1.0 if regime == "kc_only_red" else 0.0
    f["reg_sh_red"] = 1.0 if regime == "sh_only_red" else 0.0
    f["reg_sz_red"] = 1.0 if regime == "sz_only_red" else 0.0
    f["reg_spread_up"] = 1.0 if regime == "spread_high_up" else 0.0
    f["reg_all_green_strong"] = 1.0 if regime == "all_green_strong" else 0.0
    f["reg_all_green_weak"] = 1.0 if regime == "all_green_weak" else 0.0
    f["reg_all_red_strong"] = 1.0 if regime == "all_red_strong" else 0.0
    f["reg_all_red_weak"] = 1.0 if regime == "all_red_weak" else 0.0
    lbc = c.get("d0_lbc", 1) or 1
    f["reg_kc_lianban"] = 1.0 if regime == "kc_only_red" and lbc >= 2 else 0.0
    f["reg_spread_lianban"] = 1.0 if regime == "spread_high_up" and lbc >= 2 else 0.0
    f["reg_sz_lianban"] = 1.0 if regime == "sz_only_red" and lbc >= 2 else 0.0
    f["reg_green_lianban"] = 1.0 if regime == "all_green_strong" and lbc >= 2 else 0.0
    f["reg_red_lianban"] = 1.0 if regime == "all_red_strong" and lbc >= 2 else 0.0
    return f


def predict_lr(c, model, regime="normal"):
    """兼容 v4 / v5 模型"""
    if model.get("regime_used"):
        f = extract_v5(c, regime)
    else:
        f = extract_v4(c)
    means = model["feature_means"]; stds = model["feature_stds"]
    cont_keys = model["cont_keys"]
    fn = {}
    for k, v in f.items():
        if k in cont_keys:
            fn[k] = (v - means.get(k, 0)) / stds.get(k, 1)
        else:
            fn[k] = v
    z = model["bias"] + sum(model["weights"][k] * fn.get(k, 0) for k in model["weights"])
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def get_candidates(end_date):
    """主流程: 抓近 14 天涨停池 → 拉 K 线 + 资金流 → 算特征"""
    print(f"📊 扫描近 2-10 天涨停过的股票 (基准日 {end_date})...", flush=True)
    
    codes_set = set()
    name_map = {}
    for back in range(0, 14):
        d_str = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=back)).strftime("%Y-%m-%d")
        zt_pool = fetch_zt_pool(d_str)
        for it in zt_pool:
            codes_set.add(it["code"])
            name_map[it["code"]] = it["name"]
        time.sleep(0.05)
    
    codes = sorted(codes_set)
    print(f"   候选池: {len(codes)} 只", flush=True)
    
    beg = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=130)).strftime("%Y-%m-%d")
    candidates = []
    
    for i, code in enumerate(codes):
        klines, name = fetch_kline(code, beg, end_date, lookback=130)
        if not name:
            name = name_map.get(code, "?")
        if not klines or len(klines) < 30:
            continue
        
        # 资金流
        fflow = fetch_sina_fflow(code, num=60)
        time.sleep(0.05)
        
        cand = get_d0_features(code, klines, fflow, end_date)
        if cand:
            cand["name"] = name
            candidates.append(cand)
        
        if (i + 1) % 50 == 0:
            print(f"   [{i+1}/{len(codes)}] 候选 {len(candidates)}", flush=True)
    
    print(f"   通过初筛: {len(candidates)} 只", flush=True)
    return candidates


def format_msg(candidates, model, date):
    P_high = model["P_high"]; P_mid = model["P_mid"]
    
    if not candidates:
        return f"⚔️ {date} 涨停回马枪 v0.4\n❌ 无候选"
    
    candidates.sort(key=lambda x: -x["lr_prob"])
    
    tier_a = [c for c in candidates if c["lr_prob"] >= P_high]
    tier_b = [c for c in candidates if P_mid <= c["lr_prob"] < P_high]
    tier_c = [c for c in candidates if 0.6 <= c["lr_prob"] < P_mid]
    
    lines = []
    lines.append(f"⚔️ {date} 涨停回马枪 (v0.4 修复泄漏, 统一 cb5 窗口)")
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append(f"候选 {len(candidates)} | 极强 {len(tier_a)} | 强 {len(tier_b)} | 关注 {len(tier_c)}")
    lines.append(f"模型: 时序 AUC {model['ts_auc']:.2f}, Top10% 命中 {model['top10_hit']*100:.0f}%")
    lines.append("")
    
    def render(c):
        out = [f"{c['code']} {c['name']} 📊{c['lr_prob']:.2f}"]
        out.append(f"   D0={c['d0_date']}({c['days_since_d0']}天前) {c['d0_chg']:.1f}% {c.get('d0_lbc',1)}板")
        feat = []
        feat.append(f"回调{c['callback_pct']:.1f}%")
        feat.append(f"跌{c['min_close_pct']:.1f}%")
        feat.append("守MA5" if not c['broke_ma5'] else "破MA5")
        # 资金流
        cb5 = c.get('cb5_main_avg', 0)
        flow_tag = ""
        if cb5 >= 2: flow_tag = f"💰主力{cb5:.1f}亿/日"
        elif cb5 >= 0.5: flow_tag = f"主力+{cb5:.2f}亿/日"
        elif cb5 < -0.5: flow_tag = f"⚠️主力{cb5:.2f}亿/日(反指)"
        if flow_tag: feat.append(flow_tag)
        cb5_ratio = c.get('cb5_in_ratio', 0)
        if cb5_ratio >= 0.6: feat.append("🔴多日连购")
        out.append(f"   {' | '.join(feat)}")
        return out
    
    if tier_a:
        lines.append(f"🔥🔥🔥 极强档 (P≥{P_high}, 历史胜率 ≥85%)")
        for c in tier_a[:10]:
            lines.extend(render(c))
        lines.append("")
    
    if tier_b:
        lines.append(f"🔥 强档 (P≥{P_mid}, 历史胜率 ≥70%)")
        for c in tier_b[:10]:
            lines.extend(render(c))
        lines.append("")
    
    if tier_c and not tier_a:
        lines.append(f"🟡 关注档 (P≥0.6)")
        for c in tier_c[:10]:
            lines.extend(render(c))
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append(f"💡 v0.4: 形态+连板+cb5 主力大单, 真实 AUC 0.77, Top10% 91%")
    lines.append(f"⚠️ 不构成投资建议, 自行二次确认")
    return "\n".join(lines)


def send_wechat(msg):
    import re
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL, "--account", WX_ACCOUNT,
           "--target", WX_TARGET, "--message", msg, "--json"]
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
                    except Exception: pass
            if mid:
                print(f"✅ 微信推送成功 (第{retry+1}次) mid={mid}", flush=True)
                return True
            print(f"⚠️ 微信 #{retry+1}: {r.stderr[-200:]}", flush=True)
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ 异常 #{retry+1}: {e}", flush=True)
            time.sleep(2)
    return False


def send_email(msg, date):
    body_path = f"/tmp/reversal-v4-{date}.txt"
    with open(body_path, "w", encoding="utf-8") as f:
        f.write(msg)
    try:
        r = subprocess.run(
            ["node", str(WORKSPACE / "qq-send.js"),
             "--to", "1628354330@qq.com",
             "--subject", f"⚔️ 回马枪 v0.4 {date}",
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
    
    # 优先找 v0.5 模型, fallback v0.4
    cands_v5 = sorted(BACKTEST_DIR.glob("reversal-lr-*-v5.json"), reverse=True)
    cands_v4 = sorted(BACKTEST_DIR.glob("reversal-lr-*-v4.json"), reverse=True)
    if cands_v5:
        model_path = cands_v5[0]
    elif cands_v4:
        model_path = cands_v4[0]
    else:
        print("❌ 没有模型, 请先跑 reversal_lr_v5.py 或 v4", flush=True)
        sys.exit(1)
    
    with open(model_path, encoding="utf-8") as f:
        model = json.load(f)
    print(f"📦 加载模型: {model_path.name} (regime_used={model.get('regime_used', False)})", flush=True)
    print(f"   时序 AUC: {model['ts_auc']:.4f}, Top10%: {model['top10_hit']*100:.1f}%", flush=True)
    print(f"   阈值: P_high={model['P_high']}, P_mid={model['P_mid']}", flush=True)
    
    # 拉市场风格指标
    print("🌍 拉市场风格...", flush=True)
    style = fetch_market_style(target_date)
    print(f"   上证 5日: {style.get('sh_5d')}%, 创业 5日: {style.get('cy_5d')}%, 差异: {style.get('cy_sh_diff')}%", flush=True)
    sh_5d = style.get("sh_5d") or 0
    diff = style.get("cy_sh_diff") or 0
    if sh_5d <= -1: stype1 = "弱势"
    elif sh_5d >= 1: stype1 = "强势"
    else: stype1 = "震荡"
    if diff <= -1: stype2 = "大盘风"
    elif diff >= 1: stype2 = "小盘风"
    else: stype2 = "均衡"
    print(f"   风格: {stype1} + {stype2}", flush=True)
    
    candidates = get_candidates(target_date)
    if not candidates:
        print("❌ 无候选", flush=True)
        sys.exit(1)
    
    # 检测今日市场 regime
    regime = detect_regime_v5(style)
    print(f"🌺 今日 regime: {regime}", flush=True)
    
    # LR 预测: regime 进入 model + post-hoc 调权
    for c in candidates:
        base = predict_lr(c, model, regime=regime)
        boost = style_boost(c, style)  # 含 6 类 regime post-hoc 调权
        c["lr_prob_base"] = round(base, 4)
        c["lr_prob_boost"] = round(boost, 4)
        c["market_regime"] = regime
        # v0.5 联合使用 base + post-hoc boost
        if model.get("regime_used"):
            adjusted = base + boost
            c["lr_prob"] = round(min(0.99, max(0.01, adjusted)), 4)
            c["lr_prob_with_boost"] = c["lr_prob"]
        else:
            # v0.4 fallback: 纯 base
            c["lr_prob_with_boost"] = round(min(0.99, max(0.01, base + boost)), 4)
            c["lr_prob"] = round(base, 4)
    
    # 落档
    save_path = PICKS_DIR / f"reversal-v4-{target_date}.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump({"date": target_date, "model_version": model["version"],
                   "market_style": style, "style_label": f"{stype1}+{stype2}",
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
