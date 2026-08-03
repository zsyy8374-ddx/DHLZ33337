#!/usr/bin/env python3
"""
tdx_wxd_bk.py — 通达信问小达 选板块 v1.2 (Playwright standalone)
查询问小达主题 → 按「所属通达信概念/指数」「所属行业」聚合 → 输出板块排名

用法:
 python3 skills/tdx-wxd-bk/scripts/tdx_wxd_bk.py "核电"
 python3 skills/tdx-wxd-bk/scripts/tdx_wxd_bk.py "核电" --json --stocks
"""
import json, sys, argparse, subprocess
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent.parent  # scripts -> tdx-wxd-bk -> skills -> workspace root
TDX_TOOL = WORKSPACE / "tools" / "tdx_zhangting.py"


def parse_tdx_field(val: str) -> list[str]:
    if not val:
        return []
    return [p.strip() for p in val.split("@") if p.strip()]


def run_tdx_query(query: str) -> list[dict]:
    result = subprocess.run(
        ["/usr/bin/python3", str(TDX_TOOL), "--query", query],
        capture_output=True, text=True, timeout=120,
        cwd=str(WORKSPACE),
    )
    if result.returncode != 0:
        print(f"[tdx_wxd_bk] Error: {result.stderr[:500]}", file=sys.stderr)
        return []
    
    stdout = result.stdout.strip()
    if not stdout:
        return []
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        start = stdout.find('[')
        end = stdout.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(stdout[start:end])
        return []


def detect_concept_field(stocks: list[dict]) -> str:
    for f in ["所属通达信概念", "所属通达信指数"]:
        if any(s.get(f, "") for s in stocks[:5]):
            return f
    return ""


def aggregate(stocks: list[dict], field: str) -> list[tuple]:
    if not field:
        return []
    counter: dict[str, int] = Counter()
    items: dict[str, list[str]] = {}
    
    for s in stocks:
        raw = s.get(field, "")
        for val in parse_tdx_field(raw):
            counter[val] += 1
            if val not in items:
                items[val] = []
            code = s.get("sec_code", s.get("code", ""))
            name = s.get("sec_name", s.get("name", ""))
            items[val].append(f"{code} {name}")
    
    return [(v, c, items[v]) for v, c in counter.most_common()]


def main():
    parser = argparse.ArgumentParser(description="通达信问小达 选板块")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--stocks", action="store_true")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    
    print(f"[tdx_wxd_bk] 搜索: {args.query}", file=sys.stderr)
    stocks = run_tdx_query(args.query)
    
    if not stocks:
        result = {"query": args.query, "total_stocks": 0, "concepts": [], "industries": []}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"问小达未返回 '{args.query}' 的结果")
        return
    
    total = len(stocks)
    concept_field = detect_concept_field(stocks)
    field_label = "通达信概念" if concept_field and "概念" in concept_field else ("通达信指数" if concept_field and "指数" in concept_field else "概念/指数")
    
    concepts = aggregate(stocks, concept_field) if concept_field else []
    industries = aggregate(stocks, "所属行业")
    
    if args.json:
        print(json.dumps({
            "query": args.query, "total_stocks": total,
            "concept_field": concept_field,
            "concepts": [{"name": n, "count": c, "stocks": s} for n, c, s in concepts[:args.top]],
            "industries": [{"name": n, "count": c, "stocks": s} for n, c, s in industries[:args.top]],
        }, ensure_ascii=False, indent=2))
        return
    
    print(f"\n{'='*60}")
    print(f"📊 问小达选板块 — '{args.query}'（{total}只股票）")
    print(f"{'='*60}")
    
    if concepts:
        print(f"\n🏷️  {field_label} TOP {args.top}:")
        for i, (cname, cnt, s_list) in enumerate(concepts[:args.top], 1):
            bar = "█" * min(cnt, 25)
            print(f"  {i:2d}. {cname:14s} {cnt:3d}只 {bar}")
            if args.stocks and s_list:
                for s in s_list[:5]:
                    print(f"       {s}")
                if len(s_list) > 5:
                    print(f"       ... 等{len(s_list)}只")
    
    if industries:
        print(f"\n🏭 行业板块 TOP {args.top}:")
        for i, (iname, cnt, s_list) in enumerate(industries[:args.top], 1):
            bar = "█" * min(cnt, 20)
            print(f"  {i:2d}. {iname:14s} {cnt:3d}只 {bar}")
            if args.stocks and s_list:
                for s in s_list[:3]:
                    print(f"       {s}")
                if len(s_list) > 3:
                    print(f"       ... 等{len(s_list)}只")
    
    n_concept = len(concepts) if concepts else 0
    n_ind = len(industries) if industries else 0
    print(f"\n📌 共{total}只股票，{n_concept}个{field_label}板块，{n_ind}个行业板块")


if __name__ == "__main__":
    main()
