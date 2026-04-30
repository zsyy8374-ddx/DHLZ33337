#!/usr/bin/env python3
"""
build_sector_map.py — 离线构建股票→行业映射 (东财概念/行业)

逻辑:
  1. 东财行业板块全列表 (m:90+t:2)
  2. 每个板块拉成分股 (secid=BK0xxx)
  3. 反向构建 code → sector

输出: data/stock_sector_map.json
"""
import json, time
from pathlib import Path
from urllib.request import urlopen, Request

WORKSPACE = Path("/Users/openclaw/.openclaw/workspace-dengxian")
DATA_DIR = WORKSPACE / "data"
DATA_DIR.mkdir(exist_ok=True)


def http_get_json(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return None


def fetch_all_sectors():
    """东财所有行业 + 概念板块"""
    out = []
    for fs_code in ["m:90+t:2", "m:90+t:3"]:  # 行业 + 概念
        url = (f"http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1"
               f"&fltt=2&invt=2&fid=f3&fs={fs_code}&fields=f12,f14")
        d = http_get_json(url)
        if not d: continue
        items = d.get("data", {}).get("diff", []) or []
        for it in items:
            if it.get("f12"):
                out.append({"code": it["f12"], "name": it["f14"]})
    return out


def fetch_sector_stocks(sec_code):
    """单个板块的成分股"""
    url = (f"http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1"
           f"&fltt=2&invt=2&fid=f3&fs=b:{sec_code}+f:!50&fields=f12,f14")
    d = http_get_json(url)
    if not d: return []
    items = d.get("data", {}).get("diff", []) or []
    return [it["f12"] for it in items if it.get("f12")]


def main():
    print("📊 拉所有行业板块...", flush=True)
    sectors = fetch_all_sectors()
    print(f"   板块 {len(sectors)} 个", flush=True)
    
    # 构建 code -> [sector1, sector2, ...] (一只票可能在多个板块, 取第一个)
    code_to_sector = {}
    sector_constituents = {}
    
    for i, sec in enumerate(sectors):
        codes = fetch_sector_stocks(sec["code"])
        sector_constituents[sec["name"]] = {"code": sec["code"], "stocks": codes}
        for code in codes:
            if code not in code_to_sector:
                code_to_sector[code] = sec["name"]
        time.sleep(0.1)
        if (i + 1) % 20 == 0:
            print(f"   [{i+1}/{len(sectors)}] 累计股票 {len(code_to_sector)}", flush=True)
    
    print(f"\n✅ 总覆盖: {len(code_to_sector)} 只股票", flush=True)
    
    out = {
        "code_to_sector": code_to_sector,
        "sector_constituents": sector_constituents,
        "n_stocks": len(code_to_sector),
        "n_sectors": len(sectors),
    }
    
    save_path = DATA_DIR / "stock_sector_map.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"📁 落档: {save_path}", flush=True)


if __name__ == "__main__":
    main()
