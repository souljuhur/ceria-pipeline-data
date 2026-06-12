"""
0_collect.py — [Stage 0] OpenAlex 다층 쿼리 문헌 수집

기존 pipeline.py 대비 개선 사항:
  - 다층 쿼리 합집합 (코어+합성법별+형상별+도핑별 등 40개 쿼리)
  - 커서 페이지네이션 (offset 방식 대비 속도/안정성 향상)
  - abstract_inverted_index → 평문 복원 (초록 저장)
  - OA 분기 필드 보존 (is_oa, oa_status, oa_url, pdf_url)
  - Triage 태깅 7종 (tagged_methods/morphologies/mineralizer/additives/solvent/assist/dopant)
  - OpenAlex ID + DOI 이중 중복 제거
  - 지수 백오프 재시도 (429/5xx 대응)
  - 출력 이원화: papers.jsonl (2단계 추출 입력) + papers_summary.csv (사람 검토용)
  - polite pool 헤더 (mailto 포함)

실행:
  conda activate test
  python 0_collect.py                # 전체 수집
  python 0_collect.py --dry-run      # 쿼리 목록·설정만 확인
  python 0_collect.py --limit 100    # 쿼리당 최대 100건
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime

import requests

# ── 설정 ──────────────────────────────────────────────────────────────────────
EMAIL        = "juhur@soulbrain.co.kr"   # polite pool용 (OpenAlex 권장)
FROM_YEAR    = 1990
TO_YEAR      = 2026
MAX_PER_QUERY = 500    # 쿼리당 최대 수집 건수
PER_PAGE      = 200    # OpenAlex 최대 200
SLEEP_SEC     = 0.35   # 쿼리 간 대기 (polite)
MAX_RETRIES   = 4
TIMEOUT       = 30

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
BASE_URL   = "https://api.openalex.org/works"

# ── 검색 쿼리 (합집합) ─────────────────────────────────────────────────────────
QUERIES = [
    # ── 코어 ──────────────────────────────────────────────────────────────────
    "ceria nanoparticle synthesis",
    "CeO2 nanoparticle synthesis",
    "cerium oxide nanoparticle synthesis",
    "nanoceria synthesis",
    # ── 합성법별 ──────────────────────────────────────────────────────────────
    "ceria hydrothermal synthesis",
    "CeO2 solvothermal synthesis",
    "cerium oxide precipitation synthesis nanoparticle",
    "ceria co-precipitation synthesis",
    "ceria thermal decomposition nanocrystal",
    "CeO2 sol-gel nanoparticle",
    "cerium oxide combustion synthesis nanoparticle",
    "ceria microwave synthesis nanoparticle",
    "cerium oxide sonochemical nanoparticle",
    "ceria spray pyrolysis nanoparticle",
    "cerium oxide mechanochemical synthesis",
    # ── 형상별 ────────────────────────────────────────────────────────────────
    "ceria nanocube facet synthesis",
    "CeO2 nanorod synthesis",
    "ceria nanopolyhedra synthesis",
    "CeO2 octahedra nanocrystal",
    "ceria nanosphere synthesis",
    "CeO2 nanoflower hierarchical",
    "ceria nanoplate synthesis",
    "CeO2 nanotube synthesis",
    # ── 도핑 ──────────────────────────────────────────────────────────────────
    "La doped ceria nanoparticle",
    "Eu doped ceria nanoparticle",
    "Gd doped CeO2 nanoparticle",
    "Nd doped cerium oxide nanoparticle",
    "Sm doped ceria synthesis",
    "Y doped CeO2 nanoparticle",
    # ── 응용·조건별 ───────────────────────────────────────────────────────────
    "ceria CMP abrasive slurry nanoparticle",
    "CeO2 oxygen storage capacity catalyst",
    "ceria antioxidant nanoparticle biomedical",
    # ── 전구체·음이온별 ───────────────────────────────────────────────────────
    "cerium sulfate ceria nanoparticle morphology",
    "cerium chloride ceria nanorod synthesis",
    "ceric ammonium nitrate ceria nanocube",
    # ── 첨가제·조건 조합 ──────────────────────────────────────────────────────
    "urea ceria nanocube hydrothermal",
    "CTAB ceria morphology nanoparticle",
    "PVP ceria nanoparticle size",
    "polyol ethylene glycol ceria nanoparticle",
    "H2O2 oxidation nanoceria size",
    "calcination temperature ceria crystallite size",
]

# ── Triage 태깅 사전 ───────────────────────────────────────────────────────────
_METHOD_KW = {
    "hydrothermal":          ["hydrothermal"],
    "solvothermal":          ["solvothermal"],
    "sol-gel":               ["sol-gel", "sol gel", "solgel", "pechini"],
    "co-precipitation":      ["co-precipitation", "coprecipitation"],
    "precipitation":         ["precipitation"],
    "combustion":            ["combustion", "auto-combustion", "autoignition"],
    "microwave":             ["microwave"],
    "thermal_decomposition": ["thermal decomposition", "thermolysis", "pyrolysis"],
    "spray_pyrolysis":       ["spray pyrolysis", "flame spray"],
    "sonochemical":          ["sonochemical", "ultrasonic", "ultrasound", "sonication"],
    "mechanochemical":       ["mechanochemical", "ball mill"],
}

_MORPH_KW = {
    "cube":      ["nanocube", "nano-cube", "cubic"],
    "rod":       ["nanorod", "nano-rod", "nanowire", "nano-wire"],
    "sphere":    ["nanosphere", "spherical nanoparticle"],
    "polyhedra": ["polyhedra", "polyhedron", "octahedra", "truncated"],
    "flower":    ["nanoflower", "flower-like", "hierarchical"],
    "plate":     ["nanoplate", "nanosheet", "platelet"],
    "tube":      ["nanotube", "tubular"],
}

_MINERALIZER_KW = {
    "NaOH":     ["naoh", "sodium hydroxide"],
    "KOH":      ["koh", "potassium hydroxide"],
    "ammonia":  ["ammonia", "ammonium hydroxide", "nh4oh", " nh3 "],
    "urea":     ["urea"],
    "HMTA":     ["hexamethylenetetramine", "hmta", "hexamine"],
    "TMAH":     ["tmah", "tetramethylammonium hydroxide"],
}

_ADDITIVE_KW = {
    "CTAB":      ["ctab", "cetyltrimethylammonium"],
    "SDS":       ["sds", "sodium dodecyl sulfate", "dodecyl sulphate"],
    "PVP":       ["pvp", "polyvinylpyrrolidone"],
    "PEG":       ["peg", "polyethylene glycol"],
    "citrate":   ["citrate", "citric acid"],
    "oleic_acid":["oleic acid", "oleate"],
    "oleylamine":["oleylamine"],
}

_SOLVENT_KW = {
    "water":           ["aqueous", "deionized water", "distilled water"],
    "ethylene_glycol": ["ethylene glycol", "polyol"],
    "ethanol":         ["ethanol"],
    "methanol":        ["methanol"],
    "isopropanol":     ["isopropanol", "2-propanol"],
    "DMF":             ["dimethylformamide", " dmf "],
}

_ASSIST_KW = {
    "H2O2":         ["h2o2", "hydrogen peroxide"],
    "sonochemical": ["sonochem", "ultrasonic", "ultrasound"],
    "microwave":    ["microwave"],
    "calcination":  ["calcin", "anneal"],
}

_DOPANT_KW = {
    "La": ["la-doped", "lanthanum doped", "la/ceo2", "la-ceo2"],
    "Nd": ["nd-doped", "neodymium doped"],
    "Pr": ["pr-doped", "praseodymium doped"],
    "Sm": ["sm-doped", "samarium doped"],
    "Y":  ["y-doped", "yttrium doped"],
    "Gd": ["gd-doped", "gadolinium doped"],
    "Eu": ["eu-doped", "europium doped"],
    "Co": ["co-doped ceria", "cobalt doped ceria"],
    "Zr": ["zr-doped ceria", "zirconia ceria", "ceria-zirconia"],
}


# ── 유틸리티 ──────────────────────────────────────────────────────────────────
def _tag(text, kw_map):
    low = text.lower()
    return [label for label, variants in kw_map.items()
            if any(v in low for v in variants)]


def _reconstruct_abstract(inv):
    """abstract_inverted_index → 평문."""
    if not inv:
        return ""
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    pos.sort()
    return " ".join(w for _, w in pos)


def _request(params):
    headers = {"User-Agent": f"ceria-collect/2.0 (mailto:{EMAIL})"}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(BASE_URL, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503):
                wait = 2 ** attempt
                print(f"    HTTP {r.status_code} → {wait}s 대기", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            wait = 2 ** attempt
            print(f"    요청 오류({e}) → {wait}s 재시도", file=sys.stderr)
            time.sleep(wait)
    return None


def _search_query(query, max_per_query):
    """커서 페이지네이션 단일 쿼리."""
    collected, cursor = [], "*"
    meta_count = None
    while cursor and len(collected) < max_per_query:
        params = {
            "search":  query,
            "filter":  (f"from_publication_date:{FROM_YEAR}-01-01,"
                        f"to_publication_date:{TO_YEAR}-12-31,"
                        f"type:article"),
            "select":  ("id,doi,title,publication_year,primary_location,"
                        "open_access,best_oa_location,"
                        "abstract_inverted_index,cited_by_count"),
            "per-page": PER_PAGE,
            "cursor":   cursor,
            "mailto":   EMAIL,
        }
        data = _request(params)
        if not data:
            break
        meta = data.get("meta") or {}
        if meta_count is None:
            meta_count = meta.get("count")
        results = data.get("results") or []
        if not results:
            break
        collected.extend(results)
        cursor = meta.get("next_cursor")
        time.sleep(SLEEP_SEC)
    return collected[:max_per_query], meta_count


# 동료심사 보고서·정정·철회 등 비연구논문 제목 패턴 (소문자 접두어)
# 동료심사 보고서·정정·철회 등 비연구논문 제목 패턴
_JUNK_TITLE_RE = re.compile(
    r"^("
    r"review for\b"         # 동료심사 보고서
    r"|comment on\b"        # 코멘트 논문
    r"|reply to\b"          # 저자 답변
    r"|response to\b"       # 저자 응답
    r"|correction\b"        # 오류 정정 (Correction to: / Correction: / Correction of)
    r"|erratum\b"           # 오탈자 정정
    r"|retraction\b"        # 철회 공고
    r"|corrigendum\b"       # 공식 정정
    r"|letter to\b"         # 편집자에게 편지
    r"|addendum\b"          # 부록 공지
    r"|discussion of\b"     # 토론
    r")",
    re.IGNORECASE,
)


def _is_junk_title(title: str) -> bool:
    """동료심사 보고서·정정·철회 등 비연구논문 제목이면 True."""
    return bool(_JUNK_TITLE_RE.match(title.strip()))


def _parse_work(w):
    abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
    title    = w.get("title") or ""
    haystack = f"{title} {abstract}"

    oa      = w.get("open_access") or {}
    best_oa = w.get("best_oa_location") or {}
    source  = ((w.get("primary_location") or {}).get("source") or {})

    doi = w.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    doi = doi.lower().strip()

    return {
        "openalex_id":        w.get("id"),
        "doi":                doi,
        "title":              title,
        "year":               w.get("publication_year"),
        "journal":            source.get("display_name"),
        "abstract":           abstract,
        "is_oa":              oa.get("is_oa", False),
        "oa_status":          oa.get("oa_status"),
        "oa_url":             oa.get("oa_url"),
        "pdf_url":            best_oa.get("pdf_url"),
        "cited_by_count":     w.get("cited_by_count"),
        "tagged_methods":     _tag(haystack, _METHOD_KW),
        "tagged_morphologies":_tag(haystack, _MORPH_KW),
        "tagged_mineralizer": _tag(haystack, _MINERALIZER_KW),
        "tagged_additives":   _tag(haystack, _ADDITIVE_KW),
        "tagged_solvent":     _tag(haystack, _SOLVENT_KW),
        "tagged_assist":      _tag(haystack, _ASSIST_KW),
        "tagged_dopant":      _tag(haystack, _DOPANT_KW),
    }


def collect(max_per_query):
    by_id, seen_dois = {}, set()

    junk_count = 0
    for qi, q in enumerate(QUERIES, 1):
        print(f"[{qi:02d}/{len(QUERIES)}] {q!r}")
        works, meta_count = _search_query(q, max_per_query)
        before = len(by_id)
        for w in works:
            rec = _parse_work(w)
            wid, doi = rec["openalex_id"], rec["doi"]
            if not wid:
                continue
            if wid in by_id:
                continue
            if doi and doi in seen_dois:
                continue
            if _is_junk_title(rec.get("title") or ""):
                junk_count += 1
                continue
            by_id[wid] = rec
            if doi:
                seen_dois.add(doi)
        new = len(by_id) - before
        pct = f"{meta_count:,}" if meta_count is not None else "?"
        print(f"    수집 {len(works):>4}건  신규 {new:>4}건  누적 {len(by_id):,}건  "
              f"(검색 총량 {pct})")

    if junk_count:
        print(f"\n  [필터] 비연구논문(동료심사 보고서·정정·철회 등) 제외: {junk_count}건")
    records = list(by_id.values())
    records.sort(key=lambda r: r.get("cited_by_count") or 0, reverse=True)
    return records


def _report(records):
    n = len(records)
    oa_n   = sum(1 for r in records if r["is_oa"])
    pdf_n  = sum(1 for r in records if r.get("pdf_url"))
    abs_n  = sum(1 for r in records if r.get("abstract"))

    print(f"\n{'='*60}")
    print(f"수집 완료: {n:,}건")
    print(f"  OA:        {oa_n:>5} ({oa_n/n*100:4.1f}%)")
    print(f"  PDF URL:   {pdf_n:>5} ({pdf_n/n*100:4.1f}%)")
    print(f"  초록 보유: {abs_n:>5} ({abs_n/n*100:4.1f}%)")

    for label, kw_key in [("합성법", "tagged_methods"),
                           ("형상",   "tagged_morphologies"),
                           ("도판트", "tagged_dopant")]:
        cnt = Counter()
        for r in records:
            for t in r[kw_key]:
                cnt[t] += 1
        if cnt:
            top = cnt.most_common(8)
            print(f"\n  [{label} 태그]")
            for k, v in top:
                print(f"    {k:<25} {v:>5}편")

    year_cnt = Counter(r["year"] for r in records if r.get("year"))
    if year_cnt:
        recent = sorted(year_cnt.items())[-5:]
        print(f"\n  [최근 5년 연도별]")
        for yr, cnt_v in recent:
            print(f"    {yr}: {cnt_v:>4}편")


def _save(records, tag):
    jsonl_path = os.path.join(OUTPUT_DIR, f"collected_papers_{tag}.jsonl")
    csv_path   = os.path.join(OUTPUT_DIR, f"collected_papers_{tag}_summary.csv")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\nJSONL 저장: {jsonl_path}")

    csv_fields = ["doi", "title", "year", "journal", "is_oa", "oa_status",
                  "pdf_url", "cited_by_count",
                  "tagged_methods", "tagged_morphologies", "tagged_mineralizer",
                  "tagged_additives", "tagged_solvent", "tagged_assist", "tagged_dopant"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            row = {k: ("|".join(v) if isinstance(v, list) else v)
                   for k, v in rec.items() if k in csv_fields}
            writer.writerow(row)
    print(f"CSV 저장:  {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="OpenAlex 다층 쿼리 문헌 수집")
    parser.add_argument("--dry-run", action="store_true", help="쿼리 목록·설정만 출력")
    parser.add_argument("--limit",   type=int, default=MAX_PER_QUERY,
                        help=f"쿼리당 최대 건수 (기본 {MAX_PER_QUERY})")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[dry-run] 쿼리 {len(QUERIES)}개  기간 {FROM_YEAR}-{TO_YEAR}  "
              f"쿼리당 최대 {args.limit}건")
        for i, q in enumerate(QUERIES, 1):
            print(f"  {i:02d}. {q}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tag = datetime.now().strftime("%Y%m%d_%H%M")

    print(f"OpenAlex 수집 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print(f"  기간: {FROM_YEAR}~{TO_YEAR}  쿼리: {len(QUERIES)}개  "
          f"최대/쿼리: {args.limit}  SLEEP: {SLEEP_SEC}s")
    print()

    records = collect(max_per_query=args.limit)
    _report(records)
    _save(records, tag)

    print(f"\n완료. 이전 DB와 비교해 신규 DOI를 pipeline.py(Excel)에 추가하세요.")
    print(f"  기존 DB: output/ceria_synthesis_database.xlsx")


if __name__ == "__main__":
    main()
