"""分析多日板块强度趋势, 找出'稳定 Top'的真主升板块"""
import pandas as pd
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta

OUT = Path('/Users/openclaw/.openclaw/workspace-dengxian/mx_output')


def get_recent_trading_days(n=8):
    """动态获取最近 n 个交易日 (按北京时间)"""
    days = []
    d = datetime.now()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.strftime('%Y-%m-%d'))
        d -= timedelta(days=1)
    return list(reversed(days))


# 默认: 最近 8 个交易日 (有文件的); 如果某天文件没, 跳过
DATES = []
for d in get_recent_trading_days(10):  # 多拿几天防跳空
    if (OUT / f'sector_strength_{d}.csv').exists():
        DATES.append(d)
DATES = DATES[-8:]  # 只看最近 8 个
if not DATES:  # 回退: 用原始固定日期
    DATES = ['2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24',
             '2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30']

# 收集每天的 Top 30
all_data = {}  # {date: df}
for d in DATES:
    f = OUT / f'sector_strength_{d}.csv'
    if not f.exists():
        print(f"⚠ {d} 缺数据"); continue
    df = pd.read_csv(f)
    df['rank'] = range(1, len(df)+1)
    all_data[d] = df

# 板块 → 各日排名
sec_ranks = defaultdict(dict)  # {sector: {date: rank}}
sec_scores = defaultdict(dict)
for d, df in all_data.items():
    for _, r in df.iterrows():
        sec = r['板块']
        sec_ranks[sec][d] = r['rank']
        sec_scores[sec][d] = r['综合分']

# 每个板块的: 出现天数(在Top30) / 平均排名 / 最佳排名 / 趋势
TOP_N = 20
results = []
for sec, ranks in sec_ranks.items():
    in_top = [d for d, r in ranks.items() if r <= TOP_N]
    if not in_top: continue
    avg_rank = sum(ranks.values()) / len(ranks)
    best_rank = min(ranks.values())
    days_in_top = len(in_top)
    
    # 趋势: 最后 3 天 vs 前 3 天
    sorted_dates = sorted(ranks.keys())
    if len(sorted_dates) >= 6:
        early_avg = sum(ranks[d] for d in sorted_dates[:3]) / 3
        late_avg  = sum(ranks[d] for d in sorted_dates[-3:]) / 3
        trend = early_avg - late_avg  # 正 = 排名变好(数字变小)
    else:
        trend = 0
    
    results.append({
        '板块': sec,
        f'Top{TOP_N}天数': days_in_top,
        '总出现天数': len(ranks),
        '平均排名': round(avg_rank, 1),
        '最佳排名': best_rank,
        '趋势(向好+)': round(trend, 1),
        **{d: ranks.get(d, '-') for d in DATES}
    })

df = pd.DataFrame(results)
df = df.sort_values([f'Top{TOP_N}天数', '平均排名'], ascending=[False, True]).reset_index(drop=True)

print(f"=== 多日 (8 天) 板块强度趋势 — 真主升板块筛选 ===\n")
print(f"{'排':>2s} {'板块':<14s} {'Top'+str(TOP_N)+'天':>5s} {'均排':>5s} {'最佳':>4s} {'趋势':>5s}  {'4-21 4-22 4-23 4-24 4-27 4-28 4-29 4-30':<48s}")
print('-'*120)

for i, r in df.head(25).iterrows():
    daily = ' '.join(f"{int(r[d]):>3d}" if r[d] != '-' else "  -" for d in DATES)
    print(f"{i+1:>2d} {str(r['板块'])[:14]:<14s} {int(r[f'Top{TOP_N}天数']):>5d} "
          f"{r['平均排名']:>5.1f} {int(r['最佳排名']):>4d} {r['趋势(向好+)']:>+5.1f}  {daily}")

# 写 CSV (两份: 一份固定名供下游读, 一份带日期备份)
out = OUT / 'sector_trend_8day_2026-04-21_to_30.csv'  # 下游读这个 (帮本名锁定)
df.to_csv(out, index=False, encoding='utf-8-sig')
print(f"\n✅ 写入 {out}")

# 备份一份带当前范围的
backup = OUT / f'sector_trend_8day_{DATES[0]}_to_{DATES[-1]}.csv'
if backup != out:
    df.to_csv(backup, index=False, encoding='utf-8-sig')
    print(f"✅ 备份 {backup}")

# 结论摘要: 哪些板块 8 天里有 ≥5 天进 Top20
stable = df[df[f'Top{TOP_N}天数'] >= 5]
print(f"\n=== 稳定 Top{TOP_N} (8 天里 ≥5 天) — 真主升板块 ===")
for _, r in stable.iterrows():
    print(f"  {r['板块']:<14s}  Top{TOP_N}: {r[f'Top{TOP_N}天数']}/8天, 均排 {r['平均排名']:.1f}, 趋势 {r['趋势(向好+)']:+.1f}")
