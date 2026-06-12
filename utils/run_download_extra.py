"""
추가 PDF 다운로드 + 텍스트 추출
전문 없는 논문을 대상으로 여러 소스를 순서대로 시도합니다.

시도 순서:
  1. 기존 PDF 있지만 텍스트 미추출  → 텍스트만 재추출
  2. OA URL 있지만 PDF 미확보       → 재다운로드
  3. URL 없는 논문                  → Unpaywall 재조회
                                    → OpenAlex OA URL
                                    → Semantic Scholar OA PDF
                                    → CORE.ac.uk
                                    → Sci-Hub (SCIHUB_ENABLED=True 시)

CMD 터미널에서:
  python run_download_extra.py
  python run_download_extra.py --scihub       ← Sci-Hub 포함
  python run_download_extra.py --dry-run      ← 현황 분석만 (다운로드 없음)
"""
import os, re, sys, time, glob, argparse
import requests
import pandas as pd
import pdfplumber
try:
    import fitz as pymupdf; PYMUPDF = True
except ImportError:
    PYMUPDF = False
from bs4 import BeautifulSoup
from tqdm import tqdm

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
_BASE     = r"d:\머신러닝 교육\ceria_pipeline_data"
META_PATH = os.path.join(_BASE, "output", "papers_metadata.xlsx")
PDF_DIR   = os.path.join(_BASE, "pdf")
TEXT_DIR  = os.path.join(_BASE, "text")
EMAIL     = "juhur@soulbrain.co.kr"

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(TEXT_DIR, exist_ok=True)

# ── 인자 처리 ─────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--scihub",   action="store_true", help="Sci-Hub 다운로드 포함")
ap.add_argument("--dry-run",  action="store_true", help="현황 분석만 출력")
args = ap.parse_args()

SCIHUB_ENABLED = args.scihub
SCIHUB_URLS    = ["https://sci-hub.mk/", "https://sci-hub.se/", "https://sci-hub.st/"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ── 메타데이터 로드 ───────────────────────────────────────────────────────────
print("papers_metadata.xlsx 로드 중...")
df = pd.read_excel(META_PATH)
print(f"총 {len(df):,}편  |  컬럼: {list(df.columns)}\n")

def _col(name):
    return name if name in df.columns else None

COL_OA   = _col("open_access_url")
COL_PDF  = _col("local_pdf_path")
COL_TEXT = _col("text_path")

# ── 파일 존재 여부 확인 헬퍼 ──────────────────────────────────────────────────
def _txt_exists(stem: str) -> bool:
    return os.path.exists(os.path.join(TEXT_DIR, stem + ".txt"))

def _pdf_exists(stem: str) -> bool:
    return os.path.exists(os.path.join(PDF_DIR, stem + ".pdf"))

def _doi_stem(doi) -> str:
    if not doi or pd.isna(doi):
        return ""
    return str(doi).strip().replace("/", "_").replace(":", "_")

def safe_fname(pid, title="") -> str:
    base = re.sub(r'[\\/:*?"<>|]', "_", str(pid or title or "unknown"))
    return base.strip()[:120]

# ── 현황 분류 ─────────────────────────────────────────────────────────────────
cat_text   = []   # A: PDF 있음, 텍스트 없음
cat_retry  = []   # B: OA URL 있음, PDF 없음
cat_nourl  = []   # C: URL 없음 (새 소스 시도 필요)

for idx, row in df.iterrows():
    pid  = row["paper_id"]
    doi  = row.get("doi", "")
    stem = _doi_stem(doi) or safe_fname(pid)
    oa   = str(row.get(COL_OA, "") or "").strip()
    lpdf = str(row.get(COL_PDF, "") or "").strip()

    has_text = _txt_exists(stem)
    has_pdf  = _pdf_exists(stem) or (lpdf and os.path.exists(lpdf) and os.path.getsize(lpdf) > 1000)

    if has_text:
        continue

    if has_pdf:
        cat_text.append((idx, row, stem))       # A
    elif oa and not oa.startswith("file://"):
        cat_retry.append((idx, row, stem, oa))  # B
    else:
        cat_nourl.append((idx, row, stem))       # C

total_missing = len(cat_text) + len(cat_retry) + len(cat_nourl)
print(f"=== 현황 분석 ===")
print(f"  전문 있음 (text/*.txt):                {len(df) - total_missing:>6,}편")
print(f"  [A] PDF 있지만 텍스트 미추출:         {len(cat_text):>6,}편")
print(f"  [B] OA URL 있지만 PDF 미확보:         {len(cat_retry):>6,}편")
print(f"  [C] URL 없음 (새 소스 필요):          {len(cat_nourl):>6,}편")
print(f"  Sci-Hub 시도: {'예 (--scihub)' if SCIHUB_ENABLED else '아니오 (--scihub 추가 시 활성화)'}\n")

if args.dry_run:
    print("--dry-run 모드: 다운로드 없이 종료합니다.")
    sys.exit(0)

# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
def extract_text(pdf_path: str) -> str:
    try:
        pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        if pages:
            return "\n\n".join(pages)
    except Exception:
        pass
    if PYMUPDF:
        try:
            doc = pymupdf.open(pdf_path)
            text = "\n\n".join(p.get_text() for p in doc)
            doc.close()
            if text.strip():
                return text
        except Exception:
            pass
    return ""

def save_text(stem: str, text: str) -> bool:
    if not text.strip():
        return False
    path = os.path.join(TEXT_DIR, stem + ".txt")
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)
    return True

def download_pdf(url: str, save_path: str, _depth: int = 0) -> bool:
    """
    PDF 다운로드. Content-Type 검사를 완화하고 magic bytes(%PDF)로 실제 PDF 여부 확인.
    HTML 응답인 경우 페이지 내 PDF 링크를 탐색해 재시도 (최대 1회 재귀).
    """
    if _depth > 1:   # HTML redirect 재귀 최대 1회 제한
        return False

    for attempt, hdrs in enumerate([HEADERS, {**HEADERS, "User-Agent": "Mozilla/5.0"}]):
        try:
            r = requests.get(url, headers=hdrs, timeout=40, stream=True, allow_redirects=True)
            if r.status_code != 200:
                continue

            ct = r.headers.get("Content-Type", "").lower()

            # HTML 응답 → 페이지 내 PDF 링크 탐색
            if "html" in ct:
                html = r.text
                soup = BeautifulSoup(html, "lxml")
                pdf_link = ""
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith(".pdf") or "pdf" in href.lower():
                        pdf_link = href if href.startswith("http") else (
                            url.rsplit("/", 1)[0] + "/" + href.lstrip("/")
                        )
                        break
                # meta refresh / iframe 으로 PDF 직접 임베드된 경우
                if not pdf_link:
                    for tag in soup.find_all(["iframe", "embed"], src=True):
                        src = tag.get("src", "")
                        if "pdf" in src.lower():
                            pdf_link = src if src.startswith("http") else "https:" + src
                            break
                if pdf_link and pdf_link != url:
                    return download_pdf(pdf_link, save_path, _depth=_depth + 1)
                continue

            # PDF 또는 octet-stream → 저장 후 magic bytes 확인
            if any(t in ct for t in ("pdf", "octet-stream", "binary", "download", "force-download")) \
                    or url.lower().endswith(".pdf"):
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                size = os.path.getsize(save_path)
                if size < 1000:
                    os.remove(save_path)
                    continue
                # magic bytes: 실제 PDF인지 확인
                with open(save_path, "rb") as f:
                    header = f.read(5)
                if header.startswith(b"%PDF"):
                    return True
                os.remove(save_path)   # PDF 아님

        except Exception:
            pass
        time.sleep(1.0)
    return False

# ── A: PDF → 텍스트 재추출 ───────────────────────────────────────────────────
print(f"[A] PDF → 텍스트 추출: {len(cat_text)}편")
a_ok = 0
for idx, row, stem in tqdm(cat_text):
    pid  = row["paper_id"]
    lpdf = str(row.get(COL_PDF, "") or "").strip()
    # pdf/ 폴더에서 stem으로도 탐색
    pdf_path = lpdf if (lpdf and os.path.exists(lpdf)) else os.path.join(PDF_DIR, stem + ".pdf")
    if not os.path.exists(pdf_path):
        continue
    text = extract_text(pdf_path)
    if save_text(stem, text):
        a_ok += 1
print(f"  → 성공: {a_ok}편\n")

# ── B: OA URL 재다운로드 ──────────────────────────────────────────────────────
print(f"[B] OA URL 재다운로드: {len(cat_retry)}편")
b_ok = 0
for idx, row, stem, oa_url in tqdm(cat_retry):
    pdf_path = os.path.join(PDF_DIR, stem + ".pdf")
    if download_pdf(oa_url, pdf_path):
        text = extract_text(pdf_path)
        if save_text(stem, text):
            b_ok += 1
    time.sleep(0.5)
print(f"  → 성공: {b_ok}편\n")

# ── C: 새 소스에서 URL 발굴 ───────────────────────────────────────────────────
print(f"[C] 새 소스에서 PDF 확보: {len(cat_nourl)}편")

# C-1. Unpaywall 재조회
def get_unpaywall(doi: str) -> str:
    if not doi or pd.isna(doi):
        return ""
    url = f"https://api.unpaywall.org/v2/{requests.utils.quote(str(doi).strip(), safe='')}?email={EMAIL}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            best = (r.json().get("best_oa_location") or {})
            return best.get("url_for_pdf", "") or ""
    except Exception:
        pass
    return ""

# C-2. OpenAlex OA URL
def get_openalex(doi: str) -> str:
    if not doi or pd.isna(doi):
        return ""
    url = f"https://api.openalex.org/works/https://doi.org/{requests.utils.quote(str(doi).strip(), safe='')}"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": f"mailto:{EMAIL}"})
        if r.status_code == 200:
            data = r.json()
            # primary_location
            loc = data.get("primary_location") or {}
            pdf = loc.get("pdf_url", "")
            if pdf:
                return pdf
            # best_oa_location
            oa = data.get("best_oa_location") or {}
            return oa.get("pdf_url", "") or ""
    except Exception:
        pass
    return ""

# C-3. Semantic Scholar OA PDF
def get_semantic_scholar(doi: str) -> str:
    if not doi or pd.isna(doi):
        return ""
    url = (f"https://api.semanticscholar.org/graph/v1/paper/DOI:{requests.utils.quote(str(doi).strip(), safe='')}"
           f"?fields=openAccessPdf")
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            oa = r.json().get("openAccessPdf") or {}
            return oa.get("url", "") or ""
    except Exception:
        pass
    return ""

# C-4. CORE.ac.uk
def get_core(doi: str) -> str:
    if not doi or pd.isna(doi):
        return ""
    url = f"https://api.core.ac.uk/v3/search/works?q=doi:{requests.utils.quote(str(doi).strip(), safe='')}&limit=1"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                dl = results[0].get("downloadUrl", "") or ""
                if dl:
                    return dl
    except Exception:
        pass
    return ""

# C-5. Sci-Hub
def get_scihub(doi: str) -> str:
    for base in SCIHUB_URLS:
        try:
            r = requests.get(f"{base}{doi}", headers=HEADERS, timeout=20, allow_redirects=True)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for tag, attr in [("iframe","src"), ("embed","src")]:
                el = soup.find(tag, id="pdf") or soup.find(tag, attrs={"type":"application/pdf"})
                if el and el.get(attr):
                    src = el[attr]
                    return ("https:" + src) if src.startswith("//") else src
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower():
                    if href.startswith("//"):
                        return "https:" + href
                    if href.startswith("/"):
                        return base.rstrip("/") + href
                    return href
        except Exception:
            pass
        time.sleep(0.5)
    return ""

SOURCES = [
    ("Unpaywall",        get_unpaywall),
    ("OpenAlex",         get_openalex),
    ("SemanticScholar",  get_semantic_scholar),
    ("CORE.ac.uk",       get_core),
]
if SCIHUB_ENABLED:
    SOURCES.append(("Sci-Hub", get_scihub))

c_results = {s: 0 for s, _ in SOURCES}
c_ok = 0
SAVE_INTERVAL = 50

for i, (idx, row, stem) in enumerate(tqdm(cat_nourl, desc="C 소스 탐색")):
    doi = str(row.get("doi", "") or "").strip()
    if not doi:
        continue

    pdf_path = os.path.join(PDF_DIR, stem + ".pdf")
    found = False

    for src_name, src_fn in SOURCES:
        pdf_url = src_fn(doi)
        if not pdf_url:
            time.sleep(0.3)
            continue

        if download_pdf(pdf_url, pdf_path):
            text = extract_text(pdf_path)
            if save_text(stem, text):
                c_ok += 1
                c_results[src_name] += 1
                df.at[idx, "open_access_url"]  = pdf_url
                df.at[idx, "local_pdf_path"]   = pdf_path
            found = True
            break
        time.sleep(0.5)

    if not found:
        time.sleep(0.2)

    # 주기적 저장
    if (i + 1) % SAVE_INTERVAL == 0:
        df.to_excel(META_PATH, index=False)
        tqdm.write(f"  [{i+1}/{len(cat_nourl)}] 중간 저장 완료")

df.to_excel(META_PATH, index=False)

print(f"\n=== [C] 결과 ===")
for src, cnt in c_results.items():
    print(f"  {src:<20} {cnt:>5,}편")
print(f"  합계                 {c_ok:>5,}편\n")

# ── 최종 요약 ─────────────────────────────────────────────────────────────────
total_ok = a_ok + b_ok + c_ok
txt_count = len(glob.glob(os.path.join(TEXT_DIR, "*.txt")))
print(f"=== 최종 요약 ===")
print(f"  이번 실행 신규 확보:  {total_ok:,}편")
print(f"    [A] 텍스트 추출:   {a_ok:,}편")
print(f"    [B] URL 재다운:    {b_ok:,}편")
print(f"    [C] 새 소스:       {c_ok:,}편")
print(f"  text/ 총 파일 수:    {txt_count:,}편")
print(f"  전문 없는 잔여:      {len(df) - txt_count:,}편")
