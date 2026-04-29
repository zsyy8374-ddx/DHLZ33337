#!/usr/bin/env python3
"""
backtest_v24.py — v2.4 重大升级

数据源升级:
  - 主源从龙虎榜 → 东财涨停池 (push2ex.eastmoney.com/getTopicZTPool)
  - 直接拿: 封板时间(fbt)/封单金额(fund)/连板数(lbc)/真实板块(hybk)/换手率(hs)/炸板数(zbc)
  - 候选股池扩大 2-3 倍 (覆盖全市场涨停, 不只龙虎榜)

v2.3 → v2.4 维度变化:
  ① 反包/形态 (20分)            保持, 但 lbc 取代 K 线推算
  ② 龙虎榜陷阱 (-15~+5分)        保持 (龙虎榜数据另接)
  ③ 量价关系 (20分)              保持
  ④ 连板辨识度 (25分)            保持
  ⑤ 盘子 (10分)                 保持
  ⑥ 量能 (5分)                  保持
  ⑦ [改] 大盘情绪 → 相对强度    当日涨停数 / 60日均值
  ⑧ [改] 板块梯队 → 真实板块    同 hybk 当日涨停数
  ⑨ [新增] 涨停时间 (15分)       fbt 越早越强
  ⑩ [新增] 封单强度 (10分)       fund / ltsz 比值
  ⑪ [新增] 一字/纯净度 (5分)     fbt=lbt, zbc=0

满分 ~135, 阈值要重新校准
"""
import json, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
OUT_DIR = WORKSPACE / "backtest"
OUT_DIR.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"
BJT = timezone(timedelta(hours=8))
VERSION = "v2.4"


def is_zt(code, chg):
    if chg is None: return False
    if code.startswith(('300','688')): return chg >= 19.5
    if code.startswith(('8','4','9')): return chg >= 29.5
    return chg >= 9.7


def http_get(url, retries=4, timeout=15):
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


def trading_days(end, n):
    e = datetime.strptime(end, "%Y-%m-%d"); out=[]; cur=e
    while len(out)<n:
        if cur.weekday()<5: out.append(cur.strftime("%Y-%m-%d"))
        cur -= timedelta(days=1)
    return list(reversed(out))


def fetch_zt_pool(date):
    """东财涨停池 (主数据源)"""
    d_str = date.replace("-","")
    url=("https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989&"
         f"dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt%3Aasc&date={d_str}")
    d = http_get(url)
    if not d: return []
    pool = d.get("data",{}).get("pool", [])
    # 过滤掉 fbt=0 的 (是停牌或无效数据)
    return [s for s in pool if s.get("fbt", 0) > 0]


def fetch_lhb(date):
    """龙虎榜 (用于龙虎榜陷阱维度)"""
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

_kc = {}
def fetch_k(code, beg, end):
    key = f"{code}|{beg}|{end}"
    if key in _kc: return _kc[key]
    sym = tx_prefix(code) + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{beg},{end},320,qfq"
    d = http_get(url)
    if not d: _kc[key]=[]; return []
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
    _kc[key]=out
    return out


def score_v24(zt_rec, lhb_rec, kline, idx, sector_zt_count, market_strength):
    """v2.4 评分.
    zt_rec: 涨停池记录 (主源)
    lhb_rec: 龙虎榜记录 (可选, 用于陷阱维度)
    kline: 该股 K线
    idx: 当日 K 线 index
    sector_zt_count: 当日同板块涨停数
    market_strength: 当日全市场涨停 / 60日均值 (相对强度)
    """
    code = zt_rec.get("c","")
    today = kline[idx]
    sc = {}; ft = {}
    
    lbc = zt_rec.get("lbc", 1)  # 直接用涨停池给的连板数
    fbt = zt_rec.get("fbt", 0)  # 首次封板时间 HHMMSS
    lbt = zt_rec.get("lbt", 0)  # 最后封板时间
    fund = zt_rec.get("fund", 0)  # 封单金额
    ltsz = zt_rec.get("ltsz", 0)  # 流通市值
    hs = zt_rec.get("hs", 0)  # 换手率
    zbc = zt_rec.get("zbc", 0)  # 炸板次数
    hybk = zt_rec.get("hybk", "")
    cap_yi = ltsz / 1e8 if ltsz else 0
    
    ft.update({"lbc":lbc,"fbt":fbt,"lbt":lbt,"fund_yi":round(fund/1e8,2),
               "ltsz_yi":round(cap_yi,1),"hs":round(hs,1),"zbc":zbc,"hybk":hybk})

    # ─── ① 反包/形态 (20分) ─── 用 lbc + K线推 反包
    is_fanbao = False
    if lbc == 1 and idx >= 2:
        prev = kline[idx-1]
        had_zt = any(is_zt(code, kline[j]["chg_pct"]) for j in range(max(0,idx-5), idx-1))
        if had_zt and prev["chg_pct"] < 0:
            is_fanbao = True
    
    if lbc >= 3:
        sc["form"] = 20
    elif is_fanbao:
        sc["form"] = 16
    elif lbc == 2:
        sc["form"] = 14
    elif lbc == 1:
        prev = kline[idx-1] if idx>0 else None
        if prev and prev["vol"] > 0 and 0.8 <= today["vol"]/prev["vol"] <= 1.5:
            sc["form"] = 12
        else:
            sc["form"] = 8
    else:
        sc["form"] = 4

    # ─── ② 龙虎榜陷阱 (-15~+5) ───
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
    else:
        sc["fund_trap"] = 2  # 不在龙虎榜 = 中性偏弱(没大资金关注)

    # ─── ③ 量价关系 (20分) ───
    prev = kline[idx-1] if idx>0 else None
    vol_score = 10
    vol_reason = ""
    if prev and prev["vol"] > 0:
        rv = today["vol"] / prev["vol"]
        ft["vol_ratio"] = round(rv, 2)
        prev_chg = prev["chg_pct"]
        if rv < 0.7 and prev_chg > 5:
            vol_score = 20; vol_reason = "缩量加速"
        elif 0.8 <= rv <= 1.5:
            vol_score = 16; vol_reason = "温和放量"
        elif 1.5 < rv <= 3:
            vol_score = 10; vol_reason = "爆量"
        elif rv > 3:
            vol_score = 5; vol_reason = "天量"
        else:
            vol_score = 6; vol_reason = "缩量但弱"
    sc["vol"] = vol_score
    ft["vol_reason"] = vol_reason

    # ─── ④ 连板辨识度 (25分) ───
    if lbc >= 5: sc["distinct"] = 25
    elif lbc >= 3: sc["distinct"] = 20
    elif lbc == 2: sc["distinct"] = 16
    elif lbc == 1: sc["distinct"] = 12
    else: sc["distinct"] = 5

    # ─── ⑤ 盘子 (10分) ───
    if 30 <= cap_yi <= 80: sc["cap"] = 10
    elif 20 <= cap_yi < 30 or 80 < cap_yi <= 150: sc["cap"] = 6
    elif cap_yi < 20 and cap_yi > 0: sc["cap"] = 3
    elif cap_yi > 150: sc["cap"] = 2
    else: sc["cap"] = 4

    # ─── ⑥ 量能 (5分) ───
    vr = ft.get("vol_ratio", 1.0)
    if vr < 0.7: sc["volume"] = 5
    elif vr <= 1.5: sc["volume"] = 4
    elif vr <= 2.5: sc["volume"] = 2
    else: sc["volume"] = 0

    # ─── ⑦ 大盘情绪 (10分) - 改为相对强度 ───
    ft["market_strength"] = round(market_strength, 2)
    if market_strength >= 1.5: sc["emotion"] = 10  # 高潮市
    elif market_strength >= 1.2: sc["emotion"] = 8
    elif market_strength >= 0.9: sc["emotion"] = 5
    elif market_strength >= 0.7: sc["emotion"] = 3
    else: sc["emotion"] = 1  # 冰点不加分

    # ─── ⑧ 板块梯队 (15分) - 用真实 hybk ───
    if sector_zt_count >= 5: sc["sector"] = 15
    elif sector_zt_count >= 3: sc["sector"] = 12
    elif sector_zt_count == 2: sc["sector"] = 8
    else: sc["sector"] = 4
    ft["sector_zt"] = sector_zt_count

    # ─── ⑨ 涨停时间 (15分) - 新增! ───
    # fbt 是 HHMMSS 格式, 9:25 = 92500
    if fbt == 0: sc["zt_time"] = 0
    elif fbt <= 92500: sc["zt_time"] = 15  # 一字板/集合竞价
    elif fbt <= 93500: sc["zt_time"] = 14  # 9:30-9:35 抢筹
    elif fbt <= 100000: sc["zt_time"] = 12  # 9:35-10:00
    elif fbt <= 103000: sc["zt_time"] = 10  # 10:00-10:30
    elif fbt <= 113000: sc["zt_time"] = 7   # 上午剩余
    elif fbt <= 140000: sc["zt_time"] = 5   # 下午前段
    else: sc["zt_time"] = 3                 # 14:00 后弱势
    
    # ─── ⑩ 封单强度 (10分) - 新增! ───
    if fund > 0 and ltsz > 0:
        seal_pct = fund / ltsz * 100  # 封单 / 流通市值
        ft["seal_pct"] = round(seal_pct, 2)
        if seal_pct >= 5: sc["seal"] = 10  # 封板极强
        elif seal_pct >= 3: sc["seal"] = 8
        elif seal_pct >= 1.5: sc["seal"] = 6
        elif seal_pct >= 0.5: sc["seal"] = 4
        else: sc["seal"] = 1
    else:
        sc["seal"] = 0

    # ─── ⑪ 一字/纯净度 (5分) - 新增! ───
    is_yizi = (fbt == lbt and fbt > 0)
    if is_yizi and zbc == 0: sc["pure"] = 5
    elif zbc == 0: sc["pure"] = 4
    elif zbc <= 2: sc["pure"] = 2
    else: sc["pure"] = 0
    ft["is_yizi"] = is_yizi

    return {"scores": sc, "total": sum(sc.values()), "features": ft}


def outcome(kline, idx, code):
    if idx+1>=len(kline): return None
    nxt = kline[idx+1]; tc = kline[idx]["close"]
    if tc<=0: return None
    return {
        "promoted": is_zt(code, nxt["chg_pct"]),
        "next_chg": nxt["chg_pct"],
        "next_open": (nxt["open"]-tc)/tc*100,
        "next_close": (nxt["close"]-tc)/tc*100,
        "next_high": (nxt["high"]-tc)/tc*100,
    }


def run(days_back, end_date):
    print(f"📅 {VERSION} 回测: 最近 {days_back} 工作日, 截至 {end_date}", flush=True)
    days = trading_days(end_date, days_back)
    print(f"   {days[0]} → {days[-1]}\n", flush=True)

    # ① 抓涨停池 (主源)
    print(f"🔥 [1/5] 抓 {len(days)} 天涨停池...", flush=True)
    pool_by_date = {}
    daily_zt_count = {}
    daily_sector_count = {}  # date -> Counter(板块: 涨停数)
    for i, d in enumerate(days):
        pool = fetch_zt_pool(d)
        pool_by_date[d] = pool
        daily_zt_count[d] = len(pool)
        daily_sector_count[d] = Counter(s.get("hybk","unknown") for s in pool)
        print(f"   [{i+1:>2}/{len(days)}] {d}: {len(pool):>3}", flush=True)
        time.sleep(0.2)

    # 算大盘情绪相对强度 (用整段 mean 做基线)
    avg_zt = sum(daily_zt_count.values()) / max(1, len(daily_zt_count))
    print(f"   日均涨停: {avg_zt:.1f}", flush=True)

    # ② 抓龙虎榜 (副源 → 陷阱维度)
    print(f"\n📋 [2/5] 抓 {len(days)} 天龙虎榜 (副源)...", flush=True)
    lhb_by_date = {}
    for i, d in enumerate(days):
        lhb_by_date[d] = fetch_lhb(d)
        if (i+1) % 10 == 0: print(f"   [{i+1}/{len(days)}]", flush=True)
        time.sleep(0.15)

    # 收集所有 (code, date) 对
    targets = []
    for d, pool in pool_by_date.items():
        for s in pool:
            c = s.get("c")
            if c: targets.append((d, c, s))
    
    by_code = defaultdict(list)
    for d, c, s in targets: by_code[c].append((d, s))
    print(f"   涨停池总记录: {len(targets)} | 唯一股: {len(by_code)}", flush=True)

    # ③ 拉 K 线
    print(f"\n📈 [3/5] K线 ({len(by_code)} 只)...", flush=True)
    beg = (datetime.strptime(days[0],"%Y-%m-%d")-timedelta(days=15)).strftime("%Y-%m-%d")
    end_buf = (datetime.strptime(days[-1],"%Y-%m-%d")+timedelta(days=10)).strftime("%Y-%m-%d")
    klines_by_code = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_k, c, beg, end_buf): c for c in by_code.keys()}
        done = 0
        for fut in as_completed(futs):
            klines_by_code[futs[fut]] = fut.result()
            done += 1
            if done % 100 == 0: print(f"   K线 [{done}/{len(by_code)}]", flush=True)

    # ④ 评分
    print(f"\n📊 [4/5] {VERSION} 评分...", flush=True)
    samples = []
    no_kline=no_idx=no_next=0
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: no_kline += len(items); continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d, zt_rec in items:
            i = idxmap.get(d)
            if i is None: no_idx+=1; continue
            # 不再用 K 线判涨停, 用涨停池数据 (zt_rec)
            lhb_rec = lhb_by_date.get(d, {}).get(code)
            sector_zt = daily_sector_count[d].get(zt_rec.get("hybk","unknown"), 1)
            mkt_strength = daily_zt_count[d] / avg_zt if avg_zt > 0 else 1.0
            sc = score_v24(zt_rec, lhb_rec, kl, i, sector_zt, mkt_strength)
            oc = outcome(kl, i, code)
            if not oc: no_next += 1; continue
            samples.append({
                "date": d, "code": code,
                "name": zt_rec.get("n",""),
                **sc, **oc,
                "in_lhb": bool(lhb_rec),
            })

    print(f"\n   有效样本: {len(samples)} | 无K线={no_kline} 无idx={no_idx} 无次日={no_next}", flush=True)
    if not samples: print("❌ 无样本"); return
    
    # ⑤ 分析
    print(f"\n📈 [5/5] 分析...", flush=True)
    analyze(samples, end_date)


def analyze(samples, end_date):
    n = len(samples)
    pr = sum(1 for s in samples if s["promoted"])
    rate = pr/n*100
    avgo = sum(s["next_open"] for s in samples)/n
    avgc = sum(s["next_close"] for s in samples)/n
    avgh = sum(s["next_high"] for s in samples)/n
    print(f"   {VERSION} 总体: n={n} 晋级={pr} ({rate:.2f}%)  均开{avgo:+.2f}% 均收{avgc:+.2f}% 均高{avgh:+.2f}%", flush=True)
    
    # 龙虎榜 vs 非龙虎榜
    in_lhb = [s for s in samples if s["in_lhb"]]
    out_lhb = [s for s in samples if not s["in_lhb"]]
    if in_lhb:
        p = sum(1 for s in in_lhb if s["promoted"])
        print(f"   上榜龙虎: n={len(in_lhb)} 晋级率={p/len(in_lhb)*100:.1f}%", flush=True)
    if out_lhb:
        p = sum(1 for s in out_lhb if s["promoted"])
        print(f"   未上龙虎: n={len(out_lhb)} 晋级率={p/len(out_lhb)*100:.1f}%", flush=True)

    # 分数桶
    bk = defaultdict(lambda:{"n":0,"p":0,"c":0})
    for s in samples:
        b = bk[s["total"]//10*10]; b["n"]+=1
        if s["promoted"]: b["p"]+=1
        b["c"]+=s["next_close"]
    score_buckets = []
    for v in sorted(bk):
        b=bk[v]
        if b["n"]==0: continue
        score_buckets.append({            "range":f"[{v},{v+10})", "n":b["n"], "p":b["p"],
            "rate":round(b["p"]/b["n"]*100,1),
            "avg_close":round(b["c"]/b["n"],2)})

    # 维度分析
    DIM_LABEL = {
        "form":"反包/形态","fund_trap":"龙虎榜陷阱","vol":"量价关系",
        "distinct":"连板辨识度","cap":"盘子","volume":"量能",
        "emotion":"大盘情绪","sector":"板块梯队",
        "zt_time":"涨停时间(NEW)","seal":"封单强度(NEW)","pure":"一字纯净(NEW)"
    }
    dim_analysis={}
    for dim, label in DIM_LABEL.items():
        bd = defaultdict(lambda:{"n":0,"p":0,"c":0})
        for s in samples:
            v = s["scores"].get(dim,0); d=bd[v]
            d["n"]+=1
            if s["promoted"]: d["p"]+=1
            d["c"]+=s["next_close"]
        rows=[{"score":v,"n":bd[v]["n"],"p":bd[v]["p"],
               "rate":round(bd[v]["p"]/bd[v]["n"]*100,1) if bd[v]["n"] else 0,
               "avg_close":round(bd[v]["c"]/bd[v]["n"],2) if bd[v]["n"] else 0}
              for v in sorted(bd)]
        diff = rows[-1]["rate"]-rows[0]["rate"] if len(rows)>=2 else 0
        dim_analysis[dim]={"label":label,"rows":rows,"high_low_diff":round(diff,1)}

    # 阈值分析
    thr_analysis=[]
    for thr in range(40, 141, 5):
        sub=[s for s in samples if s["total"]>=thr]
        if len(sub)<5: continue
        p=sum(1 for s in sub if s["promoted"])
        thr_analysis.append({"thr":thr,"n":len(sub),"p":p,
                             "rate":round(p/len(sub)*100,1),
                             "avg_close":round(sum(s["next_close"] for s in sub)/len(sub),2)})

    top_hit = sorted([s for s in samples if s["promoted"] and s["total"]>=80], key=lambda s:-s["total"])[:30]
    top_miss = sorted([s for s in samples if not s["promoted"] and s["total"]>=80], key=lambda s:-s["total"])[:25]

    write_md(samples, n, pr, rate, avgo, avgc, avgh, score_buckets,
             dim_analysis, thr_analysis, top_hit, top_miss, end_date)

    p_json = OUT_DIR / f"v24-results-{end_date}.json"
    with open(p_json,"w",encoding="utf-8") as f:
        json.dump({"version":VERSION,
                   "summary":{"n":n,"promoted":pr,"rate":rate},
                   "buckets":score_buckets,"dims":dim_analysis,
                   "thresholds":thr_analysis,"samples":samples},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"   ✅ JSON: {p_json}", flush=True)


def write_md(samples, n, pr, rate, avgo, avgc, avgh, buckets, dims, thresholds, top_hit, top_miss, end_date):
    p = OUT_DIR / f"v24-results-{end_date}.md"
    md=[]
    md.append(f"# {VERSION} 涨停晋级策略 回测报告\n")
    md.append(f"_截止 {end_date} (北京) | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 总览\n")
    md.append(f"- 总样本: **{n}** (源自涨停池, 比 v2.3 龙虎榜数据扩 2-3 倍)")
    md.append(f"- 晋级率: **{rate:.2f}%** ({pr}/{n})")
    md.append(f"- 次日均开 {avgo:+.2f}%, 均收 {avgc:+.2f}%, 均高 {avgh:+.2f}%\n")

    md.append("## 📈 总分 vs 晋级率\n")
    md.append("| 分数段 | 样本 | 晋级 | 晋级率 | 次日均收 |")
    md.append("|---|---:|---:|---:|---:|")
    for b in buckets:
        md.append(f"| {b['range']} | {b['n']} | {b['p']} | {b['rate']}% | {b['avg_close']:+.2f}% |")

    md.append("\n## 🎯 阈值分析\n")
    md.append("| 阈值 | 样本 | 晋级 | 晋级率 | 次日均收 |")
    md.append("|---|---:|---:|---:|---:|")
    for t in thresholds:
        md.append(f"| ≥{t['thr']} | {t['n']} | {t['p']} | {t['rate']}% | {t['avg_close']:+.2f}% |")

    md.append("\n## 🔬 各维度有效性\n")
    md.append("| 维度 | 高低差 | 解读 |")
    md.append("|---|---:|---|")
    rank = sorted(dims.items(), key=lambda x:-x[1]["high_low_diff"])
    for dim, da in rank:
        d = da["high_low_diff"]
        v = "✅ 强有效" if d>=15 else "🟡 弱有效" if d>=5 else "⚪ 无效" if d>=-5 else "❌ 反向"
        md.append(f"| {da['label']} | {d:+.1f}% | {v} |")
    md.append("")
    for dim, da in rank:
        md.append(f"### {da['label']}\n")
        md.append("| 维度得分 | 样本 | 晋级 | 晋级率 | 次日均收 |")
        md.append("|---:|---:|---:|---:|---:|")
        for r in da["rows"]:
            md.append(f"| {r['score']} | {r['n']} | {r['p']} | {r['rate']}% | {r['avg_close']:+.2f}% |")
        md.append("")

    md.append("## ✅ 高分命中 (≥80 分且晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 板 | 时间 | 封单 | 板块 | 次日收 |")
    md.append("|---|---|---|---:|---:|---:|---:|---|---:|")
    for s in top_hit:
        ft = s["features"]
        fbt_str = f"{ft.get('fbt',0)//10000:02d}:{(ft.get('fbt',0)//100)%100:02d}" if ft.get('fbt') else "-"
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {ft.get('lbc','-')} | {fbt_str} | {ft.get('fund_yi','-')}亿 | {ft.get('hybk','-')} | {s['next_close']:+.2f}% |")

    md.append("\n## ❌ 高分炸板 (≥80 分未晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 板 | 时间 | 封单 | 板块 | 次日收 |")
    md.append("|---|---|---|---:|---:|---:|---:|---|---:|")
    for s in top_miss:
        ft = s["features"]
        fbt_str = f"{ft.get('fbt',0)//10000:02d}:{(ft.get('fbt',0)//100)%100:02d}" if ft.get('fbt') else "-"
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {ft.get('lbc','-')} | {fbt_str} | {ft.get('fund_yi','-')}亿 | {ft.get('hybk','-')} | {s['next_close']:+.2f}% |")

    with open(p, "w", encoding="utf-8") as f: f.write("\n".join(md))
    print(f"   ✅ MD: {p}", flush=True)


if __name__ == "__main__":
    days_back = int(sys.argv[1]) if len(sys.argv)>1 else 30
    end_date = sys.argv[2] if len(sys.argv)>2 else datetime.now(BJT).strftime("%Y-%m-%d")
    run(days_back, end_date)
