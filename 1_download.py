"""
run_download_noa.py — 비-OA 논문 전문 보완

전략 (순서대로 시도):
  1. PMC (PubMed Central) — 합법, NCBI 무료 API
  2. Unpaywall OA URL 재시도  — 합법
  3. Sci-Hub              — ⚠ 저작권 주의, --scihub 옵션 필요

사용법:
  python run_download_noa.py              # PMC + Unpaywall만 (기본)
  python run_download_noa.py --scihub    # Sci-Hub 포함
  python run_download_noa.py --dry-run   # 대상 확인만
  python run_download_noa.py --limit 50  # 최대 50편 처리
  python run_download_noa.py --backfill-pdf  # 텍스트만 있고 PDF 없는 기존 논문에 PMC PDF 소급 수집

PMC 수집 방식:
  - XML 전문을 우선 파싱 (텍스트 품질 우수, 노이즈 적음)
  - XML 파싱과 무관하게 PDF도 병행 저장 (HasPDF=Y 논문만)
  - 텍스트는 항상 XML 파싱 결과 사용 (PDF 재추출 안 함)

출력:
  text/ 폴더에 .txt 파일 추가
  pdf/  폴더에 .pdf 파일 추가 (PMC HasPDF=Y 논문)
  output/noa_download_cache.json 에 진행 상황 저장 (재시작 가능)
"""
import os, sys, re, json, time, argparse, logging, hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

# Windows cp949 환경에서 ✓/✗ 등 유니코드 출력 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import pandas as pd

# cloudscraper: Cloudflare 봇 보호 우회 (pip install cloudscraper)
try:
    import cloudscraper
    _scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _scraper = requests
    _HAS_CLOUDSCRAPER = False

BASE     = Path(r"d:\머신러닝 교육\ceria_pipeline_data")
OUTPUT   = BASE / "output"
XLSX     = OUTPUT / "ceria_synthesis_database.xlsx"
PDF_DIR  = BASE / "pdf"
TEXT_DIR = BASE / "text"
CACHE    = OUTPUT / "noa_download_cache.json"

# NCBI E-utilities
PMC_ESEARCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PMC_EFETCH   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PMC_SUMMARY  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Sci-Hub 미러 (접속 확인된 것 우선 배치)
SCIHUB_MIRRORS = [
    "https://sci-hub.sidesgame.com",  # 사용자 확인 접속 가능
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
    "https://sci-hub.mksa.top",
    "https://sci-hub.ren",
    "https://sci-hub.cat",
]

# 브라우저 헤더 (Accept-Encoding 제외 — requests가 자동 처리)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
SAVE_INTERVAL = 25  # N편마다 캐시 저장

# ── 로깅 ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── 캐시 ─────────────────────────────────────────────────────────────────────
def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"done_dois": [], "pmc_ok": 0, "scihub_ok": 0, "failed": []}

def save_cache(c: dict):
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def _safe_fname(doi: str) -> str:
    return doi.replace("/", "_").replace(":", "_")

def has_text(doi: str) -> bool:
    return (TEXT_DIR / f"{_safe_fname(doi)}.txt").exists()

def has_pdf(doi: str) -> bool:
    return (PDF_DIR / f"{_safe_fname(doi)}.pdf").exists()

# ── 내용 중복 방지: 기존 파일 MD5 집합 (최초 호출 시 1회 로드) ─────────────────
_content_hashes: set = set()
_hashes_loaded: bool = False

def _load_content_hashes():
    global _content_hashes, _hashes_loaded
    if _hashes_loaded:
        return
    if TEXT_DIR.exists():
        for p in TEXT_DIR.glob("*.txt"):
            try:
                h = hashlib.md5(p.read_text(encoding="utf-8", errors="replace").strip()
                                 .encode("utf-8", errors="replace")).hexdigest()
                _content_hashes.add(h)
            except Exception:
                pass
    _hashes_loaded = True

def save_text(doi: str, text: str) -> bool:
    text = text.strip()
    if len(text) < 300:
        return False
    if _safe_fname(doi).upper().startswith("NOID"):
        return False  # DOI 없는 파일은 저장 안 함
    _load_content_hashes()
    h = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
    if h in _content_hashes:
        return False  # 동일 내용 이미 존재
    (TEXT_DIR / f"{_safe_fname(doi)}.txt").write_text(text, encoding="utf-8", errors="replace")
    _content_hashes.add(h)
    return True

def pdf_to_text(doi_or_stem: str) -> str:
    """PDF → 텍스트 (pdfplumber). doi 또는 파일명 stem 모두 허용."""
    # stem 직접 전달 시 그대로 사용, DOI면 안전 파일명으로 변환
    stem = doi_or_stem if (PDF_DIR / f"{doi_or_stem}.pdf").exists() else _safe_fname(doi_or_stem)
    pdf_path = PDF_DIR / f"{stem}.pdf"
    if not pdf_path.exists():
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages[:30])
    except Exception:
        return ""

def download_pdf(doi: str, url: str) -> bool:
    """URL → pdf/ 저장"""
    path = PDF_DIR / f"{_safe_fname(doi)}.pdf"
    if path.exists():
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and b"%PDF" in r.content[:1024]:
            path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


# ── PMC ──────────────────────────────────────────────────────────────────────
def doi_to_pmcid(doi: str) -> str | None:
    """DOI → PMC ID"""
    try:
        r = requests.get(PMC_ESEARCH, params={
            "db": "pmc", "term": f"{doi}[doi]",
            "retmode": "json", "retmax": 1,
        }, headers=HEADERS, timeout=15)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
    except Exception:
        return None

def fetch_pmc_fulltext(pmcid: str) -> str:
    """PMC XML → 평문 (실험 섹션 포함)"""
    try:
        r = requests.get(PMC_EFETCH, params={
            "db": "pmc", "id": pmcid,
            "rettype": "full", "retmode": "xml",
        }, headers=HEADERS, timeout=30)
        root = ET.fromstring(r.content)
        chunks = []
        for elem in root.iter():
            if elem.tag in ("p", "title", "label", "caption"):
                txt = " ".join(elem.itertext()).strip()
                if txt:
                    chunks.append(txt)
        return "\n".join(chunks)
    except Exception:
        return ""

def fetch_pmc_pdf_url(pmcid: str) -> str:
    """PMC PDF 직접 링크 (HasPDF=Y 논문만)"""
    try:
        r = requests.get(PMC_SUMMARY, params={
            "db": "pmc", "id": pmcid, "retmode": "json",
        }, headers=HEADERS, timeout=15)
        result = r.json().get("result", {}).get(pmcid, {})
        if result.get("haspdf") == "Y":
            return f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/"
    except Exception:
        pass
    return ""

def try_pmc(doi: str) -> str:
    """PMC 수집: XML 전문 파싱 + PDF 병행 저장

    텍스트는 항상 XML 파싱 결과를 사용 (PDF 추출보다 노이즈 적음).
    HasPDF=Y 논문은 XML 성공 여부와 무관하게 PDF도 함께 저장.
    """
    pmcid = doi_to_pmcid(doi)
    if not pmcid:
        return ""
    time.sleep(0.4)  # NCBI rate limit ≤ 3 req/s

    # 1. XML 전문 파싱 (텍스트 품질 우선)
    text = fetch_pmc_fulltext(pmcid)

    # 2. PDF 병행 저장 (XML 성공 여부와 무관하게 시도)
    time.sleep(0.4)
    pdf_url = fetch_pmc_pdf_url(pmcid)
    if pdf_url and not has_pdf(doi):
        download_pdf(doi, pdf_url)

    # 3. XML 충분하면 XML 텍스트 반환 (PDF 재추출 안 함)
    if len(text) > 500:
        return text

    # 4. XML 부족 시 PDF 텍스트로 폴백
    if has_pdf(doi):
        return pdf_to_text(doi)

    return ""


# ── Unpaywall 재시도 ──────────────────────────────────────────────────────────
def try_unpaywall(doi: str, oa_url: str) -> str:
    """기존 open_access_url로 재시도"""
    if not oa_url or not str(oa_url).startswith("http"):
        return ""
    if download_pdf(doi, str(oa_url)):
        return pdf_to_text(doi)
    return ""


# ── Semantic Scholar ─────────────────────────────────────────────────────────
def try_semantic_scholar(doi: str) -> str:
    """Semantic Scholar API → openAccessPdf.url로 PDF 다운로드."""
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf"
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        if r.status_code != 200:
            return ""
        data = r.json()
        pdf_info = data.get("openAccessPdf")
        if not pdf_info or not pdf_info.get("url"):
            return ""
        pdf_url = pdf_info["url"]
        if download_pdf(doi, pdf_url):
            return pdf_to_text(doi)
    except Exception:
        pass
    return ""


# ── Sci-Hub ──────────────────────────────────────────────────────────────────
def _fix_url(u: str, mirror: str) -> str:
    u = u.strip().rstrip("'\"")
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return mirror + u
    if not u.startswith("http"):
        return mirror + "/" + u
    return u

def _extract_pdf_url(html: str, mirror: str) -> str:
    """Sci-Hub HTML에서 PDF 직접 다운로드 URL 추출 (6가지 패턴)"""

    # 패턴 1: <embed src="//..." type="application/pdf">  ← 가장 흔함
    m = re.search(
        r'<embed[^>]+src=["\']([^"\']+)["\'][^>]*type=["\']application/pdf["\']',
        html, re.I)
    if not m:
        m = re.search(
            r'<embed[^>]*type=["\']application/pdf["\'][^>]*src=["\']([^"\']+)["\']',
            html, re.I)
    if not m:
        m = re.search(r'<embed[^>]+src=["\']([^"\'#]+\.pdf[^"\']*)["\']', html, re.I)
    if m:
        return _fix_url(m.group(1), mirror)

    # 패턴 2: <iframe src="//...">
    m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if m:
        u = m.group(1)
        if any(k in u for k in ('.pdf', '/pdf', 'download', 'sci-hub')):
            return _fix_url(u, mirror)

    # 패턴 3: onclick="location.href='//...'"  ← save 버튼
    m = re.search(
        r"onclick=[\"'](?:location\.href\s*=\s*)?[\"']([^\"']+)[\"']",
        html, re.I)
    if m:
        u = m.group(1)
        if any(k in u for k in ('.pdf', '/pdf', 'download')):
            return _fix_url(u, mirror)

    # 패턴 4: location.href = '//...'  (JavaScript 변수 할당)
    m = re.search(r"location\.href\s*=\s*[\"']([^\"']+)[\"']", html, re.I)
    if m:
        return _fix_url(m.group(1), mirror)

    # 패턴 5: div id="pdf" 내부 src
    m = re.search(
        r'id=["\']pdf["\'][^>]*>.*?src=["\']([^"\']+)["\']',
        html, re.I | re.S)
    if m:
        return _fix_url(m.group(1), mirror)

    # 패턴 6: https://... .pdf 직접 링크
    m = re.search(r'(https?://[^\s"\'<>]+\.pdf(?:\?[^\s"\'<>]*)?)', html, re.I)
    if m:
        return m.group(1)

    # 패턴 7: //downloads/ 또는 //cdn. 경로
    m = re.search(r'["\'](\/{1,2}(?:downloads?|cdn|files)[^\s"\'<>]+)["\']', html, re.I)
    if m:
        return _fix_url(m.group(1), mirror)

    return ""

def try_scihub(doi: str) -> str:
    """Sci-Hub에서 PDF 수집 (cloudscraper → requests 순서, 미러 순차 시도)"""
    cf_note = "cloudscraper" if _HAS_CLOUDSCRAPER else "requests(cloudscraper 미설치)"
    for mirror in SCIHUB_MIRRORS:
        try:
            url = f"{mirror}/{doi}"
            # Cloudflare 우회: cloudscraper 우선, 없으면 requests
            sess = _scraper
            r = sess.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
            print(f"    [{mirror.replace('https://',''):<30}] HTTP {r.status_code}  ({len(r.content):,}bytes) [{cf_note}]")
            if r.status_code != 200:
                time.sleep(0.5)
                continue

            # 응답이 PDF 자체인 경우 (직접 리다이렉트)
            if b"%PDF" in r.content[:1024]:
                pdf_path = PDF_DIR / f"{_safe_fname(doi)}.pdf"
                pdf_path.write_bytes(r.content)
                text = pdf_to_text(doi)
                if len(text) > 300:
                    print(f"    → 직접 PDF 응답 성공 ({len(text):,}자)")
                    return text

            # HTML 디코딩 (인코딩 자동 감지)
            html = r.text
            pdf_url = _extract_pdf_url(html, mirror)
            if pdf_url:
                print(f"    → PDF URL 발견: {pdf_url[:80]}")
            else:
                snippet = html[:200].replace('\n', ' ').strip()
                print(f"    → PDF URL 추출 실패. HTML: {snippet[:150]}")

            if not pdf_url:
                continue
            if download_pdf(doi, pdf_url):
                text = pdf_to_text(doi)
                if len(text) > 300:
                    return text
        except Exception:
            pass
        time.sleep(0.8)
    return ""


def _load_xlsx(path):
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)


# ── 메인 ─────────────────────────────────────────────────────────────────────
def backfill_pdf():
    """텍스트만 있고 PDF 없는 기존 논문에 PMC PDF 소급 수집.

    XML 파싱 텍스트는 그대로 유지하고, PDF 파일만 추가 저장.
    PMC에 PDF가 없는 논문(HasPDF=N)은 건너뜀.
    """
    PDF_DIR.mkdir(exist_ok=True)

    df = _load_xlsx(XLSX)
    targets = [
        str(r["doi"]).strip()
        for _, r in df.iterrows()
        if pd.notna(r.get("doi"))
        and has_text(str(r["doi"]).strip())
        and not has_pdf(str(r["doi"]).strip())
    ]

    print("=" * 60)
    print(f"텍스트 있음 / PDF 없음: {len(targets):,}편")
    print("PMC HasPDF=Y 논문만 PDF 저장 (텍스트는 기존 XML 파싱 결과 유지)")
    print("=" * 60)

    ok = 0
    no_pmc = 0
    no_pdf_url = 0

    for i, doi in enumerate(targets, 1):
        print(f"[{i:>4}/{len(targets)}] {doi}", end="  ", flush=True)

        pmcid = doi_to_pmcid(doi)
        if not pmcid:
            print("PMC 없음")
            no_pmc += 1
            time.sleep(0.2)
            continue

        time.sleep(0.4)
        pdf_url = fetch_pmc_pdf_url(pmcid)
        if not pdf_url:
            print(f"HasPDF=N (PMC{pmcid})")
            no_pdf_url += 1
            time.sleep(0.2)
            continue

        if download_pdf(doi, pdf_url):
            ok += 1
            pdf_size = (PDF_DIR / f"{_safe_fname(doi)}.pdf").stat().st_size // 1024
            print(f"✓ PDF 저장 ({pdf_size:,}KB)")
        else:
            print(f"✗ 다운로드 실패 (PMC{pmcid})")

        time.sleep(0.4)

    print("\n" + "=" * 60)
    print(f"완료: {ok}편 PDF 저장")
    print(f"  PMC 없음:     {no_pmc}편")
    print(f"  HasPDF=N:     {no_pdf_url}편")
    print(f"  저장 성공:    {ok}편")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scihub",   action="store_true",
                        help="Sci-Hub 병행 사용 (저작권 주의)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="대상 목록 확인만 (실제 다운로드 없음)")
    parser.add_argument("--limit",    type=int, default=0,
                        help="최대 처리 편 수 (0=전체)")
    parser.add_argument("--reset",    action="store_true",
                        help="캐시 초기화 후 전체 재시도 (done_dois 삭제)")
    parser.add_argument("--backfill-pdf", action="store_true",
                        help="텍스트만 있고 PDF 없는 기존 논문에 PMC PDF 소급 수집")
    args = parser.parse_args()

    if args.backfill_pdf:
        backfill_pdf()
        return

    print("=" * 60)
    print("비-OA 논문 전문 보완")
    print(f"  0단계: 기존 PDF → 텍스트 추출 (무료, 즉시)")
    print(f"  1순위: Unpaywall OA URL")
    print(f"  2순위: PMC (NCBI 무료 API)")
    print(f"  3순위: Semantic Scholar OA PDF (합법, 무료)")
    print(f"  4순위: Sci-Hub  {'✓ 활성 (저작권 주의)' if args.scihub else '✗ 비활성 (--scihub 옵션으로 활성화)'}")
    print("=" * 60)

    # ── 0단계: 이미 PDF 있는데 텍스트만 없는 경우 먼저 처리 ─────────────────
    print("\n── 0단계: 기존 PDF → 텍스트 추출 ──────────────────────────")
    pdf_files = {p.stem for p in PDF_DIR.glob("*.pdf")} if PDF_DIR.exists() else set()
    txt_files = {t.stem for t in TEXT_DIR.glob("*.txt")} if TEXT_DIR.exists() else set()
    pdf_no_text = pdf_files - txt_files

    if pdf_no_text:
        TEXT_DIR.mkdir(exist_ok=True)
        extracted = 0
        _load_content_hashes()
        for stem in sorted(pdf_no_text):
            if stem.upper().startswith("NOID"):
                continue  # DOI 없는 PDF 건너뜀
            text = pdf_to_text(stem).strip()
            if len(text) > 300:
                h = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
                if h not in _content_hashes:
                    (TEXT_DIR / f"{stem}.txt").write_text(
                        text, encoding="utf-8", errors="replace"
                    )
                    _content_hashes.add(h)
                    extracted += 1
        print(f"  PDF→텍스트 추출: {extracted}/{len(pdf_no_text)}편")
    else:
        print(f"  PDF 있는 미추출 논문 없음")

    # ── 대상 선정: 텍스트 없는 논문 ─────────────────────────────────────────
    df = _load_xlsx(XLSX)

    target_rows = df[
        df["doi"].notna() &
        df["doi"].apply(lambda d: not has_text(str(d).strip()))
    ].copy()

    total_db   = len(df)
    total_text = sum(1 for d in df["doi"].dropna() if has_text(str(d).strip()))

    print(f"\n전체 DB:       {total_db:,}편")
    print(f"전문 보유:     {total_text:,}편 ({total_text/total_db*100:.1f}%)")
    print(f"전문 미보유:   {len(target_rows):,}편")

    if args.limit:
        target_rows = target_rows.head(args.limit)
        print(f"처리 한도:     {args.limit}편")

    if args.dry_run:
        print("\n[dry-run] 실제 다운로드 없이 종료.")
        return

    cache = load_cache()

    if args.reset:
        # done_dois 초기화 (pmc_ok/scihub_ok 누적 수치는 유지)
        cache["done_dois"] = []
        save_cache(cache)
        print("캐시 초기화 완료 (done_dois 삭제)\n")

    done_set   = set(cache["done_dois"])
    failed_set = set(cache.get("failed", []))

    # --scihub 모드: Sci-Hub까지 시도하여 실패한 것(failed)만 제외
    #               done_dois에만 있는 논문(Sci-Hub 미시도)은 재시도
    # 일반 모드:    done_dois(이미 처리 시도한 항목) 모두 제외
    skip_set = failed_set if args.scihub else done_set

    targets = [
        (str(r["doi"]).strip(),
         str(r.get("oa_url", "") or ""))
        for _, r in target_rows.iterrows()
        if str(r["doi"]).strip() not in skip_set
        and not has_text(str(r["doi"]).strip())
    ]
    print(f"미처리 대상:   {len(targets):,}편\n")

    pmc_ok = cache.get("pmc_ok", 0)
    sh_ok  = cache.get("scihub_ok", 0)

    for i, (doi, oa_url) in enumerate(targets, 1):
        print(f"[{i:>4}/{len(targets)}] {doi}")
        found = False

        # 1순위: Unpaywall URL 재시도
        if oa_url and not found:
            text = try_unpaywall(doi, oa_url)
            if save_text(doi, text):
                print(f"  ✓ Unpaywall PDF ({len(text):,}자)")
                found = True

        # 2순위: PMC (XML 파싱 + PDF 병행 저장)
        if not found:
            text = try_pmc(doi)
            if save_text(doi, text):
                pmc_ok += 1
                pdf_note = " +PDF" if has_pdf(doi) else ""
                print(f"  ✓ PMC XML{pdf_note} ({len(text):,}자)")
                found = True
            else:
                print(f"  ✗ PMC 없음")

        # 3순위: Semantic Scholar OA PDF (합법, 무료 API)
        if not found:
            time.sleep(0.3)
            text = try_semantic_scholar(doi)
            if save_text(doi, text):
                print(f"  ✓ Semantic Scholar ({len(text):,}자)")
                found = True
            else:
                print(f"  ✗ S2 없음")

        # 4순위: Sci-Hub (옵션)
        if not found and args.scihub:
            time.sleep(1.5)
            text = try_scihub(doi)
            if save_text(doi, text):
                sh_ok += 1
                print(f"  ✓ Sci-Hub ({len(text):,}자)")
                found = True
            else:
                print(f"  ✗ Sci-Hub도 없음")
                cache["failed"].append(doi)

        done_set.add(doi)
        cache["done_dois"]  = list(done_set)
        cache["pmc_ok"]     = pmc_ok
        cache["scihub_ok"]  = sh_ok

        if i % SAVE_INTERVAL == 0:
            save_cache(cache)
            print(f"\n  [저장] PMC={pmc_ok}, Sci-Hub={sh_ok}\n")

    save_cache(cache)

    print("\n" + "=" * 60)
    print(f"완료")
    print(f"  PMC 성공:     {pmc_ok}편")
    print(f"  Sci-Hub 성공: {sh_ok}편")
    print(f"  처리 총계:    {len(targets)}편")
    new_text = sum(1 for d in df["doi"].dropna() if has_text(str(d).strip()))
    print(f"  전문 보유:    {new_text:,}편 ({new_text/total_db*100:.1f}%)  [이전: {total_text:,}편]")
    print("=" * 60)

    if pmc_ok + sh_ok > 0:
        print("\n새로 수집된 전문으로 후처리를 실행하려면:")
        print("  python run_post_pipeline.py")

if __name__ == "__main__":
    main()
