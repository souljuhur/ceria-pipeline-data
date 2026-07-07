"""
run_weekly.py — 주간 자동 파이프라인
  1. OpenAlex에서 지난 7일 신규 CeO2 논문 수집
  2. 기존 DB와 중복 제거 후 Excel에 추가
  3. OA PDF 다운로드 + 텍스트 추출
  4. 후처리 파이프라인 전체 실행
  5. ML 모델 업데이트

매주 월요일 09:00 Task Scheduler에 의해 자동 실행.
수동 실행: python run_weekly.py
"""
import os, sys, json, logging, time, subprocess
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd

try:
    import pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

BASE   = Path(r"d:\머신러닝 교육\ceria_pipeline_data")
OUTPUT = BASE / "output"
XLSX   = OUTPUT / "ceria_synthesis_database.xlsx"
STATE  = OUTPUT / "weekly_state.json"
LOGS   = OUTPUT / "logs"
PDF    = BASE / "pdf"
TEXT   = BASE / "text"
PYTHON = sys.executable

# ── 로깅 ────────────────────────────────────────────────────────────────────
LOGS.mkdir(parents=True, exist_ok=True)
_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_path = LOGS / f"weekly_{_ts}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        logging.FileHandler(_log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── OpenAlex 검색 쿼리 ───────────────────────────────────────────────────────
OPENALEX_QUERIES = [
    "ceria nanoparticle synthesis",
    "cerium oxide nanoparticle synthesis",
    "CeO2 nanoparticle preparation",
    "ceria hydrothermal synthesis",
    "ceria sol-gel synthesis",
]
OPENALEX_SELECT = (
    "id,doi,title,authorships,publication_year,"
    "primary_location,abstract_inverted_index,cited_by_count,open_access"
)

# ── 상태 관리 ────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"last_run": None, "total_added": 0, "runs": []}

def save_state(state: dict):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 기존 DOI 목록 ────────────────────────────────────────────────────────────
def get_existing_dois() -> set:
    if not XLSX.exists():
        return set()
    df = pd.read_excel(XLSX, sheet_name=0, usecols=["doi"])
    return set(df["doi"].dropna().astype(str).str.strip().str.lower())

# ── OpenAlex 수집 ────────────────────────────────────────────────────────────
def _decode_abstract(inv_idx: dict) -> str:
    if not inv_idx:
        return ""
    pos_word = {}
    for word, positions in inv_idx.items():
        for p in positions:
            pos_word[p] = word
    return " ".join(pos_word[p] for p in sorted(pos_word))

def fetch_openalex(query: str, from_date: str, max_results: int = 500) -> list:
    url = "https://api.openalex.org/works"
    params = {
        "filter": f"title.search:{query},from_publication_date:{from_date},type:article",
        "per-page": 100,
        "cursor": "*",
        "select": OPENALEX_SELECT,
    }
    papers = []
    while len(papers) < max_results:
        try:
            r = requests.get(url, params=params, timeout=30,
                             headers={"User-Agent": "CeO2-pipeline/2.0 (research)"})
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning(f"    OpenAlex 요청 실패: {e}")
            break
        batch = data.get("results", [])
        if not batch:
            break
        papers.extend(batch)
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
        time.sleep(0.15)
    return papers

def paper_to_row(p: dict) -> dict | None:
    doi = (p.get("doi") or "").replace("https://doi.org/", "").strip().lower()
    if not doi:
        return None
    loc   = p.get("primary_location") or {}
    src   = loc.get("source") or {}
    oa    = p.get("open_access") or {}
    return {
        "doi":            doi,
        "title":          p.get("title", ""),
        "year":           p.get("publication_year"),
        "journal":        src.get("display_name", ""),
        "authors":        "; ".join(
            (a.get("author") or {}).get("display_name", "")
            for a in (p.get("authorships") or [])[:5]
        ),
        "abstract":       _decode_abstract(p.get("abstract_inverted_index")),
        "citation_count": p.get("cited_by_count", 0),
        "is_oa":          bool(oa.get("is_oa")),
        "open_access_url": oa.get("oa_url") or "",
        "source_api":     "OpenAlex",
    }

# ── PDF 다운로드 ─────────────────────────────────────────────────────────────
def _safe_doi_filename(doi: str) -> str:
    return doi.replace("/", "_").replace(":", "_")

def download_pdf(doi: str, url: str) -> bool:
    if not url:
        return False
    path = PDF / f"{_safe_doi_filename(doi)}.pdf"
    if path.exists():
        return True
    try:
        r = requests.get(url, timeout=30,
                         headers={"User-Agent": "CeO2-pipeline/2.0"})
        if r.status_code == 200 and b"%PDF" in r.content[:1024]:
            path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False

# ── 텍스트 추출 ──────────────────────────────────────────────────────────────
def extract_text(doi: str):
    safe = _safe_doi_filename(doi)
    pdf_p = PDF / f"{safe}.pdf"
    txt_p = TEXT / f"{safe}.txt"
    if txt_p.exists() or not pdf_p.exists():
        return
    if not _HAS_PDFPLUMBER:
        log.warning("pdfplumber 미설치 — 텍스트 추출 불가 (pip install pdfplumber)")
        return
    try:
        with pdfplumber.open(pdf_p) as pdf:
            text = "\n".join(
                page.extract_text() or "" for page in pdf.pages[:30]
            )
        txt_p.write_text(text, encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 스크립트 실행 ────────────────────────────────────────────────────────────
def run_script(script: str, timeout: int = 1800) -> bool:
    log.info(f"  → {script} ...")
    _env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    try:
        r = subprocess.run(
            [PYTHON, str(BASE / script)],
            cwd=str(BASE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_env,
        )
        lines = (r.stdout or "").splitlines()
        # 처음 3줄 + 마지막 3줄 출력 (중간 생략)
        show = lines[:3] + (["     ..."] if len(lines) > 6 else []) + lines[-3:]
        for line in show:
            log.info(f"     {line}")
        if r.returncode != 0:
            log.warning(f"     [실패] returncode={r.returncode}")
            for line in (r.stderr or "").splitlines()[-15:]:
                log.warning(f"     STDERR: {line}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log.warning(f"     [타임아웃] {script}")
        return False
    except Exception as e:
        log.warning(f"     [오류] {e}")
        return False

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info(f"CeO2 주간 파이프라인 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)

    state = load_state()

    # 검색 기준 날짜: 마지막 실행 -1일 (최초 실행이면 14일 전)
    if state["last_run"]:
        since = (
            datetime.fromisoformat(state["last_run"]) - timedelta(days=1)
        ).strftime("%Y-%m-%d")
    else:
        since = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    log.info(f"신규 논문 기준: {since} 이후")

    existing_dois = get_existing_dois()
    log.info(f"기존 DB: {len(existing_dois):,}편\n")

    # ── 1. OpenAlex 수집 ─────────────────────────────────────────────────────
    log.info("── 1. 신규 논문 수집 ────────────────────────────────────────")
    new_rows: dict[str, dict] = {}
    for q in OPENALEX_QUERIES:
        papers = fetch_openalex(q, since)
        added = 0
        for p in papers:
            row = paper_to_row(p)
            if row and row["doi"] and row["doi"] not in existing_dois and row["doi"] not in new_rows:
                new_rows[row["doi"]] = row
                added += 1
        log.info(f"  [{q:<40}] {len(papers):>4}건 → 신규 {added}편")

    new_count = len(new_rows)
    log.info(f"\n신규 논문 합계: {new_count}편")

    # ── 2. Excel 업데이트 ─────────────────────────────────────────────────────
    log.info("\n── 2. DB 업데이트 ───────────────────────────────────────────")
    if new_count > 0:
        if not XLSX.exists():
            log.error(f"Excel 파일 없음: {XLSX}")
            return
        df_orig = pd.read_excel(XLSX, sheet_name=0)
        # format_excel.py 실행 후 요약행이 생긴 경우 방어
        if "doi" not in df_orig.columns:
            df_orig = pd.read_excel(XLSX, sheet_name=0, header=5)
        new_df  = pd.DataFrame(list(new_rows.values()))

        # 기존 컬럼 순서 유지 (없는 컬럼은 NaN)
        for col in df_orig.columns:
            if col not in new_df.columns:
                new_df[col] = pd.NA
        shared = [c for c in df_orig.columns if c in new_df.columns]
        df_updated = pd.concat([df_orig, new_df[shared]], ignore_index=True)

        xl = pd.ExcelFile(XLSX)
        other_sheets = {s: xl.parse(s) for s in xl.sheet_names
                        if s not in ("합성조건", "Sheet1")}
        xl.close()
        with pd.ExcelWriter(XLSX, engine="openpyxl") as w:
            df_updated.to_excel(w, sheet_name="합성조건", index=False)
            for sn, sd in other_sheets.items():
                sd.to_excel(w, sheet_name=sn, index=False)
        log.info(f"Excel 저장: 총 {len(df_updated):,}편 (신규 {new_count}편 추가)")

        # ── 3. PDF 다운로드 + 텍스트 추출 ─────────────────────────────────
        log.info("\n── 3. PDF 다운로드 + 텍스트 추출 ───────────────────────")
        PDF.mkdir(exist_ok=True)
        TEXT.mkdir(exist_ok=True)
        pdf_ok = 0
        for doi, row in new_rows.items():
            if download_pdf(doi, row.get("open_access_url", "")):
                pdf_ok += 1
            extract_text(doi)
        log.info(f"PDF 다운로드: {pdf_ok}/{new_count}편")
    else:
        log.info("추가할 신규 논문 없음 — 후처리만 실행합니다.")

    # ── 4. 후처리 파이프라인 ──────────────────────────────────────────────────
    log.info("\n── 4. 후처리 파이프라인 ─────────────────────────────────────")
    # (script, desc, timeout_seconds)  — timeout=None → 함수 기본값 사용
    post_steps = [
        ("3_merge.py",              "샘플 병합",             1800),
        ("4_extract_targeted.py",   "핵심 15필드 재추출",    3600),
        ("5_table_extract.py",      "표/그림 입자크기 보완", 3600),
        ("6_fill_keywords.py",      "키워드 보완",           1800),
        ("7_calc_completeness.py",  "완성도 점수 계산",      1800),
        ("8_normalize_data.py",     "데이터 정규화",         1800),
        ("9_add_tags.py",           "OA/방법/형태 태그",     1800),
        ("10_build_dataset.py",     "JSONL 데이터셋 생성",   1800),
        ("12_model.py",             "ML 모델 업데이트",      7200),
    ]
    results = {}
    for script, desc, tmo in post_steps:
        log.info(f"\n  [{desc}]")
        results[script] = run_script(script, timeout=tmo)

    # ── 5. 상태 저장 ──────────────────────────────────────────────────────────
    state["last_run"]    = datetime.now().isoformat()
    state["total_added"] = state.get("total_added", 0) + new_count
    state.setdefault("runs", []).append({
        "date":       state["last_run"],
        "new_papers": new_count,
        "results":    {k: ("성공" if v else "실패") for k, v in results.items()},
        "log":        str(_log_path),
    })
    state["runs"] = state["runs"][-52:]  # 최근 1년치
    save_state(state)

    ok = sum(results.values())
    log.info(f"\n{'='*60}")
    log.info(f"완료: 신규 {new_count}편 추가 | {ok}/{len(post_steps)} 단계 성공")
    log.info(f"로그: {_log_path}")
    log.info("=" * 60)

if __name__ == "__main__":
    main()
