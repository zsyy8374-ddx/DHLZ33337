#!/usr/bin/env python3
"""
引擎2: 韭研公社 — crawl4AI + proxy + requests搜索（2026-07-25 v5）
================================================================
IP 被雷池 WAF 封 → Firecrawl 信用额耗尽 → crawl4AI+proxy(首页) + requests+proxy(搜索)

用法：
  bash tools/jiuyan_radar.sh "超节点 算力" --max 10        # 搜索 /search/new?k= (v5 新增)
  bash tools/jiuyan_radar.sh --homepage --max 10            # 仅首页（无搜索）
  bash tools/jiuyan_radar.sh --article 4el8rqveaxp          # 取单篇全文
  bash tools/jiuyan_radar.sh --article https://www.jiuyangongshe.com/a/4el8rqveaxp
"""

import sys, json, re, os, subprocess, argparse, asyncio, urllib.request, urllib.parse, time, tempfile

CRAWL4AI_PY = "/tmp/crawl4ai_venv/bin/python3"
PROXY_LIST_URL = "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http&timeout=3000&country=all&anonymity=elite&limit=15"

PROXY_CACHE_FILE = "/tmp/jiuyan_proxy.txt"
PROXY_CACHE_TTL = 300


def _get_cached_proxy():
    if os.path.exists(PROXY_CACHE_FILE):
        age = time.time() - os.path.getmtime(PROXY_CACHE_FILE)
        if age < PROXY_CACHE_TTL:
            with open(PROXY_CACHE_FILE) as f:
                p = f.read().strip()
            if p:
                return p
    return None


def _set_cached_proxy(proxy):
    with open(PROXY_CACHE_FILE, "w") as f:
        f.write(proxy)


def _find_proxy_for_requests(retries=2):
    """找一个能用的代理（用于 curl 请求），支持重试 + 重新拉取代理列表"""
    cached = _get_cached_proxy()
    if cached:
        r = subprocess.run(["curl", "-s", "--proxy", cached, "--max-time", "10", "-o", "/dev/null", "-w", "%{http_code}", "https://www.jiuyangongshe.com"], capture_output=True, text=True, timeout=12)
        if r.stdout.strip() == "200":
            return cached
        sys.stderr.write(f"  ⚠️ 缓存代理失效，重新获取...\n")
    
    for attempt in range(retries):
        if attempt > 0:
            sys.stderr.write(f"  🔄 重试 {attempt+1}/{retries}（重新拉取代理列表）...\n")
            import time
            time.sleep(2)
        
        proxies = fetch_proxies()
        if not proxies:
            sys.stderr.write(f"  ⚠️ proxyscrape 无返回（尝试 {attempt+1}/{retries}）\n")
            continue
        
        sys.stderr.write(f"  📡 {len(proxies)} 代理待测...\n")
        tested = 0
        for p in proxies:
            r = subprocess.run(["curl", "-s", "--proxy", p, "--max-time", "10", "-o", "/dev/null", "-w", "%{http_code}", "https://www.jiuyangongshe.com"], capture_output=True, text=True, timeout=12)
            tested += 1
            code = r.stdout.strip()
            if code == "200":
                _set_cached_proxy(p)
                sys.stderr.write(f"  🟢 {p} ({tested}/{len(proxies)} 通过)\n")
                return p
        
        sys.stderr.write(f"  ❌ {len(proxies)} 代理全灭（尝试 {attempt+1}/{retries}）\n")
    
    sys.stderr.write(f"  ❌ {retries} 次重试全失败\n")
    return None


def fetch_proxies():
    try:
        req = urllib.request.Request(PROXY_LIST_URL, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
        return [f"http://{p.strip()}" for p in body.strip().split("\n") if p.strip()]
    except Exception as e:
        sys.stderr.write(f"  ⚠️ proxy fetch: {e}\n")
        return []


async def _test_proxy(proxy, url):
    """异步测试代理（在 subprocess 中运行）"""
    script = f'''
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
async def main():
    config = CrawlerRunConfig(proxy_config="{proxy}", cache_mode=CacheMode.BYPASS)
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url="{url}", config=config)
            if result.success and result.markdown and len(result.markdown) > 500:
                print("OK")
            else:
                print("FAIL")
    except Exception:
        print("FAIL")
asyncio.run(main())
'''
    r = subprocess.run([CRAWL4AI_PY, "-c", script], capture_output=True, text=True, timeout=30)
    return "OK" in r.stdout


async def find_working_proxy(url="https://www.jiuyangongshe.com"):
    cached = _get_cached_proxy()
    if cached and await _test_proxy(cached, url):
        sys.stderr.write(f"  🟢 复用缓存代理: {cached}\n")
        return cached

    proxies = fetch_proxies()
    if not proxies:
        sys.stderr.write("  ❌ 无法获取代理列表\n")
        return None

    sys.stderr.write(f"  🔍 测试 {len(proxies)} 个代理...\n")
    for p in proxies:
        if await _test_proxy(p, url):
            sys.stderr.write(f"  🟢 可用: {p}\n")
            _set_cached_proxy(p)
            return p
    sys.stderr.write("  ❌ 所有代理均不可用\n")
    return None


def scrape_url(url, proxy, timeout=45):
    """用 crawl4AI + proxy 爬单个页面，返回 markdown"""
    outfile = tempfile.mktemp(suffix=".json", prefix="jiuyan_")
    script = f'''
import asyncio, json
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
async def main():
    config = CrawlerRunConfig(proxy_config="{proxy}", cache_mode=CacheMode.BYPASS)
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url="{url}", config=config)
            data = {{"ok": result.success, "text": result.markdown or ""}}
            if not result.success:
                data["error"] = str(result.error_message or "")[:500]
            with open("{outfile}", "w") as f:
                json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        with open("{outfile}", "w") as f:
            json.dump({{"ok": False, "error": str(e)[:500]}}, f, ensure_ascii=False)
asyncio.run(main())
'''
    r = subprocess.run([CRAWL4AI_PY, "-c", script], capture_output=True, text=True, timeout=timeout)
    try:
        with open(outfile) as f:
            data = json.load(f)
        os.unlink(outfile)
        return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.stderr.write(f"  ⚠️ 解析结果失败: {e}\n")
        if os.path.exists(outfile):
            os.unlink(outfile)
        return {"ok": False, "error": f"parse error: {e}"}


def _search_articles(query, proxy):
    """v5: 用 curl + proxy 调用 /search/new?k= 端点搜索文章"""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://www.jiuyangongshe.com/search/new?k={encoded}"
        
        # Use curl subprocess (reliable, handles proxy + SSL consistently)
        cmd = [
            "curl", "-s", "--proxy", proxy,
            "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "-H", "Accept-Language: zh-CN,zh;q=0.9",
            "-H", "Accept: text/html,application/xhtml+xml",
            "--max-time", "20",
            url
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        html = r.stdout
        
        # Extract article links from SSR HTML
        # Format: <a href="/a/ID"><span>text</span></a>
        article_ids = set()
        articles = []
        
        # Find all /a/ID links
        for m in re.finditer(r'/a/([\w-]+)', html):
            aid = m.group(1)
            if aid in article_ids:
                continue
            article_ids.add(aid)
            
            # Extract surrounding context to find the title span
            start = max(0, m.start() - 50)
            end = min(len(html), m.end() + 300)
            ctx = html[start:end]
            
            # Extract span text
            spans = re.findall(r'<span[^>]*>(.*?)</span>', ctx)
            title = ' '.join(s.strip() for s in spans if s.strip())
            if not title or len(title) < 5:
                # Try alt text
                alt_match = re.search(r'<a[^>]*>([^<]{5,200})</a>', ctx)
                if alt_match:
                    title = alt_match.group(1).strip()
            
            if not title or len(title) < 5:
                continue
            
            skip_words = ['更多', '首页', '登录', '退出', '下载', '我的',
                         '关注', '社群', '交易计划', '产业库', 'AI助手']
            if any(w in title for w in skip_words):
                continue
            
            articles.append({
                "title": title,
                "url": f"https://www.jiuyangongshe.com/a/{aid}",
                "author": "",
                "date": "",
                "source": "jiuyangongshe",
            })
        
        return articles[:50]
    except Exception as e:
        sys.stderr.write(f"  ⚠️ 搜索失败: {e}\n")
        return None


def parse_article_list(markdown):
    """从首页 markdown 解析文章列表"""
    articles = []
    seen_urls = set()
    lines = [l.strip() for l in markdown.split("\n")]
    
    for i, line in enumerate(lines):
        m = re.search(r'\[([^\]]*)\]\((https://www\.jiuyangongshe\.com/a/([\w-]+))\)', line)
        if not m or m.group(2) in seen_urls:
            continue
        seen_urls.add(m.group(2))
        
        article_url = m.group(2)
        title = ""
        author = ""
        date = ""
        
        for j in range(i - 1, max(i - 10, 0), -1):
            prev = lines[j]
            if not prev or prev.startswith("![") or prev.startswith("S ") or prev.startswith("<!--"):
                continue
            if re.match(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', prev):
                if not date:
                    date = prev
                continue
            if prev.startswith("* [!") or prev.startswith("> [!["):
                continue
            if "medal" in prev or "勋章" in prev:
                continue
            if len(prev) < 30 and not prev.startswith("http"):
                if not author:
                    author = prev
                continue
            if not title and len(prev) > 5:
                title = prev
                break
        
        if not title:
            body_snip = m.group(1)
            if len(body_snip) > 10:
                title = body_snip[:80]
            else:
                continue
        
        skip_titles = {"最新发布", "最新热度", "最新互动", "30天热度",
                       "全部", "个股研究", "题材行业", "纪要转载", "资讯荟萃",
                       "登录注册", "我的主页", "退出", "新帖播报"}
        if title in skip_titles or len(title) < 3:
            continue
        
        articles.append({
            "title": title,
            "author": author,
            "date": date,
            "url": article_url,
            "source": "jiuyangongshe",
        })
    
    return articles


def extract_article(markdown, article_url=""):
    """从文章页 markdown 提取标题、作者、日期、正文"""
    lines = markdown.split("\n")
    title = ""
    author = ""
    date = ""
    body_start = 0
    
    for i, line in enumerate(lines):
        ls = line.strip()
        if not title:
            h_match = re.match(r'^#\s+(.+)$', ls)
            if h_match:
                title = h_match.group(1)
                continue
        if not title and i < 10 and len(ls) > 10 and not ls.startswith("[") and "http" not in ls:
            title = ls
        if not author and "作者" in ls:
            m = re.search(r'作者[：:]\s*(.+?)(?:\s|$)', ls)
            if m:
                author = m.group(1).strip()
        if not date:
            m = re.search(r'(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})', ls)
            if m:
                date = m.group(1).strip()
        if body_start == 0 and len(ls) > 50 and "韭研公社" not in ls:
            body_start = i
    
    body = "\n".join(lines[body_start:]) if body_start > 0 else markdown
    
    return {
        "url": article_url,
        "title": title,
        "author": author,
        "date": date,
        "body": body.strip(),
    }


def main():
    parser = argparse.ArgumentParser(description="韭研公社文章提取 (v5: requests搜索 + crawl4AI全文)")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--article", default="", help="取单篇全文")
    parser.add_argument("--homepage", action="store_true", help="仅首页，不搜索")
    parser.add_argument("--proxy", default="", help="手动指定代理")
    args = parser.parse_args()

    # --article 模式
    if args.article:
        article_id = args.article
        m = re.search(r'/a/([\w-]+)', article_id)
        if m:
            article_id = m.group(1)
        url = f"https://www.jiuyangongshe.com/a/{article_id}"
        sys.stderr.write(f"📄 韭研公社 全文: {article_id}...\n")
        
        proxy = args.proxy or asyncio.run(find_working_proxy(url))
        if not proxy:
            print(json.dumps({"error": "no proxy available"}, ensure_ascii=False))
            sys.exit(1)

        data = scrape_url(url, proxy)
        if not data.get("ok"):
            print(json.dumps({"error": data.get("error", "scrape failed")}, ensure_ascii=False))
            sys.exit(1)

        content = extract_article(data["text"], url)
        if args.json:
            print(json.dumps(content, ensure_ascii=False, indent=2))
        else:
            print(f"\n**{content.get('title', '')}**\n")
            if content.get("author"):
                print(f"作者: {content['author']}")
            if content.get("date"):
                print(f"日期: {content['date']}")
            print(f"\n{content.get('body', '')}")
        sys.exit(0)

    articles = []

    # === 并行模式（v5.1）：首页 + 搜索同时启动，互不阻塞 ===
    # 首页用 crawl4AI 渲染（成功率高，~5s）
    # 搜索用 curl+proxy 调 /search/new?k=（有 proxy 时 ~5-15s）
    # 两者并行，先到的先用，后到的合并去重。总耗时 = max(首页, 搜索) ≤ 20s

    if args.query and not args.homepage:
        sys.stderr.write(f"🔍 韭研公社: 并行搜索+首页...\n")

        def _fetch_homepage():
            """抓取首页文章列表（独立线程）"""
            proxy = args.proxy or asyncio.run(find_working_proxy())
            if not proxy:
                return []
            data = scrape_url("https://www.jiuyangongshe.com", proxy)
            if data.get("ok"):
                return parse_article_list(data["text"])
            return []

        def _fetch_search():
            """搜索文章（独立线程）"""
            proxy = args.proxy or _get_cached_proxy() or _find_proxy_for_requests()
            if not proxy:
                proxy = asyncio.run(find_working_proxy())
            if not proxy:
                return []
            return _search_articles(args.query, proxy)

        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
        hp_articles = []
        sr_articles = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_home = executor.submit(_fetch_homepage)
            f_search = executor.submit(_fetch_search)
            try:
                for future in as_completed([f_home, f_search], timeout=18):
                    try:
                        result = future.result(timeout=5)
                    except Exception as e:
                        sys.stderr.write(f"  ⚠️ {e}\n")
                        continue
                    if future == f_home:
                        hp_articles = result
                        sys.stderr.write(f"  📋 首页: {len(result)} 篇\n")
                    else:
                        sr_articles = result
                        sys.stderr.write(f"  🔎 搜索: {len(result)} 篇\n")
            except TimeoutError:
                unfinished = sum(1 for f in [f_home, f_search] if not f.done())
                sys.stderr.write(f"  ⚠️ {unfinished} 个超时，用已完成的\n")
            # cancel 未完成的，避免 shutdown 卡死
            for f in [f_home, f_search]:
                if not f.done():
                    f.cancel()

        # 合并：搜索优先（更精准） + 首页补充（更全）
        articles = sr_articles[:]
        seen = {a["url"] for a in articles}
        for a in hp_articles:
            if a["url"] not in seen:
                articles.append(a)
                seen.add(a["url"])

        if not articles:
            sys.stderr.write("  ⚠️ 搜索+首页均无结果\n")
        else:
            sys.stderr.write(f"  ✅ 合并后: {len(articles)} 篇\n")

    elif args.homepage or not args.query:
        sys.stderr.write("🔍 韭研公社 首页 (crawl4AI+proxy)...\n")
        proxy = args.proxy or asyncio.run(find_working_proxy())
        if not proxy:
            print("[]" if args.json else "  ❌ 无可用代理")
            sys.exit(1)
        data = scrape_url("https://www.jiuyangongshe.com", proxy)
        if data.get("ok"):
            articles = parse_article_list(data["text"])
            sys.stderr.write(f"  ✅ {len(articles)} 篇\n")
        else:
            sys.stderr.write(f"  ⚠️ 首页抓取失败: {data.get('error', 'unknown')}\n")

    if args.json:
        print(json.dumps(articles[:args.max], ensure_ascii=False, indent=2))
    else:
        for i, a in enumerate(articles[:args.max], 1):
            author = f" | 👤 {a['author']}" if a.get('author') else ""
            title = a['title']
            print(f"  {i}. {title}{author}")
            if a.get('url'):
                print(f"     {a['url']}")
        if not articles:
            print("  (无匹配文章)")


if __name__ == "__main__":
    main()
