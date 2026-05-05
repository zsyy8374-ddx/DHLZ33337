#!/usr/bin/env python3
"""
002805 丰元股份 节后 5-6 09:35 开盘扫描.
查: 当前价/涨跌幅/封单结构/板块同步性 → 输出操作建议.

调用: python3 watch_002805.py
环境变量: MX_APIKEY
"""
import os, sys, json, subprocess, datetime, urllib.request
from pathlib import Path

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
MX_DATA = WORKSPACE / "skills/mx-data/mx_data.py"
OUT_DIR = WORKSPACE / "mx_output/002805/watch"
OUT_DIR.mkdir(parents=True, exist_ok=True)

YESTERDAY_CLOSE = 22.85  # 4-30 收盘
ZT_START = 21.00         # 4-29 涨停起点 (清仓红线)

def run_mx(query: str) -> dict:
    out = subprocess.run(
        ["python3", str(MX_DATA), query, str(OUT_DIR)],
        capture_output=True, text=True, env={**os.environ},
        timeout=60
    )
    # find raw json
    safe = query.replace(" ", "_").replace("/", "_")
    for f in sorted(OUT_DIR.glob(f"mx_data_{safe[:60]}*_raw.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            return json.loads(f.read_text())
        except: pass
    return {"_stdout": out.stdout, "_stderr": out.stderr}

def extract_table(raw: dict, sheet_idx: int = 0) -> list:
    try:
        tables = raw.get("result", {}).get("dataTableDTOList", [])
        if sheet_idx >= len(tables): return []
        t = tables[sheet_idx]
        cols = [c.get("name") or c.get("nameCh") or c.get("nameEn") for c in t.get("columnDescList", [])]
        rows = []
        for row in t.get("dataList", []):
            rows.append(dict(zip(cols, row)))
        return rows
    except Exception as e:
        return [{"_err": str(e)}]

def fmt_pct(x):
    try: return f"{float(x):.2f}%"
    except: return str(x)

def fetch_realtime_eastmoney(code: str = "002805") -> dict:
    """东财香港 IP 备用实时行情接口 (海外可访问)."""
    secid = f"0.{code}" if code.startswith(("00","30")) else f"1.{code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz{code}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        d = data.get("data",{}).get(f"sz{code}",{}).get("data",{})
        qt = d.get("qt",{}).get(f"sz{code}",[])
        if qt and len(qt) > 35:
            return {
                "name": qt[1], "price": float(qt[3]), "pre_close": float(qt[4]),
                "open": float(qt[5]), "vol": qt[6], "amount": qt[37] if len(qt)>37 else None,
                "pct": float(qt[32]) if qt[32] else None,
                "high": float(qt[33]), "low": float(qt[34]), "turnover": qt[38] if len(qt)>38 else None
            }
    except Exception as e:
        return {"_err": str(e)}
    return {}

def main():
    lines = []
    lines.append(f"📊 002805 丰元股份 — 节后 5-6 开盘扫描")
    lines.append(f"扫描时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Beijing)")
    lines.append(f"参考线: 昨收 ¥{YESTERDAY_CLOSE} / 红线 ¥{ZT_START}")
    lines.append("")

    # 1. 实时行情 (东财香港接口, 海外稳定)
    rt = fetch_realtime_eastmoney("002805")
    cur_price = None
    if rt and "price" in rt:
        cur_price = rt["price"]
        lines.append(f"💰 当前: ¥{rt['price']:.2f} ({rt.get('pct',0):+.2f}%)")
        lines.append(f"   开 {rt['open']:.2f} | 高 {rt['high']:.2f} | 低 {rt['low']:.2f} | 昨收 {rt['pre_close']:.2f}")
        if rt.get("turnover"):
            lines.append(f"   换手率 {rt['turnover']}% | 成交额 {rt.get('amount','-')}")
        gap_pct = (rt["price"] - YESTERDAY_CLOSE) / YESTERDAY_CLOSE * 100
        lines.append(f"   vs 4-30 收: {gap_pct:+.2f}%")
    else:
        lines.append(f"⚠️ 实时行情拉取失败: {rt.get('_err','no data')}")
        # fallback to mx_data
        raw = run_mx("002805丰元股份最新价 涨跌幅 成交量 换手率")
        rows = extract_table(raw, 0)
        if rows:
            r = rows[0]
            cur_price = r.get("收盘价") or r.get("最新价")
            lines.append(f"💰 备用源: ¥{cur_price} ({fmt_pct(r.get('涨跌幅'))})")

    # 2. 资金流向
    raw2 = run_mx("002805主力资金净流入")
    rows2 = extract_table(raw2, 0)
    if rows2:
        r = rows2[0]
        # try multiple field names
        net = None
        for k in ("主力净流入","主力净流入资金","净流入"):
            if k in r:
                net = r[k]; break
        if net is not None:
            lines.append(f"💸 主力资金: {net}")

    # 3. 板块状态 (固态电池)
    raw3 = run_mx("固态电池板块今日涨幅 涨停家数")
    rows3 = extract_table(raw3, 0)
    if rows3:
        r = rows3[0]
        sec_pct = r.get("涨跌幅(算数平均)") or r.get("涨跌幅")
        lines.append(f"🔋 固态电池板块: {fmt_pct(sec_pct)}")

    raw4 = run_mx("固态电池板块今日涨停股数量")
    rows4 = extract_table(raw4, 0)
    if rows4:
        r = rows4[0]
        zt_count = r.get("涨停家数") or "-"
        lines.append(f"   板块涨停家数: {zt_count}")

    # 4. 封单状态 (尝试)
    raw5 = run_mx("002805当前涨停封单量 封单额")
    rows5 = extract_table(raw5, 0)
    if rows5:
        r = rows5[0]
        lines.append(f"🔒 封单: {r}")

    # 5. 操作建议
    lines.append("")
    lines.append("🎯 操作建议:")
    try:
        cp = float(str(cur_price).replace("元","")) if not isinstance(cur_price,(int,float)) else float(cur_price)
        gap = (cp - YESTERDAY_CLOSE) / YESTERDAY_CLOSE * 100
        if cp < ZT_START:
            lines.append(f"  🚨 已跌破红线 ¥{ZT_START} → **立即清仓**, 不要犹豫")
        elif gap >= 5:
            lines.append(f"  ⚠️ 高开 {gap:.1f}% 冲高 → **建议清仓获利了结**, 不贪第3连板")
        elif gap >= 1:
            lines.append(f"  🟡 高开 {gap:.1f}% → 看 10:00 前能否站稳 ¥{YESTERDAY_CLOSE}")
            lines.append(f"     站住: 持有观察 / 跌破: 减半仓")
        elif gap >= -2:
            lines.append(f"  🟡 平/小幅低开 → **建议清仓**, 走出来再说")
        else:
            lines.append(f"  🚨 低开 {gap:.1f}% → **直接割肉**, 这种走势主力出货实锤")
    except:
        lines.append("  (无法解析价格, 请人工判断)")

    lines.append("")
    lines.append("铁纪律: ¥21.00 红线 / 不补仓 / 早盘 10:00 前出胜负")

    out_text = "\n".join(lines)
    print(out_text)

    # save snapshot
    snap = OUT_DIR / f"snapshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    snap.write_text(out_text, encoding="utf-8")

if __name__ == "__main__":
    main()
