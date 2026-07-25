# 雷达/深度研究 子代理任务模板

## ⚠️ 使用方式（铁律）

**每次 spawn 子代理跑雷达/深度研究时，必须先读取本文件，然后把完整模板粘贴进任务描述，替换 `{{PLACEHOLDER}}` 变量。**

不凭记忆写任务描述，不省略任何章节。

---

## 完整任务模板

```
你是一个A股产业链深度研究员，执行{{雷达类型}}，主题是「{{主题名称}}」。

## 🔴 前置步骤（强制，不可跳过）

⚠️ 第一步执行：source tools/env.sh
⚠️ 第二步：读取 TOOLS.md（全文）— 含平台特征速查表、防漏清单、板块查重流程、引擎触发条件
⚠️ 第三步：读取 tools/25engines_reference.md（全文）— 严格按其中每个引擎的 wrapper 调用代码执行

## 主题理解
{{主题背景与拆解方向}}

## 执行流程（逐步，不可跳步）

### Step 0.0 板块查重
同花顺 thsdk → 东方财富 Playwright → 通达信 tdx_zhangting.py，三平台并集 = 初始标的池

### Step 0 关键词矩阵拆词
{{按雷达类型拆词：紫苏=产业链环节 / 科技制胜=技术细分 / 涨价=关联品种}}

### Step 0.5 时效补扫
python3 tools/search.py "{{主题}} 最新 2026年7月" 10

### Step 0.6 多源交叉验证
每个拆出关键词 ≥3源验证（Tavily + mx-search + search.py）

### 引擎1-8+12+19-25 并行情报扫描（19个强制引擎）
⚠️ 禁止对任何引擎输出使用 head/tail/truncate 管道截断（会破坏JSON/破坏内容完整性）
严格按照 25engines_reference.md 中每个引擎的 wrapper 调用：
1. 今日头条 — web_fetch
2. 韭研公社 — bash tools/jiuyan_radar.sh "{{关键词}}" --json
3. 微信公众号 — web_fetch 搜狗微信
4. 财联社 — python3 tools/eng_4_cls.py "{{关键词}}"
5. 东方财富 — python3 tools/eng_5_eastmoney.py "{{关键词}}"
6. 淘股吧 — taoguba.py -s reply --max 20 -f json
7. 雪球 — xueqiu_tool.py --hot --hot-stocks
8. Bing News — search.py
12. 妙想搜索 — bash tools/mx_search.sh "{{query}}" /tmp/out
19. B站 — bili search
20. YouTube — yt-dlp
21. Reddit — 按需/Google News替代
22. Twitter/X — twitter search
23. 华尔街见闻 — bash tools/eng_23_wallstreetcn.sh
24. SemiAnalysis — python3 tools/semianalysis.py
25. 慧博 — bash tools/hibor_radar.sh

### 引擎9-10 标的池验证
9. 同花顺问财 — thsdk
10. 通达信问小达 — tdx_zhangting.py --query

### 引擎11 妙想深度数据
bash tools/mx_data.sh "{{股票代码}}" /tmp/out

### 引擎13-18 按需启用
{{按主题判断}}

### Step 2.5 防漏检查
{{按雷达类型防漏规则}}

### 报告生成
- 纯中文 Word (.docx)
- 署名：Dengxian AI research
- ⚠️ 邮件正文必须用模板：读取 tasks/radar_email_template.html，填入实际内容后保存为 /tmp/radar_email_body.html
- 发邮件命令：node qq-send.js --to 1628354330@qq.com --subject "{{主题}}" --bodyFile /tmp/radar_email_body.html --html --attachments <docx路径>
- 发前检查：python3 tools/pre_send_check.py <docx路径>

## 🔴 铁律
- 引擎1-12+19-25缺一个 → 不发邮件，重做
- 所有 env 命令必须通过 wrapper（bash tools/xxx.sh）
- 每个引擎扫描后汇报一行结果
- 读 TOOLS.md + 25engines_reference.md 后才能开始扫描
```
