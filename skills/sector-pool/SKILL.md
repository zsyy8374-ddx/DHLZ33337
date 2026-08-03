---
name: sector-pool
display_name: 三平台板块池
title: 三平台板块池构建 (THS + TDX + DFCF)
description: 给定题材关键词，自动搜索同花顺/通达信/东方财富三大平台相关概念板块，拉取成分股，合并去重输出统一股票池。雷达 Step 0.0 板块查重的核心工具。
author: dengxian
version: 2.2.0
---

# sector-pool 三平台板块池

给定题材关键词 → 三平台搜索概念板块 → 拉成分股 → 合并去重 → 输出统一标的池。

## 用法

```bash
# 全平台
python3 skills/sector-pool/scripts/sector_pool.py "新型电力系统"

# JSON 输出
python3 skills/sector-pool/scripts/sector_pool.py "新型电力系统" --json

# 指定平台 + 额外关键词
python3 skills/sector-pool/scripts/sector_pool.py "新型电力系统" \
  --keywords "智能电网" "特高压" "储能" "虚拟电厂" --json

# 摘要模式 (不含个股明细)
python3 skills/sector-pool/scripts/sector_pool.py "新型电力系统" --summary --json
```

## 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `theme` | 题材关键词（必填） | - |
| `--keywords` | 额外搜索关键词，用于拆词扩展 | 主题词本身 |
| `--json` | JSON 格式输出 | 文本 |
| `--summary` | 摘要模式，只含代码不含个股详情 | 完整 |
| `--output/-o` | 输出到文件 | stdout |
| `--no-ths` | 跳过同花顺 | 不跳过 |
| `--no-tdx` | 跳过通达信 | 不跳过 |
| `--no-dfcf` | 跳过东方财富 | 不跳过 |

## 三平台原理

### 同花顺 (THS)
- **搜索板块**: `thsdk.search_symbols()` → 筛选 URFI(概念)/UFIA(行业) 板块
- **拉成分股**: `thsdk.block_constituents(THSCODE)` → 每板块去前缀得 A 股代码
- **优势**: TCP 直连，稳定可靠，板块体系最完整

### 通达信 (TDX/问小达)
- **搜索股票**: `tdx_zhangting.py --query` → Playwright 抓取问小达
- **聚合板块**: 按 `所属行业` 字段反向聚合 → 行业板块排名
- **优势**: 不依赖 API key，独立 Playwright 抓取

### 东方财富 (DFCF)
- **搜索板块**: push2 API (全量拉取 → 关键词筛选) + fallback 已知 BK 映射表
- **拉成分股**: push2 API `fs=b:BKxxxx`
- **注意**: API 可能 502，此时自动用已知映射表兜底

## 输出 JSON 结构

```json
{
  "theme": "新型电力系统",
  "platforms": {
    "ths": {
      "sectors": {
        "URFI885921": {
          "name": "储能", "market": "URFI",
          "count": 280, "stocks": [{"code": "300750", "name": "宁德时代"}, ...]
        }
      },
      "total_stocks": 1234
    },
    "tdx": { ... },
    "dfcf": { ... }
  },
  "merged_stocks": {
    "300750": {"code": "300750", "name": "宁德时代"},
    ...
  },
  "total_merged": 567
}
```

## 依赖

- **同花顺**: thsdk (`from thsdk import THS`), 账号 zsyyddx
- **通达信**: `tools/tdx_zhangting.py` (Playwright + Chromium)
- **东方财富**: Python urllib (push2 API, 可能不稳定)

## 使用场景

- **雷达 Step 0.0 板块查重**: 三平台并集构建初始标的池
- **题材广度验证**: 看一个题材在三平台的板块覆盖是否充分
- **标的池快速构建**: 输入题材词 → 直接得到三个维度的股票列表
