"""
vision 캐시에서 '처리했지만 데이터 못 찾은' DOI를 제거.
→ run_table_extraction.py --vision 재실행 시 개선된 코드로 재시도.

CMD (프로젝트 루트에서 실행):
  python utils/reset_vision_cache.py
"""
import json, os

CACHE = r"d:\머신러닝 교육\ceria_pipeline_data\output\table_extraction_vision_cache.json"

with open(CACHE, encoding="utf-8") as f:
    cache = json.load(f)

done    = set(cache.get("done_dois", []))
results = set(cache.get("results", {}).keys())
failed  = done - results

print(f"전체 done_dois   : {len(done):,}편")
print(f"결과 있는 DOI    : {len(results):,}편")
print(f"실패(재시도 대상): {len(failed):,}편")

# 실패 DOI만 done_dois에서 제거 (성공한 것은 유지)
cache["done_dois"] = list(results)

with open(CACHE, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)

print(f"\n캐시 정리 완료 → 잔여 done_dois: {len(results):,}편")
print("이제 실행하세요: python run_table_extraction.py --vision")
