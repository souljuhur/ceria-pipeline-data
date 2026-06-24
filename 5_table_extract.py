"""
PDF 표/그림 기반 입자크기 추출기

텍스트 추출로 놓친 입자크기 데이터를 두 단계로 보완:
  1차: pdfplumber 표 추출 + GPT-4o-mini (저비용, 빠름)
  2차: PyMuPDF 페이지 이미지 + GPT-4o vision (--vision 옵션, 그림 포함)

대상: ceria_samples_merged.csv (없으면 ceria_samples.csv) 중
      particle_size_tem_nm AND crystallite_size_xrd_nm 모두 null인 샘플

출력:
  output/table_extraction_cache.json   — 진행 상황 (재시작 가능)
  output/ceria_samples_merged.csv      — 제자리 업데이트

CMD:
  python run_table_extraction.py                  # 표 추출만 (기본)
  python run_table_extraction.py --vision         # 표+그림 (GPT-4o, 비용↑)
  python run_table_extraction.py --limit 20       # 소규모 테스트
  python run_table_extraction.py --dry-run        # 대상 확인만
"""

import os, json, re, time, argparse, base64, io
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# ── 경로 ─────────────────────────────────────────────────────────────────────
BASE_DIR         = r"d:\머신러닝 교육\ceria_pipeline_data"
PDF_DIR          = os.path.join(BASE_DIR, "pdf")
MERGED_CSV       = os.path.join(BASE_DIR, "output", "ceria_samples_merged.csv")
RAW_CSV          = os.path.join(BASE_DIR, "output", "ceria_samples.csv")
TEXT_CACHE_PATH  = os.path.join(BASE_DIR, "output", "table_extraction_cache.json")
VISION_CACHE_PATH= os.path.join(BASE_DIR, "output", "table_extraction_vision_cache.json")

SAVE_INTERVAL = 20   # N편마다 CSV 저장

# ── CLI ──────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--limit",   type=int, default=0)
ap.add_argument("--vision",  action="store_true",
                help="GPT-4o 비전으로 그림 페이지 분석 (비용↑)")
ap.add_argument("--dry-run", action="store_true",
                help="API 호출 없이 대상 확인만")
args = ap.parse_args()

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── OpenAI 초기화 ─────────────────────────────────────────────────────────────
if not args.dry_run:
    if not OPENAI_KEY:
        raise SystemExit("OPENAI_API_KEY 없음.")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
    except ImportError:
        raise SystemExit("pip install openai")

# ── pdfplumber / PyMuPDF ──────────────────────────────────────────────────────
try:
    import pdfplumber
except ImportError:
    raise SystemExit("pip install pdfplumber")

fitz_ok = False
if args.vision:
    try:
        import fitz  # PyMuPDF
        fitz_ok = True
    except ImportError:
        print("[경고] PyMuPDF 없음 — --vision 비활성화. pip install pymupdf")
        args.vision = False

# ── 유틸 ─────────────────────────────────────────────────────────────────────
_SIZE_HINT = re.compile(
    r'(?:particle|crystallite|grain|crystal|primary|TEM|SEM|XRD|BET|'
    r'size|diameter|d_?(?:TEM|XRD|BET|avg|mean)|'
    r'D_?(?:50|avg|mean|TEM|XRD)|'
    r'Scherrer|FWHM)',
    re.I)
_NM_HINT   = re.compile(r'\d[\d.]*\s*(?:nm|nanometer)', re.I)

def doi_to_stem(doi: str) -> str:
    return str(doi).strip().replace("/", "_").replace(":", "_").lower()

def is_size_related(text: str) -> bool:
    return bool(_SIZE_HINT.search(text) and _NM_HINT.search(text))

# ── 표 추출 (pdfplumber) ──────────────────────────────────────────────────────
def extract_tables_text(pdf_path: str, max_tables: int = 15) -> str:
    """
    PDF에서 표를 추출해 텍스트로 변환.
    입자크기 관련 표만 우선 포함, 나머지는 뒤에 붙임.
    """
    priority, other = [], []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for tbl in tables:
                    rows = []
                    for row in tbl:
                        if row:
                            rows.append(" | ".join(
                                str(c).strip() if c else "" for c in row))
                    tbl_str = "\n".join(rows)
                    if is_size_related(tbl_str):
                        priority.append(tbl_str)
                    else:
                        other.append(tbl_str)
    except Exception as e:
        return f"[표 추출 오류: {e}]"

    combined = priority + other
    return "\n\n---TABLE---\n\n".join(combined[:max_tables]) if combined else ""


# ── 결과/실험 페이지 텍스트 추출 ──────────────────────────────────────────────
_RES_HEADER = re.compile(
    r'(?:results?(?:\s+and\s+discussion)?'
    r'|characterization(?:\s+results?)?'
    r'|discussion'
    r'|physical\s+properties'
    r'|structural\s+(?:analysis|properties|characterization)'
    r'|table\s*\d'
    r'|\d+[\.\d]*\s*(?:results?|characterization|discussion))',
    re.I)

def extract_result_pages_text(pdf_path: str, max_chars: int = 6000) -> str:
    """결과 섹션 위주 페이지 텍스트 (스캔 PDF 대응 포함)."""
    chunks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_text = ""
            for page in pdf.pages:
                txt = page.extract_text() or ""
                total_text += txt
                if _RES_HEADER.search(txt[:300]) or is_size_related(txt):
                    chunks.append(txt)
            # 스캔 PDF: 전체 텍스트가 거의 없으면 모든 페이지 포함
            if len(total_text.strip()) < 200:
                chunks = []  # 빈 텍스트는 vision에서 처리
    except Exception:
        pass
    combined = "\n\n".join(chunks)
    return combined[:max_chars]


# ── 페이지 이미지 추출 (PyMuPDF) ──────────────────────────────────────────────
def extract_figure_pages_b64(pdf_path: str, dpi: int = 150,
                              max_pages: int = 8) -> list[dict]:
    """결과 섹션 페이지를 base64 이미지로 변환.
    스캔 PDF(텍스트 없음) → 전 페이지 포함으로 자동 전환."""
    if not fitz_ok:
        return []
    images = []
    try:
        fitz.TOOLS.mupdf_display_errors(False)  # MuPDF 구조 트리 경고 억제
        doc = fitz.open(pdf_path)
        mat = fitz.Matrix(dpi / 72, dpi / 72)

        # 스캔 PDF 감지: 전체 페이지 텍스트 합계가 200자 미만
        total_txt = "".join(p.get_text() for p in doc)
        is_scanned = len(total_txt.strip()) < 200

        for page in doc:
            txt = page.get_text()
            # 스캔 PDF는 모든 페이지 포함, 일반 PDF는 결과 섹션만
            if not is_scanned:
                if not (_RES_HEADER.search(txt[:300]) or is_size_related(txt)):
                    continue
            pix = page.get_pixmap(matrix=mat)
            buf = io.BytesIO(pix.tobytes("jpeg", jpg_quality=75))
            b64 = base64.b64encode(buf.getvalue()).decode()
            images.append({"type": "image_url",
                           "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                                         "detail": "low"}})
            if len(images) >= max_pages:
                break
        doc.close()
    except Exception:
        pass
    return images


# ── GPT 프롬프트 ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a materials scientist extracting CeO2 nanoparticle characterization data.

Extract ALL of the following from tables or figures:
- particle_size_tem_nm     : TEM primary particle size (nm, number). PRIMARY particles only.
- crystallite_size_xrd_nm  : XRD crystallite size via Scherrer equation (nm, number).
- particle_size_sem_nm     : SEM particle size (nm, number). PRIMARY particles only.
- bet_surface_area_m2g     : BET specific surface area (m²/g, number).
- morphology               : particle shape — one of: sphere, cube, rod, wire, flower, plate, porous, hollow, octahedron, or null.
- crystal_phase            : dominant crystal phase string (e.g. "fluorite cubic", "Ce2O3") or null.

Rules:
- EXCLUDE: DLS/hydrodynamic, agglomerate, pore size, film thickness, wavelength.
- For ranges → midpoint (5–20 nm → 12.5).
- For multiple samples → pick the UNDOPED / baseline / pure CeO2 sample.
- null for any field not clearly stated.

Return ONLY valid JSON (no markdown):
{"particle_size_tem_nm": <number or null>, "crystallite_size_xrd_nm": <number or null>, "particle_size_sem_nm": <number or null>, "bet_surface_area_m2g": <number or null>, "morphology": <string or null>, "crystal_phase": <string or null>}"""


def ask_gpt_text(title: str, tables_text: str, page_text: str) -> dict:
    content = f"Title: {title}\n\n"
    if tables_text:
        content += f"[TABLES]\n{tables_text[:3500]}\n\n"
    if page_text:
        content += f"[PAGE TEXT]\n{page_text[:2500]}"

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user",   "content": content}],
            max_tokens=150,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:
        tqdm.write(f"    GPT-text 오류: {e}")
        return {}


def ask_gpt_vision(title: str, images: list[dict]) -> dict:
    if not images:
        return {}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": f"Title: {title}\n\nExtract particle size data from these PDF pages."},
            *images,
        ]},
    ]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=150,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:
        tqdm.write(f"    GPT-vision 오류: {e}")
        return {}


def safe_nm(val) -> float | None:
    """값이 유효한 입자크기(0.3~500nm)이면 float, 아니면 None."""
    try:
        v = float(val)
        return v if 0.3 <= v <= 500 else None
    except Exception:
        return None

def safe_bet(val) -> float | None:
    """BET 표면적 유효 범위 (1~1500 m²/g)."""
    try:
        v = float(val)
        return v if 1.0 <= v <= 1500 else None
    except Exception:
        return None

VALID_MORPHOLOGIES = {"sphere", "cube", "rod", "wire", "flower", "plate",
                      "porous", "hollow", "octahedron"}

def safe_morph(val) -> str | None:
    """GPT가 반환한 morphology 문자열 검증."""
    if not val or not isinstance(val, str):
        return None
    v = val.strip().lower()
    return v if v in VALID_MORPHOLOGIES else None


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    # 1. CSV 로드
    csv_path = MERGED_CSV if os.path.exists(MERGED_CSV) else RAW_CSV
    print(f"데이터 로드: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  총 {len(df):,}행")

    # particle_size_primary_nm 없으면 생성
    for col in ["particle_size_tem_nm", "crystallite_size_xrd_nm",
                "particle_size_sem_nm", "bet_surface_area_m2g"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    if "particle_size_primary_nm" not in df.columns:
        df["particle_size_primary_nm"] = np.nan
        for col in ["particle_size_tem_nm", "particle_size_sem_nm"]:  # XRD 결정자 크기 제외
            if col in df.columns:
                df["particle_size_primary_nm"] = df["particle_size_primary_nm"].fillna(df[col])

    # 2. 대상 DOI: TEM AND SEM 모두 null인 샘플의 논문 (composite 목표 기준)
    missing_mask = (
        df["particle_size_tem_nm"].isna() &
        df.get("particle_size_sem_nm", pd.Series(np.nan, index=df.index)).isna()
    )
    missing_dois = set(df.loc[missing_mask, "doi"].dropna().astype(str))

    # PDF 파일이 있는 DOI만 추출
    pdf_stems = {
        os.path.splitext(fn)[0].lower()
        for fn in os.listdir(PDF_DIR) if fn.endswith(".pdf")
    }
    targets = []
    for doi in missing_dois:
        stem = doi_to_stem(doi)
        if stem in pdf_stems:
            title_rows = df[df["doi"].astype(str) == doi]["title"]
            title = title_rows.iloc[0] if not title_rows.empty else ""
            targets.append({"doi": doi, "stem": stem, "title": str(title)})

    if args.limit:
        targets = targets[:args.limit]

    mode_label = "표+그림(vision)" if args.vision else "표(text)"
    cache_path = VISION_CACHE_PATH if args.vision else TEXT_CACHE_PATH
    est_unit   = 0.005 if args.vision else 0.0003
    print(f"\n모드             : {mode_label}")
    print(f"입자크기 누락 샘플: {missing_mask.sum():,}개")
    print(f"해당 논문 수      : {len(missing_dois):,}편")
    print(f"PDF 있는 논문     : {len(targets):,}편  ← 처리 대상")
    print(f"예상 비용         : ~${len(targets) * est_unit:.2f}")
    if args.vision:
        print("  (GPT-4o vision: 페이지당 ~$0.001, 논문당 최대 8페이지)")

    if args.dry_run:
        print("\n--dry-run 종료")
        return

    # 3. 캐시 로드 (text/vision 분리)
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        done_dois = set(cache.get("done_dois", []))
        results   = cache.get("results", {})
        print(f"캐시({mode_label}): {len(done_dois):,}편 완료")
    else:
        done_dois, results = set(), {}
        print(f"캐시 없음 — {mode_label} 처음 실행")

    targets = [t for t in targets if t["doi"] not in done_dois]
    print(f"잔여 처리 대상    : {len(targets):,}편\n")

    # 4. 추출 루프
    updated = 0
    for i, paper in enumerate(tqdm(targets, desc="표/그림 추출")):
        doi   = paper["doi"]
        stem  = paper["stem"]
        title = paper["title"]
        pdf_p = os.path.join(PDF_DIR, stem + ".pdf")

        # 손상/빈 PDF 사전 체크 (1KB 미만 → 스킵)
        try:
            if os.path.getsize(pdf_p) < 1024:
                tqdm.write(f"  [스킵] 빈/손상 PDF ({doi[:40]})")
                done_dois.add(doi)
                continue
        except OSError:
            done_dois.add(doi)
            continue

        # 표 + 페이지 텍스트 추출 (항상 실행)
        tables_text = extract_tables_text(pdf_p)
        page_text   = extract_result_pages_text(pdf_p)

        found = {}
        if tables_text or page_text:
            found = ask_gpt_text(title, tables_text, page_text)

        if args.vision:
            # vision 모드: 텍스트에서 찾았어도 그림까지 분석
            images = extract_figure_pages_b64(pdf_p)
            if images:
                vision_found = ask_gpt_vision(title, images)
                # 텍스트에서 못 찾은 값만 vision 결과로 보완
                for k in ["particle_size_tem_nm", "crystallite_size_xrd_nm",
                          "particle_size_sem_nm", "bet_surface_area_m2g",
                          "morphology", "crystal_phase"]:
                    if found.get(k) is None and vision_found.get(k) is not None:
                        found[k] = vision_found[k]

        done_dois.add(doi)

        tem   = safe_nm(found.get("particle_size_tem_nm"))
        xrd   = safe_nm(found.get("crystallite_size_xrd_nm"))
        sem   = safe_nm(found.get("particle_size_sem_nm"))
        bet   = safe_bet(found.get("bet_surface_area_m2g"))
        morph = safe_morph(found.get("morphology"))
        phase = str(found["crystal_phase"]).strip() if found.get("crystal_phase") else None

        any_found = any(v is not None for v in [tem, xrd, sem, bet, morph, phase])

        if any_found:
            results[doi] = {k: v for k, v in {
                "particle_size_tem_nm":    tem,
                "crystallite_size_xrd_nm": xrd,
                "particle_size_sem_nm":    sem,
                "bet_surface_area_m2g":    bet,
                "morphology":              morph,
                "crystal_phase":           phase,
            }.items() if v is not None}

            # DataFrame 업데이트
            mask = df["doi"].astype(str) == doi
            for col, val in [
                ("particle_size_tem_nm",    tem),
                ("crystallite_size_xrd_nm", xrd),
                ("particle_size_sem_nm",    sem),
                ("bet_surface_area_m2g",    bet),
                ("morphology",              morph),
                ("crystal_phase",           phase),
            ]:
                if val is None:
                    continue
                if col not in df.columns:
                    df[col] = np.nan
                null_col = df[col].isna() if col not in ("morphology", "crystal_phase") \
                           else df[col].isna() | (df[col].astype(str).str.strip() == "")
                df.loc[mask & null_col, col] = val
            updated += 1

        # composite 재계산: TEM → SEM (XRD 결정자 크기 제외)
        df["particle_size_primary_nm"] = np.nan
        for col in ["particle_size_tem_nm", "particle_size_sem_nm"]:
            if col in df.columns:
                df["particle_size_primary_nm"] = df["particle_size_primary_nm"].fillna(df[col])

        # particle_size_source 동기화 (TEM 우선)
        if "particle_size_source" not in df.columns:
            df["particle_size_source"] = pd.NA
        _tem_ok2 = df["particle_size_tem_nm"].notna() if "particle_size_tem_nm" in df.columns \
                   else pd.Series(False, index=df.index)
        _sem_ok2 = df["particle_size_sem_nm"].notna() if "particle_size_sem_nm" in df.columns \
                   else pd.Series(False, index=df.index)
        df["particle_size_source"] = np.select(
            [_tem_ok2, _sem_ok2], ["TEM", "SEM"], default=pd.NA)

        # 주기적 저장
        if (i + 1) % SAVE_INTERVAL == 0:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"done_dois": list(done_dois), "results": results}, f)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            comp = df["particle_size_primary_nm"].notna().sum()
            pct  = comp / len(df) * 100
            tqdm.write(f"  [{i+1}편] composite {comp:,}/{len(df):,} = {pct:.1f}%")

        time.sleep(0.05)

    # 5. 최종 저장
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"done_dois": list(done_dois), "results": results}, f)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # 6. 결과 요약
    comp  = df["particle_size_primary_nm"].notna().sum()
    pct   = comp / len(df) * 100
    print(f"\n완료!")
    print(f"  새로 추출된 논문 : {updated:,}편")
    print(f"  composite 커버리지: {comp:,}/{len(df):,} = {pct:.1f}%")
    if pct >= 80:
        print("  ✓ 목표 80% 달성!")
    else:
        print(f"  목표(80%)까지 {80-pct:.1f}%p 남음")

    # 추가 필드 커버리지
    extra_cols = [
        ("particle_size_sem_nm",    "SEM 입자크기"),
        ("bet_surface_area_m2g",    "BET 표면적"),
        ("morphology",              "형태(morphology)"),
        ("crystal_phase",           "결정상"),
    ]
    for col, label in extra_cols:
        if col in df.columns:
            n = df[col].notna().sum()
            print(f"  {label:<18}: {n:,}/{len(df):,} ({n/len(df)*100:.1f}%)")

    print(f"\n  저장: {csv_path}")


if __name__ == "__main__":
    main()
