"""
0_merge_new.py — 신규 수집 논문(0_collect.py 출력)을 기존 Excel DB에 병합

처리 흐름:
  1. 기존 ceria_synthesis_database.xlsx 로드
  2. 최신 collected_papers_*.jsonl 로드 (--jsonl 로 지정 가능)
  3. DOI 기준 중복 제거 → 신규 행만 추가
  4. abstract / pdf_url / oa_url 컬럼 추가 (없으면)
  5. ceria_synthesis_database.xlsx 덮어쓰기 저장

사용법:
  python 0_merge_new.py                        # 자동: output/ 최신 JSONL (전체 추가)
  python 0_merge_new.py --synthesis-only       # tagged_methods 있는 논문만 추가 (권장)
  python 0_merge_new.py --jsonl output/collected_papers_20260610_0826.jsonl
  python 0_merge_new.py --dry-run              # 통계만 출력, 저장 없음
  python 0_merge_new.py --synthesis-only --dry-run  # 필터 적용 후 건수 확인
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT    = os.path.join(BASE_DIR, "output")
XLSX_PATH = os.path.join(OUTPUT, "ceria_synthesis_database.xlsx")

# 동료심사 보고서·정정·철회 등 비연구논문 제목 필터 (0_collect.py와 동기화)
_JUNK_RE = re.compile(
    r"^("
    r"review for\b|comment on\b|reply to\b|response to\b"
    r"|correction\b|erratum\b|retraction\b|corrigendum\b"
    r"|letter to\b|addendum\b|discussion of\b"
    r")",
    re.IGNORECASE,
)

def _is_junk_title(title) -> bool:
    if not title or not isinstance(title, str):
        return False
    return bool(_JUNK_RE.match(title.strip()))


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def _load_xlsx(path):
    """요약행 자동 감지 후 헤더 행 결정."""
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)


def _norm_doi(doi):
    if not doi or (isinstance(doi, float) and np.isnan(doi)):
        return ""
    d = str(doi).lower().strip()
    if d.startswith("https://doi.org/"):
        d = d[len("https://doi.org/"):]
    return d


def _latest_jsonl():
    pattern = os.path.join(OUTPUT, "collected_papers_*.jsonl")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    return files[-1]  # 가장 최신 (이름 정렬 = 날짜 정렬)


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl",           default=None,  help="JSONL 경로 (기본: 최신 파일)")
    parser.add_argument("--dry-run",         action="store_true", help="저장 없이 통계만 출력")
    parser.add_argument("--synthesis-only",  action="store_true",
                        help="tagged_methods 또는 tagged_morphologies 있는 논문만 추가")
    args = parser.parse_args()

    # ── 1. JSONL 경로 결정 ─────────────────────────────────────────────────
    jsonl_path = args.jsonl or _latest_jsonl()
    if not jsonl_path or not os.path.exists(jsonl_path):
        print("오류: JSONL 파일 없음. 0_collect.py 먼저 실행하세요.")
        sys.exit(1)
    print(f"JSONL: {os.path.basename(jsonl_path)}")

    # ── 2. 기존 Excel 로드 ─────────────────────────────────────────────────
    if not os.path.exists(XLSX_PATH):
        print(f"오류: {XLSX_PATH} 없음")
        sys.exit(1)
    df_old = _load_xlsx(XLSX_PATH)
    df_old.columns = [str(c).strip() for c in df_old.columns]
    print(f"기존 DB: {len(df_old):,}편  열: {len(df_old.columns)}개")

    # 기존 DOI 집합 (정규화)
    existing_dois = set()
    if "doi" in df_old.columns:
        existing_dois = {_norm_doi(d) for d in df_old["doi"].dropna()} - {""}
    print(f"  기존 DOI: {len(existing_dois):,}개")

    # ── 3. JSONL 로드 ──────────────────────────────────────────────────────
    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    print(f"수집 JSONL: {len(records):,}건")

    # ── 4. 신규 DOI 필터링 ─────────────────────────────────────────────────
    new_recs = []
    no_doi   = 0
    for rec in records:
        doi = _norm_doi(rec.get("doi", ""))
        if not doi:
            no_doi += 1
            continue
        if doi not in existing_dois:
            new_recs.append(rec)

    print(f"  DOI 없음: {no_doi}건 (스킵)")
    print(f"  기존 중복: {len(records) - no_doi - len(new_recs):,}건")
    print(f"  신규 추가 대상: {len(new_recs):,}건")

    # ── 비연구논문 제목 필터 (항상 적용) ──────────────────────────────────────
    before_junk = len(new_recs)
    new_recs = [r for r in new_recs if not _is_junk_title(r.get("title", ""))]
    if before_junk - len(new_recs):
        print(f"  비연구논문(동료심사·정정·철회) 제외: {before_junk - len(new_recs)}건")

    # ── 합성 논문 필터 ────────────────────────────────────────────────────
    if args.synthesis_only:
        before_filter = len(new_recs)
        new_recs = [r for r in new_recs
                    if r.get("tagged_methods") or r.get("tagged_morphologies")]
        print(f"  --synthesis-only 필터: {before_filter:,} → {len(new_recs):,}건 "
              f"({before_filter - len(new_recs):,}건 제외)")

    if not new_recs:
        print("\n신규 논문 없음 — 종료")
        return

    if args.dry_run:
        print("\n[dry-run] 저장 없이 종료. --dry-run 제거 후 재실행하면 병합됩니다.")
        _show_sample(new_recs)
        return

    # ── 5. 신규 행 DataFrame 생성 ──────────────────────────────────────────
    # 기존 paper_id 최댓값 이어서 부여
    existing_cols = list(df_old.columns)
    if "paper_id" in df_old.columns:
        try:
            max_id = int(pd.to_numeric(df_old["paper_id"], errors="coerce").max())
        except Exception:
            max_id = len(df_old)
    else:
        max_id = len(df_old)

    rows = []
    for i, rec in enumerate(new_recs, 1):
        doi       = _norm_doi(rec.get("doi", ""))
        tags_m    = rec.get("tagged_methods", [])
        tags_mo   = rec.get("tagged_morphologies", [])

        row = {col: np.nan for col in existing_cols}
        row["paper_id"]          = max_id + i
        row["doi"]               = doi
        row["title"]             = rec.get("title") or np.nan
        row["year"]              = rec.get("year")  or np.nan
        row["journal"]           = rec.get("journal") or np.nan
        row["citation_count"]    = rec.get("cited_by_count") or np.nan
        row["is_oa"]             = rec.get("is_oa", False)
        row["source_api"]        = "openalex_v2"
        row["tagged_methods"]    = "|".join(tags_m)   if tags_m  else np.nan
        row["tagged_morphologies"] = "|".join(tags_mo) if tags_mo else np.nan
        rows.append(row)

    df_new = pd.DataFrame(rows, columns=existing_cols)

    # ── 6. abstract / pdf_url / oa_url 컬럼 추가 (없는 경우) ──────────────
    extra_cols = []
    for col, jsonl_key in [("abstract", "abstract"),
                            ("pdf_url",  "pdf_url"),
                            ("oa_url",   "oa_url")]:
        if col not in df_old.columns:
            df_old[col] = np.nan
            df_new[col] = [rec.get(jsonl_key) or np.nan for rec in new_recs]
            extra_cols.append(col)
        else:
            df_new[col] = [rec.get(jsonl_key) or np.nan for rec in new_recs]

    if extra_cols:
        print(f"\n  신규 컬럼 추가: {extra_cols}")

    # ── 7. 병합 후 저장 ────────────────────────────────────────────────────
    df_merged = pd.concat([df_old, df_new], ignore_index=True)
    print(f"\n병합 결과: {len(df_old):,} + {len(df_new):,} = {len(df_merged):,}편")
    print(f"  열 수: {len(df_merged.columns)}개")

    # 백업
    backup = XLSX_PATH.replace(".xlsx", "_backup_before_merge.xlsx")
    if not os.path.exists(backup):
        df_old.to_excel(backup, index=False)
        print(f"  백업 저장: {os.path.basename(backup)}")

    df_merged.to_excel(XLSX_PATH, index=False)
    print(f"  저장 완료: {XLSX_PATH}")

    # ── 8. 통계 요약 ───────────────────────────────────────────────────────
    print("\n[통계]")
    oa_new = sum(1 for r in new_recs if r.get("is_oa"))
    pdf_new = sum(1 for r in new_recs if r.get("pdf_url"))
    print(f"  신규 OA: {oa_new}/{len(new_recs)} ({oa_new/len(new_recs)*100:.1f}%)")
    print(f"  신규 PDF URL: {pdf_new}/{len(new_recs)} ({pdf_new/len(new_recs)*100:.1f}%)")

    from collections import Counter
    method_cnt = Counter()
    morph_cnt  = Counter()
    for rec in new_recs:
        for t in rec.get("tagged_methods", []):
            method_cnt[t] += 1
        for t in rec.get("tagged_morphologies", []):
            morph_cnt[t] += 1
    if method_cnt:
        print("  신규 합성법 태그:")
        for k, v in method_cnt.most_common(6):
            print(f"    {k:<20} {v:>4}편")
    if morph_cnt:
        print("  신규 형상 태그:")
        for k, v in morph_cnt.most_common(5):
            print(f"    {k:<20} {v:>4}편")

    print("\n다음 단계:")
    print("  python 1_download.py   # 신규 OA PDF 다운로드")
    print("  python 2_extract.py    # GPT 합성조건 추출")


def _show_sample(recs, n=5):
    print(f"\n[샘플 {min(n, len(recs))}건]")
    for rec in recs[:n]:
        tags = "|".join(rec.get("tagged_methods", []))
        print(f"  {rec.get('year','?')} | {(rec.get('title') or '')[:60]} | {tags}")


if __name__ == "__main__":
    main()
