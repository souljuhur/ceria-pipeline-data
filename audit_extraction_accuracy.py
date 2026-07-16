"""
audit_extraction_accuracy.py — 추출 정확도 자동 감사 (재추출 후 상시 실행용)

31차 세션에서 수동으로 발견한 ce_precursor="CeO2" 오분류(12.3%)·PDF 텍스트 손상(36%)
버그를 재현하지 않기 위해, 매번 재추출(4_extract_targeted.py) 후 자동 실행되는
2단계 감사 도구.

Tier 1 [무료, 전수 검사] — 텍스트 존재 여부
  문자열 필드(ce_precursor, solvent, capping_agent 등) 값이 원문에 실제로
  등장하는지 정규화 후 대조. 전체 데이터셋에 대해 API 비용 없이 실행.

Tier 2 [GPT, 샘플 검사] — 의미 검증
  무작위 샘플 논문에 대해 GPT-4o-mini가 원문 vs 추출값을 대조, 실제로 틀렸거나
  (예: 최종 생성물명을 전구체로 오인) 원문에서 뒷받침되지 않는 필드를 리포트.

실행:
  python audit_extraction_accuracy.py                  # 기본: tier1 전수 + tier2 30편 샘플
  python audit_extraction_accuracy.py --n 50           # tier2 샘플 수 조정
  python audit_extraction_accuracy.py --skip-llm       # tier1만 (무료)
  python audit_extraction_accuracy.py --skip-heuristic # tier2만
  python audit_extraction_accuracy.py --seed 42        # 샘플 재현성 고정

출력:
  output/audit_tier1_text_presence.csv   — 필드별 "원문 미검출" 의심 행
  output/audit_tier2_llm_findings.csv    — GPT가 지적한 실제 오류 후보
  콘솔에 필드별/전체 요약 통계 출력
"""
import os
import re
import sys
import json
import time
import random
import argparse
import threading
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE = Path(r"d:\머신러닝 교육\ceria_pipeline_data")

# ── 4_extract_targeted.py 재사용 (필드 목록·경로·유틸 함수 공유) ─────────────────
_spec = importlib.util.spec_from_file_location(
    "m4", os.path.join(str(BASE), "4_extract_targeted.py"))
m4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m4)

CSV           = m4.CSV
TEXT          = m4.TEXT
TARGET_FIELDS = m4.TARGET_FIELDS
_safe_doi     = m4._safe_doi
_is_empty     = m4._is_empty

OUTPUT = BASE / "output"

# 원문 대조 가능한 문자열 필드만 (숫자 필드는 계산으로 도출되는 경우가 많아 제외)
STRING_FIELDS = [
    "synthesis_method", "ce_precursor", "solvent",
    "capping_agent", "chelating_agent", "atmosphere", "morphology",
]
# 값 자체가 범주형 버킷이라 원문 검색이 의미 없는 값들
_SKIP_VALUES = {"unknown", "other", "unidentified_method", "none", "null", "nan", ""}


# ── Tier 1: 텍스트 존재 여부 (무료, 전수) ─────────────────────────────────────
def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# 34차: ce_precursor 화학식↔화학명 동치 검사 (원문이 "cerium nitrate hexahydrate"처럼
# 산문 화학명으로 서술된 경우, GPT가 정확히 표준 화학식(Ce(NO3)3·6H2O)으로 변환해도
# 리터럴 문자열 대조로는 잡히지 않아 과탐(false positive) 발생 — 33차 감사에서 확인된
# 41.6% flag의 대부분이 이 패턴으로 추정됨 (표본 검토: 28건 중 11건 심층 확인, 10건이
# 이 유형의 과탐, 1건만 실제 의심 사례).
_ANION_ALIASES = [
    (re.compile(r"no3", re.IGNORECASE), ["nitrate"]),
    (re.compile(r"(?<!f)cl(?!o)", re.IGNORECASE), ["chloride"]),
    (re.compile(r"so4", re.IGNORECASE), ["sulfate", "sulphate"]),
    (re.compile(r"ch3coo|\boac\b|acetate", re.IGNORECASE), ["acetate"]),
    (re.compile(r"co3", re.IGNORECASE), ["carbonate"]),
    (re.compile(r"c2o4|oxalate", re.IGNORECASE), ["oxalate"]),
    (re.compile(r"\(oh\)", re.IGNORECASE), ["hydroxide"]),
    (re.compile(r"acac", re.IGNORECASE), ["acetylacetonate"]),
]
_AMMONIUM_CERIC_RE = re.compile(r"\(nh4\)2ce\(no3\)6|nh42ceno36", re.IGNORECASE)


def _ce_precursor_alt_match(raw_value: str, text_norm: str) -> bool:
    """화학명 산문 표현(예: cerium nitrate hexahydrate)이 원문에 있는지 확인.

    34차 2차 표본 검토에서 확인된 두 가지 보정:
    1. 논문들이 "cerium nitrate"까지는 쓰지만 "hexahydrate"는 생략하는 경우가 매우
       흔함(상업용 Ce(NO3)3의 표준 형태가 육수화물이라 다들 당연히 생략) — 수화물 명
       불일치를 실패 조건으로 쓰면 이런 정상 케이스까지 과탐 처리됨. 수화물은 검사하지
       않음(있으면 좋지만 없어도 통과).
    2. ammonium ceric nitrate ((NH4)2Ce(NO3)6)는 논문마다 어순이 제각각
       ("ammonium ceric nitrate", "cerium ammonium nitrate", "ceric ammonium
       nitrate" 등) — 특정 어순 문자열을 찾는 대신 "ammonium"과 "nitrate" 두
       단어가 모두 있는지만 확인.
    공통: "cerium/cerous/ceric" 언급 자체가 원문에 있는지 요구해 무관한 음이온 매칭
    (예: 다른 시약의 nitrate)으로 인한 오탐 확인을 방지.
    """
    if not any(k in text_norm for k in ("cerium", "cerous", "ceric")):
        return False  # 세륨 관련 언급 자체가 없음(다른 시약일 가능성) — 대체 검사 불가

    if _AMMONIUM_CERIC_RE.search(raw_value):
        return "ammonium" in text_norm and "nitrate" in text_norm

    for pat, names in _ANION_ALIASES:
        if pat.search(raw_value):
            return any(_normalize(n) in text_norm for n in names)
    return False  # 인식 가능한 음이온 패턴 없음 — 대체 검사 불가


def _value_found_in_text(value: str, text_norm: str, field: str = "") -> bool:
    """세미콜론으로 구분된 다중값은 개별 토큰 중 하나라도 원문에 있으면 통과."""
    for token in str(value).split(";"):
        token = token.strip()
        if not token or token.lower() in _SKIP_VALUES:
            continue
        v_norm = _normalize(token)
        if len(v_norm) < 3:
            continue  # 너무 짧은 값(예: "Ce")은 오탐 방지를 위해 스킵
        if v_norm in text_norm:
            continue
        if v_norm[:5] in text_norm:  # 어간 수준 완화 매칭 (spherical vs sphere 등)
            continue
        if field == "ce_precursor" and _ce_precursor_alt_match(token, text_norm):
            continue
        return False
    return True


def run_tier1(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[Tier 1] 텍스트 존재 여부 검사 (전수, 무료)")
    text_cache: dict = {}
    flags = []

    for doi, group in df.groupby("doi"):
        if pd.isna(doi):
            continue
        txt_path = TEXT / f"{_safe_doi(doi)}.txt"
        if doi not in text_cache:
            if txt_path.exists():
                try:
                    raw = txt_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    raw = ""
            else:
                raw = ""
            text_cache[doi] = _normalize(raw)
        text_norm = text_cache[doi]
        if not text_norm:
            continue  # 전문 없는 논문은 검사 불가 → 스킵

        for idx, row in group.iterrows():
            for field in STRING_FIELDS:
                val = row.get(field)
                if _is_empty(val):
                    continue
                if not _value_found_in_text(val, text_norm, field=field):
                    flags.append({
                        "doi": doi, "row_index": idx, "field": field,
                        "extracted_value": val,
                    })

    flags_df = pd.DataFrame(flags)
    n_checked_dois = sum(1 for v in text_cache.values() if v)
    print(f"  검사 대상: {n_checked_dois:,}편 (전문 보유)")
    print(f"  원문 미검출 의심: {len(flags_df):,}건")
    if not flags_df.empty:
        print("\n  필드별 미검출 건수:")
        for field, cnt in flags_df["field"].value_counts().items():
            total = df[field].apply(lambda v: not _is_empty(v)).sum()
            print(f"    {field:<20} {cnt:>5,} / {total:,}행 ({100*cnt/max(total,1):.1f}%)")
    return flags_df


# ── Tier 2: GPT 의미 검증 (샘플) ──────────────────────────────────────────────
_AUDIT_SYSTEM_PROMPT = """\
You are a fact-checker auditing automated data extraction from CeO2 (ceria) \
nanoparticle synthesis papers. You will be given the extracted JSON fields \
and a text snippet (Experimental/Results sections). Flag a field ONLY if you \
have SPECIFIC, QUOTABLE evidence that it is wrong — for example:
- the extracted "precursor" is clearly the final product name, not a starting reagent
- the text states a DIFFERENT number/word for that exact quantity (contradiction)
- the value is physically impossible (e.g. pH=20, negative temperature for aqueous synthesis)
- the value is clearly linked to a different synthesis/sample in the paper

DO NOT flag a field just because this snippet doesn't happen to restate it —
the full paper is longer than this snippet, and the number may be computed \
(e.g. concentration = mmol/volume) or stated elsewhere. Absence of confirmation \
is NOT evidence of error. Do not nitpick units, decimal rounding, or which \
specific reagent among several co-mentioned chemicals is "the" mineralizer/capping \
agent — extraction pipelines intentionally simplify these. Only report an issue \
when you would confidently tell a domain expert "this specific value is wrong, \
here is the exact text that contradicts it." If a field is null, ignore it. \
Return an empty issues list if you are not highly confident of a contradiction."""

_AUDIT_TOOL = {
    "type": "function",
    "function": {
        "name": "report_audit_issues",
        "description": "Report genuine extraction errors found by comparing extracted fields to source text.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["issues"],
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["field", "extracted_value", "verdict", "reason"],
                        "properties": {
                            "field": {"type": "string"},
                            "extracted_value": {"type": "string"},
                            "verdict": {
                                "type": "string",
                                "enum": ["wrong_value", "unsupported", "unit_error",
                                         "wrong_sample_linkage", "hallucinated"],
                            },
                            "reason": {"type": "string",
                                       "description": (
                                           "Must include a short direct quote or paraphrase of the "
                                           "SPECIFIC contradicting sentence from the text. "
                                           "If you cannot quote a contradiction, do not report this issue."
                                       )},
                        },
                    },
                },
            },
        },
    },
}


def _audit_one(doi: str, fields: dict, client) -> list:
    txt_path = TEXT / f"{_safe_doi(doi)}.txt"
    if not txt_path.exists():
        return []
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < 200:
        return []
    # 4_extract_targeted.py와 동일한 로직: Experimental/Results 섹션 우선 추출
    # (단순 앞부분 truncate 시 실험 조건이 뒤쪽에 있는 논문은 GPT가 "본문에 없음"으로
    #  오탐하기 쉬움 — 30차+ 세션 캘리브레이션에서 확인)
    snippet = m4._extract_snippet(text)
    payload = {k: v for k, v in fields.items() if not _is_empty(v)}
    if not payload:
        return []

    user_msg = (
        f"Extracted fields (JSON):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"Paper text:\n{snippet}"
    )
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _AUDIT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=800,
                tools=[_AUDIT_TOOL],
                tool_choice={"type": "function", "function": {"name": "report_audit_issues"}},
            )
            tool_calls = resp.choices[0].message.tool_calls
            if not tool_calls:
                return []
            result = json.loads(tool_calls[0].function.arguments)
            issues = result.get("issues", [])
            for issue in issues:
                issue["doi"] = doi
            return issues
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "limit" in err:
                time.sleep(2 ** attempt)
            else:
                return []
    return []


def run_tier2(df: pd.DataFrame, n: int, seed, workers: int) -> pd.DataFrame:
    print(f"\n[Tier 2] GPT 의미 검증 (무작위 {n}편 샘플)")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("  OPENAI_API_KEY 없음 — tier2 스킵")
        return pd.DataFrame()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except ImportError:
        print("  pip install openai 필요 — tier2 스킵")
        return pd.DataFrame()

    dois_with_text = [
        d for d in df["doi"].dropna().unique()
        if (TEXT / f"{_safe_doi(d)}.txt").exists()
    ]
    if not dois_with_text:
        print("  전문 보유 논문 없음 — tier2 스킵")
        return pd.DataFrame()

    rng = random.Random(seed)
    sample_dois = rng.sample(dois_with_text, min(n, len(dois_with_text)))
    print(f"  대상: {len(sample_dois)}편  |  예상 비용: ~${len(sample_dois) * 0.0015:.3f}")

    # doi → 대표 필드값 (첫 샘플 행 기준; 샘플-레벨 CSV라 논문당 여러 행 존재 가능)
    doi_fields = {}
    for doi in sample_dois:
        row = df[df["doi"] == doi].iloc[0]
        doi_fields[doi] = {f: row.get(f) for f in TARGET_FIELDS}

    all_issues = []
    print_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_audit_one, doi, doi_fields[doi], client): doi
            for doi in sample_dois
        }
        done = 0
        for future in as_completed(futures):
            doi = futures[future]
            issues = future.result()
            done += 1
            if issues:
                all_issues.extend(issues)
                with print_lock:
                    print(f"  [{done}/{len(sample_dois)}] {doi[:45]:<45} issue {len(issues)}건")
            elif done % 10 == 0:
                with print_lock:
                    print(f"  [{done}/{len(sample_dois)}] 진행 중...")

    issues_df = pd.DataFrame(all_issues)
    n_clean = len(sample_dois) - issues_df["doi"].nunique() if not issues_df.empty else len(sample_dois)
    print(f"\n  검사 완료: {len(sample_dois)}편")
    print(f"  이상 없음: {n_clean}편  |  이슈 발견: {len(sample_dois) - n_clean}편 ({len(issues_df)}건)")
    if not issues_df.empty:
        print("\n  필드별 이슈 건수:")
        for field, cnt in issues_df["field"].value_counts().items():
            print(f"    {field:<20} {cnt:>3}건")
        print("\n  ⚠ GPT 판정은 참고용입니다 — gpt-4o-mini가 가끔 스니펫에 재확인되지"
              "않는다는 이유만으로 과탐지하거나 자기모순적 사유를 대기도 합니다. "
              "CSV의 reason 열에 인용된 원문 근거를 사람이 확인한 뒤 반영하세요.")
    return issues_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30, help="tier2 GPT 샘플 논문 수 (기본 30)")
    parser.add_argument("--seed", type=int, default=None, help="샘플 시드 (재현성용, 기본 매번 랜덤)")
    parser.add_argument("--workers", type=int, default=15)
    parser.add_argument("--skip-llm", action="store_true", help="tier1만 실행 (무료)")
    parser.add_argument("--skip-heuristic", action="store_true", help="tier2만 실행")
    args = parser.parse_args()

    if not CSV.exists():
        print(f"CSV 없음: {CSV}"); sys.exit(1)
    df = pd.read_csv(CSV, dtype=str, low_memory=False)
    print(f"CSV 로드: {len(df):,}행 / {df['doi'].nunique():,}편")

    print("\n" + "=" * 60)
    print("  추출 정확도 자동 감사")
    print("=" * 60)

    tier1_df = pd.DataFrame()
    tier2_df = pd.DataFrame()

    if not args.skip_heuristic:
        tier1_df = run_tier1(df)
        if not tier1_df.empty:
            path = OUTPUT / "audit_tier1_text_presence.csv"
            tier1_df.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"\n  저장: {path}")

    if not args.skip_llm:
        tier2_df = run_tier2(df, n=args.n, seed=args.seed, workers=args.workers)
        if not tier2_df.empty:
            path = OUTPUT / "audit_tier2_llm_findings.csv"
            tier2_df.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"  저장: {path}")

    print("\n" + "=" * 60)
    print("완료.")
    if not tier1_df.empty or not tier2_df.empty:
        print("  → 상위 빈발 필드/패턴을 검토해 프롬프트·후처리 규칙 개선 검토 권장")
    print("=" * 60)


if __name__ == "__main__":
    main()
