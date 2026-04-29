#!/usr/bin/env python3
"""
backtest_v2.py — 涨停晋级六维量化策略 v2.0 回测引擎

v2.0 维度 (来自外部策略文档):
  ① 反包/二波形态 (20分): 断板反包 / 连板加速 / 二板 / 优质首板 / 普通首板 / 烂板
  ② 业绩验证 (20分):     一季报净利同比 (用东财财报API)
  ③ 涨价硬逻辑 (15分):   ⚠️ 公开数据不足, 用占位 (后续手工补)
  ④ 龙虎榜资金 (15分):   机构净买 + 游资席位识别 (近似)
  ⑤ 量价关系 (15分):     缩量加速 / 温和放量 / 爆量分歧 / 放量烂板 / 天量滞涨
  ⑥ 连板辨识度 (15分):   全市场连板对比 (用当日全市场最高板代理)

数据源: datacenter-web.eastmoney.com + web.ifzq.gtimg.cn (腾讯K线, 海外稳定)
对比: 同样回测 + 同样样本, 看 v2.0 vs v1.0 真实胜率差异
"""
import json, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
OUT_DIR = WORKSPACE / "backtest"
OUT_DIR.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)"
BJT = timezone(timedelta(hours=8))

# 顶级游资席位关键词 (近似识别)
TOP_HOTMONEY = ["小鳄鱼", "方新侠", "国君上海", "炒股养家", "瑞鹤仙", "孙哥", "赵老哥",
                "上海溧阳路", "上海浦东新区银城中路", "财通证券绍兴", "中信杭州延安路",
                "西藏东方财富拉萨", "国泰君安上海江苏路"]
# 量化席位 (波动剧烈, 警惕)
QUANT_SEATS = ["拉萨团结路第二", "拉萨东环路第二", "拉萨金融城南环路", "深圳益田路荣超"]


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


# ─── 龙虎榜 ───
def fetch_lhb(date):
    url=("https://datacenter-web.eastmoney.com/api/data/v1/get?"
         "sortColumns=NET_BS_AMT&sortTypes=-1&pageSize=300&pageNumber=1&"
         "reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&"
         f"filter=(TRADE_DATE%3E%3D%27{date}%27)(TRADE_DATE%3C%3D%27{date}%27)")
    d = http_get(url)
    if not d: return []
    res = d.get("result") if isinstance(d, dict) else None
    if not isinstance(res, dict): return []
    data = res.get("data") or []
    seen=set(); uniq=[]
    for r in data:
        c = r.get("SECURITY_CODE")
        if c and c not in seen: seen.add(c); uniq.append(r)
    return uniq


# ─── K线 (腾讯) ───
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


# ─── 业绩数据 (一季报核心指标) ───
_perf_cache = {}
def fetch_perf(code):
    """拿最新一季报 + 业绩预告"""
    if code in _perf_cache: return _perf_cache[code]
    # 核心指标
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
           "reportName=RPT_LICO_FN_CPD_BB&columns=ALL&pageSize=8&pageNumber=1&"
           f"filter=(SECURITY_CODE%3D%22{code}%22)")
    d = http_get(url)
    rows = []
    if d and isinstance(d.get("result"), dict):
        rows = d["result"].get("data") or []
    # 预告
    url2 = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
            "reportName=RPT_PUBLIC_OP_NEWPREDICT&columns=ALL&pageSize=4&pageNumber=1&"
            f"filter=(SECURITY_CODE%3D%22{code}%22)")
    d2 = http_get(url2)
    pred_rows = []
    if d2 and isinstance(d2.get("result"), dict):
        pred_rows = d2["result"].get("data") or []
    res = {"reports": rows, "predicts": pred_rows}
    _perf_cache[code] = res
    return res


# ─── 全市场每日最高连板数 (用于第6维) ───
_max_zt_cache = {}
def get_max_consec_zt(date, all_records_by_date):
    """近似: 当日所有龙虎榜上榜涨停股中, 最高的"5日内涨停数"作为该日"市场最高板"近似"""
    return _max_zt_cache.get(date, 0)


# ─── 评分 v2.0 ───
def score_v2(rec, kline, idx, perf_data, market_max_zt, all_zt_codes_today=None):
    code = rec.get("SECURITY_CODE","")
    today = kline[idx]
    explain = (rec.get("EXPLAIN") or rec.get("EXPLANATION") or "")
    sc = {}; ft = {}

    # ─── ① 反包/二波形态 (20分) ───
    n_zt_5d = sum(1 for j in range(max(0,idx-4), idx+1) if j<len(kline) and is_zt(code, kline[j]["chg_pct"]))
    n_zt_2d = sum(1 for j in range(max(0,idx-1), idx+1) if j<len(kline) and is_zt(code, kline[j]["chg_pct"]))
    ft["zt_5d"] = n_zt_5d
    ft["zt_2d"] = n_zt_2d
    
    # 判断是否"反包" (前一天阴线/破板, 今天涨停)
    is_fanbao = False
    if idx >= 2:
        prev = kline[idx-1]
        prev2 = kline[idx-2]
        # 反包定义: 前1-3日内有过涨停, 但中间断了, 今日重新涨停
        had_zt_recently = any(is_zt(code, kline[j]["chg_pct"]) for j in range(max(0,idx-5), idx-1))
        prev_is_red = prev["chg_pct"] < 0
        if had_zt_recently and prev_is_red and not is_zt(code, prev["chg_pct"]):
            is_fanbao = True
    ft["is_fanbao"] = is_fanbao
    
    if is_fanbao:
        sc["form"] = 20  # 断板反包板
    elif n_zt_5d >= 3:
        sc["form"] = 16  # 连板加速 3板+
    elif n_zt_2d == 2:
        sc["form"] = 14  # 二板确认
    elif n_zt_5d == 1:
        # 优质首板: 缩量 + 实体大
        prev = kline[idx-1] if idx>0 else None
        if prev and prev["vol"] > 0:
            vol_ratio = today["vol"] / prev["vol"]
            if 0.8 <= vol_ratio <= 1.5:
                sc["form"] = 12  # 优质首板
            else:
                sc["form"] = 8   # 普通首板
        else:
            sc["form"] = 8
    else:
        sc["form"] = 4  # 烂板

    # ─── ② 业绩验证 (20分) ───
    perf_score = 8  # 默认: 持平
    perf_reason = "无数据"
    if perf_data and perf_data["reports"]:
        # 找日期 ≤ idx 那天的最新一季报 (避免未来数据)
        today_dt = datetime.strptime(today["date"], "%Y-%m-%d")
        latest = None
        for r in perf_data["reports"]:
            nd = r.get("NOTICE_DATE", "")
            if nd:
                try:
                    nd_dt = datetime.strptime(nd[:10], "%Y-%m-%d")
                    if nd_dt <= today_dt:
                        if latest is None or nd_dt > datetime.strptime(latest.get("NOTICE_DATE","")[:10], "%Y-%m-%d"):
                            latest = r
                except: pass
        if latest:
            tq = latest.get("PARENT_NETPROFIT_TQ")
            ft["perf_tq"] = tq
            ft["perf_period"] = latest.get("REPORTDATEWZ", "")
            perf_reason = f"{latest.get('REPORTDATEWZ','')} 净利同比 {tq}%"
            if tq is not None:
                if tq > 50: perf_score = 20
                elif tq > 30: perf_score = 18
                elif tq > 0: perf_score = 15
                elif tq > -30: perf_score = 8
                else: perf_score = 0  # 业绩雷
    sc["perf"] = perf_score
    ft["perf_reason"] = perf_reason

    # ─── ③ 涨价硬逻辑 (15分) — 占位, 公开数据不足 ───
    # 用上榜原因里的"涨价"、"硬逻辑"关键词近似
    if "涨价" in explain or "提价" in explain:
        sc["price_logic"] = 8
    else:
        sc["price_logic"] = 5  # 中性占位
    ft["price_logic_proxy"] = "关键词近似"

    # ─── ④ 龙虎榜资金 (15分) ───
    net_amt = rec.get("BILLBOARD_NET_AMT", 0) or rec.get("NET_BS_AMT", 0) or 0
    ft["net_wan"] = round(net_amt/10000, 0)
    
    has_inst_buy = "机构" in explain and "买入" in explain
    has_top_hm = any(kw in explain for kw in TOP_HOTMONEY)  # 上榜原因里很少出现席位名, 这是粗近似
    has_quant = any(kw in explain for kw in QUANT_SEATS)
    
    fund_score = 0
    if net_amt < 0:
        fund_score = 0  # 净卖出
    elif has_inst_buy and has_top_hm and net_amt > 1e8:
        fund_score = 15  # 共振
    elif has_inst_buy and net_amt > 5e7:
        fund_score = 13
    elif has_top_hm and net_amt > 5e7:
        fund_score = 12
    elif has_quant and net_amt > 3e7:
        fund_score = 9
    elif net_amt > 1e7:
        fund_score = 8
    else:
        fund_score = 5
    sc["fund"] = fund_score

    # ─── ⑤ 量价关系 (15分) ───
    prev = kline[idx-1] if idx>0 else None
    vol_score = 8  # 默认中性
    vol_reason = "无前日数据"
    if prev and prev["vol"] > 0:
        rv = today["vol"] / prev["vol"]
        ft["vol_ratio"] = round(rv, 2)
        # 缩量加速 (前日大涨/涨停, 今日继续涨停且量缩)
        prev_chg = prev["chg_pct"]
        if rv < 0.7 and prev_chg > 5:
            vol_score = 15  # 缩量加速
            vol_reason = "缩量加速"
        elif 0.8 <= rv <= 1.5:
            vol_score = 12  # 温和放量
            vol_reason = "温和放量"
        elif 1.5 < rv <= 3:
            vol_score = 8   # 爆量分歧转一致
            vol_reason = "爆量"
        elif rv > 3:
            vol_score = 5   # 放量烂板
            vol_reason = "天量"
        else:
            vol_score = 5   # 缩太多 (无人接盘)
            vol_reason = "缩量但弱"
    sc["vol"] = vol_score
    ft["vol_reason"] = vol_reason

    # ─── ⑥ 连板辨识度 (15分) ───
    # 用当日"5日内涨停数"对比"市场最高"
    if market_max_zt > 0:
        ratio_to_max = n_zt_5d / market_max_zt
        if n_zt_5d >= 5:
            sc["distinct"] = 15  # 市场最高板
        elif n_zt_5d >= 3:
            sc["distinct"] = 12  # 板块龙头 3-4板
        elif n_zt_5d == 2:
            sc["distinct"] = 10  # 二板晋级
        elif n_zt_5d == 1:
            sc["distinct"] = 8   # 前排跟风
        else:
            sc["distinct"] = 5
    else:
        sc["distinct"] = 5

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
    print(f"📅 v2.0 回测: 最近 {days_back} 工作日, 截至 {end_date}", flush=True)
    days = trading_days(end_date, days_back)
    print(f"   {days[0]} → {days[-1]}\n", flush=True)

    # 1. 拉龙虎榜
    print(f"🔥 [1/4] 抓 {len(days)} 天龙虎榜...", flush=True)
    all_recs = []
    for i, d in enumerate(days):
        recs = fetch_lhb(d)
        for r in recs:
            all_recs.append((d, r.get("SECURITY_CODE"), r.get("SECURITY_NAME_ABBR"), r))
        print(f"   [{i+1:>2}/{len(days)}] {d}: {len(recs):>3} 只", flush=True)
        time.sleep(0.25)
    print(f"\n   总记录: {len(all_recs)}", flush=True)

    # 2. 并发拉 K 线
    by_code = defaultdict(list)
    for d,c,n,r in all_recs: by_code[c].append((d,n,r))
    print(f"\n🔍 [2/4] 拉 K 线 ({len(by_code)} 只)...", flush=True)
    beg = (datetime.strptime(days[0],"%Y-%m-%d")-timedelta(days=15)).strftime("%Y-%m-%d")
    end_buf = (datetime.strptime(days[-1],"%Y-%m-%d")+timedelta(days=10)).strftime("%Y-%m-%d")
    klines_by_code = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fetch_k, c, beg, end_buf): c for c in by_code.keys()}
        done = 0
        for fut in as_completed(futs):
            c = futs[fut]
            klines_by_code[c] = fut.result()
            done += 1
            if done % 100 == 0:
                print(f"   K线进度 [{done}/{len(by_code)}]", flush=True)

    # 3. 并发拉业绩数据 (只拉涨停的票, 减少调用)
    print(f"\n📊 [3/4] 筛涨停股 + 拉业绩...", flush=True)
    zt_codes = set()
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,n,r in items:
            i = idxmap.get(d)
            if i is None: continue
            if is_zt(code, kl[i]["chg_pct"]):
                zt_codes.add(code)
                break
    print(f"   涨停股: {len(zt_codes)} 只", flush=True)

    perf_by_code = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_perf, c): c for c in zt_codes}
        done = 0
        for fut in as_completed(futs):
            c = futs[fut]
            perf_by_code[c] = fut.result()
            done += 1
            if done % 100 == 0:
                print(f"   业绩进度 [{done}/{len(zt_codes)}]", flush=True)
    print(f"   业绩数据: 已拉 {len(perf_by_code)} 只", flush=True)

    # 4. 计算每日"市场最高板"
    market_max_by_date = defaultdict(int)
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,n,r in items:
            i = idxmap.get(d)
            if i is None or not is_zt(code, kl[i]["chg_pct"]): continue
            n_zt = sum(1 for j in range(max(0,i-4), i+1) if j<len(kl) and is_zt(code, kl[j]["chg_pct"]))
            if n_zt > market_max_by_date[d]:
                market_max_by_date[d] = n_zt

    # 5. 评分
    print(f"\n📊 [4/4] v2.0 评分 + 分析...", flush=True)
    samples = []
    no_kline=not_zt=no_next=0
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: no_kline += len(items); continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,name,rec in items:
            i = idxmap.get(d)
            if i is None: continue
            if not is_zt(code, kl[i]["chg_pct"]): not_zt+=1; continue
            sc = score_v2(rec, kl, i, perf_by_code.get(code), market_max_by_date.get(d,0))
            oc = outcome(kl, i, code)
            if not oc: no_next+=1; continue
            samples.append({"date":d, "code":code, "name":name,
                            **sc, **oc,
                            "explain":(rec.get("EXPLAIN") or rec.get("EXPLANATION") or "")[:80]})

    print(f"\n   有效样本: {len(samples)} | 无K线={no_kline} 非涨停={not_zt} 无次日={no_next}", flush=True)
    if not samples: print("❌ 无样本"); return
    analyze(samples, end_date)


def analyze(samples, end_date):
    n = len(samples); pr = sum(1 for s in samples if s["promoted"]); rate = pr/n*100
    avgo = sum(s["next_open"] for s in samples)/n
    avgc = sum(s["next_close"] for s in samples)/n
    avgh = sum(s["next_high"] for s in samples)/n
    print(f"\n   v2.0 总体: n={n} 晋级={pr} ({rate:.2f}%)  均开{avgo:+.2f}% 均收{avgc:+.2f}% 均高{avgh:+.2f}%", flush=True)

    # 总分桶
    bk = defaultdict(lambda:{"n":0,"p":0,"o":0,"c":0,"h":0})
    for s in samples:
        b = bk[s["total"]//10*10]; b["n"]+=1
        if s["promoted"]: b["p"]+=1
        b["o"]+=s["next_open"]; b["c"]+=s["next_close"]; b["h"]+=s["next_high"]
    score_buckets=[]
    for v in sorted(bk):
        b=bk[v]
        if b["n"]==0: continue
        score_buckets.append({"range":f"[{v},{v+10})", "n":b["n"], "p":b["p"],
                              "rate":round(b["p"]/b["n"]*100,1),
                              "avg_open":round(b["o"]/b["n"],2),
                              "avg_close":round(b["c"]/b["n"],2),
                              "avg_high":round(b["h"]/b["n"],2)})

    DIM_LABEL = {"form":"反包/形态","perf":"业绩验证","price_logic":"涨价逻辑(占位)",
                 "fund":"龙虎榜资金","vol":"量价关系","distinct":"连板辨识度"}
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

    thr_analysis=[]
    for thr in range(40,91,5):
        sub=[s for s in samples if s["total"]>=thr]
        if len(sub)<5: continue
        p=sum(1 for s in sub if s["promoted"])
        thr_analysis.append({"thr":thr,"n":len(sub),"p":p,
                             "rate":round(p/len(sub)*100,1),
                             "avg_close":round(sum(s["next_close"] for s in sub)/len(sub),2)})

    top_hit = sorted([s for s in samples if s["promoted"] and s["total"]>=70], key=lambda s:-s["total"])[:25]
    top_miss = sorted([s for s in samples if not s["promoted"] and s["total"]>=70], key=lambda s:-s["total"])[:25]

    write_md(samples, n, pr, rate, avgo, avgc, avgh,
             score_buckets, dim_analysis, thr_analysis, top_hit, top_miss, end_date)
    write_json(samples, score_buckets, dim_analysis, thr_analysis, n, pr, rate, end_date)


def write_json(samples, buckets, dims, thresholds, n, pr, rate, end_date):
    p = OUT_DIR / f"v2-results-{end_date}.json"
    with open(p,"w",encoding="utf-8") as f:
        json.dump({"version":"v2.0",
                   "summary":{"n":n,"promoted":pr,"rate":rate},
                   "buckets":buckets,"dims":dims,"thresholds":thresholds,
                   "samples":samples}, f, ensure_ascii=False, indent=2, default=str)
    print(f"   ✅ JSON: {p}")


def write_md(samples, n, pr, rate, avgo, avgc, avgh, buckets, dims, thresholds, top_hit, top_miss, end_date):
    p = OUT_DIR / f"v2-results-{end_date}.md"
    md=[]
    md.append(f"# v2.0 涨停晋级六维策略 回测报告\n")
    md.append(f"_截止 {end_date} (北京) | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 总览\n")
    md.append(f"- 总样本: **{n}**")
    md.append(f"- 总体晋级率: **{rate:.2f}%** ({pr}/{n})")
    md.append(f"- 次日均开盘: **{avgo:+.2f}%**")
    md.append(f"- 次日均收盘: **{avgc:+.2f}%**")
    md.append(f"- 次日均最高: **{avgh:+.2f}%**\n")

    md.append("## 📈 总分 vs 晋级率\n")
    md.append("| 分数段 | 样本 | 晋级 | 晋级率 | 次日开 | 次日收 | 次日高 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|")
    for b in buckets:
        md.append(f"| {b['range']} | {b['n']} | {b['p']} | {b['rate']}% | {b['avg_open']:+.2f}% | {b['avg_close']:+.2f}% | {b['avg_high']:+.2f}% |")

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

    md.append("## ✅ TOP 命中样本 (≥70 分且晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 形态 | 业绩 | 涨价 | 资金 | 量价 | 辨识 | 次日收 | 上榜原因 |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for s in top_hit:
        sc = s["scores"]
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {sc.get('form',0)} | {sc.get('perf',0)} | {sc.get('price_logic',0)} | {sc.get('fund',0)} | {sc.get('vol',0)} | {sc.get('distinct',0)} | {s['next_close']:+.2f}% | {s['explain']} |")

    md.append("\n## ❌ 高分但炸板 (≥70 分却未晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 形态 | 业绩 | 涨价 | 资金 | 量价 | 辨识 | 次日收 | 上榜原因 |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for s in top_miss:
        sc = s["scores"]
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {sc.get('form',0)} | {sc.get('perf',0)} | {sc.get('price_logic',0)} | {sc.get('fund',0)} | {sc.get('vol',0)} | {sc.get('distinct',0)} | {s['next_close']:+.2f}% | {s['explain']} |")

    md.append("\n## 💡 v2.0 vs v1.0 对比要点\n")
    md.append("- 关注哪些维度的高低差 >0 (真有效) vs <0 (反向)")
    md.append("- ≥70 分阈值的实际晋级率 vs v1.0 的 12.5%")
    md.append("- 业绩验证(②)和量价关系(⑤)是 v2.0 vs v1.0 的核心新维度, 看它们高低差")

    with open(p, "w", encoding="utf-8") as f: f.write("\n".join(md))
    print(f"   ✅ MD: {p}")


if __name__ == "__main__":
    days_back = int(sys.argv[1]) if len(sys.argv)>1 else 30
    end_date = sys.argv[2] if len(sys.argv)>2 else datetime.now(BJT).strftime("%Y-%m-%d")
    run(days_back, end_date)
