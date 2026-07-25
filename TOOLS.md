# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

### 东方财富 WAP 文章抓取 (2026-06-18)
- **问题**: wap.eastmoney.com 文章内容由 JS (`newsbefore.js`) 动态加载，curl/web_fetch 只能拿到空壳
- **解法**: Chrome headless 渲染
 ```bash
 /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
 --headless --disable-gpu --dump-dom --no-sandbox \
 'https://wap.eastmoney.com/a/文章ID.html' > /tmp/em_rendered.html
 ```
- 渲染后的 HTML 里 `NewsContentBody` 就有完整文章内容

### 🔍 自建多源搜索 search.py (2026-06-27, 命名 2026-06-30)
- **背景**: Tavily 经常 433、DDG 被反爬（验证码）、Bing web_fetch 返回垃圾、Chrome segfault
- **解法**: 自建多源搜索 `tools/search.py`，主力源 Bing News RSS（已验证可靠）
 ```bash
 python3 tools/search.py "搜索关键词" [max_results=10]
 ```
- 输出 JSON：{query, total, results: [{title, snippet, url, source}]}
- 自动识别中英文：英文优先 Bing News RSS，中文切 Bing Web + 财经站点 site: 搜索
- 回退链：Bing News RSS → Bing Web → Wikipedia
- **使用场景**: 行业调研、个股情报、紫苏/涨价雷达前期的资料收集

### 📊 TDX 涨停板抓取工具 tdx_zhangting.py（2026-06-30）
- **位置**：`tools/tdx_zhangting.py`
- **原理**：Playwright 加载通达信问小达页面 → 拦截 TQL API → 翻页全部抓取 → JSON/CSV/分类输出
- **全部 170 只涨停股一次抓完**（6页翻页，自动去重）
- **用法**：
 ```bash
 python3 tools/tdx_zhangting.py # 默认"涨停板块"，JSON输出
 python3 tools/tdx_zhangting.py --query "芯片" # 自定义查询
 python3 tools/tdx_zhangting.py --csv # CSV输出
 python3 tools/tdx_zhangting.py --compact # 精简字段JSON
 python3 tools/tdx_zhangting.py --categorize # 按原因揭秘分类输出
 ```
- **API端点**：`POST wenda.tdx.com.cn/TQL?Entry=NLPSE.NLPQuery&RI=<session>`
- **分页参数**：POST body `POS` offset（0/30/60/90/120/150），每页30条
- **注意**：需要浏览器session（RI token），直接curl不行

### 搜索历史记录
- 2026-06-27: DDG 验证码反爬 → 不可用；Chrome headless macOS ARM segfault → 不可用；Bing News RSS 中英文均通 → 当前主力

### 🛰️🍃📈 三大雷达 · 25 引擎扫描系统（引擎1-12+19-25强制，13-18灵活）

🔴 **铁律零（2026-07-24 董哥明令）：任何时候使用25引擎，严格按 `tools/25engines_reference.md` 方法执行。不凭记忆，不自创方法，每个引擎必须用文档规定的 wrapper 调用。**
🔴 **铁律零补充（2026-07-24 董哥明令）：任何 spawn 子代理跑雷达/深度研究，任务描述必须要求子代理读取 `TOOLS.md` + `tools/25engines_reference.md`。不读这两个文件 = 用错命令 = 漏数据 = 不合格。**

运行**任何**雷达（紫苏/科技制胜/涨价），**引擎1-12+19-25一个不能少**，引擎13-18按主题判断启用，不能只靠既有知识和单一数据源。

#### 🔑 Step 0 关键词矩阵（2026-07-15 加入·优先于引擎启动，2026-07-22 升级加入板块查重）

**核心原则：搜索词精度 > 引擎数量。先拆词，再启动引擎。先覆盖所有子类/环节，再做深度分析。**

| 雷达 | 拆词方式 | 示例 |
|:--:|------|------|
| 🍃 紫苏 | 产业链环节级拆词 | "半导体硅片"→拆为「硅料/拉晶/切片/抛光/清洗/检测/耗材/封装材料」每环节单独搜 |
| 🛰️ 科技制胜 | 技术细分方向拆词（带预设子类清单） | "创新药"→拆为「肿瘤/自免/罕见病/麻醉/血液/眼科/中枢神经/代谢/抗感染/疫苗/ADC/双抗/CAR-T/基因编辑/AI制药」每方向单独搜 |
| 📈 涨价 | 关联品种拆词 | "碳酸锂"→上游「锂辉石/盐湖提锂」+下游「正极材料/电池回收」+替代「钠电池/固态电池」 |

**拆词前，必须先查三大平台有没有对应板块**（2026-07-22 董哥明令加入）：

#### 🔍 Step 0.0 板块查重（拆词前强制执行）

**不要凭空拆词！先查平台板块，存在板块 = 直接拉成分股 = 标的池更完整。**

| 平台 | 查法 | 拿什么 |
|:--:|------|------|
| 同花顺 | `ths.search_symbols("主题词")` → 找概念板块代码 → `ths.block_constituents(CODE)` | 概念成分股完整列表 |
| 东方财富 | Playwright 访问 `https://so.eastmoney.com/news/s?keyword=主题词+概念板块` → 找板块代码 → Playwright 拉成分股 | 东方财富概念板块 + 成分股 |
| 通达信 | `python3 tools/tdx_zhangting.py --query "主题词" --compact` | 问小达主题池 + 涨停原因 |

**查法详解**：

**① 同花顺（thsdk，最可靠）**：
```python
from thsdk import THS
ths = THS({'username': 'zsyyddx', 'password': 'jgyyddx33'})
ths.connect()

# 用多种关键词搜板块（中文、英文缩写、别名都试）
r = ths.search_symbols('AI PC')
r = ths.search_symbols('AIPC')
r = ths.search_symbols('人工智能PC')

# 找到板块代码后拉成分股
r = ths.block_constituents('板块代码')
# 返回: [{代码: 'USHA600xxx', 名称: '股票名'}, ...]
# USHA=沪市 USZA=深市，去前缀得A股代码
```

**② 东方财富（Playwright 渲染）**：
```python
# 东方财富有独立的板块体系，与同花顺不完全重叠
# 搜索页能发现板块信息
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(f"https://so.eastmoney.com/news/s?keyword=AIPC+概念板块", ...)
    # 页面底部"相关概念板块"区域有成分股链接
    # 点进去拉成分股列表
```

**③ 通达信（问小达）**：
```bash
python3 tools/tdx_zhangting.py --query "AI PC" --compact
# 主题搜索，涵盖涨停股+相关股票
```

**合并规则**：
- 三个平台各拉 → 三者并集 = 初始标的池
- 板块查重得到的标的池 → 作为引擎9-10的输入验证基准
- 如果三个平台都没有对应板块 → 才退回手工拆词构建标的池

**拆词完成后**，生成关键词矩阵（主题 × 细分词组合），然后才进入引擎扫描。

#### 🔑 Step 0.5 时效补扫（2026-07-15 加入）

雷达启动后、引擎扫描前，**强制搜最近一周公告**（确保不漏最新催化剂）：
```bash
# 用 announcement-search 或 mx-search 搜7天内公告
python3 skills/mx-search/mx_search.py "<主题> 公告 2026年7月" /tmp/mx_announce
# 或用 search.py 搜 news
python3 tools/search.py "<主题> 最新 2026年7月" 10
```

#### 🔑 Step 0.6 多源交叉验证（2026-07-15 加入）

每个拆出关键词至少从 **3个不同源** 验证（Tavily + mx-search + search.py），避免单源偏差：
```bash
web_search "<拆词关键词> A股 2026" 5          # Tavily
python3 skills/mx-search/mx_search.py "<拆词关键词> 产业链" /tmp/mx_kw  # 妙想
python3 tools/search.py "<拆词关键词> A股 国产替代" 5  # Bing News
```

#### 引擎调用表（含触发条件与调用方法）

| # | 引擎 | 调用方法 | 什么时候调 | 拿到什么 |
|:--:|------|------|------|------|
| 1 | 今日头条 | `web_fetch "https://so.toutiao.com/search?dvpf=pc&keyword=<主题>+上游+卡脖子&pd=information"` | 雷达启动，第一步 | 新闻事件列表、涨停概念感知 |
| 2 | 韭研公社 | `bash tools/jiuyan_radar.sh "<主题>" --json`（🔴 不限条数/不截断/不pipe） | 雷达启动，第一步 | 🔥 v5.1 并行搜索+首页 |
| 3 | 微信公众号 | `web_fetch "https://weixin.sogou.com/weixin?type=2&query=<日期>+<主题>+国产替代&timeline=1"` | 雷达启动，第一步 | 散户复盘观点、直接标的名单 |
| 4 | 财联社 | Playwright 脚本：`python3 /tmp/zisu_playwright_scan.py`（需改写关键词） | 雷达启动，第一步 | 电报快讯(2157条)+资讯(3377条)+VIP研报 |
| 5 | 东方财富 | 同上 Playwright 脚本 | 雷达启动，第一步 | 当日概念涨跌TOP10+领涨股+板块异动时间线 |
| 6 | 淘股吧 | `python3 skills/taoguba/scripts/taoguba.py -s reply --max 20 -f json` | 雷达启动，第一步 | 游资情绪面、实盘选手复盘 |
| 7 | 雪球 | `python3 tools/xueqiu_tool.py --hot --hot-stocks` | 雷达启动，第一步 | 热门事件TOP10+热门股票TOP20+讨论数 |
| 8 | Bing News | `python3 tools/search.py "<主题> 上游 卡脖子 国产替代 A股" 10` | 雷达启动，第一步 | 跨平台聚合文章，英文来源也能覆盖 |
| 9 | 同花顺问财 | `thsdk`: connect → search_symbols → block_constituents(THSCODE) | 情报扫描后，标的池构建时 | 概念成分股完整列表+标的覆盖率验证 |
| 10 | 通达信问小达 | `python3 tools/tdx_zhangting.py --query "<主题>" --compact` | 情报扫描后，标的池构建时 | 主题股票池全覆盖(去重)+涨停原因揭秘 |
| 11 | 妙想 mx-data | `python3 skills/mx-data/mx_data.py "<候选列表> 最新价 涨跌幅 总市值 市盈率 主力资金流向"` | 标的池确定后，四视角评分前 | 批量行情+财务三表+资金流，Step 3 硬数据 |
| 12 | 妙想 mx-search | `python3 skills/mx-search/mx_search.py "<主题>+产业链+最新研报"` | 雷达启动，第一步（与1-8并行） | 机构研报+公司公告+互动问答+行业数据，金融信源智能筛选 |

> ⚠️ 1-8 + 12 并行启动（情报扫描），9-10 标的池构建时调用，11 评分前调用。不可跳步。

**执行顺序（不可跳步）**：雷达启动 → Step 0.0 板块查重(同花顺+东财+通达信) → Step 0 关键词矩阵拆词 → Step 0.5 时效补扫 → Step 0.6 多源验证 → 引擎 1-8+12 并行情报扫描 → 引擎 9-10 标的池验证(以板块成分股为基准交叉验证) → 标的池确定 → 引擎 11 妙想深度验证 → 雷达评分 → Step 2.5 防漏检查 → 定稿

> 🧠 记忆口诀：1头条 2公社 3微信 4财联 5东财 6淘股 7雪球 8Bing(中英) 9问财 10问小达 11妙想数据 12妙想搜索 19B站 20油管(中英) 21Reddit(英) 22Twitter(中英) 23华尔街 24Semi(英) 25慧博(研报) → 19个强制一个不落
> 🧠 灵活口诀：13集微(半导体) 14互动易(验证) 15龙虎榜(异动) 16Bing英文(中英) 17GoogleNews(中英) 18SeekingAlpha(英) → 按主题判断
> 🌐 中英双搜引擎：8(Bing) 16(Bing英文) 17(GoogleNews) 20(YouTube) 22(Twitter) 24(SemiAnalysis) → 每个引擎中英各搜一轮
> 🇬🇧 仅英文引擎：18(SeekingAlpha) 21(Reddit) → 英文平台，只搜英文

---

### 🛰️🍃📈 三大雷达 · 防漏检查清单（2026-06-29 设立，适用于全部三个雷达）

八大平台扫描完成后、雷达定稿前，必须执行防漏检查。

---

#### 🛰️ 科技制胜雷达：按「技术细分方向」防漏

```bash
# 补扫搜索词模板
python3 tools/search.py "<主题> (<遗漏子类1> OR <遗漏子类2>) 全球领先 全球首款 FDA获批 A股" 10
```

| 主题 | 预设子类清单 |
|------|------------|
| 创新药 | 肿瘤/自免/罕见病/麻醉/血液/眼科/中枢神经/代谢/抗感染/疫苗 |
| 半导体 | 设计/制造/封测/设备/材料/EDA/IP/第三代半导体/硅光/先进封装 |
| 新能源 | 光伏/风电/储能/氢能/核能/特高压/智能电网/虚拟电厂 |
| AI | 算力/大模型/应用/数据/机器人/自动驾驶/边缘AI/端侧AI |
| 新材料 | 碳纤维/高温合金/稀土永磁/电子化学品/生物基材料/气凝胶 |

---

#### 🍃 紫苏雷达：按「产业链环节」防漏

核心陷阱：从下游反推时，容易只推到一个环节（如只推到前道材料，漏了后道封装材料——硅微粉事故）。

```bash
# 补扫搜索词：直接搜"<产品/主题> 上游 耗材 卡脖子 A股 国产替代"
python3 tools/search.py "<主题> 上游 耗材 卡脖子 A股 国产替代" 10
# 再从最终产品反推一遍
python3 tools/search.py "<最终产品> 上游 材料 设备 耗材 国产替代 A股" 10
```

**必问三句话**（定稿前自问自答）：
1. "这个主题除了我想到的环节，从**最终产品**反推，还有哪些相关材料/耗材/设备细分被卡脖子？"
2. "我推的产业链是从A到B到C——中间有没有跳过环节？"
3. "我是否同时覆盖了前道和后道？制造和封装？材料和设备？"

---

#### 📈 涨价雷达：按「关联品种」防漏

核心陷阱：只看到涨价品种本身，没看到涨价逻辑的上下游传导和替代品。

```bash
# 补扫 1：上游传导
python3 tools/search.py "<涨价品种> 上游 原材料 涨价 2026" 10
# 补扫 2：下游受益
python3 tools/search.py "<涨价品种> 下游 受益 替代 2026" 10
# 补扫 3：替代品/关联品
python3 tools/search.py "<涨价品种> 替代 竞品 跟涨 关联 A股 2026" 10
```

**必问三句话**：
1. "这个品种涨价了，它的原材料有没有跟着涨？"
2. "下游谁受益？有没有替代品也跟着涨？"
3. "同一个大品类下面，有没有其他品种也在这波涨价周期里？"

---

**通用收尾检查**（三个雷达共用）：
1. 对照子类/环节/关联清单 → 标记遗漏
2. 补一次反向搜索
3. 标注"已通过防漏检查 ✅"后才能定稿发邮箱

---

### 🌐 七大平台搜索矩阵（2026-06-29 打通验证）

所有平台均在本日实战中验证通过，方法固化如下。

#### 环境依赖
- **Playwright + Chromium**（财联社、东方财富、雪球必需）
 ```bash
 pip3 install playwright
 python3 -m playwright install chromium
 ```
- 浏览器路径：`~/Library/Caches/ms-playwright/chromium-1223/`

---

#### ❶ 今日头条 — web_fetch（服务端渲染，零依赖）

```bash
# 搜索资讯
web_fetch "https://so.toutiao.com/search?dvpf=pc&keyword={关键词}&pd=information"
```

| 要点 | 说明 |
|------|------|
| 渲染方式 | 服务端渲染，web_fetch 直接拿 |
| 关键词 | 用 `+` 连接多词，如 `6月29日+涨停+概念` |
| 限制 | 只给标题+摘要，全文需另 Playwright 渲染文章链接 |
| 用途 | 新闻事件速览、涨停概念感知 |

---

#### ❷ 韭研公社 — 并行搜索+首页 v5.1（🔴 不限条数、不截断、不pipe）

**方案**：crawl4AI + 免费代理。搜索和首页双线程并行，互不阻塞。

```bash
bash tools/jiuyan_radar.sh "主题词" --json          # 🔴 JSON模式，不限条数不截断
bash tools/jiuyan_radar.sh "主题词" --json > /tmp/jy.json  # 输出到文件
bash tools/jiuyan_radar.sh --homepage            # 仅首页
bash tools/jiuyan_radar.sh --article <文章ID>     # 单篇全文
```

| 要点 | 说明 |
|------|------|
| 🔴 红线 | 禁止 `\| head` / `\| tail` / 任何截断命令。代码内已移除所有内置截断 |
| 代理获取 | proxyscrape 拉 15 个代理 → 逐个测试 → 2 次重试（间隔 2s）→ 5 分钟缓存 |
| 超时处理 | 18s 总超时，未完成的 future 自动 cancel，已完成的保留 |
| 速度 | 并行模式 ≤18s（vs v5.0 串行 40s+） |
| 依赖 | Python 3.13 venv + Playwright，无 API key |
| 降级 | 搜索挂 → 首页顶上；首页慢 → 搜索结果直接用 |
| 用途 | 产业链深度、题材全景感知、散户深度研报 |

---

#### ❸ 微信公众号 — web_fetch 搜狗微信

```bash
web_fetch "https://weixin.sogou.com/weixin?type=2&query={关键词}&timeline=1"
```

⚠️ **必须带日期才能命中当天文章**，纯宽泛词返回旧文甚至 2016 年的。

| 要点 | 说明 |
|------|------|
| `timeline=1` | 按时间排序；不加按相关性 |
| 正确示例 | `6月29日+复盘+涨停` / `6月29日+创新药+CRO` |
| 错误示例 | `热点板块` → 返回 2016 年旧文 |
| 用途 | 散户复盘观点、直接给标的名单 |

---

#### ❹ 财联社 — Playwright 渲染

```python
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
 browser = p.chromium.launch(headless=True)
 page = browser.new_page()
 page.goto(f"https://www.cls.cn/searchPage?keyword={关键词}&type=all",
 wait_until="load", timeout=15000)
 time.sleep(4)
 page.evaluate('window.scrollBy(0, 1500)')
 time.sleep(2)
 text = page.inner_text('body')
 browser.close()
```

| 要点 | 说明 |
|------|------|
| 渲染方式 | Next.js 客户端渲染，web_fetch 拿不到内容 |
| 关键词陷阱 | ❌ "热点板块" → 被理解成房地产土拍；✅ "概念板块"→ 科技概念 |
| 数据维度 | 电报(4367条)+资讯(7029条)+VIP+话题+板块+股票 |
| 用途 | 电报快讯最及时、机构晨会观点、VIP 深度研报 |

---

#### ❺ 东方财富 — Playwright 渲染

```python
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
 browser = p.chromium.launch(headless=True)
 page = browser.new_page()
 page.goto(f"https://so.eastmoney.com/news/s?keyword={关键词}&pageindex=1&searchrange=8192",
 wait_until="load", timeout=15000)
 time.sleep(5)
 text = page.inner_text('body')
 browser.close()
```

| 要点 | 说明 |
|------|------|
| 渲染方式 | 客户端渲染，web_fetch 只拿到导航骨架 |
| 独有优势 | 页面底部自带**当日概念板块涨跌幅 TOP 10** + 板块异动时间线 |
| 关键词陷阱 | 同财联社，"热点板块"=土拍，"概念板块"=科技 |
| 用途 | 当日涨跌幅排行、领涨股、ETF 资金流向 |

---

#### ❻ 淘股吧 — taoguba.py

```bash
# 热门帖 TOP 20（按回复数排序）
python3 skills/taoguba/scripts/taoguba.py -s reply --max 20

# JSON 输出
python3 skills/taoguba/scripts/taoguba.py -s reply --max 25 -f json
```

| 要点 | 说明 |
|------|------|
| 搜索功能 | 需 MFA 认证，不可用。用最新帖列表替代 |
| 数据字段 | author, title, likes, comments, time, article_url |
| 独有优势 | 游资复盘情绪面（"高位踩成泥""别把主线做丢了"），其他平台没有 |
| 用途 | 短线情绪、实盘选手复盘感受 |

---

#### ❼ 雪球 — xueqiu_tool.py（macOS 适配版）

```bash
# 热门事件 TOP 15（含讨论数）
python3 tools/xueqiu_tool.py --hot

# 热门股票 TOP 20（含涨跌幅、美股映射）
python3 tools/xueqiu_tool.py --hot-stocks

# 全部拿
python3 tools/xueqiu_tool.py --hot --hot-stocks

# 刷新 Cookie（如过期）
python3 tools/xueqiu_tool.py --renew
```

| 要点 | 说明 |
|------|------|
| 原理 | Playwright headless 访问雪球首页获取 Cookie → 保存到 `/tmp/xueqiu_storage.json` → 复用 |
| macOS 适配 | 原版（小龙虾）写死 `channel="msedge"`，已改为默认 Chromium |
| 无需滑块 | macOS headless 模式验证码未触发，可直接获取有效 Token |
| 搜索限制 | 雪球已废弃 search/timeline API，搜索页需登录。热门事件+热股功能正常 |
| 独有优势 | 讨论数（热度量化）、美股映射、事件+股票双维度 |

---

#### 🆕 Bing News — search.py（通用兜底）

```bash
python3 tools/search.py "关键词" 10
```

跨平台聚合，英文来源也能覆盖。

---

#### ❾ 同花顺问财 — thsdk（2026-06-30 打通）

```python
from thsdk import THS
ths = THS({'username': 'zsyyddx', 'password': 'jgyyddx33'})
ths.connect()
# 搜索概念板块代码
r = ths.search_symbols('工业互联网')
# 获取成分股
r = ths.block_constituents('URFI885783') # 同花顺概念代码
# r.data: [{代码: 'USHA600845', 名称: '宝信软件'}, ...]
# 代码格式: USHA=沪市, USZA=深市, 去掉前缀得A股代码
```

| 要点 | 说明 |
|------|------|
| 原理 | TCP 直连同花顺服务器，稳定可靠 |
| 概念数量 | 438 只工业互联网成分股（vs 问财 Web：0 结果） |
| 用途 | 验证标的是否在概念板块、成分股全覆盖 |
| 注意 | Web 版问财客户端渲染，不可用。只走 thsdk |

---

#### ❿ 通达信问小达 — tdx_zhangting.py（2026-06-30 打通，2026-07-11 修复自定义查询bug）

```bash
# 主题股票池查询（涨停板+相关股票）
python3 tools/tdx_zhangting.py --query "工业互联网" --compact
# --categorize 按原因揭秘分类，--csv CSV输出
# 热搜词不适用时，用关键词拆解：python3 tools/tdx_zhangting.py --query "CAR-T" --compact
```

| 要点 | 说明 |
|------|------|
| 原理 | Playwright 加载问小达页面 → 拦截 TQL API → 翻页抓取 |
| 涨停板模式 | HTTP POST 翻页，94只一次抓全 |
| 自定义查询 | captured response 回退（首页~30只），翻页需 HTTP POST（2026-07-11修复：空headers检测→自动回退） |
| 关键词拆解 | 一个词没结果→拆成子词逐一搜（如 CGT→CAR-T/细胞治疗/基因治疗/干细胞） |
| 数据量 | 涨停板94只，自定义30只/页 |
| 稳定性 | 偶有 EPIPE crash（翻页过多），重试可解决 |
| 用途 | 主题股票池全覆盖、涨停原因揭秘、盘面概念感知 |
| 注意 | 与涨停板分析共用同一脚本，通过 --query 区分 |
| 备用 | 问财 hithink-astock-selector / hithink-sector-selector |

---

#### 📊 平台特征速查表

| 平台 | 工具 | 最适合看什么 | 渲染 | 难度 |
|:----:|:----:|------------|:----:|:----:|
| 今日头条 | web_fetch | 新闻事件/涨停概念速览 | SSR | 低 |
| 韭研公社 | bash tools/jiuyan_radar.sh (并行搜索+首页) | 深度研报/题材挖掘 | 🔥 v5.1 并行 | 低 |
| 微信公众号 | web_fetch(搜狗) | 散户情绪/复盘观点 | SSR | 低 |
| 财联社 | Playwright | 电报快讯/机构观点 | CSR | 中 |
| 东方财富 | Playwright | 当日涨跌幅排行TOP10 | CSR | 中 |
| 淘股吧 | taoguba.py | 游资复盘/情绪面 | SSR | 低 |
| 雪球 | xueqiu_tool.py | 热门股票+讨论热度+美股 | CSR | 中 |
| Bing News | search.py | 跨平台聚合 | RSS | 低 |
| 同花顺问财 | thsdk | 概念成分股验证 | TCP | 低 |
| 通达信问小达 | tdx_zhangting.py | 主题股票池+涨停揭秘 | Playwright | 中 |
| 妙想 mx-data | mx_data.py | 个股行情+财务+资金流 | API | 低 |
| 华尔街见闻 | Playwright | 全球宏观+中国产业交叉视角 | CSR | 中 |
| SemiAnalysis | `python3 tools/semianalysis.py "query"` (Substack API) | 芯片/算力产业链最深度英文 | Substack API | 低 |
| 慧博投研资讯 | Playwright | 2000万+券商研报发现（摘要级） | SSR混合 | 低 |

> SSR = 服务端渲染（web_fetch 直接拿） / CSR = 客户端渲染（需 Playwright）

#### ⚡ 快速全扫命令（25引擎，以"工业互联网"为例）

```bash
# ===== 引擎1-10+12+19-24 情报扫描（并行启动）=====
# 引擎1: 今日头条
web_fetch "https://so.toutiao.com/search?dvpf=pc&keyword=工业互联网+上游+卡脖子&pd=information"
# 引擎2: 韭研公社（🔥 v5 curl+proxy搜索，7/25打通）
# 搜索：npx firecrawl-cli interact "Go to https://www.jiuyangongshe.com. Type '关键词' into search box, press Enter, wait 3s, extract article list."
# 全文：npx firecrawl-cli interact "Go to https://www.jiuyangongshe.com/a/<ID> and extract full article content"
# 引擎3: 微信公众号
web_fetch "https://weixin.sogou.com/weixin?type=2&query=6月30日+工业互联网+国产替代&timeline=1"
# 引擎4+5: 财联社+东财 (需 Playwright，见上方代码模板)
# 引擎6: 淘股吧
python3 skills/taoguba/scripts/taoguba.py -s reply --max 20 -f json
# 引擎7: 雪球
python3 tools/xueqiu_tool.py --hot --hot-stocks
# 引擎8: Bing News
python3 tools/search.py "工业互联网 上游 国产替代 A股" 10
# 引擎9: 同花顺问财 (thsdk)
# from thsdk import THS; ths=THS({'username':'zsyyddx','password':'jgyyddx33'}); ths.connect(); ths.block_constituents('URFI885783')
# 引擎10: 通达信问小达
python3 tools/tdx_zhangting.py --query "工业互联网" --compact
# 引擎12: 妙想资讯搜索
python3 skills/mx-search/mx_search.py "工业互联网+产业链+最新研报" /tmp/mx_search

# 引擎19: B站（中文）
bili search "工业互联网" --type video -n 5

# 引擎20: YouTube（中英双搜）
yt-dlp --dump-json "ytsearch5:工业互联网 中国" | python3 -c "..."
yt-dlp --dump-json "ytsearch5:Industrial Internet China IIoT" | python3 -c "..."

# 引擎21+22: Reddit + Twitter（社交舆论双引擎）— social_radar.sh 统一方案 🔥

✅ **2026-07-22 全部打通**：Firecrawl Search `site:reddit.com` + `site:x.com` 均可用。

```bash
# 双平台同搜（最常用）
bash tools/social_radar.sh "AI PC Nvidia RTX" --max 15 --json > /tmp/social.json

# 单平台
bash tools/social_radar.sh "半导体设备 国产替代" --platform reddit --max 10 --json
bash tools/social_radar.sh "创新药 FDA" --platform twitter --max 10 --json

# 输出格式: {"twitter": [...], "reddit": [...]}
```

| 引擎 | 方法 | 效果 |
|:--:|------|:--:|
| Reddit | Firecrawl Search `site:reddit.com` | ⭐⭐⭐⭐⭐ 英文极好 |
| Twitter | Firecrawl Search `site:x.com` + twitter-cli feed | ⭐⭐⭐⭐ 英文好，中文有spam |

### 打通历程
- Reddit: rdt-cli SIGKILL → RSS 被屏蔽 → **Firecrawl Search 可行**
- Twitter: search API 404 → Nitter 全灭 → Playwright 超时 → **Firecrawl Search 可行**

脚本：`tools/social_radar.sh` + `tools/social_radar.py`（Reddit+Twitter 统一）


# 引擎23: 华尔街见闻（Playwright搜索，见上方代码模板）
# 搜索URL: https://wallstreetcn.com/search?q=工业互联网

# 引擎24: SemiAnalysis（Substack API，2026-07-22验证）
# python3 tools/semianalysis.py "AI PC Nvidia chip" --max 10 --json

# 引擎25: 慧博投研资讯（Playwright行业分类浏览）
# 行业编码：%B5%E7%D7%D3=电子, %D0%C5%CF%A2%C9%E8%B1%B8=信息设备 等
python3 /tmp/hibor_scan.py --industry "电子"  # 需自写脚本，根据主题匹配行业

# ===== 标的池确定后 =====
# 引擎11: 妙想 mx-data 深度验证
python3 skills/mx-data/mx_data.py "候选股列表 最新价 涨跌幅 总市值 市盈率 主力资金流向" /tmp/mx_radar

# ===== 按需补充 =====
# 引擎13-18按主题判断启用（参考上方完整手册）
```
```

---

### 🧠 妙想 mx-data 深度数据引擎（2026-06-30 打通）

定位：紫苏雷达 Step 3 的数据引擎，标的池确定后批量拉行情+财务。

```bash
export MX_APIKEY=mkt_O4mKgLzdImocmBp0sAngCIsKzsOy7mOkSkKA50aWBm0

# 多股行情（5只齐查，秒出）
python3 skills/mx-data/mx_data.py "宝信软件 汇川技术 东土科技 最新价 涨跌幅 总市值 市盈率 主力资金流向"

# 个股财务（3年利润表）
python3 skills/mx-data/mx_data.py "宝信软件 近三年净利润 营业收入 毛利率 研发费用"

# 东财概念指数（用东财编码，如 BK1119=PLC概念）
python3 skills/mx-data/mx_data.py "PLC概念指数最新点位 涨跌幅"
```

| 要点 | 说明 |
|------|------|
| 原理 | 东方财富 API，自然语言→金融数据，稳定可靠 |
| ✅ 能做 | 个股行情（多只齐查）、财务三表、东财概念指数 |
| ❌ 不做 | 概念成分股（交给 thsdk）、通用概念指数（需东财编码） |
| 雷达定位 | Step 3 四视角数据引擎：技术面(行情) + 资金面(资金流+财务) |

---

### 📚 25引擎完整文档（2026-07-01 设立，7/6 升级为25引擎加入华尔街见闻+SemiAnalysis+慧博）

**引擎1-12+19-25强制，引擎13-18按主题灵活选用。**

两套资源，互为补充：

| 文件 | 用途 | 使用场景 |
|------|------|------|
| `tools/25engines_reference.md` | 完整调用手册：25个引擎的确切代码、参数、账号密码、启用规则 | spawn子代理时复制Step 0 |
| `tools/11engines_scan.py` | 引擎1-10一键扫描脚本 | 子代理第一件事直接执行 |

**25引擎速查**：

| # | 引擎 | 方式 | 强制/按需 |
|:--:|------|:--:|:--:|
| 1 | 今日头条 | web_fetch | 🔴 强制 |
| 2 | 韭研公社 | bash tools/jiuyan_radar.sh | 🔴 强制 |
| 3 | 微信公众号 | web_fetch(搜狗) | 🔴 强制 |
| 4 | 财联社 | Playwright | 🔴 强制 |
| 5 | 东方财富 | Playwright | 🔴 强制 |
| 6 | 淘股吧 | m.tgb.cn curl | 🔴 强制 |
| 7 | 雪球 | Playwright v2 | 🔴 强制 |
| 8 | Bing News | search.py | 🔴 强制 |
| 9 | 同花顺问财 | thsdk TCP | 🔴 强制 |
| 10 | 通达信问小达 | Playwright | 🔴 强制 |
| 11 | 妙想 mx-data | API | 🔴 强制 |
| 12 | 妙想 mx-search | API | 🔴 强制 |
| 13 | 集微网 | web_fetch | 🟡 半导体/电子主题 |
| 14 | 互动易 | web_fetch | 🟡 标的池确定后 |
| 15 | 龙虎榜 | wudao-intel | 🟡 有涨停标的 |
| 16 | Bing News英文 | search.py（英文query） | 🟡 全球产业链对标 |
| 17 | Google News | `python3 tools/google_news.py "query" both` | 🟡 需更广英文覆盖 |
| 18 | Seeking Alpha | `python3 tools/seeking_alpha.py "query" --json` | 🟡 美股映射标的 |
| 23 | 华尔街见闻 | Playwright搜索 | 🔴 新增强制 |
| 24 | SemiAnalysis | firecrawl-cli search → web_fetch | 🔴 新增强制 |
| 25 | 慧博投研资讯 | Firecrawl scrape 行业分类 | 🔴 新增强制 |

**⚠️ 外媒引擎规则（2026-07-01 董哥明令，2026-07-24 升级拆词铁律）**：

### 🔴 国外引擎拆词铁律（2026-07-24 董哥明令）

**中文整句翻译丢进英文搜索 = 垃圾结果。必须先拆中文关键词 → 逐词翻译成英文 → 每个英文关键词组单独搜。**

| 步骤 | 错误做法 | 正确做法 |
|:--:|------|------|
| 拆词 | "高温电力链多次涨停" → 直接翻译 | 拆为「全球高温」「电网负荷」「特高压招标」「海缆」「液冷散热」 |
| 翻译 | "high temperature power grid multiple limit up" | 每个子词独立翻译："record heat wave power grid", "UHV tender transmission", "submarine cable wind power" |
| 搜索 | 1次搜索 | 每个英文词组单独1次搜索（N个子词 = N次搜索） |

**实测对比（2026-07-24）**：
- 整句翻译 "China power grid heat wave demand"：1条 China Daily
- 拆词后 "record heat wave power grid" + "UHV tender" + "submarine cable"：5条（Reuters + Bloomberg + China Daily）
- 利基话题差距更大："Japan Tosoh dental zirconia supply disruption"→0条，拆为"dental zirconia Tosoh"→Google News命中2条

**适用引擎**：8(Bing) 16(Bing英文) 17(GoogleNews) 20(YouTube) 21(Reddit) 22(Twitter) 24(SemiAnalysis) 18(SeekingAlpha)

---

- 引擎16-18用英文搜索，但报告里全部中文输出
- 英文原文作为引用标注，正文全部翻译成中文
- **邮件附件Word文件名必须是中文**（如「紫苏雷达·电容·报告.docx」不是「zisu_capacitor_report.docx」）

**引擎启用规则**：1-12+19-25强制，13-18按主题灵活判断。子代理必须汇报启用理由。

**🔴 强制引擎总数：19个（1-12 + 19-25）**

> 🔴 适用范围：🍃紫苏 · 🛰️科技制胜 · 📈涨价 · 🎯纯度 —— 四个雷达通用。不因雷达类型跳过。

**spawn 子代理标准流程**（2026-07-15 设立，2026-07-22 全面升级）

⚠️ **关键原则：不要在 task 描述里手写引擎调用方法！让子代理读 `tools/25engines_reference.md`。**
- 引擎调用方法集中在 `tools/25engines_reference.md`，今天修了明天所有雷达自动生效
- API key 集中在 `tools/env.sh`，子代理第一件事 source

**Task 描述固定模板**：
```
⚠️ 25引擎铁律：引擎1-12+19-25缺一个返回重做，引擎13-18按主题判断启用
⚠️ 第一步执行：source tools/env.sh
⚠️ 严格按 tools/25engines_reference.md 中每个引擎的方法执行，不要用 web_search site: 代替 Firecrawl/SemiAnalysis
⚠️ 引擎结果必须全部整合进报告，不能只扫描不整合（AIPC雷达事故：Bing英文扫了但没加进报告）
   - 引擎16 Bing英文 → 报告中必须有「全球视角验证（Bing英文来源）」独立章
   - 引擎23 华尔街见闻 → 必须有独立章
   - 引擎24 SemiAnalysis → 必须有独立章
   - 引擎2 韭研公社 → 必须有独立节
   - 引擎25 慧博 → 必须有独立节（用Firecrawl scrape）
   每个引擎发现必须标注来源，不能混在其他章节里消失

[雷达类型+主题+标的池…具体任务内容]
```

**执行顺序（不可跳步）**：
1. `source tools/env.sh` 加载 API key
2. Step 0.0 板块查重（同花顺+东财+通达信）
3. Step 0 关键词矩阵拆词
4. Step 0.5 时效补扫 + Step 0.6 多源验证
5. 引擎 1-12+19-25 情报扫描（并行，严格按 25engines_reference.md）
6. 标的池验证 + 引擎 11 深度数据
7. 评分 → Step 2.5 防漏 → 定稿
4. 子代理基于扫描结果构建标的池
5. 子代理执行引擎11妙想验证
6. 子代理判断并执行引擎13-18（汇报启用理由）
7. 四视角评分 → Step 2.5 防漏检查 → 生成docx → 发邮件

> ⚠️ 核心原则：搜索词精度 > 引擎数量。先拆词验证覆盖面，再启动引擎做深度。不要拿了宽泛词直接轰引擎。

### 🚨 子代理上下文溢出防范 · 三阶段分拆规则（2026-07-18 设立，Atlas950 纯度雷达事故）

> 🔴 适用范围：🍃紫苏雷达 · 🛰️科技制胜雷达 · 📈涨价雷达 · 🎯题材纯度雷达 —— 全部四个雷达强制执行，无一例外。

**事故**：单子代理跑 25 引擎全流程，提示词 ~6000 字符 + MX 搜索 8 组各数千字返回 → 上下文溢出，结果截断，前半段引擎数据全部丢失。

**规则：大雷达（紫苏/科技制胜/涨价/纯度）统一分三阶段 spawn，禁止单代理一口气跑完。**

| 阶段 | 子代理 label | 任务 | 输出方式 | 预估耗时 |
|:--:|------|------|------|:--:|
| 1 | `radar_p1_intel` | Step 0 拆词 + Step 0.5 时效补扫 + Step 0.6 多源验证 + 引擎 1-8+12+19-25 并行情报扫描 | **每个引擎结果写文件** `/tmp/radar_eng_{N}.txt`，不靠返回 | 3-5min |
| 2 | `radar_p2_pool` | 读取阶段1所有 `/tmp/radar_eng_*.txt` + 引擎 9-10 标的池验证 + 引擎 11 深度数据 | 标的池 JSON → `/tmp/radar_pool.json` | 2-3min |
| 3 | `radar_p3_report` | 读取 `/tmp/radar_pool.json` + 阶段1引擎文件 → 四视角评分 → Step 2.5 防漏 → 生成 docx | Word 报告路径 | 2-3min |

**关键规则**：
- 阶段 1 子代理任务描述必须写：`⚠️ 每个引擎结果写入 /tmp/radar_eng_{N}.txt，不要依赖返回传递数据`
- 阶段 2/3 子代理任务描述开头附阶段 1 已完成引擎的文件清单
- 发邮件由主会话亲手执行（已有规则），子代理不代发
- 如果标的 < 30 只或引擎数量 < 12 个（如简单概念），可以合并为两阶段（1+2 合并）

### 🤖 Playwright 引擎独立脚本（2026-07-18 脚本化）

引擎 4/5/23/25 需要用 Playwright 渲染 CSR 页面。已写成独立 `.py` 脚本，子代理直接调用，不用嵌 Playwright 代码：

```bash
python3 tools/eng_4_cls.py "<关键词>"          # 引擎4: 财联社
python3 tools/eng_5_eastmoney.py "<关键词>"    # 引擎5: 东方财富
python3 tools/eng_23_wallstreetcn.py "<关键词>" # 引擎23: 华尔街见闻
# 引擎25: 慧博投研资讯（🔥 Firecrawl scrape，2026-07-22打通）
# 行业 URL 编码：电子=%B5%E7%D7%D3 计算机=%BC%C6%CB%E3%BB%FA
npx firecrawl-cli scrape "https://www.hibor.com.cn/newweb/web/hangye?f=3&hy1=%B5%E7%D7%D3"
```

### ✅ 25引擎强制CHECKLIST（2026-07-18 设立，防止引擎遗漏）

**每个 spawn 子代理的任务描述末尾必须附以下 checklist，子代理返回时必须逐项打勾。**

```
## ⚠️ 25引擎完成CHECKLIST（返回时逐项标记）
| # | 引擎 | 命令 | ✓/✗ |
|:--:|------|------|:--:|
| 1 | 今日头条 | web_fetch | |
| 2 | 韭研公社 | bash tools/jiuyan_radar.sh | |
| 3 | 微信公众号 | web_fetch 搜狗微信 | |
| 4 | 财联社 | python3 tools/eng_4_cls.py | |
| 5 | 东方财富 | python3 tools/eng_5_eastmoney.py | |
| 6 | 淘股吧 | python3 skills/taoguba/scripts/taoguba.py | |
| 7 | 雪球 | python3 tools/xueqiu_tool.py | |
| 8 | Bing News | python3 tools/search.py | |
| 9 | 同花顺问财 | thsdk (账号 zsyyddx) | |
| 10 | 通达信问小达 | python3 tools/tdx_zhangting.py | |
| 11 | 妙想MX Data | python3 skills/mx-data/mx_data.py | |
| 12 | 妙想MX搜索 | python3 skills/mx-search/mx_search.py (8组关键词) | |
| 13 | 集微网 | web_search site:jiweinet.com (仅半导体) | |
| 14 | 互动易 | python3 tools/search.py 互动易+标的 | |
| 15 | 龙虎榜 | web_search/wudao-intel (涨停标的) | |
| 16 | Bing英文 | python3 tools/search.py 英文关键词 | |
| 17 | Google News | web_fetch RSS / `tools/google_news.py` | |
| 18 | Seeking Alpha | `tools/seeking_alpha.py` (via Google News) | |
| 19 | B站 | bili search | |
| 20 | YouTube | yt-dlp --dump-json | |
| 21 | Reddit | RSS 直调（rdt CLI SIGKILL）| |
| 22 | Twitter/X | feed+user-posts（search ❌）| |
| 23 | 华尔街见闻 | python3 tools/eng_23_wallstreetcn.py | |
| 24 | SemiAnalysis | firecrawl-cli search site:newsletter.semianalysis.com | |
| 25 | 慧博投研 | Firecrawl scrape | |
```

**使用方式**：子代理返回结果时，必须在消息中附上填好的 checklist 表格（✓/✗ 标记）。缺 ✓ 的引擎视为不合格，主会话拒绝收报告。

**引擎16特别说明**：search.py英文查询已验证可用（"MLCC capacitor China"返回3篇MSN/Reuters英文报道），适用于几乎所有有全球对标的技术主题。

**关键账号（已嵌入脚本和手册）**：
- 同花顺问财：`zsyyddx` / `jgyyddx33`
- 妙想 mx-data：`MX_APIKEY=mkt_O4mKgLzdImocmBp0sAngCIsKzsOy7mOkSkKA50aWBm0`

---

### 🆕 引擎23：华尔街见闻 — Playwright 搜索（2026-07-06 打通）

```python
from playwright.sync_api import sync_playwright
import time, urllib.parse

keyword = urllib.parse.quote('AI硬件')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(f'https://wallstreetcn.com/search?q={keyword}', wait_until='load', timeout=15000)
    time.sleep(3)
    page.evaluate('window.scrollBy(0, 2000)')
    time.sleep(2)
    text = page.inner_text('body')
    browser.close()
```

| 要点 | 说明 |
|------|------|
| 渲染方式 | Next.js CSR，需 Playwright |
| 搜索质量 | "AI硬件"55条结果，时效性+深度兼备 |
| 独有优势 | 全球宏观+中国AI硬件交叉视角，现有引擎无替代 |
| 定位 | 🔴 强制引擎，情报扫描第一步并行启动 |
| 典型内容 | Meta卖算力砸崩AI硬件、AI硬件黄金时代、芯片半导体大爆发、中际旭创登顶第一重仓 |

---

### 🆕 引擎25：慧博投研资讯 — Firecrawl scrape 研报发现（2026-07-22 重新打通 🔥）

⚠️ Playwright inner_text 拿不到内容（JS 动态渲染），改用 Firecrawl scrape。

```bash
# 🔥 Firecrawl scrape 行业分类页（能渲染 JS，拿到完整研报列表，2026-07-22验证）
export FIRECRAWL_API_KEY=fc-a48d2a5ebcfb427fb438f992d62bf43e

# 选1-3个最相关行业，URL编码行业名称
# 电子=%B5%E7%D7%D3  计算机=%BC%C6%CB%E3%BB%FA  医药生物=%D2%BD%D2%A9%C9%FA%CE%EF
# 信息服务=%D0%C5%CF%A2%B7%FE%CE%F1  化工=%BB%AF%B9%A4  机械设备=%BB%FA%D0%B5%C9%E8%B1%B8
npx firecrawl-cli scrape "https://www.hibor.com.cn/newweb/web/hangye?f=3&hy1=%B5%E7%D7%D3"
```

| 要点 | 说明 |
|------|------|
| 原理 | Firecrawl scrape 完整渲染 JS 页面 → 拿到研报标题/机构/作者/日期/评级/页数 |
| 覆盖 | 28个大行业×细分行业，每页30篇研报 |
| 限制 | 全文展开需登录（loginLayer），PDF原文需登录 |
| 行业编码 | 用 Python `urllib.parse.quote('电子')` 获取 URL 编码 |
| 搜索 | 全站搜索报"服务器请求错误"，不可用 |
| 定位 | 🔴 强制引擎，2000万+投研文档，摘要级情报 |
| 典型 | 7/22 电子行业：东吴-800V、金元-AMD Helios、财通-封测、东吴-端侧AI周跟踪、东海-WAIC |

### 🆕 引擎24：SemiAnalysis — firecrawl-cli search + web_fetch（2026-07-06 打通，2026-07-22 升级搜索方法）

```bash
# Step 1: Firecrawl 搜索发现文章（绕过Tavily 433限流）
npx firecrawl-cli search "<topic> site:semianalysis.com"

# Step 2: web_fetch 获取单篇全文
web_fetch "https://newsletter.semianalysis.com/p/<article-slug>"
```

| 要点 | 说明 |
|------|------|
| 主站 | semianalysis.com 是商业落地页，文章在 newsletter.semianalysis.com（Substack） |
| 搜索方式 | firecrawl-cli search site:semianalysis.com（2026-07-22验证），不用 semianalysis.com 自身的搜索（404） |
| 内容深度 | 芯片/算力/数据中心产业链全球最深英文源，无人能敌 |
| 定位 | 🔴 强制引擎，情报扫描第一步并行启动 |
| 典型内容 | The Great AI Silicon Shortage、Rubin CPO架构、HBM4挑战、液冷、多数据中心训练、GPU短缺价格指数 |
| 注意 | 英文内容，报告中翻译为中文 |

---

## 🔄 雷达引擎备用数据源方案 (2026-07-09)

每个引擎都有主数据源，当主源不可用时自动降级到备用源。

### 降级总表

| 引擎 | 主数据源 | 备用1 | 备用2 | 降级触发 |
|:--:|------|------|------|------|
| 9 同花顺问财 | thsdk TCP | 问财 iwencai (hithink-astock-selector) | mx-xuangu | thsdk无数据/断连 |
| 10 通达信问小达 | tdx_zhangting.py | 关键词拆解（自定义查询回退captured response） | 问财 hithink-astock-selector | 翻页解析失败/空结果 |
| 11 妙想 mx-data | mx_data.py API | 问财 hithink-finance-query | 腾讯财经 free_finance.py | mx-data限额/超时 |
| 12 妙想 mx-search | mx_search.py API | 问财 report-search | 问财 news-search | mx-search限额/超时 |
| 4 财联社 | Playwright | 问财 news-search | web_search | Playwright crash/OOM |
| 5 东方财富 | Playwright | 问财 hithink-sector-selector | web_search | Playwright crash/OOM |

### 问财 iwencai 技能调用方式

所有问财技能通过 OpenAPI 调用，API key 在 `~/.zshrc` 中：
```
IWENCAI_BASE_URL=https://openapi.iwencai.com
IWENCAI_API_KEY=sk-proj-01-...
```

10个技能安装路径：`~/.openclaw/workspace-dengxian/skills/<slug>/`

**引擎9 备用：问财智能选股**
```bash
# 替代 thsdk 搜索概念成分股
python3 skills/hithink-astock-selector/scripts/cli.py --query "华为昇腾概念股" --limit 20
# 返回：股票代码、简称、最新价、涨跌幅、所属概念、纳入原因、行业、板块
```

**引擎10 备用：问财板块发现**
```bash
# 替代 tdx_zhangting.py 涨停/板块分析
python3 skills/hithink-sector-selector/scripts/cli.py --query "超节点 产业链" --limit 20
```

**引擎11 备用：问财财务查询**
```bash
# 替代 mx-data 获取批量财务数据
python3 skills/hithink-finance-query/scripts/cli.py --query "盛科通信 中科曙光 澜起科技 净利润 营收 毛利率" --limit 5
```

**引擎12 备用：问财研报/新闻搜索**
```bash
# 替代 mx-search 获取研报
python3 skills/report-search/scripts/report_search.py "超节点 华为 研报" --size 10
# 替代 mx-search 获取新闻
python3 skills/news-search/scripts/cli.py --query "超节点 华为 Atlas" --limit 10
```

**引擎4 备用：问财新闻**
```bash
# 替代 Playwright 抓财联社
python3 skills/news-search/scripts/cli.py --query "超节点 涨停 概念股" --limit 10
```

**引擎5 备用：问财板块发现**
```bash
# 替代 Playwright 抓东财概念涨跌
python3 skills/hithink-sector-selector/scripts/cli.py --query "当日热点概念 涨幅" --limit 10
```

### 三级降级链（引擎11完整示例）
```
mx_data.py → 失败/限额 → hithink-finance-query → 失败 → free_finance.py (腾讯+东财)
```

### 其他引擎的主备方案

| 引擎 | 主源 | 备用 | 说明 |
|:--:|------|------|------|
| 1 今日头条 | web_fetch | web_search site:toutiao.com | 头条反爬时用搜索 |
| 2 韭研公社 | curl+proxy (bash tools/jiuyan_radar.sh) | 跳过（不可用） | 🔥 7/25 v5 打通搜索端点 /search/new?k= |
| 3 微信公众号 | web_fetch 搜狗 | web_search site:mp.weixin.qq.com | 搜狗反爬时备选 |
| 6 淘股吧 | taoguba.py | web_search site:tgb.cn | 脚本故障时用搜索 |
| 7 雪球 | xueqiu_tool.py | 问财 news-search | Playwright crash时 |
| 8 Bing News | search.py | web_search (Tavily) | search.py故障时 |
| 13 集微网 | web_fetch | web_search site:jiweinet.com | 反爬时备用 |
| 14 互动易 | web_fetch | 问财 announcement-search | 反爬时切公告搜索 |
| 15 龙虎榜 | wudao-intel | 问财 hithink-event-query | API故障时 |
| 19-22 视频社交 | bili/yt-dlp/rdt/twitter | web_search | CLI故障时 |
| 23 华尔街见闻 | Playwright | web_search site:wallstreetcn.com | Playwright crash时 |
| 24 SemiAnalysis | firecrawl-cli search + web_fetch | 跳过（纯英文源无替代） | 搜索失败时 |
| 25 慧博 | Firecrawl scrape 行业分类 | 问财 report-search | 优先Firecrawl |

### 子代理环境变量传递
spawn 子代理时，IWENCAI_API_KEY 需要显式传入或确保子代理能读取 `~/.zshrc`。
建议在任务描述中直接写入 API key（子代理是隔离环境，不会泄漏到外部）。

### 引擎选择决策树（子代理用）
```
需要成分股列表？
  → 优先 thsdk.search_symbols + block_constituents
  → 失败 → hithink-astock-selector
  → 仍失败 → mx-xuangu

需要行情/财务？
  → 优先 mx-data
  → 限额/超时 → hithink-finance-query
  → 仍失败 → free_finance.py

需要研报/新闻？
  → 优先 mx-search
  → 限额/超时 → report-search / news-search
  → 仍失败 → web_search

需要涨停板分析？
  → 优先 tdx_zhangting.py
  → 解析失败 → hithink-sector-selector
  → 仍失败 → wudao-limitup
```

---

## ⚠️ 个股深度研究 · 12引擎强制执行清单（2026-07-24 设立，603496漏引擎事故）

### 事故
董哥要求603496恒为科技个股深度研究，我只跑了引擎8+11+12（3个）就写报告，跳过了头条/韭研公社/微信/淘股吧/雪球/通达信/慧博/B站。结果漏掉了：
- 收购方案从75%发行股份缩水为51%现金（4.67亿）
- 头条有质疑文章「超节点赛道技术有底子但商业化进度明显落后」
- 7/8、7/16、7/17三次涨停记录
- 光大证券跟踪报告

### 根因
凭经验判断「个股不需要那些引擎」→自动跳过→跟雷达漏标同一个病根。SKILL.md 写了12引擎我当建议没当命令。

### 规则（铁律·2026-07-24 董哥明令：25引擎全量，跟雷达对齐）

**🔴 Step -1（强制，不可跳过）：先读取 `tools/25engines_reference.md`**，严格按其中每个引擎的 wrapper 调用代码执行。
- 妙想搜索必须用 `bash tools/mx_search.sh`（不用 `export && python`）
- 妙想数据必须用 `bash tools/mx_data.sh`
- 韭研公社必须用 `bash tools/jiuyan_radar.sh`（v5 curl搜索，7/25起）
- Reddit 必须用 `bash tools/social_radar.sh`
- Twitter 必须用 `bash tools/twitter_radar.sh`
- SemiAnalysis 必须用 `python3 tools/semianalysis.py`
- 慧博必须用 `npx firecrawl-cli scrape`
**没读到这个文件 = 不发报告。**

**每次个股深度研究，25引擎缺一不可，逐项打勾，不可凭经验跳过。**

**强制引擎（20个：1-14 + 19-25）**

| # | 引擎 | 调用方法 | 拿什么 |
|:--:|------|------|------|
| 1 | 今日头条 | web_fetch 头条搜索 | 媒体动态、收购变动、质疑观点 |
| 2 | 韭研公社 | bash tools/jiuyan_radar.sh | 散户产业链深度分析 |
| 3 | 微信公众号 | web_fetch 搜狗微信 | 涨停记录、券商研报、散户复盘 |
| 4 | 财联社 | python3 tools/eng_4_cls.py | 电报快讯、VIP研报 |
| 5 | 东方财富 | python3 tools/eng_5_eastmoney.py | 概念板块归属、领涨股 |
| 6 | 淘股吧 | taoguba.py | 游资情绪、短线讨论热度 |
| 7 | 雪球 | xueqiu_tool.py | 热门事件+热门股票 |
| 8 | Bing News | tools/search.py | 跨平台聚合+英文源 |
| 9 | 同花顺问财 | thsdk search_symbols | 概念板块归属验证 |
| 10 | 通达信问小达 | tdx_zhangting.py | 主题池+涨停原因 |
| 11 | 妙想MX Data | mx_data.py | 财务三表+估值+资金流 |
| 12 | 妙想MX搜索 | mx_search.py | 机构研报+公告+互动问答 |
| 13 | 集微网 | web_fetch + web_search | 半导体/芯片主题（按需）|
| 14 | 互动易 | tools/search.py 互动易+标的 | 🔴 验证产业链地位、订单、客户 |
| 19 | B站 | bili search | 视频解读、散户科普 |
| 20 | YouTube | yt-dlp | 全球视频+英文解读 |
| 21 | Reddit | rdt search | 全球社区讨论+批判视角 |
| 22 | Twitter/X | twitter search | KOL+官号实时观点 |
| 23 | 华尔街见闻 | tools/eng_23_wallstreetcn.py | 宏观+产业交叉视角 |
| 24 | SemiAnalysis | firecrawl-cli search | 芯片/算力全球最深英文源 |
| 25 | 慧博 | tools/eng_25_hibor.py | 2000万+券商研报库 |

**灵活引擎（5个：15-18+13按需，按主题判断）**

| # | 引擎 | 触发条件 |
|:--:|------|------|
| 15 | 龙虎榜 | 近5日有涨停/异动时 |
| 16 | Bing英文 | 有全球产业链对标（默认启用） |
| 17 | Google News | 需更广泛英文报道时 |
| 18 | Seeking Alpha | 有美股映射标的时 |

**使用方式**：每次个股深度研究完成后必须附CHECKLIST逐项打 ✓/✗。20个强制引擎缺一个=不合格，不发邮件，重做。

**🔴 互动易特别强调**：每个股深度研究都必须搜互动易，这是验证产业链地位、在手订单、客户关系的直接渠道，上市公司在互动易的回复具有半官方性质，比其他二手信息源可靠。

**执行顺序**：引擎 1-8+12+19-25 并行情报扫描 → 引擎 9-10 概念验证 → 引擎 11 深度数据 → 引擎 13-18 按需补扫 → 四视角分析 → 报告

**603496事故教训**：跳过引擎1-3+6-7+10+14，漏掉收购方案缩水、头条质疑、三次涨停、光大研报、互动易订单验证。不跑全量=漏关键信息，没有例外。

**互动易查询模板**（每只个股必问4类问题）：
1. 在手订单：「互动易 <简称> 订单 客户 产能」
2. 产业链地位：「互动易 <简称> 行业地位 市场份额 供应商」
3. 技术进展：「互动易 <简称> 研发 产品进展 认证」
4. AI/热点相关：「互动易 <简称> AI 智算 Agent OCS 光交换」
