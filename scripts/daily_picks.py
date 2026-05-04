#!/usr/bin/env python3
"""
daily_picks.py — 每个交易日北京 17:30 跑 v2.4 评分, 推送候选股到微信

数据源:
  - 主源: 东财涨停池 push2ex.eastmoney.com/getTopicZTPool (含封板时间/封单/连板数)
  - 副源: 东财龙虎榜 (用于陷阱维度)
  - K线: 腾讯 ifzq

用法:
  python3 daily_picks.py                  # 推送当天
  python3 daily_picks.py 2026-04-28       # 重跑指定日期
  python3 daily_picks.py 2026-04-28 dry   # 只预览不发
"""
import json, os, sys, time, urllib.request, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
PICKS_DIR = WORKSPACE / "picks"
PICKS_DIR.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"
BJT = timezone(timedelta(hours=8))
VERSION = "v2.7"  # v2.6 + 一字板剔除 + 主升板块真加分 + 板块资金净流入加分
LR_MODEL_PATH = WORKSPACE / "backtest" / "v25-lr-results-2026-04-28.json"
SECTOR_TREND_PATH = WORKSPACE / "mx_output" / "sector_trend_8day_2026-04-21_to_30.csv"
WENCAI_ZT_DIR = WORKSPACE / "mx_output"  # wencai_zt_<DATE>.csv

WX_CHANNEL = "openclaw-weixin"
WX_ACCOUNT = "ba28cc3242ca-im-bot"
WX_TARGET = "o9cq80ykY28_hN0jDZS8efZ03Aw8@im.wechat"


def is_zt(code, chg):
    if chg is None: return False
    if code.startswith(('300','688')): return chg >= 19.5
    if code.startswith(('8','4','9')): return chg >= 29.5
    return chg >= 9.7


def http_get(url, retries=3, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                txt = r.read().decode("utf-8", errors="replace")
                if not txt.strip(): raise ValueError("empty")
                return json.loads(txt)
        except Exception:
            time.sleep(0.5 + i*0.6)
    return None


def fetch_zt_pool(date):
    d_str = date.replace("-","")
    url=("https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989&"
         f"dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt%3Aasc&date={d_str}")
    d = http_get(url)
    if not d: return []
    pool = d.get("data",{}).get("pool", [])
    return [s for s in pool if s.get("fbt", 0) > 0]


def fetch_lhb(date):
    url=("https://datacenter-web.eastmoney.com/api/data/v1/get?"
         "sortColumns=NET_BS_AMT&sortTypes=-1&pageSize=300&pageNumber=1&"
         "reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&"
         f"filter=(TRADE_DATE%3E%3D%27{date}%27)(TRADE_DATE%3C%3D%27{date}%27)")
    d = http_get(url)
    if not d: return {}
    res = d.get("result") if isinstance(d, dict) else None
    if not isinstance(res, dict): return {}
    by_code={}
    for r in res.get("data") or []:
        c = r.get("SECURITY_CODE")
        if c and c not in by_code: by_code[c] = r
    return by_code


def tx_prefix(code): return "sh" if code.startswith('6') else "sz"

def fetch_k(code, beg, end):
    sym = tx_prefix(code) + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},320,qfq"
    d = http_get(url)
    if not d: return []
    sd = d.get("data",{}).get(sym,{})
    klines = sd.get("qfqday") or sd.get("day") or []
    out = []
    for k in klines:
        if len(k) < 6: continue
        try:
            out.append({"date":k[0],"open":float(k[1]),"close":float(k[2]),
                        "high":float(k[3]),"low":float(k[4]),"vol":float(k[5])})
        except: pass
    for i in range(len(out)):
        if i == 0: out[i]["chg_pct"] = 0.0
        else:
            pc = out[i-1]["close"]
            out[i]["chg_pct"] = (out[i]["close"] - pc)/pc*100 if pc>0 else 0
    return out


def score_v24(zt_rec, lhb_rec, kline, idx, sector_zt_count, market_strength):
    code = zt_rec.get("c","")
    today = kline[idx]
    sc = {}; ft = {}
    
    lbc = zt_rec.get("lbc", 1)
    fbt = zt_rec.get("fbt", 0)
    lbt = zt_rec.get("lbt", 0)
    fund = zt_rec.get("fund", 0)
    ltsz = zt_rec.get("ltsz", 0)
    hs = zt_rec.get("hs", 0)
    zbc = zt_rec.get("zbc", 0)
    hybk = zt_rec.get("hybk", "")
    cap_yi = ltsz / 1e8 if ltsz else 0
    
    ft.update({"lbc":lbc,"fbt":fbt,"lbt":lbt,"fund_yi":round(fund/1e8,2),
               "ltsz_yi":round(cap_yi,1),"hs":round(hs,1),"zbc":zbc,"hybk":hybk})

    # ① 反包/形态
    is_fanbao = False
    if lbc == 1 and idx >= 2:
        prev = kline[idx-1]
        had_zt = any(is_zt(code, kline[j]["chg_pct"]) for j in range(max(0,idx-5), idx-1))
        if had_zt and prev["chg_pct"] < 0: is_fanbao = True
    if lbc >= 3: sc["form"] = 20
    elif is_fanbao: sc["form"] = 16
    elif lbc == 2: sc["form"] = 14
    elif lbc == 1:
        prev = kline[idx-1] if idx>0 else None
        if prev and prev["vol"] > 0 and 0.8 <= today["vol"]/prev["vol"] <= 1.5:
            sc["form"] = 12
        else: sc["form"] = 8
    else: sc["form"] = 4

    # ② 龙虎榜陷阱
    if lhb_rec:
        explain = (lhb_rec.get("EXPLAIN") or lhb_rec.get("EXPLANATION") or "")
        net_amt = lhb_rec.get("BILLBOARD_NET_AMT", 0) or lhb_rec.get("NET_BS_AMT", 0) or 0
        n_inst = explain.count("机构")
        if n_inst >= 3 and net_amt > 5e7: sc["fund_trap"] = -15
        elif n_inst >= 2: sc["fund_trap"] = -10
        elif n_inst == 1 and "买入" in explain: sc["fund_trap"] = -5
        elif "机构" in explain and "卖出" in explain: sc["fund_trap"] = 3
        elif net_amt > 0 and n_inst == 0: sc["fund_trap"] = 5
        else: sc["fund_trap"] = 0
        ft["lhb_explain"] = explain[:60]
    else:
        sc["fund_trap"] = 2

    # ③ 量价关系
    prev = kline[idx-1] if idx>0 else None
    vol_score = 10
    vol_reason = ""
    if prev and prev["vol"] > 0:
        rv = today["vol"] / prev["vol"]
        ft["vol_ratio"] = round(rv, 2)
        prev_chg = prev["chg_pct"]
        if rv < 0.7 and prev_chg > 5: vol_score = 20; vol_reason = "缩量加速"
        elif 0.8 <= rv <= 1.5: vol_score = 16; vol_reason = "温和放量"
        elif 1.5 < rv <= 3: vol_score = 10; vol_reason = "爆量"
        elif rv > 3: vol_score = 5; vol_reason = "天量"
        else: vol_score = 6; vol_reason = "缩量但弱"
    sc["vol"] = vol_score
    ft["vol_reason"] = vol_reason

    # ④ 连板辨识度
    if lbc >= 5: sc["distinct"] = 25
    elif lbc >= 3: sc["distinct"] = 20
    elif lbc == 2: sc["distinct"] = 16
    elif lbc == 1: sc["distinct"] = 12
    else: sc["distinct"] = 5

    # ⑤ 盘子
    if 30 <= cap_yi <= 80: sc["cap"] = 10
    elif 20 <= cap_yi < 30 or 80 < cap_yi <= 150: sc["cap"] = 6
    elif cap_yi < 20 and cap_yi > 0: sc["cap"] = 3
    elif cap_yi > 150: sc["cap"] = 2
    else: sc["cap"] = 4

    # ⑥ 量能
    vr = ft.get("vol_ratio", 1.0)
    if vr < 0.7: sc["volume"] = 5
    elif vr <= 1.5: sc["volume"] = 4
    elif vr <= 2.5: sc["volume"] = 2
    else: sc["volume"] = 0

    # ⑦ 大盘情绪 (相对强度)
    ft["market_strength"] = round(market_strength, 2)
    if market_strength >= 1.5: sc["emotion"] = 10
    elif market_strength >= 1.2: sc["emotion"] = 8
    elif market_strength >= 0.9: sc["emotion"] = 5
    elif market_strength >= 0.7: sc["emotion"] = 3
    else: sc["emotion"] = 1

    # ⑧ 板块梯队
    if sector_zt_count >= 5: sc["sector"] = 15
    elif sector_zt_count >= 3: sc["sector"] = 12
    elif sector_zt_count == 2: sc["sector"] = 8
    else: sc["sector"] = 4
    ft["sector_zt"] = sector_zt_count

    # ⑨ 涨停时间 (NEW)
    if fbt == 0: sc["zt_time"] = 0
    elif fbt <= 92500: sc["zt_time"] = 15
    elif fbt <= 93500: sc["zt_time"] = 14
    elif fbt <= 100000: sc["zt_time"] = 12
    elif fbt <= 103000: sc["zt_time"] = 10
    elif fbt <= 113000: sc["zt_time"] = 7
    elif fbt <= 140000: sc["zt_time"] = 5
    else: sc["zt_time"] = 3
    
    # ⑩ 封单强度 (NEW - 王者!)
    if fund > 0 and ltsz > 0:
        seal_pct = fund / ltsz * 100
        ft["seal_pct"] = round(seal_pct, 2)
        if seal_pct >= 5: sc["seal"] = 10
        elif seal_pct >= 3: sc["seal"] = 8
        elif seal_pct >= 1.5: sc["seal"] = 6
        elif seal_pct >= 0.5: sc["seal"] = 4
        else: sc["seal"] = 1
    else:
        sc["seal"] = 0

    # ⑪ 一字板严格检测 + 严重降权 (一字板买不到)
    p_open = today.get("open", 0)
    p_close = today.get("close", 0)
    p_high = today.get("high", 0)
    p_low = today.get("low", 0)
    is_yizi_strict = False
    if p_open and p_close and p_high and p_low:
        is_yizi_strict = (abs(p_open - p_close) / p_close < 0.005 and
                          abs(p_high - p_low) / p_close < 0.005)
    is_yizi = is_yizi_strict or (fbt == lbt and fbt > 0 and zbc == 0)
    if is_yizi_strict: sc["pure"] = -30  # 一字板买不到, 直接扣 30 分剔除
    elif zbc == 0: sc["pure"] = 4
    elif zbc <= 2: sc["pure"] = 2
    else: sc["pure"] = 0
    ft["is_yizi"] = is_yizi
    ft["is_yizi_strict"] = is_yizi_strict

    return {"scores": sc, "total": sum(sc.values()), "features": ft}


def load_lr_model():
    if not LR_MODEL_PATH.exists(): return None
    try:
        with open(LR_MODEL_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"weights": d["weights"], "bias": d["bias"],
                "means": d["feature_means"], "stds": d["feature_stds"],
                # v3.0: 动态阈值 (旧模型没有这些字段时回退默认)
                "P_high": d.get("P_high", 0.40),
                "P_mid": d.get("P_mid", 0.25),
                "version": d.get("version", "v2.8.3"),
                "ts_avg_auc": d.get("ts_avg_auc", d.get("avg_auc", 0)),
                "trained_at": d.get("trained_at", "")}
    except Exception as e:
        print(f"⚠️ LR 模型加载失败: {e}", flush=True)
        return None


def extract_lr_features(c):
    """v2.8.3: 仅 14 个特征 (Ablation 删除了 13 个噪音, AUC 0.69)"""
    ft = c["features"]
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
    }


def predict_lr(c, model):
    import math
    if not model: return None
    feats = extract_lr_features(c)
    cont_keys = ["lbc", "seal_pct", "hs"]  # v2.8.3
    norm = {}
    for k, v in feats.items():
        if k in cont_keys:
            m = model["means"].get(k, 0)
            s = model["stds"].get(k, 1)
            norm[k] = (v - m) / s if s > 0 else 0
        else:
            norm[k] = v
    z = model["bias"] + sum(model["weights"].get(k, 0) * norm[k] for k in norm)
    if z < -500: return 0.0
    if z > 500: return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def get_today_picks(target_date=None):
    if target_date: date = target_date
    else: date = datetime.now(BJT).strftime("%Y-%m-%d")
    
    print(f"📅 {date} v2.4 评分", flush=True)
    
    # 涨停池 (主源)
    pool = fetch_zt_pool(date)
    if not pool:
        print(f"❌ {date} 涨停池无数据", flush=True)
        return None, date
    print(f"   涨停池: {len(pool)} 只", flush=True)
    
    # 龙虎榜 (副源)
    lhb_today = fetch_lhb(date)
    print(f"   龙虎榜: {len(lhb_today)} 只", flush=True)
    
    # 板块涨停数
    sector_count = Counter(s.get("hybk","unknown") for s in pool)
    
    # 大盘相对强度: 用 60 日均值做基线 (无回测期数据时, 用经验值 30)
    BASELINE = 30  # 历史均值经验值
    market_strength = len(pool) / BASELINE
    
    # 拉 K 线 (近 30 天)
    end_dt = datetime.strptime(date, "%Y-%m-%d")
    beg = (end_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"   拉 K 线...", flush=True)
    klines = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_k, s["c"], beg, end): s["c"] for s in pool}
        for fut in as_completed(futs):
            klines[futs[fut]] = fut.result()
    
    # 评分
    candidates = []
    for s in pool:
        code = s["c"]
        kl = klines.get(code) or []
        if not kl: continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        i = idxmap.get(date)
        if i is None: continue
        sc = score_v24(s, lhb_today.get(code), kl, i,
                       sector_count.get(s.get("hybk","unknown"), 1),
                       market_strength)
        # 一字板 直接剔除 (买不到, 推也是误导)
        if sc["features"].get("is_yizi_strict"):
            continue
        candidates.append({
            "code": code, "name": s.get("n",""),
            "total": sc["total"], "scores": sc["scores"],
            "features": sc["features"],
            "in_lhb": code in lhb_today,
        })
    
    lr_model = load_lr_model()
    if lr_model:
        meta = {"P_high": lr_model["P_high"], "P_mid": lr_model["P_mid"],
                "version": lr_model["version"], "trained_at": lr_model["trained_at"],
                "ts_avg_auc": lr_model["ts_avg_auc"]}
        for c in candidates:
            p = predict_lr(c, lr_model)
            if p is not None:
                c["lr_prob"] = round(p, 4)
            c["_model_meta"] = meta
        candidates.sort(key=lambda x: (-x.get("lr_prob", 0), -x["total"]))
        print(f"   LR: 已加载 {lr_model['version']} ({lr_model['trained_at']}), "
              f"P_high={lr_model['P_high']}, P_mid={lr_model['P_mid']}, "
              f"Top 概率={candidates[0].get('lr_prob', 0):.3f}" if candidates else "无候选", flush=True)
    else:
        candidates.sort(key=lambda x: -x["total"])
    
    # 主升板块加分 (v2.6) — 不改 total/lr_prob, 只加个 tag 供推送显示
    annotate_mainline(candidates, date)
    return candidates, date


def load_mainline_sectors():
    """加载 8 日趋势, 返回 (主升集合, 强势集合)"""
    if not SECTOR_TREND_PATH.exists():
        return set(), set()
    try:
        import csv
        mainline = set()
        strong = set()
        with SECTOR_TREND_PATH.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                top_days = int(row.get('Top20天数', 0) or 0)
                if top_days >= 5: mainline.add(row['板块'])
                if top_days >= 3: strong.add(row['板块'])
        return mainline, strong
    except Exception as e:
        print(f"⚠ 加载主升板块失败: {e}")
        return set(), set()


def load_concepts_for_date(date):
    """加载 wencai_zt_<DATE>.csv, 返回 {code: [concept,...]}"""
    f = WENCAI_ZT_DIR / f'wencai_zt_{date}.csv'
    if not f.exists():
        return {}
    try:
        import csv
        out = {}
        with f.open(encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                code = str(r.get('code') or r.get('股票代码','')).split('.')[0]
                if not code: continue
                concepts_str = r.get('所属概念','') or ''
                out[code] = [c.strip() for c in concepts_str.split(';') if c.strip()]
        return out
    except Exception as e:
        print(f"⚠ 加载概念失败: {e}")
        return {}


def load_sector_today(date):
    """加载当日 sector_strength_<date>.csv, 返回资金净流入 Top 5 板块集合"""
    f = WORKSPACE / "mx_output" / f"sector_strength_{date}.csv"
    if not f.exists():
        return set(), set()
    try:
        import csv
        rows = []
        with f.open(encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                try:
                    zhuli = float(r.get('主力(亿)','0') or 0)
                    score = float(r.get('综合分','0') or 0)
                    rows.append((r['板块'], zhuli, score))
                except: pass
        # 资金净流入 Top 5 = 今日热点
        rows_zhuli = sorted(rows, key=lambda x: x[1], reverse=True)[:5]
        hot_capital = set(r[0] for r in rows_zhuli if r[1] > 0)
        # 综合分 Top 10 = 今日强势
        rows_score = sorted(rows, key=lambda x: x[2], reverse=True)[:10]
        strong_today = set(r[0] for r in rows_score)
        return hot_capital, strong_today
    except Exception as e:
        print(f"⚠ 加载当日板块资金失败: {e}")
        return set(), set()


def annotate_mainline(candidates, date):
    """给候选股加 mainline/strong/hot_capital tags + 真加分"""
    mainline, strong = load_mainline_sectors()
    hot_capital, strong_today = load_sector_today(date)
    if not (mainline or hot_capital):
        return
    concepts = load_concepts_for_date(date)
    n_main = 0
    n_hot = 0
    for c in candidates:
        cs = concepts.get(c['code'], [])
        m_tags = [x for x in cs if x in mainline]
        s_tags = [x for x in cs if x in strong and x not in mainline]
        # 新: 今日资金净流入 Top 5 板块
        h_tags = [x for x in cs if x in hot_capital]
        # 新: 今日综合强势 Top 10
        st_tags = [x for x in cs if x in strong_today and x not in hot_capital]
        # 真加分 (最小幅度, 不胖走个股自身分 — 龙头本身已经高分)
        bonus = 0
        if m_tags: bonus += 3  # 8 日主升
        elif s_tags: bonus += 2  # 8 日强势
        if h_tags: bonus += 2   # 今日资金净流入 Top 5
        if bonus > 0:
            c['scores']['sector_main'] = bonus
            c['total'] = c['total'] + bonus
            c['mainline_tags_score'] = bonus  # 用于推送显示
        c['hot_capital_tags'] = h_tags[:3]
        c['mainline_tags'] = m_tags
        c['strong_tags'] = s_tags[:3]
        if m_tags: n_main += 1
    print(f"   主升板块标记: {n_main}/{len(candidates)} 只股在主升 ({sorted(mainline)})", flush=True)


def fmt_time(fbt):
    if not fbt: return "-"
    h = fbt // 10000
    m = (fbt // 100) % 100
    return f"{h:02d}:{m:02d}"


def format_wechat_msg(candidates, date):
    if not candidates:
        return f"📊 {date} (北京)\n❌ 涨停池无数据"
    
    n = len(candidates)
    has_lr = any("lr_prob" in c for c in candidates)
    
    if has_lr:
        # v3.0: 从 model 读动态阈值 (默认 0.40/0.25 向后兼容)
        model_meta = candidates[0].get("_model_meta", {})
        P_high = model_meta.get("P_high", 0.40)
        P_mid = model_meta.get("P_mid", 0.25)
        if P_high < 0.20 or P_high > 0.85: P_high = 0.40
        if P_mid < 0.10 or P_mid > P_high: P_mid = max(0.25, P_high - 0.15)
        tier_a = [c for c in candidates if c.get("lr_prob", 0) >= P_high]
        tier_b = [c for c in candidates if P_mid <= c.get("lr_prob", 0) < P_high]
        tier_c = [c for c in candidates if 0.15 <= c.get("lr_prob", 0) < P_mid]
        label_a = f"≥ {P_high:.2f} 概率 极强 (胜率≥60%)"
        label_b = f"≥ {P_mid:.2f} 概率 强   (胜率≥50%)"
        label_c = "≥ 0.15 概率 关注"
    else:
        tier_a = [c for c in candidates if c["total"] >= 120]
        tier_b = [c for c in candidates if 110 <= c["total"] < 120]
        tier_c = [c for c in candidates if 100 <= c["total"] < 110]
        label_a = "≥120 分 极强 (胜率60%)"
        label_b = "≥110 分 强   (胜率58%)"
        label_c = "≥100 分 关注 (胜率38%)"
    
    lines = []
    if has_lr:
        mm = candidates[0].get("_model_meta", {})
        ver_tag = mm.get("version", "v2.8.3")
        if mm.get("trained_at"):
            ver_tag += f" ({mm['trained_at']})"
    else:
        ver_tag = "v2.4"
    lines.append(f"📊 {date} A股 {ver_tag} 候选股")
    lines.append(f"━━━━━━━━━━━━━━━━━")
    lines.append(f"涨停: {n} | 极强: {len(tier_a)} | 强: {len(tier_b)} | 关注: {len(tier_c)}")
    # v3.0 模型可信度: P≥P_high 票数越多越可信 (P_high 动态校准)
    if has_lr:
        n_high = len(tier_a)
        if n_high >= 4:
            lines.append(f"🟢 模型可信度高 ({n_high} 只强信号) - 可重仓")
        elif n_high >= 2:
            lines.append(f"🟡 模型可信度中 ({n_high} 只强信号) - 标准仓位")
        elif n_high == 1:
            lines.append(f"🟠 模型可信度偏低 ({n_high} 只强信号) - 减仓观望")
        else:
            lines.append(f"🔴 模型无强信号 - 历史胜率低, 谨慎出手")
    lines.append("")
    
    def render(c, prefix=""):
        ft = c["features"]
        sc = c["scores"]
        lbc = ft.get("lbc", 1)
        fbt = fmt_time(ft.get("fbt", 0))
        fund_yi = ft.get("fund_yi", 0)
        seal_pct = ft.get("seal_pct", 0)
        cap = ft.get("ltsz_yi", 0)
        hybk = ft.get("hybk", "")
        zbc = ft.get("zbc", 0)
        lhb_tag = " 🐉" if c["in_lhb"] else ""
        # 主升板块 tag (v2.6)
        m_tags = c.get('mainline_tags', [])
        s_tags = c.get('strong_tags', [])
        main_tag = " 🔥" if m_tags else (" ⚡" if s_tags else "")
        prob = c.get("lr_prob")
        prob_str = f" 📊{prob:.2f}" if prob is not None else ""
        
        out = [f"{prefix}{c['code']} {c['name']} {c['total']}分{prob_str}{lhb_tag}{main_tag}"]
        feat_parts = [f"{lbc}板", fbt]
        if fund_yi >= 0.5: feat_parts.append(f"封{fund_yi:.1f}亿")
        if seal_pct >= 0.5: feat_parts.append(f"占{seal_pct:.1f}%")
        if cap >= 1: feat_parts.append(f"{cap:.0f}亿盘")
        if hybk: feat_parts.append(hybk[:6])
        if zbc > 0: feat_parts.append(f"⚠️{zbc}炸")
        out.append(f"   {' | '.join(feat_parts)}")
        # 主升板块详情 (只在有时显示)
        if m_tags:
            out.append(f"   🔥主升: {'/'.join(m_tags[:3])}")
        elif s_tags:
            out.append(f"   ⚡强势: {'/'.join(s_tags[:2])}")
        out.append(f"   形{sc.get('form',0)}/辨{sc.get('distinct',0)}/时{sc.get('zt_time',0)}/封{sc.get('seal',0)}/价{sc.get('vol',0)}")
        return out
    
    if tier_a:
        lines.append(f"🔥🔥 {label_a}")
        for c in tier_a[:5]:
            lines.extend(render(c, "⭐⭐⭐⭐⭐ "))
        lines.append("")
    
    if tier_b:
        lines.append(f"🔥 {label_b}")
        for c in tier_b[:5]:
            lines.extend(render(c, "⭐⭐⭐⭐ "))
        lines.append("")
    
    if tier_c:
        lines.append(f"🟠 {label_c}")
        for c in tier_c[:5]:
            lines.extend(render(c, "⭐⭐⭐ "))
        lines.append("")
    
    if not tier_a and not tier_b and not tier_c:
        lines.append("⚠️ 今日无强信号票, TOP 5:")
        for c in candidates[:5]:
            prob_str = f" 概{c.get('lr_prob', 0):.2f}" if has_lr else ""
            lines.append(f"  {c['code']} {c['name']} {c['total']}分{prob_str}")
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━")
    if has_lr:
        if has_lr:
            mm = candidates[0].get("_model_meta", {})
            ts_auc = mm.get("ts_avg_auc", 0)
            auc_tag = f"时序 AUC={ts_auc:.2f}" if ts_auc else "AUC=?"
            lines.append(f"💡 v3.0+v2.7: 评分+LR+滚动retrain+🔥主升板块+💰资金净流入 ({auc_tag})")
        else:
            lines.append(f"💡 v2.7: 评分 + LR概率 + 🔥主升板块 + 💰资金净流入")
    else:
        lines.append(f"💡 v2.4 11维 (满分~135) | 封单强度+涨停时间为关键")
    lines.append(f"🐉=同时上龙虎榜 | ⚠️=有炸板 | 📊=LR预测概率")
    lines.append(f"⚠️ 不构成投资建议, 次日开盘前人工二次确认")
    
    return "\n".join(lines)


def send_email_backup(msg, subject_prefix="【候选股】"):
    """发 QQ 邮件备份 (双通道并行中的邮件部分)"""
    try:
        from pathlib import Path as _P
        from datetime import datetime as _dt
        body_file = _P("/tmp/daily_picks_email.txt")
        # 邮件主体加个头 (说明这是双发备份)
        header = f"本邮件为 A 股候选股双通道邮件留底 ({_dt.now().strftime('%Y-%m-%d %H:%M')} PDT)\n微信那边已同步推送, 邮件为万一防微信丢信的备份\n\n"
        body_file.write_text(header + msg, encoding="utf-8")
        qq_send = _P("/Users/openclaw/.openclaw/workspace-dengxian/qq-send.js")
        if not qq_send.exists():
            print(f"⚠️ qq-send.js 不存在, 跳过邮件备份", flush=True)
            return False
        # 从正文抽取当日主题 (第 1 行)
        first_line = msg.split("\n")[0][:40] if msg else "候选股"
        subject = f"{subject_prefix} {first_line}"
        r = subprocess.run(["node", str(qq_send),
                            "--to", "1628354330@qq.com",
                            "--subject", subject,
                            "--bodyFile", str(body_file)],
                          capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            print(f"📧 邮件备份成功 → 1628354330@qq.com", flush=True)
            return True
        else:
            print(f"❌ 邮件备份失败 rc={r.returncode}: {r.stderr[-200:]}", flush=True)
            return False
    except Exception as e:
        print(f"❌ 邮件备份异常: {e}", flush=True)
        return False


def send_wechat(msg):
    """发微信, 三重重试; 以 messageId 存在作为成功标识"""
    cmd = ["openclaw", "message", "send",
           "--channel", WX_CHANNEL,
           "--account", WX_ACCOUNT,
           "--target", WX_TARGET,
           "--message", msg,
           "--json"]
    last_err = ""
    msg_ids = []
    for attempt in range(1, 4):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            # 解析 JSON 拿 messageId
            mid = None
            if result.returncode == 0:
                try:
                    # stdout 有可能包含 warnings + JSON, 提取最后的 JSON
                    import re
                    m = re.search(r'\{[\s\S]*\}', result.stdout)
                    if m:
                        d = json.loads(m.group(0))
                        mid = d.get("payload", {}).get("result", {}).get("messageId")
                except Exception:
                    pass
            if mid:
                print(f"✅ 微信推送成功 (第{attempt}次) mid={mid}", flush=True)
                msg_ids.append(mid)
                from datetime import datetime as _dt
                sentinel = WORKSPACE / "picks" / "last_push.txt"
                sentinel.write_text(f"{_dt.now().strftime('%Y-%m-%d %H:%M:%S')} OK mid={mid}\n")
                return True
            last_err = f"rc={result.returncode} no_messageId | stdout={result.stdout[-300:]}"
            print(f"⚠️ 推送未确认 (第{attempt}次): {last_err}", flush=True)
        except Exception as e:
            last_err = f"exception: {e}"
            print(f"⚠️ 推送异常 (第{attempt}次): {e}", flush=True)
        if attempt < 3:
            import time as _t
            _t.sleep(8)  # 给微信网桥一些恢复时间
    
    print(f"❌ 微信推送失败 (3次重试): {last_err}", flush=True)
    # 微信完全失败时主题加 "⚠️微信未送达" 提醒
    send_email_backup(msg, subject_prefix="【⚠️微信未送达】A股候选股")
    return False


def save_log(candidates, date, msg):
    p = PICKS_DIR / f"{date}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "date": date,
                   "candidates": candidates, "msg": msg},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"   📁 落档: {p}", flush=True)


def main():
    target_date = None
    dry_run = False
    for a in sys.argv[1:]:
        if a == "dry": dry_run = True
        elif a.startswith("20"): target_date = a
    
    candidates, date = get_today_picks(target_date)
    if candidates is None:
        sys.exit(1)
    
    msg = format_wechat_msg(candidates, date)
    print("\n" + "="*60, flush=True)
    print(msg, flush=True)
    print("="*60 + "\n", flush=True)
    save_log(candidates, date, msg)
    
    if dry_run:
        print("📭 dry-run, 跳过推送", flush=True)
        sys.exit(0)
    
    # v3.0 双通道: 微信 + 邮件并行 (Dengxian 2026-04-29 同意的新规)
    wx_ok = send_wechat(msg)
    # 微信成功也发邮件 (平衡微信间歇丢信风险, 邮件作为另一个送达保障)
    if wx_ok:
        send_email_backup(msg, subject_prefix="【候选股】")
    if not wx_ok:
        sys.exit(1)
    sys.exit(0 if candidates else 2)


if __name__ == "__main__":
    main()
