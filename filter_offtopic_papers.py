"""
filter_offtopic_papers.py — 非세리아 논문 정밀 필터링

실행:
  python filter_offtopic_papers.py --dry-run    # 제거 대상 확인만 (변경 없음)
  python filter_offtopic_papers.py              # 실제 제거 수행

처리 전략 (3단계):
  1. Title/Abstract 키워드 매칭 (HTML 엔티티 디코딩 포함)
  2. 명백한 非세리아 재료 패턴 (ZnO·TiO2·NiO 등)
  3. 본문 전구체 체크 (Ce(NO3)3·CeCl3 등 합성 시작물질 탐색)

분류 계층:
  Tier1 (키워드X+샘플X): 즉시 제거, ML 영향 없음
  Tier2 명백 非세리아:   즉시 제거
  Tier2 본문 전구체 없음: 제거 (CeO2 합성 화합물 미언급)
  Tier2 본문 전구체 있음: 유지 (본문에 Ce 합성 시작물질 확인)
  Tier3 (키워드O):       유지
"""

import argparse
import html
import os
import re
import shutil
import sys
from datetime import datetime

import pandas as pd

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH  = os.path.join(BASE_DIR, "output", "ceria_synthesis_database.xlsx")
CSV_PATH    = os.path.join(BASE_DIR, "output", "ceria_samples_merged.csv")
REJECT_PATH = os.path.join(BASE_DIR, "output", "rejected_dois.csv")
TEXT_DIR    = os.path.join(BASE_DIR, "text")

# ── HTML 클리닝 ──────────────────────────────────────────────────────────────
_TAG_RE = re.compile(r"<[^>]+>")

def clean_html(text: str) -> str:
    if not text:
        return ""
    t = html.unescape(str(text))   # &lt; &gt; &amp; &#x2082; 등
    t = _TAG_RE.sub("", t)          # <sub> <i> <b> 등 태그 제거
    return t


# ── 세리아 키워드 (Title/Abstract) ────────────────────────────────────────────
# 34차: "ceric"/"cerous"(Ce4+/Ce3+ 화학명 표기) 누락 발견 — 이 표기만 쓰는 논문이
# 잘못 제거될 위험이 있어 추가. 백업 파일로 실제 영향 검증: 3,307건 제거 중 이
# 표기 부재로 인한 오제거는 0건(단어경계 없이 검증했을 때 나온 8건 후보는 전부
# "glyceric acid" 등 무관 단어의 부분문자열 오탐이었고, 단어경계를 넣은 뒤 남은
# 2건도 세리아 나노입자 합성과 무관한 논문으로 확인). 실제 손실은 없었지만
# 향후 재수집 시를 위해 방어적으로 추가 — 단어경계(\b) 필수(glyceric 등 오탐 방지).
CERIA_META = re.compile(
    r"ceria|nanoceria|CeO\s*2|cerium.dioxide|cerium.oxide|Ce2O3"
    r"|cerium.nanopart|cerium.precursor|cerium.nitrate|cerium.chloride"
    r"|cerium.acetate|cerium.carbonate|cerium.hydroxide|cerium.sulfate"
    r"|cerium\s*\(IV\)|cerium\s*\(III\)|SDC\b|GDC\b|YDC\b"
    r"|samarium.doped.ceria|gadolinium.doped.ceria|yttrium.doped.ceria"
    r"|CeZr|Ce\d*Zr\d*O|Ce\s*0\.[0-9]|CeO₂|Ce₂O₃"
    r"|\bceric\b|\bcerous\b",
    re.IGNORECASE,
)


# ── CeO2 합성 전구체 (본문 체크용 — 합성 섹션에서 등장하는 화합물) ──────────
CERIA_PRECURSOR = re.compile(
    r"CeO2|ceria|cerium\s+oxide|cerium\s+dioxide|nanoceria"
    r"|Ce\s*\(\s*NO3\s*\)|cerium\s+nitrate"
    r"|CeCl3|Ce\s*Cl\b|cerium\s+chloride"
    r"|Ce\s*\(\s*CH3COO\s*\)|cerium\s+acetate"
    r"|Ce2\s*\(\s*SO4\s*\)|cerium\s+sulfate"
    r"|Ce\s*\(\s*OH\s*\)|cerium\s+hydroxide|cerium\s+carbonate"
    r"|Ce2O3|Ce\s*O\s*2\b"
    r"|\bceric\s+(?:nitrate|chloride|sulfate|ammonium)\b"
    r"|\bcerous\s+(?:nitrate|chloride|sulfate|acetate|carbonate|hydroxide|oxalate)\b",
    re.IGNORECASE,
)


# ── 명백한 非세리아 재료 (제목 기준) ─────────────────────────────────────────
NON_CERIA_EXPLICIT = re.compile(
    r"\b(ZnO|TiO2|Fe3O4|Fe2O3|ZnS|CuO|NiO|MnO2|Al2O3|SiO2|SnO2|In2O3"
    r"|WO3|MoO3|Bi2O3|V2O5|CoO|Mn3O4|ZrO2|La2O3|Y2O3|Gd2O3|BaTiO3"
    r"|SrTiO3|BiFeO3|Co3O4|spinel\s+ferrite|carbon\s+nanotube|carbon\s+dot"
    r"|graphene\s+oxide|silver\s+nanopart|gold\s+nanopart|copper\s+nanopart"
    r"|zinc\s+nanopart|titanium\s+dioxide|iron\s+oxide\s+nanopart"
    r"|nickel\s+nanopart|manganese\s+oxide\s+nanopart|zinc\s+oxide\s+nanopart"
    r"|bismuth\s+nanopart|silver\s+nanow|silver\s+nanoprism)\b",
    re.IGNORECASE,
)


def _load_xlsx(path: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    hrow = 0
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            hrow = idx
            break
    return pd.read_excel(path, sheet_name=0, header=hrow)


def has_ceria_meta(text) -> bool:
    return bool(CERIA_META.search(clean_html(str(text)))) if pd.notna(text) else False


def is_explicit_non_ceria(title) -> bool:
    t = clean_html(str(title)) if pd.notna(title) else ""
    return bool(NON_CERIA_EXPLICIT.search(t)) and not has_ceria_meta(t)


def _doi_to_filename(doi: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", str(doi).strip()) + ".txt"


def body_has_precursor(doi: str, all_text_files: set, read_chars: int = 6000) -> bool | None:
    fn = _doi_to_filename(doi)
    if fn not in all_text_files:
        return None  # 파일 없음
    try:
        with open(os.path.join(TEXT_DIR, fn), "r", encoding="utf-8", errors="ignore") as f:
            body = f.read(read_chars)
        return bool(CERIA_PRECURSOR.search(body))
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="변경 없이 제거 대상만 보고")
    args = parser.parse_args()

    print("=" * 62)
    print("  非세리아 논문 정밀 필터링 (HTML 디코딩 + 본문 전구체 체크)")
    print(f"  모드: {'DRY-RUN (변경 없음)' if args.dry_run else '실제 실행'}")
    print("=" * 62)

    # ── 데이터 로드 ─────────────────────────────────────────────────────────
    print(f"\n[1] 데이터 로드")
    df = _load_xlsx(EXCEL_PATH)
    doi_col = next((c for c in df.columns if "doi" in str(c).lower()), "doi")
    print(f"    Excel: {len(df):,}건")

    csv_df = pd.read_csv(CSV_PATH, low_memory=False)
    csv_dois = set(csv_df["doi"].dropna().astype(str).str.strip())
    print(f"    CSV:   {len(csv_df):,}행")

    all_text_files = set(os.listdir(TEXT_DIR))

    # ── 키워드 분류 (HTML 디코딩) ────────────────────────────────────────────
    print(f"\n[2] 키워드 분류 (HTML 엔티티 디코딩 적용)")
    df["_t"]   = df["title"].apply(has_ceria_meta)
    df["_a"]   = df["abstract"].apply(has_ceria_meta) if "abstract" in df.columns else False
    df["_any"] = df["_t"] | df["_a"]
    df["_in_csv"] = df[doi_col].astype(str).str.strip().isin(csv_dois)

    tier1_mask = ~df["_any"] & ~df["_in_csv"]
    tier2_mask = ~df["_any"] &  df["_in_csv"]
    tier3_mask =  df["_any"]

    print(f"    Tier3 (키워드O, 유지):           {tier3_mask.sum():,}건")
    print(f"    Tier1 (키워드X+샘플X, 제거):      {tier1_mask.sum():,}건")
    print(f"    Tier2 (키워드X+샘플O, 정밀검사):  {tier2_mask.sum():,}건")

    # ── Tier2 상세 분류 ──────────────────────────────────────────────────────
    print(f"\n[3] Tier2 정밀 분류 (명백 非세리아 + 본문 전구체 체크)")
    tier2_df = df[tier2_mask].copy()
    tier2_df["_explicit_non"] = tier2_df["title"].apply(is_explicit_non_ceria)

    tier2_normal = tier2_df[~tier2_df["_explicit_non"]]
    print(f"    Tier2 명백 非세리아 (ZnO·TiO2 등): {tier2_df['_explicit_non'].sum()}건")
    print(f"    Tier2 본문 전구체 체크 대상:         {len(tier2_normal)}건")

    print(f"    본문 체크 중 (최대 6000자)...", end=" ", flush=True)
    tier2_normal = tier2_normal.copy()
    tier2_normal["_body"] = tier2_normal[doi_col].apply(
        lambda d: body_has_precursor(str(d).strip(), all_text_files)
    )
    print("완료")

    body_yes  = tier2_normal["_body"] == True
    body_no   = tier2_normal["_body"] == False
    body_null = tier2_normal["_body"].isna()

    print(f"      본문 전구체 있음 → 유지: {body_yes.sum()}건")
    print(f"      본문 전구체 없음 → 제거: {body_no.sum()}건")
    print(f"      파일 없음        → 유지: {body_null.sum()}건")

    # ── 최종 제거 DOI 집합 ───────────────────────────────────────────────────
    remove_dois: set[str] = set()
    remove_dois |= set(df.loc[tier1_mask, doi_col].astype(str).str.strip())
    remove_dois |= set(tier2_df.loc[tier2_df["_explicit_non"], doi_col].astype(str).str.strip())
    remove_dois |= set(tier2_normal.loc[body_no, doi_col].astype(str).str.strip())

    remove_mask_db = df[doi_col].astype(str).str.strip().isin(remove_dois)
    csv_remove_mask = csv_df["doi"].astype(str).str.strip().isin(remove_dois)
    size_col = "particle_size_primary_nm"

    print(f"\n[결과 요약]")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  제거 대상:")
    print(f"    Tier1 (키워드X+샘플X):           {tier1_mask.sum():,}건")
    print(f"    Tier2 명백 非세리아:               {tier2_df['_explicit_non'].sum():,}건")
    print(f"    Tier2 본문 전구체 없음:            {body_no.sum():,}건")
    print(f"    합계 (중복 제외):                  {len(remove_dois):,}건")
    print(f"  유지 대상:")
    print(f"    Tier3 (키워드O):                  {tier3_mask.sum():,}건")
    print(f"    Tier2 본문 전구체 확인:            {body_yes.sum():,}건")
    print(f"    Tier2 파일없음:                    {body_null.sum():,}건")
    print(f"    합계:                              {len(df) - len(remove_dois):,}건")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  CSV: {csv_remove_mask.sum():,}행 제거 / {len(csv_df):,}행 전체")
    if size_col in csv_df.columns:
        size_loss  = csv_df.loc[csv_remove_mask, size_col].notna().sum()
        size_total = csv_df[size_col].notna().sum()
        print(f"  particle_size 손실: {size_loss:,} / {size_total:,}행 "
              f"({size_loss / size_total * 100:.1f}%)")

    # 예시 출력
    print(f"\n[제거 예시 — Tier2 명백 非세리아 15건]")
    for _, r in tier2_df[tier2_df["_explicit_non"]][["doi", "title"]].head(15).iterrows():
        print(f"  {str(r['doi'])[:35]:35s} | {clean_html(str(r['title']))[:68]}")

    if args.dry_run:
        print("\n[DRY-RUN] 변경 없이 종료합니다.")
        return

    # ── 실제 실행 ────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Excel 백업 + 저장
    backup_excel = EXCEL_PATH.replace(".xlsx", f"_backup_filter_{ts}.xlsx")
    shutil.copy2(EXCEL_PATH, backup_excel)
    df_clean = df[~remove_mask_db].drop(
        columns=["_t", "_a", "_any", "_in_csv"], errors="ignore"
    )
    df_clean.to_excel(EXCEL_PATH, index=False)
    print(f"\n[실행] Excel 백업: {os.path.basename(backup_excel)}")
    print(f"       Excel 저장: {len(df_clean):,}건 ({len(df):,} → {len(df_clean):,})")

    # CSV 백업 + 저장
    backup_csv = CSV_PATH.replace(".csv", f"_backup_filter_{ts}.csv")
    shutil.copy2(CSV_PATH, backup_csv)
    csv_clean = csv_df[~csv_remove_mask]
    csv_clean.to_csv(CSV_PATH, index=False)
    print(f"       CSV 백업: {os.path.basename(backup_csv)}")
    print(f"       CSV 저장: {len(csv_clean):,}행 ({len(csv_df):,} → {len(csv_clean):,})")

    # 제거 목록 저장
    reject_df = df[remove_mask_db][[doi_col, "title", "year"]].copy()
    reject_df["remove_reason"] = "tier1"
    reject_df.loc[
        reject_df[doi_col].astype(str).str.strip().isin(
            set(tier2_df.loc[tier2_df["_explicit_non"], doi_col].astype(str).str.strip())
        ), "remove_reason"
    ] = "tier2_explicit_non_ceria"
    reject_df.loc[
        reject_df[doi_col].astype(str).str.strip().isin(
            set(tier2_normal.loc[body_no, doi_col].astype(str).str.strip())
        ), "remove_reason"
    ] = "tier2_no_body_precursor"
    reject_df.to_csv(REJECT_PATH, index=False, encoding="utf-8-sig")
    print(f"       제거 목록: {REJECT_PATH}")

    print(f"\n완료!")
    print(f"  ⚠️  이후 실행 필요: main.py --reset --from 3")


if __name__ == "__main__":
    main()
