#!/usr/bin/env python3
"""
backtest_v21.py — 涨停晋级 v2.1 (基于 v2.0 回测的反馈调整)

v2.0 → v2.1 修订:
  ① 反包/形态 (20分)        保持
  ② 业绩雷扫描 (一票否决 -30分)  ← 反向使用!
  ③ 涨价逻辑 (15分)         占位 (无数据)
  ④ 龙虎榜陷阱 (-15分扣分)  ← 反向使用! 多家机构买入扣分
  ⑤ 量价关系 (20分, 权重↑)  ← 强有效, 加权
  ⑥ 连板辨识度 (25分, 权重↑) ← 最强有效, 加权

满分: 100 (反包20 + 涨价15 + 量价20 + 连板25 + 微调20) - 业绩雷一票否决 - 资金陷阱扣分
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
VERSION = "v2.1"


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


_perf_cache = {}
def fetch_perf(code):
    if code in _perf_cache: return _perf_cache[code]
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
           "reportName=RPT_LICO_FN_CPD_BB&columns=ALL&pageSize=8&pageNumber=1&"
           f"filter=(SECURITY_CODE%3D%22{code}%22)")
    d = http_get(url)
    rows = []
    if d and isinstance(d.get("result"), dict):
        rows = d["result"].get("data") or []
    _perf_cache[code] = {"reports": rows}
    return _perf_cache[code]


def score_v21(rec, kline, idx, perf_data):
    """v2.1 评分"""
    code = rec.get("SECURITY_CODE","")
    today = kline[idx]
    explain = (rec.get("EXPLAIN") or rec.get("EXPLANATION") or "")
    sc = {}; ft = {}; vetoes = []

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

    # ─── ② 业绩雷一票否决 (-30 分) ───
    perf_score = 0  # v2.1 不再用业绩当加分
    perf_veto = False
    perf_reason = "无数据"
    if perf_data and perf_data["reports"]:
        today_dt = datetime.strptime(today["date"], "%Y-%m-%d")
        latest = None
        latest_dt = None
        for r in perf_data["reports"]:
            nd = r.get("NOTICE_DATE", "")
            if nd:
                try:
                    nd_dt = datetime.strptime(nd[:10], "%Y-%m-%d")
                    if nd_dt <= today_dt and (latest_dt is None or nd_dt > latest_dt):
                        latest = r; latest_dt = nd_dt
                except: pass
        if latest:
            tq = latest.get("PARENT_NETPROFIT_TQ")
            ft["perf_tq"] = tq
            ft["perf_period"] = latest.get("REPORTDATEWZ", "")
            if tq is not None and tq < -30:
                # 业绩雷! 但不一票否决, 而是给 -30 惩罚 (允许极强题材股反弹)
                perf_score = -30
                perf_veto = True
                vetoes.append(f"业绩雷({latest.get('REPORTDATEWZ','')} 净利同比 {tq:.1f}%)")
                perf_reason = f"业绩雷 {tq:.1f}%"
            else:
                perf_score = 0
                perf_reason = f"{latest.get('REPORTDATEWZ','')} {tq}%"
    sc["perf"] = perf_score
    ft["perf_reason"] = perf_reason
    ft["perf_veto"] = perf_veto

    # ─── ③ 涨价逻辑 (15分占位) ───
    if "涨价" in explain or "提价" in explain:
        sc["price_logic"] = 8
    else:
        sc["price_logic"] = 5

    # ─── ④ 龙虎榜陷阱 (反向: 多家机构买入扣分) ───
    # v2.0 数据: 多家机构买入 (得分13) 晋级率 13.4% (低于平均 21%) → 扣分
    fund_score = 0
    if "机构" in explain and "买入" in explain:
        # 数 "机构"出现次数
        n_inst = explain.count("机构")
        if n_inst >= 3:
            fund_score = -10  # 3+ 机构买入 = 大概率出货
        elif n_inst >= 2:
            fund_score = -5
        else:
            fund_score = 0
    elif "机构" in explain and "卖出" in explain:
        # 机构卖出反而是利好? 测试一下 (v2.0 显示 0 分票晋级率 24.7%)
        fund_score = 5
    else:
        # 无机构席位 = 纯游资 = 反而晋级率高
        fund_score = 5
    sc["fund_trap"] = fund_score

    # ─── ⑤ 量价关系 (20分, 权重↑) ───
    prev = kline[idx-1] if idx>0 else None
    vol_score = 10
    vol_reason = "无前日"
    if prev and prev["vol"] > 0:
        rv = today["vol"] / prev["vol"]
        ft["vol_ratio"] = round(rv, 2)
        prev_chg = prev["chg_pct"]
        if rv < 0.7 and prev_chg > 5:
            vol_score = 20  # 缩量加速 (满分↑)
            vol_reason = "缩量加速"
        elif 0.8 <= rv <= 1.5:
            vol_score = 16  # 温和放量
            vol_reason = "温和放量"
        elif 1.5 < rv <= 3:
            vol_score = 10
            vol_reason = "爆量"
        elif rv > 3:
            vol_score = 5
            vol_reason = "天量"
        else:
            vol_score = 6
            vol_reason = "缩量但弱"
    sc["vol"] = vol_score
    ft["vol_reason"] = vol_reason

    # ─── ⑥ 连板辨识度 (25分, 权重↑) ───
    if n_zt_5d >= 5:
        sc["distinct"] = 25  # 市场最高板 (满分)
    elif n_zt_5d >= 3:
        sc["distinct"] = 20  # 板块龙头
    elif n_zt_5d == 2:
        sc["distinct"] = 16  # 二板晋级
    elif n_zt_5d == 1:
        sc["distinct"] = 12  # 前排跟风
    else:
        sc["distinct"] = 5

    total = sum(sc.values())
    return {"scores": sc, "total": total, "features": ft, "vetoes": vetoes}


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

    print(f"\n📊 [3/4] 筛涨停 + 业绩...", flush=True)
    zt_codes = set()
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,n,r in items:
            i = idxmap.get(d)
            if i is not None and is_zt(code, kl[i]["chg_pct"]):
                zt_codes.add(code); break
    print(f"   涨停股: {len(zt_codes)}", flush=True)
    perf_by_code = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_perf, c): c for c in zt_codes}
        done = 0
        for fut in as_completed(futs):
            perf_by_code[futs[fut]] = fut.result()
            done += 1
            if done % 100 == 0: print(f"   业绩 [{done}/{len(zt_codes)}]", flush=True)

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
            sc = score_v21(rec, kl, i, perf_by_code.get(code))
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

    # 业绩雷影响
    veto_n = sum(1 for s in samples if s.get("vetoes"))
    if veto_n > 0:
        veto_p = sum(1 for s in samples if s.get("vetoes") and s["promoted"])
        no_veto_p = pr - veto_p
        no_veto_n = n - veto_n
        print(f"   业绩雷: n={veto_n}, 晋级率={veto_p/veto_n*100:.1f}%", flush=True)
        print(f"   非业绩雷: n={no_veto_n}, 晋级率={no_veto_p/no_veto_n*100:.1f}%", flush=True)

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

    DIM_LABEL = {"form":"反包/形态","perf":"业绩雷罚","price_logic":"涨价占位",
                 "fund_trap":"龙虎榜陷阱","vol":"量价关系","distinct":"连板辨识度"}
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

    p_json = OUT_DIR / f"v21-results-{end_date}.json"
    with open(p_json,"w",encoding="utf-8") as f:
        json.dump({"version":VERSION,"summary":{"n":n,"promoted":pr,"rate":rate},
                   "buckets":score_buckets,"dims":dim_analysis,"thresholds":thr_analysis,
                   "samples":samples}, f, ensure_ascii=False, indent=2, default=str)
    print(f"   ✅ JSON: {p_json}")


def write_md(samples, n, pr, rate, avgo, avgc, avgh, buckets, dims, thresholds, top_hit, top_miss, end_date):
    p = OUT_DIR / f"v21-results-{end_date}.md"
    md=[]
    md.append(f"# {VERSION} 涨停晋级策略 回测报告\n")
    md.append(f"_截止 {end_date} (北京) | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 总览\n")
    md.append(f"- 总样本: **{n}**")
    md.append(f"- 总体晋级率: **{rate:.2f}%** ({pr}/{n})")
    md.append(f"- 次日均开盘: **{avgo:+.2f}%**, 次日均收: **{avgc:+.2f}%**, 次日均高: **{avgh:+.2f}%**\n")

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
    md.append("| 日期 | 代码 | 名称 | 总分 | 形态 | 业绩 | 涨价 | 资金 | 量价 | 辨识 | 次日收 | 雷? |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for s in top_hit:
        sc = s["scores"]; veto = "/".join(s.get("vetoes") or []) or "-"
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {sc.get('form',0)} | {sc.get('perf',0)} | {sc.get('price_logic',0)} | {sc.get('fund_trap',0)} | {sc.get('vol',0)} | {sc.get('distinct',0)} | {s['next_close']:+.2f}% | {veto} |")

    md.append("\n## ❌ 高分炸板 (≥70 分未晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 形态 | 业绩 | 涨价 | 资金 | 量价 | 辨识 | 次日收 | 雷? |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for s in top_miss:
        sc = s["scores"]; veto = "/".join(s.get("vetoes") or []) or "-"
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | **{s['total']}** | {sc.get('form',0)} | {sc.get('perf',0)} | {sc.get('price_logic',0)} | {sc.get('fund_trap',0)} | {sc.get('vol',0)} | {sc.get('distinct',0)} | {s['next_close']:+.2f}% | {veto} |")

    with open(p, "w", encoding="utf-8") as f: f.write("\n".join(md))
    print(f"   ✅ MD: {p}")


if __name__ == "__main__":
    days_back = int(sys.argv[1]) if len(sys.argv)>1 else 30
    end_date = sys.argv[2] if len(sys.argv)>2 else datetime.now(BJT).strftime("%Y-%m-%d")
    run(days_back, end_date)
