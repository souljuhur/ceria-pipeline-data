"""완성도 점수 분포 분석 및 필드별 채움률 확인"""
import json, collections

_PATH = r"d:\머신러닝 교육\ceria_pipeline_data\output\ceria_dataset_full.jsonl"

scores = []
field_fills = collections.Counter()
total = 0

with open(_PATH, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        sc = r.get("completeness_score") or 0
        scores.append(sc)
        total += 1
        for k, v in (r.get("synthesis_conditions") or {}).items():
            if v is not None:
                field_fills[k] += 1

scores.sort()
print(f"총 레코드: {total:,}편\n")

# 점수 구간별 분포
buckets = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 100]
print("=== 완성도 점수 구간별 누적 편수 ===")
for thr in buckets:
    cnt = sum(1 for s in scores if s >= thr)
    pct = cnt / total * 100
    bar = "█" * (cnt // 50)
    print(f"  ≥{thr:3d}%  {cnt:>5,}편  ({pct:5.1f}%)  {bar}")

# 10분위
print("\n=== 분위수 ===")
import statistics
for p in [10, 25, 50, 75, 90, 95]:
    idx = int(len(scores) * p / 100)
    print(f"  P{p:2d}: {scores[idx]:.1f}%")

# 필드별 채움률
print("\n=== 필드별 채움률 (전체 대비) ===")
for field, cnt in sorted(field_fills.items(), key=lambda x: -x[1]):
    print(f"  {field:<35} {cnt:>5,}  ({cnt/total*100:5.1f}%)")

# synthesis_summary 있는 것
with open(_PATH, encoding="utf-8") as f:
    has_summary = sum(1 for line in f if json.loads(line).get("synthesis_summary"))
print(f"\nsynthesis_summary 있는 레코드: {has_summary:,}편 ({has_summary/total*100:.1f}%)")
