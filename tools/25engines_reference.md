# 25引擎完整配置与调用手册
# 引擎1-12+19-25强制（19个：12+7=19），引擎13-18按主题灵活选用
# 用途：每次 spawn 子代理跑雷达时，复制 Step 0 到任务描述中
# 🔴 铁律1：任何时候用25引擎，必须严格按本文件方法调用——不凭记忆，不自己发明。
# 🔴 铁律2：引擎1-12缺一个 → 返回重做；引擎19-25缺一个 → 返回重做
# 🔴 铁律3：所有 env 命令必须通过 wrapper 调用（bash tools/xxx.sh），不用 source && python3

## ⚠️ 铁律
```
⚠️ 环境变量：所有需要 env 的命令必须通过 wrapper 调用（source && command 被 exec preflight 拦截）
  通用：bash tools/run.sh <command> <args>
  妙想搜索：bash tools/mx_search.sh "<query>" /tmp/out
  妙想数据：bash tools/mx_data.sh "<codes> <fields>" /tmp/out
  韭研公社：bash tools/jiuyan_radar.sh "<query>" --json
  慧博投研：bash tools/hibor_radar.sh "<行业>" --json
⚠️ 不用 source tools/env.sh && python3 script.py（会失败！）
🔴 国外引擎拆词铁律（2026-07-24 董哥明令）：中文整句翻译→英文搜索=垃圾结果。必须：中文拆词→逐词翻译→每个英文词组单独搜。N个子词=N次搜索，不可合并。
引擎1-12缺一个 → 返回重做 → 不发邮件
引擎19-25缺一个 → 返回重做 → 不发邮件
  ⚠️ 2026-07-24升级：引擎21(Reddit)降级为按需（A股产业主题不适合Reddit，用Google News both替代）
  ⚠️ 2026-07-24升级：引擎23(华尔街见闻)改用 Google News site:法（原生搜索需登录）
引擎13-18按主题灵活启用，子代理必须判断并汇报启用理由
引擎1-10+12+19-25情报扫描(并行) → 标的池构建 → 引擎11妙想深度验证 → 引擎13-18补充 → 防漏检查 → 定稿
每完成一个引擎汇报一行结果


⚠️ 报告生成铁律（非代码块内容，必须在任务描述中明确）：
⚠️ 引擎结果整合铁律（每个来源必须查到后整合进报告，不能只扫描不整合）：
引擎16 Bing英文 → 报告中必须单独一节「全球视角验证（Bing英文来源）」
引擎24 SemiAnalysis → 报告中必须出现独立章节
引擎23 华尔街见闻 → 报告中必须出现独立章节
引擎2 韭研公社 → 报告中必须单独一节（深度文章）
每个引擎的发现必须标注来源，不能混在其他章节里消失

```

## 环境变量（已统一在 tools/env.sh，无需手动 export）
所有 wrapper 脚本内部自动 source env.sh：
- tools/mx_search.sh → MX_APIKEY
- tools/mx_data.sh → MX_APIKEY
- tools/jiuyan_radar.sh → 零依赖（crawl4AI+免费代理，无需 API key）
- tools/hibor_radar.sh → 零依赖（crawl4AI+免费代理）
- tools/social_radar.sh → 零依赖（Reddit: crawl4AI+proxy, Twitter: twitter-cli feed）
- tools/run.sh → 全部（通用）
零依赖引擎（无需 env）：tools/google_news.py, tools/seeking_alpha.py, tools/semianalysis.py

---

## 引擎1: 今日头条
**方式**: `web_fetch`（服务端渲染，零依赖）
```bash
web_fetch "https://so.toutiao.com/search?dvpf=pc&keyword=<主题>+上游+卡脖子&pd=information"
```
**拿什么**: 新闻事件列表、涨停概念感知
**关键词**: 用`+`连接，例：`物理AI+上游+传感器`

## 引擎2: 韭研公社（🔥 v5.1 并行搜索+首页，2026-07-25）

✅ **一行命令**：`bash tools/jiuyan_radar.sh`

**v5.1 核心升级**：搜索（`/search/new?k=` curl+proxy）和首页（crawl4AI 渲染）**同时启动互不阻塞**。任何一个成功就有数据，代理挂了另一个顶上。总耗时 = max(搜索, 首页) ≤ 18s。

```bash
# 🔴 搜索关键词（v5.1 并行：搜索+首页，不限条数不截断）
bash tools/jiuyan_radar.sh "<搜索关键词>" --json

# 仅首页（无搜索）
bash tools/jiuyan_radar.sh --homepage

# 单篇全文
bash tools/jiuyan_radar.sh --article <文章ID或URL>
```

**拿什么**：搜索+首页合并去重，不限条数
**🔴 红线**：禁止 pipe 到 head/tail 等任何截断命令；代码内已移除所有内置截断（标题、内容、条数）
**子代理用法**：直接用 `bash tools/jiuyan_radar.sh "<主题词>" --json`（🔴 不限制条数、不截断内容、不截断标题、禁止 pipe 到 head/tail 等任何截断命令）

**历史**：7/5 WAF → 7/15 Firecrawl → 7/24 crawl4AI+proxy → 7/25 v5.1 并行搜索+首页防超时

## 引擎3: 微信公众号
**方式**: `web_fetch` 搜狗微信（服务端渲染）
```bash
web_fetch "https://weixin.sogou.com/weixin?type=2&query=<日期>+<主题>+国产替代&timeline=1"
```
**拿什么**: 散户复盘观点、直接标的名单
⚠️ 必须带日期才能命中当天文章，不带日期返回旧文

## 引擎4: 财联社
**方式**: Playwright 渲染（客户端渲染，web_fetch拿不到）
```bash
# 🔥 正确方法（2026-07-24验证）：写入独立.py文件再执行，不要用heredoc
# Step 1: 写入脚本
cat > /tmp/cls_scan.py << 'PYEOF'
from playwright.sync_api import sync_playwright
import time, sys, urllib.parse
keyword = urllib.parse.quote("<主题>")  # 中文必须URL编码
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-gpu','--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
    page = browser.new_page()
    page.set_extra_http_headers({'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36','Accept-Language':'zh-CN,zh;q=0.9'})
    page.goto(f"https://www.cls.cn/searchPage?keyword={keyword}&type=all", wait_until="load", timeout=20000)
    time.sleep(5)
    page.evaluate('window.scrollBy(0, 2000)')
    time.sleep(3)
    page.evaluate('window.scrollBy(0, 2000)')
    time.sleep(2)
    print(page.inner_text('body')[:10000])
    browser.close()
PYEOF
# Step 2: 执行
python3 /tmp/cls_scan.py 2>&1
```
**拿什么**: 电报快讯+资讯+VIP研报，结果分三个tab：综合(N条)、资讯(M篇)、VIP(K篇)
**超时**: timeout=20000（页面加载慢），wait 5s+滚动两次
⚠️ 中文关键词必须 `urllib.parse.quote()` URL编码，否则CLS搜索返回空
⚠️ 别用"热点板块"这种关键词（会被理解为房地产土拍）
⚠️ 子代理注意：不要用 inline heredoc + exec，先 write_file 再 exec

## 引擎5: 东方财富
**方式**: Playwright 渲染（客户端渲染）
```bash
# 🔥 正确方法（2026-07-24验证）：写入独立.py文件再执行
cat > /tmp/em_scan.py << 'PYEOF'
from playwright.sync_api import sync_playwright
import time, sys, urllib.parse
keyword = urllib.parse.quote("<主题>")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-gpu','--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
    page = browser.new_page()
    page.set_extra_http_headers({'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36','Accept-Language':'zh-CN,zh;q=0.9'})
    page.goto(f"https://so.eastmoney.com/news/s?keyword={keyword}&pageindex=1&searchrange=8192", wait_until="load", timeout=20000)
    time.sleep(6)
    print(page.inner_text('body')[:8000])
    browser.close()
PYEOF
python3 /tmp/em_scan.py 2>&1
```
**拿什么**: 当日概念板块涨跌幅TOP10+领涨股+板块异动时间线+热搜
**独有优势**: 页面底部自带当日概念板块涨跌幅TOP10和异动时间线
⚠️ 中文关键词必须URL编码，timeout=20000，wait 6s
⚠️ 子代理注意：不要用 inline heredoc + exec，先 write_file 再 exec
**拿什么**: 当日概念板块涨跌幅TOP10+领涨股+板块异动时间线

## 引擎6: 淘股吧
**方式**: 手机版 `m.tgb.cn`（服务端渲染，纯curl，零依赖）
```bash
python3 /Users/openclaw/.openclaw/workspace-dengxian/skills/taoguba/scripts/taoguba.py -s reply --max 20 -f json
```
**拿什么**: 游资复盘情绪面、实盘选手讨论
**原理**: `m.tgb.cn/mIndex?blockID=1&flag=0&pageNo=1` 服务端渲染，regex解析

## 引擎7: 雪球
**方式**: Playwright 全程（反爬400016，纯HTTP不可用）
```bash
python3 /Users/openclaw/.openclaw/workspace-dengxian/tools/xueqiu_tool.py --hot --hot-stocks
```
**拿什么**: 热门事件TOP10(含讨论数)+热门股票TOP8(含涨跌幅、美股映射)
**原理**: Playwright加载首页→拦截`hot_event/list.json`+`hot_stock/list.json` API

## 引擎8: Bing News
**方式**: `search.py`（Bing News RSS，零依赖）
```bash
python3 /Users/openclaw/.openclaw/workspace-dengxian/tools/search.py "<主题> 上游 国产替代 A股" 10
```
**拿什么**: 跨平台聚合文章，中英文都能覆盖
**备用**: 搜索词格式 `<主题> 上游 卡脖子 国产替代 A股`

## 引擎9: 同花顺问财
**方式**: thsdk（TCP直连，稳定可靠）

⚠️ **字段名陷阱**：`search_symbols` 返回英文字段（`Code`/`Name`/`THSCODE`），`block_constituents` 返回中文字段（`代码`/`名称`），不可混用！

```python
from thsdk import THS
ths = THS({'username': 'zsyyddx', 'password': 'jgyyddx33'})
ths.connect()

# Step 1: 搜索概念板块（英文字段名：Code/Name/THSCODE/MarketStr）
# ⚠️ 多种关键词都试：中文全称、英文缩写、别名
queries = ['<主题>', '<主题英文缩写>', '<主题别名>']
found_codes = []
for q in queries:
    r = ths.search_symbols(q)
    data = r.data if hasattr(r, 'data') and r.data else []
    print(f'搜索「{q}」: {len(data)} 个结果')
    for item in data:
        # ⚠️ 英文字段名，不是中文！
        code = item.get('Code', '?')
        name = item.get('Name', '?')
        thscode = item.get('THSCODE', '?')
        mkt = item.get('MarketStr', '?')
        print(f'  {mkt} {code} {name} → THSCODE={thscode}')
        if 'URFI' in str(mkt) or '同指' in str(item.get('MarketDisplay', '')):
            found_codes.append(thscode)

# Step 2: 用 THSCODE 拉成分股（⚠️ 中文字段名：代码/名称）
for thscode in found_codes:
    r2 = ths.block_constituents(thscode)
    if hasattr(r2, 'data') and r2.data:
        stocks = []
        for s in r2.data:
            raw_code = s.get('代码', '')  # 如 USHA600845
            name = s.get('名称', '')       # 如 宝信软件
            # 去前缀：USHA→沪市(6开头) USZA→深市(0/3开头)
            clean_code = raw_code[4:] if len(raw_code) >= 4 else raw_code
            stocks.append(f'{clean_code} {name}')
        print(f'{thscode} 成分股: {len(stocks)} 只')
        for s in stocks[:10]:
            print(f'  {s}')
        if len(stocks) > 10:
            print(f'  ... 还有 {len(stocks)-10} 只')
    else:
        print(f'{thscode} 成分股: 无数据')

# Step 3: 多个查询都没有板块 → 退回手工拆词构建标的池
if not found_codes:
    print('⚠️ 没找到概念板块，退回手工拆词')
```
**拿什么**: 概念成分股完整列表、标的覆盖率验证
**账号**: zsyyddx / jgyyddx33

## 引擎10: 通达信问小达
**方式**: Playwright + API拦截（翻6页，数据处理在browser.close前完成）
```bash
python3 /Users/openclaw/.openclaw/workspace-dengxian/tools/tdx_zhangting.py --query "<主题>" --compact --pages 2
```
**拿什么**: 主题股票池全覆盖(去重)+涨停原因揭秘
⚠️ `--pages 2` 用于雷达（主题查询结果少），涨停板块用 `--pages 6`
⚠️ EPIPE已修复：所有JSON解析在`browser.close()`之前

## 引擎11: 妙想 mx-data

⚠️ 查询格式：空格分隔代码 + 必须带字段名（不能只用逗号分隔代码，不能只写代码不写字段名）
正确：`688110 688595 300684 最新价 涨跌幅 总市值 市盈率`
错误：`688110,688595,300684`（缺字段名，API返回空 dataTableDTOList）

**方式**: `bash tools/mx_data.sh`（wrapper 自动加载 MX_APIKEY）
```bash
bash tools/mx_data.sh "<候选股票列表> 最新价 涨跌幅 总市值 市盈率 主力资金流向" /tmp/mx_radar
```
**拿什么**: 批量行情+资金流+财务三表，Step 3 硬数据
**调用时机**: 标的池确定后，评分前
**示例**: `"汉威科技 芯动联科 奥普光电 最新价 涨跌幅 总市值 市盈率 近三年净利润"`

---

## 引擎12: 妙想 mx-search（金融资讯搜索）🆕 强制
**方式**: `bash tools/mx_search.sh`（wrapper 自动加载 MX_APIKEY）
```bash
bash tools/mx_search.sh "<主题>+产业链+最新研报" /tmp/mx_search
```
**拿什么**: 机构研报+公司公告+互动问答+行业数据，智能筛选权威金融信源
**调用时机**: 雷达启动，第一步（与引擎1-8并行）
**覆盖内容**:
- 研报：中山/光大/长江/华西/国泰海通/方正等机构最新报告
- 公告：上市公司分红/定增/业绩预告等官方公告
- 互动问答：公司直接回复的客户进展、产能规划
- 行业数据：市场白皮书、产业全景图等
**搜索示例**:
```bash
# 产业链研报
python3 skills/mx-search/mx_search.py "人形机器人产业链最新研报"
# 个股公告
python3 skills/mx-search/mx_search.py "<股票简称>最新公告"
# 行业政策
python3 skills/mx-search/mx_search.py "<行业>产业政策最新解读"
# 指定输出目录
python3 skills/mx-search/mx_search.py "<query>" /tmp/mx_search
```
**与引擎8(Bing News)的区别**: 引擎8通用搜索不分信源权威性，引擎12金融场景专用，自动筛选权威机构来源
**输出**: 终端格式化输出 + 自动保存 `/tmp/mx_search/mx_search_{query}.txt`

---

## 引擎13: 集微网（半导体/电子产业链垂直媒体）⭐ 按需启用
**触发条件**: 主题涉及半导体/芯片/电子元器件/MLCC/传感器/MEMS
**方式**: `web_fetch`（服务端渲染）
```bash
# 🔥 主力URL（2026-07-24验证）: laoyaoba.com = 集微网同集团站，服务端渲染
web_fetch "https://laoyaoba.com/search?q=<主题>"
```
**拿什么**: 半导体产业链深度报道、产能数据、供应链验证
⚠️ `jiweinet.com` 反爬，返回空。直接用 `laoyaoba.com`（同集团，内容相同）

## 引擎14: 互动易（深交所/上交所投资者问答）⭐ 按需启用
**触发条件**: 标的池确定后，针对候选标的验证产业链地位
**方式**: mx_search（主力）+ web_fetch（备用）
```bash
# 🔥 主力方法（2026-07-24验证）: mx_search 内置搜互动问答
bash tools/mx_search.sh "互动易 <股票简称> 订单 客户 产能 研发" /tmp/mx_hudong
# 备用: web_fetch（深交所/上交所搜索页是JS渲染，常拿不到内容）
web_fetch "http://irm.cninfo.com.cn/ircs/search?keyword=<股票简称>"  # 深交所 00/30
web_fetch "https://sns.sseinfo.com/search.do?keyword=<股票简称>"      # 上交所 60/68
```
**拿什么**: 公司直接回复的客户进展、产能规划、认证状态 → 比研报可靠
**调用时机**: Step 2标的筛选后，对每只候选物逐只查询
⚠️ 互动易搜索页是CSR（JS渲染），web_fetch常只拿到标题，mx_search更可靠
⚠️ 每只个股必查4类问题：在手订单/产业链地位/技术进展/AI热点相关

## 引擎15: 龙虎榜/机构席位 ⭐ 按需启用
**触发条件**: 标的近期有涨停/异动，需要验证资金面
**方式**: wudao-intel API（curl, 零依赖）
```bash
# 🔥 今日龙虎榜（2026-07-24验证）
curl -s -H "Authorization: Bearer $LB_API_KEY" \
  "$LB_API_BASE/dragon-tiger?date=2026-07-24&pageSize=20"
# 按股票查
curl -s -H "Authorization: Bearer $LB_API_KEY" \
  "$LB_API_BASE/dragon-tiger?stockCode=600519&pageSize=10"
```
**拿什么**: 机构席位买入/卖出、游资动向、北向资金、净买入额
**API Base**: `https://stock.quicktiny.cn/api/openclaw`（LB_API_KEY 在 ~/.zshrc）
⚠️ 如果标的今日无涨停/异动，此引擎可跳过

---

## 引擎16: Bing News英文版（中英双搜）⭐ 按需启用
**触发条件**: 主题有全球产业链对标（半导体/电容/机器人/AI等几乎都触发）

### 🔴 拆词铁律（2026-07-24 董哥明令）

**禁止中文整句翻译成英文搜索。必须先拆中文关键词→逐词翻译→每个英文词组独立搜索。**

| 步骤 | 错误 | 正确 |
|:--:|------|------|
| 拆词 | "高温电力链多次涨停"→整句翻译 | 拆为「全球高温」「电网负荷」「特高压」「海缆」「液冷」 |
| 翻译 | 1个长query | 每个子词独立英文query |
| 搜索 | 1次 | N次（N=子词数） |

**实测（2026-07-24）**：整句翻译→1条China Daily。拆词后"record heat wave power grid"+"UHV tender"+"submarine cable"→5条(Reuters+Bloomberg+China Daily)。

**方式**: `search.py` 中英双搜
```bash
# 🔴 正确做法：拆词后每个子词独立搜
# 例：主题=高温电力链 → 拆为：
python3 tools/search.py "China record heat wave power grid electricity demand" 5
python3 tools/search.py "State Grid UHV ultra high voltage tender 2026" 5
python3 tools/search.py "submarine power cable offshore wind China" 5
python3 tools/search.py "liquid cooling data center AI server" 5

# ❌ 错误做法：整句翻译
python3 tools/search.py "China power grid heat wave electricity demand record" 10

# 备用：中文搜索（补海外中文媒体视角）
python3 tools/search.py "<中文主题> 全球 产业链 对标" 10
```
**拿什么**: 英美主流媒体+海外中文媒体双视角
**与引擎8的区别**: 引擎8侧重中文A股视角，引擎16侧重国际产业链对标
⚠️ search.py自动识别语言：英文query → Bing News RSS（国际源），中文query → Bing Web（国内源）

## 引擎17: Google News（中英双搜）⭐ 按需启用
**触发条件**: 需要更广泛的全球报道覆盖（Bing News之外的源）
**方式**: `python3 tools/google_news.py`（Python 标准库，零依赖，不依赖 Tavily）
```bash
# 中英双搜（推荐）
python3 tools/google_news.py "<English关键词>" both --max 10

# 仅英文
python3 tools/google_news.py "<English query>" en --max 10

# 仅中文
python3 tools/google_news.py "<中文关键词>" zh --max 10

# 备用：输出 RSS URL，然后用 web_fetch
python3 tools/google_news.py --url "<关键词>" both
```
**拿什么**: Google News聚合全球200+媒体，中英文双源，覆盖Bing News遗漏的源
⚠️ 不依赖 Tavily（纯 urllib RSS），Tavily 433 时仍可用
⚠️ 包含 NVIDIA Newsroom、CNBC、Reuters、Engadget、钛媒体、驱动之家、智东西、电子工程专辑等

## 引擎18: Seeking Alpha / Yahoo Finance ⭐ 按需启用

**触发条件**: 标的池中有美股映射（如MU/NVDA/TSLA对标）或需要海外投资者观点

⚠️ Seeking Alpha 全文登录墙（web_fetch 返回登录页），无法拿完整文章。
✅ **改进方案**：通过 Google News RSS 搜索 Seeking Alpha 索引（标题+摘要）

```bash
# 搜索 Seeking Alpha 投资分析文章（标题+摘要可用）
python3 tools/seeking_alpha.py "<English keywords about the topic>" --max 10 --json

# 或者直接输出版本
python3 tools/seeking_alpha.py "Nvidia RTX Spark AI PC" --max 5
```

**拿什么**: 投资者角度分析（做多/做空逻辑、赢家/输家清单、估值对比、竞争格局）

**标题示例**（AI PC 实测输出）：
- "Nvidia's PC push lifts PC maker, Arm; pressures Qualcomm, Intel, AMD"
- "Nvidia targets the PC market; Which stocks stand to gain?"
- "Nvidia RTX Spark: What I Learned From Apple's iMac"

⚠️ 只拿标题+摘要（Google News 索引），全文需 Seeking Alpha 付费账号
⚠️ Seeking Alpha 直接访问 403，必须走 Google News 间接搜索

---

## 📋 引擎启用规则

**⚠️ 外媒引擎铁律（2026-07-01 董哥明令，2026-07-05 更新中英双搜）**：
- 引擎8、16、17 必须**中英文双搜**（中文query + 英文query各搜一轮）
- 引擎18 (Seeking Alpha) 英文平台，仅英文搜索
- 报告输出**全部中文**（英文原文翻译成中文，原文可作引用标注）

| 雷达类型 | 强制引擎 | 按需引擎 |
|------|:--:|------|
| 紫苏雷达 | 1-12 | 13(电子/半导体) 14(标的池确定后) 15(有涨停) 16(英文Bing) 17(Google News) 18(美股映射) |
| 科技制胜雷达 | 1-12 | 13(电子/半导体) 14(标的池确定后) 15(有涨停) 16(英文Bing) 17(Google News) 18(美股映射) |
| 涨价雷达 | 1-12 | 13(电子/半导体) 14(标的池确定后) 15(有涨停) 16(英文Bing) 17(Google News) 18(美股映射) |

⚠️ 引擎16(英文Bing)适用面最广——只要主题有全球产业链对标就启用，子代理应默认启用

---

## 📋 子代理任务模板

> 🔴 **任何 spawn 子代理跑雷达/深度研究，任务描述顶部必须包含以下两行**

```
⚠️ 第一步（强制·不可跳过）：
  1. 读取 tools/25engines_reference.md — 所有引擎的 bash/Python wrapper 调用代码
  2. 读取 TOOLS.md — 国外引擎拆词铁律、板块查重铁律、防漏规则、wrapper 清单
  不看这两个文件 = 用错命令 = 漏数据 = 不合格报告
```

```
你是一个<雷达名称>分析助手。执行<雷达名称>：<主题>。

⚠️ 第一步（强制）：
  1. 读取 tools/25engines_reference.md，严格按照每个引擎的 bash/Python 调用代码执行
  2. 读取 TOOLS.md，遵守国外引擎拆词铁律（中文拆词→逐词翻译→独立搜索）、板块查重铁律、防漏规则
⚠️ 所有需要环境变量的命令必须通过 wrapper 调用（`bash tools/xxx.sh`），禁止 `source && python`
⚠️ 25引擎铁律：引擎1-10+12+19-25情报扫描(必须全部执行) → 标的池构建 → 引擎11妙想深度验证 → 引擎13-18补充 → 防漏检查 → 定稿 → 生成docx → 发邮件
缺一个引擎 → 返回重做 → 不发邮件。每完成一个引擎汇报一行。

### Step 0: 情报扫描（wrapper调用，不可跳步）

引擎1 今日头条: web_fetch "https://so.toutiao.com/search?dvpf=pc&keyword=<主题>+上游+卡脖子&pd=information"
引擎2 韭研公社: bash tools/jiuyan_radar.sh "<主题>" --json （v5.1 并行搜索+首页，7/25打通）
引擎3 微信公众号: web_fetch "https://weixin.sogou.com/weixin?type=2&query=<日期>+<主题>+国产替代&timeline=1"
引擎4 财联社: [Playwright — 见25engines_reference.md引擎4代码模板]
引擎5 东方财富: [Playwright — 见25engines_reference.md引擎5代码模板]
引擎6 淘股吧: python3 skills/taoguba/scripts/taoguba.py -s reply --max 20 -f json
引擎7 雪球: python3 tools/xueqiu_tool.py --hot --hot-stocks
引擎8 Bing中文: python3 tools/search.py "<主题> 上游 国产替代 A股" 10
引擎9 问财: [thsdk — 见25engines_reference.md引擎9代码模板]
引擎10 通达信: python3 tools/tdx_zhangting.py --query "<主题>" --compact
引擎12 妙想搜索: bash tools/mx_search.sh "<主题>+产业链+最新研报" /tmp/mx_search
引擎16 Bing英文: python3 tools/search.py "<English query> global market 2026" 10
引擎17 Google News: python3 tools/google_news.py "<English query>" both --max 10
引擎19 B站: [见25engines_reference.md]
引擎20 YouTube: [见25engines_reference.md]
引擎21 Reddit: 按需启用（仅美股消费科技话题）· 常规A股主题用 Google News both 替代
引擎22 Twitter: bash tools/twitter_radar.sh "<关键词>" --feed --max 15 --json （twitter-cli feed 主力）
引擎23 华尔街见闻: python3 tools/google_news.py "wallstreetcn <中文关键词>" both --max 5（Google News索引，2026-07-24修复）
引擎24 SemiAnalysis: python3 tools/semianalysis.py "<English query>" --max 10 --json （Substack API，零依赖）
引擎25 慧博投研: bash tools/hibor_radar.sh "<行业>" --max 10 --json （crawl4AI+proxy, 零依赖）

### 引擎13-18按需判断
- 引擎13集微网：主题涉及半导体/芯片/电子/MLCC → web_fetch "https://laoyaoba.com/search?q=<主题>"（🔥 laoyaoba=集微网同集团，jiweinet反爬）
- 引擎14互动易：标的池确定后逐只查 → bash tools/mx_search.sh "互动易 <标的> 订单 客户 产能 研发" /tmp/mx_hudong（🔥 CSR页面web_fetch失效，用mx_search替代）
- 引擎15龙虎榜：有涨停/异动标的 → curl -s -H "Authorization: Bearer $LB_API_KEY" "$LB_API_BASE/dragon-tiger?date=<日期>"（🔥 wudao-intel API，7/24验证）
- 引擎17 Google News / 引擎18 Seeking Alpha：已在上方

### Step 1: 产业链拆解
从下游反推上游，拆3-5层，标卡脖子程度(★越多越卡)

### Step 2: 标的筛选
每个卡脖子环节找A股对应公司，用问财成分股验证

### Step 3: 引擎11 妙想数据验证
bash tools/mx_data.sh "<全部候选 空格分隔> 最新价 涨跌幅 总市值 市盈率 主力资金流向" /tmp/mx_radar

### Step 4: 四视角评分 + 防漏检查
每个标的技术面/资金面/情绪面/题材面各1-10分，总分40分

### Step 5: 生成docx报告+发邮件
报告署名：Dengxian AI research
邮件附件Word文件名必须是中文
node qq-send.js --to 1628354330@qq.com --subject "<中文雷达名> · <中文主题> · 报告已出" --bodyFile /tmp/email.txt --attachments /tmp/中文报告文件名.docx
```
⚠️ 邮件附件Word文件名必须是中文，如「紫苏雷达·物理AI·报告.docx」

---

## 🆕 crawl4ai 补充爬虫（2026-07-24 升级：原生支持 proxy 绕过 IP 封禁）

**定位**：Firecrawl API 耗尽后的主力替代方案，开源免费无 API key。

**安装**：Python 3.13 venv `/tmp/crawl4ai_venv`
```bash
# 已安装 crawl4ai 0.9.2 + Playwright
/tmp/crawl4ai_venv/bin/python3
```

**已验证（2026-07-24 全量实测）**：
| 站点 | 结果 | 说明 |
|------|:--:|------|
| 韭研公社 jiuyangongshe.com | ✅🔥 | +免费代理，成功穿透雷池WAF |
| Reddit r/LocalLLaMA | ✅🔥 | 7701字符，帖子完整提取 |
| Reddit r/MachineLearning | ✅🔥 | 8604字符 |
| Reddit r/singularity | ✅🔥 | 7886字符 |
| Reddit r/nvidia | ❌ | JS challenge |
| 慧博投研 hibor.com.cn | ✅🔥 | 30篇研报完整提取，GBK编码适配 |
| 财联社 cls.cn | ❌ | API动态加载 |
| Twitter/X x.com | ⚠️ | HTML可用，markdown提取为空 |

**核心突破**：`proxy_config` 参数 + 免费代理池 = 绕过 IP 封禁
```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
config = CrawlerRunConfig(proxy_config="http://proxy:port", cache_mode=CacheMode.BYPASS)
```

**工具封装**：
- 引擎2 韭研公社：`bash tools/jiuyan_radar.sh` 内置 crawl4AI+proxy（零 API key）
- 引擎21 Reddit：`bash tools/social_radar.sh` 内置 crawl4AI+proxy → old.reddit.com → BS4 解析
- 引擎25 慧博：`bash tools/hibor_radar.sh` 内置 crawl4AI+proxy → BS4 解析（GBK 编码适配）

---

## 🆕 引擎19-22：reach 视频/社交引擎（2026-07-05 新增，强制）

**与引擎1-18并行执行，不可跳过。** 补18引擎的四大盲区：B站视频评测、YouTube全球视角、Reddit技术社区、Twitter/X社交舆论。

### 前置条件
```bash
# B站: pipx install bilibili-cli（已安装 ✅）
# Reddit: uv tool install 'git+https://github.com/public-clis/rdt-cli.git'（已安装 ✅）
# Twitter/X: pipx install twitter-cli（已安装 ✅）
# YouTube: brew install yt-dlp（已安装 ✅）
```

### 引擎19：B站 视频搜索（中文）
```bash
bili search "<中文主题词1>" --type video -n 5
bili search "<中文主题词2>" --type video -n 5
```
> ⚠️ 不要用 yt-dlp 读 B站（风控 412 拦截），只用 bili-cli

### 引擎20：YouTube 视频搜索（中英双搜）
```bash
# 中文搜索
yt-dlp --dump-json "ytsearch5:<中文主题词>" | python3 -c "
import sys,json
for line in sys.stdin:
    d=json.loads(line)
    print(f'  {d[\"title\"][:80]} | {d[\"view_count\"]:,} views | {d[\"webpage_url\"]}')
"
# 英文搜索（必须！不要跳过）
yt-dlp --dump-json "ytsearch5:<English keywords>" | python3 -c "
import sys,json
for line in sys.stdin:
    d=json.loads(line)
    print(f'  {d[\"title\"][:80]} | {d[\"view_count\"]:,} views | {d[\"webpage_url\"]}')
"
```
> 中英文各搜5条，合计10条。英文视频往往是海外第一手反应，中文视频不覆盖。

### 引擎21：Reddit 全球技术社区（2026-07-24 降级为按需）

⚠️ **实测结论（2026-07-24）**：Reddit 对 A 股产业主题（MLCC/齿科氧化锆/军工重组/电网设备）完全无覆盖。
- social_radar.sh（crawl4AI+proxy）→ 0 结果
- Google News site:reddit.com → 噪音
- Bing site:reddit.com → 0 结果
- Reddit JSON API → 403

**原因**：Reddit 社区以美国消费科技/游戏/投资为主，不讨论 B2B 工业供应链或 A 股题材。

**✅ 替代方案**：引擎 17 Google News `both` 模式已覆盖 Reddit 上存在的相关内容。Reddit 降级为**按需启用**——仅当主题有明确的美股映射且有消费级讨论时启用（如 AI 芯片/Nvidia/Apple 新品等）。

```bash
# 按需启用（仅美股消费级话题）
bash tools/social_radar.sh "Nvidia AI chip datacenter" --platform reddit --max 10 --json
# 日常雷达用 Google News both 模式替代
python3 tools/google_news.py "<关键词>" both --max 10
```

### 引擎22：Twitter/X 社交舆论（2026-07-24 twitter-cli 主力）

⚠️ Firecrawl 信用额 7/24 耗尽。twitter-cli feed/user-posts 成为主力。

| 方法 | 状态 | 说明 |
|:--:|:--:|------|
| twitter-cli feed | ✅ 主力 | 首页时间线 API |
| twitter-cli user-posts | ✅ 辅助 | 用户推文 API |
| Firecrawl Search | ❌ 暂不可用 | 信用额耗尽，充值后恢复 |

#### 📦 脚本

`tools/twitter_radar.sh`（包装 env.sh + python 脚本）
`tools/twitter_radar.py`（核心逻辑）

#### 🚀 各雷达调用模板（子代理直接复制）

```bash
# ===== 引擎22：Twitter（twitter-cli feed 主力）=====

# 主力：twitter-cli feed 实时推文
bash tools/twitter_radar.sh "<雷达主题关键词>" --feed --max 15 --json > /tmp/twitter_radar.json

# 🛰️ 科技制胜雷达
bash tools/twitter_radar.sh "AI chip semiconductor" --feed --max 15 --json > /tmp/twitter_radar.json

# 🍃 紫苏雷达
bash tools/twitter_radar.sh "<环节关键词> supply chain" --feed --max 10 --json >> /tmp/twitter_radar.json

# 📈 涨价雷达
bash tools/twitter_radar.sh "<商品名> commodity price" --feed --max 10 --json > /tmp/twitter_radar.json

# 📖 结果解读
python3 -c "
import json
with open('/tmp/twitter_radar.json') as f:
    tweets = json.load(f)
for t in tweets[:10]:
    print(f\"  @{t['author']}: {t['text'][:150]}\")
"
```

#### 📊 效果对比

| 主题类型 | Firecrawl Search | twitter-cli feed | 推荐 |
|------|:--:|:--:|------|
| AI/芯片/科技（英文） | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 主力 Firecrawl |
| 医药/创新药（中文） | ⭐⭐（有 spam 噪声） | ⭐ | Firecrawl + 人工过滤 |
| A股概念/热点（中文） | ⭐⭐ | ⭐ | 优先国内平台（雪球/韭研公社） |
| 全球宏观/美股（英文） | ⭐⭐⭐⭐ | ⭐⭐⭐ | Firecrawl 主力 + feed 补充 |

#### 🔑 Token 刷新

董哥从浏览器取 cookie，更新两个文件：
```bash
# 1. ~/.zshrc
export TWITTER_AUTH_TOKEN="<新token>"
export TWITTER_CT0="<新ct0>"

# 2. tools/env.sh（子代理用）
export TWITTER_AUTH_TOKEN="<新token>"
export TWITTER_CT0="<新ct0>"
```

#### ⚠️ 常见问题

- **Firecrawl 搜不到最新几小时的内容** → 加 `--feed` 用 twitter-cli 实时补充
- **中文 spam 噪声大** → 脚本内置关键词过滤，或只用于英文主题
- **twid=1595705990887841793（Strongstocks998/大海捞针）** → 这是董哥的号，关注圈偏英文
- **FIRECRAWL_API_KEY 过期** → `fc-a48d2a5ebcfb427fb438f992d62bf43e`，在 tools/env.sh 中

### 引擎23：华尔街见闻 — 全球宏观+中国产业交叉视角（2026-07-06 新增，2026-07-24 修复）

⚠️ 原生搜索需登录（Playwright渲染也返回「无数据」）。✅ 修复方案：Google News 索引（标题+摘要级）

```bash
# 🔥 正确方法（2026-07-24验证）：Google News 搜 wallstreetcn 关键词
python3 tools/google_news.py "wallstreetcn <中文关键词1>" both --max 5
python3 tools/google_news.py "wallstreetcn <中文关键词2>" both --max 5

# 示例：
python3 tools/google_news.py "wallstreetcn MLCC 电容 涨价" both --max 5
python3 tools/google_news.py "wallstreetcn 高温 电网 用电" both --max 5
python3 tools/google_news.py "wallstreetcn 军工 重组 央企 改革" both --max 5
```

| 要点 | 说明 |
|------|------|
| 搜索 | ❌ 原生搜索需登录（Playwright渲染返回空）。✅ Google News索引 `wallstreetcn <关键词>` |
| 内容 | 标题+摘要级（Google News索引），全文需登录 |
| 定位 | 标题级情报引擎，与Seeking Alpha类似，提供宏观+产业交叉视角 |
| 独有优势 | 全球宏观+中国产业交叉视角，现有25引擎中无替代 |
| 典型内容 | AI数据中心压垮美国电网、三星1.5万亿韩元MLCC大单、电力投资新逻辑、国资委力挺军工资产注入 |

### 引擎24：SemiAnalysis — 芯片/算力产业链全球最深英文源（强制）

⚠️ 不要用 Tavily web_search site:（433）。不要用 Firecrawl search（不索引 Substack）。
✅ **新方案（2026-07-22）：Substack API —— 纯 JSON，零依赖，30篇全拿**

```bash
# 获取最近30篇文章，本地关键词过滤
python3 tools/semianalysis.py "<English keywords>" --max 10 --json

# 看最近文章
python3 tools/semianalysis.py --latest --max 5

# 常用主题关键词
# Nvidia GPU chip ARM PC
# HBM memory semiconductor
# AI datacenter liquid cooling
# China SMIC CXMT chip
```

**原理**：`newsletter.semianalysis.com/api/v1/archive?sort=new&limit=30` 返回 JSON 数组

| 要点 | 说明 |
|------|------|
| 数据来源 | Substack API（纯 JSON，无 JS 反爬） |
| 覆盖 | 最近 30 篇（1-2个月），标题+摘要+日期+免费/付费标签 |
| 依赖 | Python 标准库（urllib + json），零外部依赖 |
| 内容深度 | 芯片/算力/数据中心产业链全球最深英文源 |
| 🔓/🔒 | 标注免费/付费，付费文章只看标题摘要 |

**示例输出**（2026-07-22 实测）：
- "Nvidia GPU Debt Backstop Unleashes the AI Project Trinity" — 2026-07-06 🔒
- "Meta's Infrastructure Team Needs A Culture Reset" — 2026-07-22 🔒
- "Anthropic 3Q26 Profit Over $1B" — 2026-07-08 🔒
- "China's CXMT Is Set to Challenge DRAM Incumbents" — 2026-06 🔒
- "Is SMIC N+3's Metal Pitch Smaller than Intel 18A's?" — 2026-06-14 🔒

⚠️ 大部分文章为付费墙（🔒），标题+摘要+日期仍有价值

### 防漏规则
- 引擎19-25 与引擎1-12 并行执行，不是替代关系
- 英文来源（YouTube英文/Reddit/Twitter英文/SemiAnalysis）信息在报告正文中翻译为中文

### 引擎25：慧博投研资讯 — 券商研报聚合平台（crawl4AI+proxy，零 Firecrawl 依赖）

**唯一方法：crawl4AI + proxy → hibor.com.cn → BeautifulSoup 解析（免费，零 API key）**

```bash
bash tools/hibor_radar.sh "<行业名>" --max 10 --json
# 行业名：电子/计算机/医药生物/信息服务/化工/机械设备/通信/新能源/有色金属等
```

| 要点 | 说明 |
|------|------|
| 原理 | crawl4AI 浏览器引擎 + 免费代理池渲染慧博行业页，BeautifulSoup 解析研报列表 |
| 覆盖 | 28个大行业，每页30篇研报 |
| 编码 | ⚠️ 慧博 URL 用 GBK 编码（`%B5%E7%D7%D3`），不是 UTF-8（`%E7%94%B5%E5%AD%90`），已硬编码全部行业参数 |
| 限制 | 全文展开需登录（loginLayer拦截），PDF原文需登录；摘要级即可满足情报需求 |
| 定位 | 🔴 强制，摘要级情报引擎。2000万+投研文档，补mx-search覆盖面不足 |
| 依赖 | 零外部依赖（crawl4AI + 免费代理，无需 API key） |
