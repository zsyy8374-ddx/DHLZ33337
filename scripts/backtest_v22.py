#!/usr/bin/env python3
"""
backtest_v22.py — v2.2 (基于 v2.1 反馈, 删无效, 加新维度)

v2.1 → v2.2:
  ① 反包/形态 (20分)            保持
  ② [删除] 业绩雷罚              v2.1 测试无效
  ③ [删除] 涨价占位              永远是 0
  ④ 龙虎榜陷阱 (-15~+5分)        细化, 看净额方向
  ⑤ 量价关系 (20分)              保持
  ⑥ 连板辨识度 (25分)            保持
  ⑦ [新增] 盘子+量能 (15分)      流通市值 + 量比
  ⑧ [新增] 板块梯队 (15分)       同板块当日涨停股数

满分 110 (反包20 + 龙虎陷阱5 + 量价20 + 辨识25 + 盘子15 + 板块15) - 龙虎陷阱-15
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
VERSION = "v2.2"


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


def score_v22(rec, kline, idx, sector_zt_count_today):
    """v2.2 评分 (移除业绩雷+涨价占位, 加盘子+板块梯队)"""
    code = rec.get("SECURITY_CODE","")
    today = kline[idx]
    explain = (rec.get("EXPLAIN") or rec.get("EXPLANATION") or "")
    sc = {}; ft = {}

    # ─── ① 反包/形态 (20分) ───
    n_zt_5d = sum(1 for j in range(max(0,idx-4), idx+1) if j<len(kline) and is_zt(code, kline[j]["chg_pct"]))
    n_zt_2d = sum(1 for j in range(max(0,idx-1), idx+1) if j<len(kline) and is_zt(code, kline[j]["chg_pct"]))
    ft["zt_5d"] = n_zt_5d
    
    is_fanbao = False
    if idx >= 2:
        prev = kline[idx-1]
        had_zt_recently = any(is_zt(code, kline[j]["chg_pct"]) for j in range(max(0,idx-5), idx-1))
        if had_zt_recently and prev["chg_pct"] < 0 and not is_zt(code, prev["chg_pct"]):
            is_fanbao = True
    ft["is_fanbao"] = is_fanbao
    
    if is_fanbao:
        sc["form"] = 20
    elif n_zt_5d >= 3:
        sc["form"] = 16
    elif n_zt_2d == 2:
        sc["form"] = 14
    elif n_zt_5d == 1:
        prev = kline[idx-1] if idx>0 else None
        if prev and prev["vol"] > 0 and 0.8 <= today["vol"]/prev["vol"] <= 1.5:
            sc["form"] = 12
        else:
            sc["form"] = 8
    else:
        sc["form"] = 4

    # ─── ② 龙虎榜陷阱 (-15~+5分, 反向更细) ───
    net_amt = rec.get("BILLBOARD_NET_AMT", 0) or rec.get("NET_BS_AMT", 0) or 0
    ft["net_wan"] = round(net_amt/10000, 0)
    n_inst = explain.count("机构")
    
    if n_inst >= 3 and net_amt > 5e7:
        # 多家机构+大额买入 = 极大概率出货
        sc["fund_trap"] = -15
    elif n_inst >= 2:
        sc["fund_trap"] = -10
    elif n_inst == 1 and "买入" in explain:
        sc["fund_trap"] = -5  # 单家机构温和负面
    elif "机构" in explain and "卖出" in explain:
        sc["fund_trap"] = 3   # 机构卖出反而是利好(纯游资接力)
    elif net_amt > 0 and n_inst == 0:
        sc["fund_trap"] = 5   # 纯游资+净买入 = 真正接力
    else:
        sc["fund_trap"] = 0

    # ─── ③ 量价关系 (20分) ───
    prev = kline[idx-1] if idx>0 else None
    vol_score = 10
    vol_reason = "无前日"
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
    if n_zt_5d >= 5: sc["distinct"] = 25
    elif n_zt_5d >= 3: sc["distinct"] = 20
    elif n_zt_5d == 2: sc["distinct"] = 16
    elif n_zt_5d == 1: sc["distinct"] = 12
    else: sc["distinct"] = 5

    # ─── ⑤ [新增] 盘子+量能 (15分) ───
    # 流通市值 (来自龙虎榜数据)
    free_cap = rec.get("FREE_MARKET_CAP", 0) or 0
    cap_yi = free_cap / 1e8 if free_cap else 0
    ft["cap_yi"] = round(cap_yi, 1)
    if 30 <= cap_yi <= 80:
        cap_score = 8  # 黄金区间
    elif 20 <= cap_yi < 30 or 80 < cap_yi <= 150:
        cap_score = 5  # 次优
    elif cap_yi < 20 and cap_yi > 0:
        cap_score = 3  # 微盘 (不稳定)
    elif cap_yi > 150:
        cap_score = 2  # 大盘 (难涨停)
    else:
        cap_score = 4
    
    # 量能子项: 当日量比 (用 vol_ratio 复用)
    vol_ratio = ft.get("vol_ratio", 1.0)
    if vol_ratio < 0.7:
        vol_sub = 7  # 缩量
    elif vol_ratio <= 1.5:
        vol_sub = 5
    elif vol_ratio <= 2.5:
        vol_sub = 3
    else:
        vol_sub = 1  # 巨量危险
    sc["cap_vol"] = cap_score + vol_sub

    # ─── ⑥ [新增] 板块梯队 (15分) ───
    # 同板块当日涨停股数: 来自 sector_zt_count_today (外部计算)
    sector_zt = sector_zt_count_today.get(code, 1)
    ft["sector_zt"] = sector_zt
    if sector_zt >= 5:
        sc["sector"] = 15  # 主线板块
    elif sector_zt >= 3:
        sc["sector"] = 12
    elif sector_zt == 2:
        sc["sector"] = 8
    else:
        sc["sector"] = 4  # 孤狼

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


def compute_sector_zt(by_code, klines_by_code):
    """为每个 (date, code) 计算"同板块当日涨停股数". 
    简化: 用龙虎榜上榜涨停股的"题材关键词"匹配.
    更简的近似: 用代码段 (300xxx, 600xxx 等) 不靠谱
    最简近似: 该日全部涨停股数 = 上限指标; 这里我们对所有票统一用这个数
    """
    daily_zt_count = defaultdict(int)  # date -> count of all zt stocks
    code_zt_dates = defaultdict(set)   # code -> set of zt dates
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,n,r in items:
            i = idxmap.get(d)
            if i is None: continue
            if is_zt(code, kl[i]["chg_pct"]):
                daily_zt_count[d] += 1
                code_zt_dates[code].add(d)

    # 进阶: 用上榜原因里的关键词 (题材) 提取板块名
    # 简化: 题材关键词 → 当日内有几只票同时含这个关键词
    KEYWORDS = ["AI", "光模块", "算力", "芯片", "芯片(存储)", "芯片(CPU)",
                "钠电池", "光伏", "锂电", "燃料电池", "数字货币", "区块链",
                "新能源", "军工", "航天", "稀土", "稀有金属", "化工",
                "医药", "医疗", "白酒", "消费", "汽车", "智能驾驶",
                "机器人", "5G", "6G", "卫星", "低空经济", "人形机器人",
                "存储", "PCB", "MOSFET", "CPO", "光通信", "电子",
                "传媒", "游戏", "教育", "氢能", "储能", "多模态",
                "黄金", "有色", "煤炭", "石油", "天然气", "电力"]
    
    return daily_zt_count  # 暂用全市场涨停数 (相对值)


def run(days_back, end_date):
    print(f"📅 {VERSION} 回测: 最近 {days_back} 工作日, 截至 {end_date}", flush=True)
    days = trading_days(end_date, days_back)
    print(f"   {days[0]} → {days[-1]}\n", flush=True)

    print(f"🔥 [1/4] 抓 {len(days)} 天龙虎榜...", flush=True)
    all_recs = []
    for i, d in enumerate(days):
        recs = fetch_lhb(d)
        for r in recs:
            all_recs.append((d, r.get("SECURITY_CODE"), r.get("SECURITY_NAME_ABBR"), r))
        print(f"   [{i+1:>2}/{len(days)}] {d}: {len(recs):>3}", flush=True)
        time.sleep(0.25)
    print(f"   总记录: {len(all_recs)}", flush=True)

    by_code = defaultdict(list)
    for d,c,n,r in all_recs: by_code[c].append((d,n,r))
    print(f"\n🔍 [2/4] K线 ({len(by_code)} 只)...", flush=True)
    beg = (datetime.strptime(days[0],"%Y-%m-%d")-timedelta(days=15)).strftime("%Y-%m-%d")
    end_buf = (datetime.strptime(days[-1],"%Y-%m-%d")+timedelta(days=10)).strftime("%Y-%m-%d")
    klines_by_code = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fetch_k, c, beg, end_buf): c for c in by_code.keys()}
        done = 0
        for fut in as_completed(futs):
            klines_by_code[futs[fut]] = fut.result()
            done += 1
            if done % 100 == 0: print(f"   K线 [{done}/{len(by_code)}]", flush=True)

    # 计算"板块梯队"代理 (当日全市场涨停数, 用于权重)
    print(f"\n📊 [3/4] 计算板块梯队 + 全市场涨停数...", flush=True)
    daily_zt_count = compute_sector_zt(by_code, klines_by_code)

    # 计算每只票当日的"同期涨停股数" (用全市场为占位, 后续可加板块匹配)
    sector_zt = {}
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,n,r in items:
            i = idxmap.get(d)
            if i is not None and is_zt(code, kl[i]["chg_pct"]):
                # 把全市场涨停数 / 50 作为"板块梯队相对强度"代理
                # 即: 当日全市场涨停 ≥ 60 → 高潮市, 多 = 板块梯队多
                cnt = daily_zt_count.get(d, 1)
                # 给当前 code 用 cnt / 5 作为代理 (近似板块密度)
                sector_zt[code] = max(1, cnt // 8)

    print(f"   日均涨停数: {sum(daily_zt_count.values())/max(1,len(daily_zt_count)):.0f}", flush=True)

    print(f"\n📊 [4/4] {VERSION} 评分...", flush=True)
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
            sc = score_v22(rec, kl, i, sector_zt)
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
    print(f"\n   {VERSION} 总体: n={n} 晋级={pr} ({rate:.2f}%)  均开{avgo:+.2f}% 均收{avgc:+.2f}% 均高{avgh:+.2f}%", flush=True)

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

    DIM_LABEL = {"form":"反包/形态","fund_trap":"龙虎榜陷阱","vol":"量价关系",
                 "distinct":"连板辨识度","cap_vol":"盘子+量能","sector":"板块梯队"}
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
    for thr in range(40,101,5):
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

    p_json = OUT_DIR / f"v22-results-{end_date}.json"
    with open(p_json,"w",encoding="utf-8") as f:
        json.dump({"version":VERSION,"summary":{"n":n,"promoted":pr,"rate":rate},
                   "buckets":score_buckets,"dims":dim_analysis,"thresholds":thr_analysis,
                   "samples":samples}, f, ensure_ascii=False, indent=2, default=str)
    print(f"   ✅ JSON: {p_json}")


def write_md(samples, n, pr, rate, avgo, avgc, avgh, buckets, dims, thresholds, top_hit, top_miss, end_date):
    p = OUT_DIR / f"v22-results-{end_date}.md"
    md=[]
    md.append(f"# {VERSION} 涨停晋级策略 回测报告\n")
    md.append(f"_截止 {end_date} (北京) | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 总览\n")
    md.append(f"- 总样本: **{n}**, 晋级率 **{rate:.2f}%** ({pr}/{n})")
    md.append(f"- 次日均开 {avgo:+.2f}%, 均收 {avgc:+.2f}%, 均高 {avgh:+.2f}%\n")

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

    md.append("## ✅ 高分命中 (≥70 分且晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 形态 | 资金 | 量价 | 辨识 | 盘量 | 板块 | 次日收 |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in top_hit:
        sc = s["scores"]
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {sc.get('form',0)} | {sc.get('fund_trap',0)} | {sc.get('vol',0)} | {sc.get('distinct',0)} | {sc.get('cap_vol',0)} | {sc.get('sector',0)} | {s['next_close']:+.2f}% |")

    md.append("\n## ❌ 高分炸板 (≥70 分未晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 形态 | 资金 | 量价 | 辨识 | 盘量 | 板块 | 次日收 |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in top_miss:
        sc = s["scores"]
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {sc.get('form',0)} | {sc.get('fund_trap',0)} | {sc.get('vol',0)} | {sc.get('distinct',0)} | {sc.get('cap_vol',0)} | {sc.get('sector',0)} | {s['next_close']:+.2f}% |")

    with open(p, "w", encoding="utf-8") as f: f.write("\n".join(md))
    print(f"   ✅ MD: {p}")


if __name__ == "__main__":
    days_back = int(sys.argv[1]) if len(sys.argv)>1 else 30
    end_date = sys.argv[2] if len(sys.argv)>2 else datetime.now(BJT).strftime("%Y-%m-%d")
    run(days_back, end_date)
