"""用 v1.4 集成模型重新打分 4-29 的候选, 看 v1.4 在 4-30 实战上是否更稳
- 加载 picks/reversal-v4-2026-04-29.json 的 candidates (已有 v1.1 LR 打分)
- 用 v1.4 集成模型 重新预测
- 对比同一批候选, 哪个模型选出来的 Top 50 涨停数更多
- 注意: 4-29 推送的目标是 4-30, 但 reversal 的 outcome 需要 D0+10 个交易日, 单看 4-30 涨停数据不能严格证明 reversal, 但能反映"短期能不能拉升"
"""
import json, sys
sys.path.insert(0, '/Users/openclaw/.openclaw/workspace-dengxian/scripts')
from predict_v14 import load_v14_model, predict_v14
from lr_v11_with_recent_rev_rate import extract_v11
from pathlib import Path

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')

# 找最新 reversal-v4 推送
candidates_files = sorted(WORKSPACE.glob('picks/reversal-v4-*.json'), reverse=True)
target = None
for f in candidates_files:
    if '2026-04-29' in f.name:
        target = f; break
if not target:
    print("❌ 找不到 4-29 推送")
    print("可用:", [f.name for f in candidates_files[:5]])
    sys.exit(1)

with open(target) as f:
    data = json.load(f)
print(f"✅ 加载 {target.name}, candidates: {len(data['candidates'])}")

# v1.4 模型
model_v14 = load_v14_model()
print(f"   v1.4 模型: {len(model_v14['gbdt_trees'])} 棵 GBDT + LR")

# 4-30 真实结果 - 从 picks/reversal_hits_full.jsonl 拉
hits_file = WORKSPACE / 'picks' / 'reversal_hits_full.jsonl'
real_results = {}
if hits_file.exists():
    with open(hits_file) as f:
        for line in f:
            row = json.loads(line)
            if row.get('picks_date') == '2026-04-29':
                real_results[row['code']] = row
print(f"   4-30 实战数据: {len(real_results)} 只")

# v1.4 重新打分
candidates = data['candidates']
for c in candidates:
    # 从 candidate 里 reconstruct features
    # candidate 已经有 lr_prob (v1.1) 但没有原始 features, 我得重算
    # picks_v4.py 里有 extract_v11 数据放进 candidate 的字段, 但是单独可能不够
    # 看下 candidate 字段
    pass

print(f"\n样例 candidate 字段:")
for k in list(candidates[0].keys())[:30]:
    print(f"  {k}: {candidates[0].get(k)}")
