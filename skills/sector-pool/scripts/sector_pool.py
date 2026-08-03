#!/usr/bin/env python3
"""
sector_pool.py — 三平台板块池构建 v2.0
1. 同花顺: thsdk 搜概念 → block_constituents 拉成分股
2. 通达信: 问小达按「所属通达信概念」聚合 → 每板块的成分股即是该次查询结果
3. 东方财富: 先拉全量板块列表 → 关键词筛选 → push2 API 拉成分股

用法:
 python3 sector_pool.py "新型电力系统" --keywords "智能电网" "特高压" --json
"""
import json, sys, argparse, subprocess, time, urllib.request, ssl
from collections import defaultdict, Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
TOOLS = WORKSPACE / "tools"

# ============================================================
# 平台一：同花顺 (THS)
# ============================================================

def _search_ths_concepts(keywords: list[str]) -> dict:
    """thsdk.search_symbols → 只保留概念(URFI)+行业(UFIA)板块."""
    result = {}
    try:
        from thsdk import THS
        ths = THS({'username': 'zsyyddx', 'password': 'jgyyddx33'})
        ths.connect()
        for kw in keywords:
            try:
                r = ths.search_symbols(kw)
                if r and r.success and r.data:
                    for item in r.data:
                        mkt = item.get('MarketStr', '')
                        if mkt in ('URFI', 'UFIA'):
                            code = item.get('THSCODE', '')
                            name = item.get('Name', '')
                            if code and code not in result:
                                result[code] = {'name': name, 'market': mkt, 'keyword': kw}
            except Exception:
                pass
    except Exception as e:
        print(f"[THS] error: {e}", file=sys.stderr)
    return result


def _ths_get_stocks(sector_code: str) -> list[dict]:
    """thsdk.block_constituents → 成分股列表."""
    try:
        from thsdk import THS
        ths = THS({'username': 'zsyyddx', 'password': 'jgyyddx33'})
        ths.connect()
        r = ths.block_constituents(sector_code)
        if r and r.success and r.data:
            stocks = []
            for item in r.data:
                raw_code = item.get('代码', '')
                name = item.get('名称', '')
                clean = raw_code.replace('USHA','').replace('USZA','').replace('USZJ','').replace('USHJ','')
                if clean and len(clean) == 6:
                    stocks.append({'code': clean, 'name': name})
            return stocks
    except Exception as e:
        print(f"[THS] constituents error {sector_code}: {e}", file=sys.stderr)
    return []


# ============================================================
# 平台二：通达信 (TDX/问小达)
# ============================================================

def _tdx_query(query: str) -> list[dict]:
    """tdx_zhangting.py --query → 完整字段股票列表."""
    tdx_tool = TOOLS / "tdx_zhangting.py"
    if not tdx_tool.exists():
        return []
    try:
        r = subprocess.run(["/usr/bin/python3", str(tdx_tool), "--query", query],
                          capture_output=True, text=True, timeout=120, cwd=str(WORKSPACE))
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except Exception as e:
        print(f"[TDX] query error '{query}': {e}", file=sys.stderr)
    return []


def _parse_tdx_field(val: str) -> list[str]:
    """@val1@val2@ → [val1, val2]."""
    return [p.strip() for p in (val or '').split('@') if p.strip()]


def _tdx_find_sectors(keywords: list[str]) -> dict:
    """问小达多词查询 → 按「所属通达信概念」聚合板块，附带板块代码(index_code).
    
    并行执行多词查询，总时间 ≈ 单次最长（~40s）而非累加。
    """
    all_stocks = []
    seen = set()
    
    # 串行查询，只跑前2个核心词（同花顺已覆盖板块映射，TDX做补充验证）
    kw_list = keywords[:2]
    print(f"[TDX] 串行查询 {len(kw_list)} 个关键词 (~{len(kw_list)*40}s)...", file=sys.stderr)
    for kw in kw_list:
        try:
            stocks = _tdx_query(kw)
            for s in stocks:
                key = s.get('sec_code', '')
                if key and key not in seen:
                    seen.add(key)
                    all_stocks.append(s)
            print(f"[TDX] '{kw}' → {len(stocks)} stocks", file=sys.stderr)
        except Exception as e:
            print(f"[TDX] '{kw}' failed: {e}", file=sys.stderr)
    
    if not all_stocks:
        return {}
    
    # 检测概念字段名
    concept_field = None
    for f in ['所属通达信概念', '所属通达信指数']:
        if any(s.get(f, '') for s in all_stocks[:10]):
            concept_field = f
            break
    
    # 按概念聚合
    sectors = {}
    for s in all_stocks:
        concepts = _parse_tdx_field(s.get(concept_field, '')) if concept_field else []
        concepts = concepts or ['(未分类)']
        code = s.get('sec_code', '')
        name = s.get('sec_name', '')
        idx_code = s.get('index_code', '')
        idx_market = s.get('index_market', '')
        
        for cname in concepts:
            if cname not in sectors:
                sectors[cname] = {
                    'name': cname,
                    'tdx_concept_code': f"{idx_market}{idx_code}" if idx_code else '',
                    'stocks': []
                }
            sectors[cname]['stocks'].append({'code': code, 'name': name})
    
    return sectors


# ============================================================
# 平台三：东方财富 (DFCF)
# ============================================================

# 多个 push2 服务器镜像
PUSH2_SERVERS = [
    'http://push2.eastmoney.com',
    'http://78.push2.eastmoney.com',
    'http://75.push2.eastmoney.com',
    'http://push2delay.eastmoney.com',
    'http://1.push2.eastmoney.com',
    'http://2.push2.eastmoney.com',
]


def _dfcf_fetch_all_boards() -> list[dict]:
    """全量拉东方财富概念板块列表 (fs=m:90+t:3, 500条).
    
    尝试多个 push2 服务器，返回 [{code: BKxxxx, name: 板块名}, ...].
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for server in PUSH2_SERVERS:
        try:
            url = f"{server}/api/qt/clist/get?fid=f62&po=1&pz=500&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:3&fields=f12,f14"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://data.eastmoney.com/bkzj/gn.html',
                'Accept': '*/*',
            })
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            data = json.loads(resp.read())
            boards = data.get('data', {}).get('diff', [])
            if boards and len(boards) > 50:
                result = [{'code': b.get('f12',''), 'name': b.get('f14','')} for b in boards if b.get('f12')]
                print(f"[DFCF] {server} → {len(result)} 个概念板块", file=sys.stderr)
                return result
        except Exception as e:
            print(f"[DFCF] {server}: {e}", file=sys.stderr)
            continue
    
    return []


def _dfcf_filter_boards(all_boards: list[dict], keywords: list[str]) -> dict:
    """从全量板块列表中筛选与主题相关的."""
    result = {}
    for b in all_boards:
        name = b['name']
        code = b['code']
        for kw in keywords:
            if kw in name:
                if code not in result:
                    result[code] = {'name': name, 'keyword': kw}
                break
    # 也做反向匹配：板块名中的关键词出现在我们列表里
    for b in all_boards:
        name = b['name']
        code = b['code']
        if code in result:
            continue
        # 板块名在已知电力映射中
        for known in ['电力','电网','储能','光伏','风电','核电','氢能','碳中和','碳交易',
                      '绿电','特高压','充电','换电','虚拟电厂','抽水蓄能','柔性直流',
                      '超超临界','生物质','光热','钠离子','固态电池','可控核聚变',
                      '新能源','太阳能','变压器','逆变器','发电','输变电','配电',
                      '能源互联网','新型电力','节能']:
            if known in name and code not in result:
                result[code] = {'name': name, 'keyword': known}
                break
    return result


def _dfcf_get_stocks(board_code: str) -> list[dict]:
    """push2 API 拉东方财富板块成分股."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for server in PUSH2_SERVERS:
        try:
            url = f"{server}/api/qt/clist/get?fid=f62&po=1&pz=1000&pn=1&np=1&fltt=2&invt=2&fs=b:{board_code}&fields=f12,f14"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://quote.eastmoney.com/',
            })
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            data = json.loads(resp.read())
            items = data.get('data', {}).get('diff', [])
            stocks = [{'code': i.get('f12',''), 'name': i.get('f14','')} for i in items if i.get('f12')]
            if stocks:
                return stocks
        except Exception:
            continue
    return []


# ============================================================
# 主流程
# ============================================================

KNOWN_BK = {
    '储能': 'BK0989','特高压':'BK0918','智能电网':'BK0581','固态电池':'BK0968',
    '氢能源':'BK0864','光伏概念':'BK0588','风电':'BK0600','核电':'BK0477',
    '充电桩':'BK0700','新能源':'BK0493','电力':'BK0428','电网设备':'BK0457',
    '碳中和':'BK0834','碳交易':'BK0840','虚拟电厂':'BK1095','抽水蓄能':'BK1055',
    '绿色电力':'BK1021','换电':'BK1076','钠离子电池':'BK1070','光热发电':'BK1080',
    '生物质能':'BK0880','超超临界':'BK0960','可控核聚变':'BK1120',
    '电力物联网':'BK0891','柔性直流输电':'BK1044','光伏建筑一体化':'BK0979',
    '光伏设备':'BK1031','风电设备':'BK1032','太阳能':'BK0589','电池':'BK1033',
    '燃料电池':'BK0682','熔盐储能':'BK1103','光伏发电':'BK1375','光伏主材':'BK1318',
}


def _run_ths(keywords):
    print("[sector_pool] === 同花顺 ===", file=sys.stderr)
    sectors = _search_ths_concepts(keywords)
    data = {'sectors': {}, 'total': 0}
    stocks_all = []
    for code, info in sectors.items():
        stocks = _ths_get_stocks(code)
        data['sectors'][code] = {
            'name': info['name'], 'market': info['market'],
            'keyword': info['keyword'], 'count': len(stocks), 'stocks': stocks,
        }
        data['total'] += len(stocks)
        stocks_all.extend(stocks)
        time.sleep(0.3)
    print(f"[sector_pool] THS: {len(sectors)} sectors, {data['total']} stock-refs", file=sys.stderr)
    return 'ths', data, stocks_all


def _run_tdx(keywords):
    print("[sector_pool] === 通达信 ===", file=sys.stderr)
    sectors = _tdx_find_sectors(keywords)
    data = {'sectors': {}, 'total': 0}
    stocks_all = []
    for cname, sec in sectors.items():
        stocks = sec['stocks']
        key = sec['tdx_concept_code'] or cname
        data['sectors'][key] = {
            'name': cname, 'tdx_concept_code': sec['tdx_concept_code'],
            'count': len(stocks), 'stocks': stocks,
        }
        data['total'] += len(stocks)
        stocks_all.extend(stocks)
    print(f"[sector_pool] TDX: {len(sectors)} sectors, {data['total']} stock-refs", file=sys.stderr)
    return 'tdx', data, stocks_all


def _run_dfcf(keywords):
    print("[sector_pool] === 东方财富 ===", file=sys.stderr)
    all_boards = _dfcf_fetch_all_boards()
    if all_boards:
        sectors = _dfcf_filter_boards(all_boards, keywords)
    else:
        print("[sector_pool] DFCF API 不可用，使用已知映射表", file=sys.stderr)
        sectors = {}
        for kw in keywords:
            for bn, bc in KNOWN_BK.items():
                if kw in bn or bn in kw:
                    if bc not in sectors:
                        sectors[bc] = {'name': bn, 'keyword': kw}
    
    data = {'sectors': {}, 'total': 0}
    stocks_all = []
    for code, info in sectors.items():
        stocks = _dfcf_get_stocks(code)
        data['sectors'][code] = {
            'name': info['name'], 'keyword': info['keyword'],
            'count': len(stocks), 'stocks': stocks,
        }
        data['total'] += len(stocks)
        stocks_all.extend(stocks)
    print(f"[sector_pool] DFCF: {len(sectors)} sectors, {data['total']} stock-refs", file=sys.stderr)
    return 'dfcf', data, stocks_all


def build_pool(theme: str, keywords: list[str], platforms=('ths','tdx','dfcf')):
    """三平台并行构建板块池."""
    pool = {'theme': theme, 'platforms': {}, 'merged_stocks': {}}
    
    # 三大平台并行执行
    tasks = []
    if 'ths' in platforms:
        tasks.append(('ths', _run_ths, keywords))
    if 'tdx' in platforms:
        tasks.append(('tdx', _run_tdx, keywords))
    if 'dfcf' in platforms:
        tasks.append(('dfcf', _run_dfcf, keywords))
    
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fn, kw): name for name, fn, kw in tasks}
        for fut in as_completed(futures):
            try:
                name, data, stocks = fut.result(timeout=300)
                pool['platforms'][name] = data
                for s in stocks:
                    pool['merged_stocks'].setdefault(s['code'], s)
            except Exception as e:
                print(f"[sector_pool] Platform {futures[fut]} failed: {e}", file=sys.stderr)
    
    pool['total_merged'] = len(pool['merged_stocks'])
    return pool


def main():
    parser = argparse.ArgumentParser(description="三平台板块池 v2.0")
    parser.add_argument("theme")
    parser.add_argument("--keywords", nargs="*", help="拆词关键词")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", "-o", help="输出JSON文件")
    parser.add_argument("--summary", action="store_true", help="只含代码，不含个股明细")
    parser.add_argument("--no-ths", action="store_true")
    parser.add_argument("--no-tdx", action="store_true")
    parser.add_argument("--no-dfcf", action="store_true")
    args = parser.parse_args()
    
    platforms = []
    if not args.no_ths: platforms.append('ths')
    if not args.no_tdx: platforms.append('tdx')
    if not args.no_dfcf: platforms.append('dfcf')
    
    keywords = [args.theme] + (args.keywords or [])
    
    pool = build_pool(args.theme, keywords, tuple(platforms))
    
    if args.summary:
        for pdata in pool['platforms'].values():
            for sec in pdata['sectors'].values():
                sec['stocks'] = [s['code'] for s in sec['stocks']]
        pool['merged_stocks'] = list(pool['merged_stocks'].keys())
    
    output = json.dumps(pool, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"✅ {args.output} ({pool['total_merged']} stocks)")
    elif args.json:
        print(output)
    else:
        # 文本报告
        print(f"\n{'='*60}")
        print(f"📊 三平台板块池 — 「{args.theme}」→ {pool['total_merged']} 只标的")
        print(f"{'='*60}")
        for pname, pdata in pool['platforms'].items():
            nm = {'ths':'同花顺','tdx':'通达信','dfcf':'东方财富'}.get(pname, pname)
            print(f"\n🏷️  {nm}: {len(pdata['sectors'])} 板块, {pdata['total']} 次引用")
            for code, sec in sorted(pdata['sectors'].items(), key=lambda x: -x[1]['count'])[:10]:
                print(f"  {code:18s} {sec['name']:22s} {sec['count']:4d}只")


if __name__ == "__main__":
    main()
