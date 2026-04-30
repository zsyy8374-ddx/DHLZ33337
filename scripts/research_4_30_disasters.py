"""实验 9: 仔细看 4-30 翻车的极强档 6 只
找它们的真共同特征 (不能用历史规律解释的部分)"""
import json

with open("/Users/openclaw/.openclaw/workspace-dengxian/picks/reversal-v4-2026-04-29-with-4-30-actual.json") as f:
    cands = json.load(f)["candidates"]

disasters = [c for c in cands if c["lr_prob"] >= 0.78 and c["chg_4_30"] is not None and c["chg_4_30"] <= -3]
print(f"\n💀 4-30 极强档翻车 {len(disasters)} 只详情:")
for c in disasters:
    print(f"\n   {c['code']} {c['name']}")
    print(f"     P={c['lr_prob']:.3f}  跌{c['chg_4_30']:+.1f}%")
    print(f"     D0={c['d0_date']}  板={c['d0_lbc']}  回={c['callback_pct']:.1f}%  最低收{c['min_close_pct']:.1f}%")
    print(f"     D0 主力 +{c['d0_main_flow']:.2f}亿  cb5 {c.get('cb5_main_avg',0):+.2f}亿  cb3 {c.get('cb3_main_avg',0):+.2f}亿  cb1 {c.get('cb1_main_avg',0):+.2f}亿")
    print(f"     pre_d0_5d {c.get('pre_d0_5d_main_avg',0):+.2f}亿/日")

# 看共性
print(f"\n📊 翻车 6 只的共同特征:")
import statistics
for k in ["lr_prob","callback_pct","d0_lbc","d0_main_flow","cb5_main_avg","cb3_main_avg","cb1_main_avg","pre_d0_5d_main_avg"]:
    vals = [c.get(k,0) or 0 for c in disasters]
    print(f"   {k:<25} 范围 [{min(vals):>+7.2f}, {max(vals):>+7.2f}]  中位 {statistics.median(vals):>+7.2f}")

# 涨停 18 只的对比
zt = [c for c in cands if c["zt_4_30"]]
print(f"\n📊 涨停 18 只的同特征 (对比):")
for k in ["lr_prob","callback_pct","d0_lbc","d0_main_flow","cb5_main_avg","cb3_main_avg","cb1_main_avg","pre_d0_5d_main_avg"]:
    vals = [c.get(k,0) or 0 for c in zt]
    print(f"   {k:<25} 范围 [{min(vals):>+7.2f}, {max(vals):>+7.2f}]  中位 {statistics.median(vals):>+7.2f}")

# 关键: 看 d0_date 的具体日期分布
print(f"\n📊 翻车 vs 涨停的 d0_date 分布:")
from collections import Counter
print(f"   翻车: {dict(Counter(c['d0_date'] for c in disasters))}")
print(f"   涨停: {dict(Counter(c['d0_date'] for c in zt))}")
