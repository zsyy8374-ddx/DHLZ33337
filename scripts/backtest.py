#!/usr/bin/env python3
"""
backtest.py — 晋级股精选策略 v1.0 回测引擎

用法: python3 scripts/backtest.py [days_back=30] [end_date=今天]
输出: backtest/results-{end_date}.{json,md}
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

def is_zt(code, chg):
    if chg is None: return False
    if code.startswith(('300','688')): return chg >= 19.5
    if code.startswith(('8','4','9')): return chg >= 29.5
    return chg >= 9.7

def http_get(url, retries=4, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last_err = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                txt = r.read().decode("utf-8", errors="replace")
                if not txt.strip(): raise ValueError("empty")
                return json.loads(txt)
        except Exception as e:
            last_err = e
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

def secid(code):
    return f"1.{code}" if code.startswith('6') else f"0.{code}"

_kc = {}
def tx_prefix(code):
    return "sh" if code.startswith('6') else "sz"

def fetch_k(code, beg, end):
    """腾讯 K 线接口 (海外可达), 返回列表: date, open, close, high, low, vol, chg_pct, turnover"""
    key = f"{code}|{beg}|{end}"
    if key in _kc: return _kc[key]
    sym = tx_prefix(code) + code
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={sym},day,{beg},{end},320,qfq")
    d = http_get(url)
    if not d: _kc[key]=[]; return []
    sd = d.get("data",{}).get(sym,{})
    # 腾讯 返回 qfqday 或 day, 字段: [日期, 开, 收, 高, 低, 量]
    klines = sd.get("qfqday") or sd.get("day") or []
    out = []
    for k in klines:
        if len(k) < 6: continue
        try:
            o, c, h, l = float(k[1]), float(k[2]), float(k[3]), float(k[4])
            vol = float(k[5])
            out.append({"date":k[0],"open":o,"close":c,"high":h,"low":l,
                        "vol":vol,"amt":0.0,"chg_pct":0.0,"turnover":0.0})
        except: pass
    # 带上涨跌幅 (腾讯不提供, 手算)
    for i in range(len(out)):
        if i == 0: out[i]["chg_pct"] = 0.0
        else:
            pc = out[i-1]["close"]
            out[i]["chg_pct"] = (out[i]["close"] - pc)/pc*100 if pc>0 else 0
    _kc[key]=out
    return out

def score_v1(rec, kline, idx):
    code = rec.get("SECURITY_CODE","")
    today = kline[idx]
    prev = kline[idx-1] if idx>0 else None
    explain = (rec.get("EXPLAIN") or rec.get("EXPLANATION") or "")
    sc={}; ft={}
    # D1 题材纯度
    if "20%" in explain or "连续三个" in explain: sc["theme"]=18
    elif "异动" in explain or "7%" in explain: sc["theme"]=12
    elif "买入" in explain and "机构" in explain: sc["theme"]=10
    else: sc["theme"]=5
    # D2 封板
    chg = today.get("chg_pct",0); ft["chg_pct"]=chg
    if is_zt(code, chg): sc["seal"]=16
    elif chg>=7: sc["seal"]=8
    elif chg>=0: sc["seal"]=4
    else: sc["seal"]=0
    # D3 位置高度
    n_zt = sum(1 for j in range(max(0,idx-4), idx+1) if j<len(kline) and is_zt(code, kline[j]["chg_pct"]))
    ft["zt_5d"]=n_zt
    sc["height"]={1:12,2:15,3:12,4:8,5:3}.get(n_zt, 0)
    # D4 资金强度
    free_cap = rec.get("FREE_MARKET_CAP",0) or 0
    net_amt = rec.get("BILLBOARD_NET_AMT",0) or rec.get("NET_BS_AMT",0) or 0
    ft["net_wan"]=round(net_amt/10000,0); ft["cap_yi"]=round(free_cap/1e8,1)
    if free_cap>0:
        r = net_amt/free_cap*100; ft["net_to_cap_pct"]=round(r,2)
        sc["fund"]=15 if r>=3 else 12 if r>=1.5 else 8 if r>=0.5 else 3 if r>=0 else 0
    else:
        sc["fund"]=5
    # D5 龙虎榜
    if "机构" in explain and "买入" in explain: sc["lhb"]=12
    elif "机构" in explain and "卖出" in explain: sc["lhb"]=0
    elif net_amt>0: sc["lhb"]=8
    else: sc["lhb"]=3
    # D6 盘子+量能
    cap = free_cap/1e8
    sc_c = 5 if 30<=cap<=80 else 3 if (20<=cap<30 or 80<cap<=150) else 1
    sc_v = 3
    if prev and prev.get("vol",0)>0:
        rv = today["vol"]/prev["vol"]; ft["vol_ratio"]=round(rv,2)
        sc_v = 5 if rv<=0.7 else 4 if rv<=1.5 else 2 if rv<=2.5 else 0
    sc["cap_vol"]=sc_c+sc_v
    return {"scores":sc, "total":sum(sc.values()), "features":ft}

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
    print(f"📅 回测期: 最近 {days_back} 工作日, 截至 {end_date}", flush=True)
    days = trading_days(end_date, days_back)
    print(f"   {days[0]} → {days[-1]}\n", flush=True)

    print(f"🔥 [1/3] 抓 {len(days)} 天龙虎榜...", flush=True)
    all_recs=[]
    for i,d in enumerate(days):
        recs = fetch_lhb(d)
        for r in recs: all_recs.append((d, r.get("SECURITY_CODE"), r.get("SECURITY_NAME_ABBR"), r))
        print(f"   [{i+1:>2}/{len(days)}] {d}: {len(recs):>3} 只", flush=True)
        time.sleep(0.25)
    print(f"\n   总记录: {len(all_recs)}", flush=True)

    print(f"\n🔍 [2/3] K线 + 评分...", flush=True)
    by_code = defaultdict(list)
    for d,c,n,r in all_recs: by_code[c].append((d,n,r))
    print(f"   涉及个股: {len(by_code)}", flush=True)

    beg = (datetime.strptime(days[0],"%Y-%m-%d")-timedelta(days=15)).strftime("%Y-%m-%d")
    end_buf = (datetime.strptime(days[-1],"%Y-%m-%d")+timedelta(days=10)).strftime("%Y-%m-%d")

    samples=[]; no_kline=not_zt=no_next=0
    # 并发拉 K 线 (10 线程)
    def _fetch(code):
        return code, fetch_k(code, beg, end_buf)
    klines_by_code = {}
    done=0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_fetch, c) for c in by_code.keys()]
        for fut in as_completed(futs):
            c, kl = fut.result()
            klines_by_code[c] = kl
            done += 1
            if done % 50 == 0:
                print(f"   K线进度 [{done}/{len(by_code)}]", flush=True)
    # 评分
    for code, items in by_code.items():
        kl = klines_by_code.get(code) or []
        if not kl: no_kline += len(items); continue
        idxmap = {k["date"]:i for i,k in enumerate(kl)}
        for d,name,rec in items:
            i = idxmap.get(d)
            if i is None: continue
            if not is_zt(code, kl[i]["chg_pct"]): not_zt+=1; continue
            sc = score_v1(rec, kl, i)
            oc = outcome(kl, i, code)
            if not oc: no_next+=1; continue
            samples.append({"date":d, "code":code, "name":name,
                            **sc, **oc,
                            "explain":(rec.get("EXPLAIN") or rec.get("EXPLANATION") or "")[:80]})

    print(f"\n   有效样本: {len(samples)} | 无K线={no_kline} 非涨停={not_zt} 无次日={no_next}", flush=True)
    if not samples: print("❌ 无样本"); return

    print(f"\n📊 [3/3] 分析 + 写报告...", flush=True)
    analyze(samples, end_date)

def analyze(samples, end_date):
    n = len(samples); pr = sum(1 for s in samples if s["promoted"]); rate = pr/n*100
    avgo = sum(s["next_open"] for s in samples)/n
    avgc = sum(s["next_close"] for s in samples)/n
    avgh = sum(s["next_high"] for s in samples)/n
    print(f"   总体: n={n} 晋级={pr} ({rate:.2f}%)  均开{avgo:+.2f}% 均收{avgc:+.2f}% 均高{avgh:+.2f}%", flush=True)

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

    # 维度
    DIM_LABEL = {"theme":"题材纯度","seal":"封板/涨幅","height":"位置高度",
                 "fund":"资金强度","lhb":"龙虎榜信号","cap_vol":"盘子+量能"}
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

    # 阈值
    thr_analysis=[]
    for thr in range(40,91,5):
        sub=[s for s in samples if s["total"]>=thr]
        if len(sub)<5: continue
        p=sum(1 for s in sub if s["promoted"])
        thr_analysis.append({"thr":thr,"n":len(sub),"p":p,
                             "rate":round(p/len(sub)*100,1),
                             "avg_close":round(sum(s["next_close"] for s in sub)/len(sub),2)})

    # TOP 命中
    top_hit = sorted([s for s in samples if s["promoted"] and s["total"]>=70], key=lambda s:-s["total"])[:20]
    top_miss = sorted([s for s in samples if not s["promoted"] and s["total"]>=80], key=lambda s:-s["total"])[:20]

    write_md(samples, n, pr, rate, avgo, avgc, avgh,
             score_buckets, dim_analysis, thr_analysis, top_hit, top_miss, end_date)
    write_json(samples, score_buckets, dim_analysis, thr_analysis, n, pr, rate, end_date)

def write_json(samples, buckets, dims, thresholds, n, pr, rate, end_date):
    p = OUT_DIR / f"results-{end_date}.json"
    with open(p,"w",encoding="utf-8") as f:
        json.dump({"summary":{"n":n,"promoted":pr,"rate":rate},
                   "buckets":buckets,"dims":dims,"thresholds":thresholds,
                   "samples":samples}, f, ensure_ascii=False, indent=2, default=str)
    print(f"   ✅ JSON: {p}")

def write_md(samples, n, pr, rate, avgo, avgc, avgh, buckets, dims, thresholds, top_hit, top_miss, end_date):
    p = OUT_DIR / f"results-{end_date}.md"
    md=[]
    md.append(f"# 晋级股策略 v1.0 回测报告\n")
    md.append(f"_截止 {end_date} (北京) | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}_\n")
    md.append(f"## 📊 总览\n")
    md.append(f"- 总样本: **{n}** (涨停 + 龙虎榜上榜 + 有次日数据)")
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

    md.append("\n## 🔬 各维度有效性 (高分胜率 - 低分胜率)\n")
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

    md.append("## ✅ 高分命中样本 (≥70 分且晋级)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 次日开 | 次日收 | 上榜原因 |")
    md.append("|---|---|---|---:|---:|---:|---|")
    for s in top_hit:
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | {s['total']} | {s['next_open']:+.2f}% | {s['next_close']:+.2f}% | {s['explain']} |")

    md.append("\n## ❌ 高分但未晋级 (≥80 分却炸板)\n")
    md.append("| 日期 | 代码 | 名称 | 总分 | 次日开 | 次日收 | 上榜原因 |")
    md.append("|---|---|---|---:|---:|---:|---|")
    for s in top_miss:
        md.append(f"| {s['date']} | {s['code']} | {s['name']} | {s['total']} | {s['next_open']:+.2f}% | {s['next_close']:+.2f}% | {s['explain']} |")

    md.append("\n## 💡 结论与 v2.0 优化方向\n")
    md.append("- 看上面**维度有效性表**: 高低差 ≥15% 的维度可加权重, ≤0 的维度需移除或反向用")
    md.append("- 看**阈值分析**: 找到晋级率拐点(从平稳变陡升), 那就是新的实盘门槛")
    md.append("- 看**高分炸板样本**: 找共同特征, 可能是新的一票否决项")
    md.append("- 注意: 本回测**用上榜原因近似题材纯度, 用 5日内涨停数代理板数, 用日 K 涨幅代理封板时间**, 真实策略效果可能更高")

    with open(p, "w", encoding="utf-8") as f: f.write("\n".join(md))
    print(f"   ✅ MD: {p}")


if __name__ == "__main__":
    days_back = int(sys.argv[1]) if len(sys.argv)>1 else 30
    end_date = sys.argv[2] if len(sys.argv)>2 else datetime.now(BJT).strftime("%Y-%m-%d")
    run(days_back, end_date)
