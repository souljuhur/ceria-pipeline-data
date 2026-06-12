"""
전체 4,388편 중 전문(full text) 확인 불가 논문 수 파악
- text/ 폴더: PDF에서 추출된 텍스트 (전문)
- abstract만 있는 논문: 텍스트 파일 없고 abstract 컬럼만 존재
"""
import pandas as pd, os, glob

_BASE  = r"d:\머신러닝 교육\ceria_pipeline_data"
_XLSX  = os.path.join(_BASE, "output", "ceria_synthesis_database.xlsx")
_TEXT  = os.path.join(_BASE, "text")
_PDF   = os.path.join(_BASE, "pdf")

# ── 1. 파일 수 ──────────────────────────────────────────────────────────────
txt_files = set(os.path.splitext(os.path.basename(f))[0]
                for f in glob.glob(os.path.join(_TEXT, "*.txt")))
pdf_files = set(os.path.splitext(os.path.basename(f))[0]
                for f in glob.glob(os.path.join(_PDF, "*.pdf")))

print(f"text/ 파일 수:  {len(txt_files):,}개")
print(f"pdf/  파일 수:  {len(pdf_files):,}개")

# ── 2. Excel 로드 ───────────────────────────────────────────────────────────
df = pd.read_excel(_XLSX, sheet_name=0)
total = len(df)
print(f"\nExcel 총 레코드: {total:,}편")
print(f"컬럼 목록: {list(df.columns)}\n")

# ── 3. 텍스트 소스 컬럼 확인 ────────────────────────────────────────────────
for col in ["text_source", "text_length", "abstract", "full_text",
            "pdf_url", "has_pdf", "has_full_text"]:
    if col in df.columns:
        nn = df[col].notna().sum()
        print(f"  [{col}] 값 있음: {nn:,}편")

# ── 4. DOI 기반으로 text 파일 매칭 ─────────────────────────────────────────
def _doi_to_stem(doi):
    """DOI → 파일명 stem (슬래시, 특수문자 → 언더스코어)"""
    if not doi or pd.isna(doi):
        return None
    return str(doi).strip().replace("/", "_").replace(":", "_").lower()

has_text   = 0
has_pdf_only = 0
abstract_only = 0
no_content = 0

for _, row in df.iterrows():
    doi   = row.get("doi")
    stem  = _doi_to_stem(doi)

    in_text = stem and stem in txt_files
    in_pdf  = stem and stem in pdf_files

    if in_text:
        has_text += 1
    elif in_pdf:
        has_pdf_only += 1
    else:
        # abstract 유무 확인
        abst = row.get("abstract")
        if pd.notna(abst) and str(abst).strip():
            abstract_only += 1
        else:
            no_content += 1

print(f"\n=== 전문 접근 가능 여부 ===")
print(f"  전문 텍스트 있음 (text/*.txt):       {has_text:>6,}편  ({has_text/total*100:.1f}%)")
print(f"  PDF만 있음 (미추출):                 {has_pdf_only:>6,}편  ({has_pdf_only/total*100:.1f}%)")
print(f"  초록만 있음 (전문 없음):             {abstract_only:>6,}편  ({abstract_only/total*100:.1f}%)")
print(f"  내용 없음 (초록조차 없음):           {no_content:>6,}편  ({no_content/total*100:.1f}%)")
print(f"\n  ▶ 전문 확인 불가 (초록만 or 내용없음): {abstract_only + no_content:>6,}편  ({(abstract_only+no_content)/total*100:.1f}%)")

# ── 5. abstract 길이 분포 (전문 없는 논문들) ─────────────────────────────────
if "abstract" in df.columns:
    print(f"\n=== 초록 길이 분포 (전체) ===")
    abst_len = df["abstract"].dropna().apply(lambda x: len(str(x)))
    for bucket, label in [(0,"없음"),(1,  "1-99자"),(100,"100-299자"),
                          (300,"300-499자"),(500,"500자 이상")]:
        if bucket == 0:
            cnt = df["abstract"].isna().sum() + (df["abstract"].fillna("").str.strip()=="").sum()
        elif bucket == 1:
            cnt = ((abst_len > 0) & (abst_len < 100)).sum()
        elif bucket == 500:
            cnt = (abst_len >= 500).sum()
        else:
            hi = bucket + 200
            cnt = ((abst_len >= bucket) & (abst_len < hi)).sum()
        print(f"  {label:<15} {cnt:>6,}편")
