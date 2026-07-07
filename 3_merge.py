"""
샘플-논문 데이터 병합 (TEM 커버리지 35% → 80%+ 달성)

- ceria_samples.csv (GPT 샘플-레벨 추출) +
  ceria_synthesis_database.xlsx (규칙기반 논문-레벨 추출)
- DOI 기준 Join → 누락 필드를 논문-레벨로 보완
- particle_size_primary_nm 파생: TEM → SEM 우선순위 (1차 입자; XRD 결정자 크기 제외)
- 출력: output/ceria_samples_merged.csv

CMD:
  conda activate test
  python run_merge_samples.py
"""
import os
import numpy as np
import pandas as pd

BASE_DIR   = r"d:\머신러닝 교육\ceria_pipeline_data"
SAMPLES_IN = os.path.join(BASE_DIR, "output", "ceria_samples.csv")
EXCEL_PATH = os.path.join(BASE_DIR, "output", "ceria_synthesis_database.xlsx")
OUT_CSV    = os.path.join(BASE_DIR, "output", "ceria_samples_merged.csv")

# Excel컬럼명 → 샘플CSV컬럼명 매핑 (같은 이름이면 자동 처리됨)
COLUMN_ALIAS = {
    "bet_surface_area": "bet_surface_area_m2g",
}

# 보완 대상 필드 (중요도 순)
FILL_COLS = [
    "particle_size_tem_nm",
    "crystallite_size_xrd_nm",
    "particle_size_sem_nm",
    "synthesis_method",
    "synthesis_temperature_c",
    "synthesis_time_h",
    "calcination_temperature_c",
    "calcination_time_h",
    "ph_synthesis",
    "morphology",
    "crystal_phase",
    "bet_surface_area_m2g",
    "ce_precursor",
    "solvent",
    "mineralizer",
    "capping_agent",
    "chelating_agent",
    "oxidant",
    "dopant",
    "atmosphere",
]

SIZE_COLS = ["particle_size_tem_nm", "particle_size_sem_nm"]  # composite: TEM+SEM만 (XRD는 결정자 크기)
KEY_REPORT_COLS = [
    "particle_size_tem_nm", "crystallite_size_xrd_nm", "particle_size_sem_nm",
    "particle_size_primary_nm", "synthesis_method", "synthesis_temperature_c",
    "morphology", "crystal_phase",
]


def _load_xlsx(path):
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)


def normalize_doi(doi) -> str:
    if pd.isna(doi):
        return ""
    return str(doi).strip().lower()


def coverage(df: pd.DataFrame, label: str) -> None:
    n = len(df)
    print(f"\n[{label}] {n:,}샘플 커버리지")
    for col in KEY_REPORT_COLS:
        if col not in df.columns:
            continue
        filled = df[col].notna().sum()
        print(f"  {col:<38} {filled:>5}/{n}  ({filled/n*100:5.1f}%)")


def main() -> None:
    # ── 1. 로드 ───────────────────────────────────────────────────────────────
    print(f"샘플 CSV 로드  : {SAMPLES_IN}")
    samples = pd.read_csv(SAMPLES_IN, low_memory=False)
    print(f"  → {len(samples):,}행, {samples.shape[1]}컬럼")

    print(f"논문 Excel 로드: {EXCEL_PATH}")
    papers = _load_xlsx(EXCEL_PATH)
    print(f"  → {len(papers):,}행, {papers.shape[1]}컬럼")

    # ── 2. DOI 키 생성 ────────────────────────────────────────────────────────
    samples["_doi"] = samples["doi"].apply(normalize_doi)
    papers["_doi"]  = papers["doi"].apply(normalize_doi) if "doi" in papers.columns \
                      else pd.Series("", index=papers.index)

    coverage(samples, "병합 전")

    # ── 3. Excel 컬럼명 정규화 (alias 처리) ───────────────────────────────────
    papers = papers.rename(columns=COLUMN_ALIAS)

    # ── 4. DOI별 논문-레벨 값 맵 구성 ────────────────────────────────────────
    paper_lookup = papers.set_index("_doi")

    merged = samples.copy()
    # ArrowDtype → object 변환: Arrow string 컬럼에 숫자 할당 시 TypeError 방지
    for col in FILL_COLS:
        if col in merged.columns:
            try:
                merged[col] = merged[col].astype(object)
            except Exception:
                pass
    fill_summary = []

    for dst_col in FILL_COLS:
        # 샘플에 해당 컬럼이 없으면 생성
        if dst_col not in merged.columns:
            merged[dst_col] = np.nan

        # Excel에 해당 컬럼 없으면 스킵
        if dst_col not in paper_lookup.columns:
            continue

        src_series = paper_lookup[dst_col].dropna()
        if src_series.empty:
            continue

        doi_map = src_series.to_dict()

        # 누락된 행 + DOI 매칭 행만 채우기
        null_mask = merged[dst_col].isna()
        match_mask = merged["_doi"].isin(doi_map) & null_mask
        if match_mask.any():
            merged.loc[match_mask, dst_col] = merged.loc[match_mask, "_doi"].map(doi_map)
            fill_summary.append((dst_col, int(match_mask.sum())))

    # ── 5. 보완 결과 출력 ─────────────────────────────────────────────────────
    if fill_summary:
        print("\n[보완 결과]")
        for col, cnt in fill_summary:
            print(f"  +{cnt:>4}행  {col}")
    else:
        print("\n[보완 결과] 보완된 행 없음 (Excel에 동일 필드 없음)")

    # ── 6. 수치 이상값 제거 ────────────────────────────────────────────────────
    # TEM/SEM: 0.3~500nm (1차 입자)
    for col in SIZE_COLS:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
            merged.loc[~merged[col].between(0.3, 500, inclusive="both"), col] = np.nan
    # XRD 결정자 크기: 별도 범위 0.3~200nm (composite에 포함하지 않음)
    if "crystallite_size_xrd_nm" in merged.columns:
        merged["crystallite_size_xrd_nm"] = pd.to_numeric(
            merged["crystallite_size_xrd_nm"], errors="coerce")
        merged.loc[~merged["crystallite_size_xrd_nm"].between(0.3, 200, inclusive="both"),
                   "crystallite_size_xrd_nm"] = np.nan

    # ── 7. 1차 입자크기 파생: TEM → SEM (XRD 결정자 크기 제외) ──────────────
    merged["particle_size_primary_nm"] = np.nan
    for col in SIZE_COLS:
        if col in merged.columns:
            merged["particle_size_primary_nm"] = merged["particle_size_primary_nm"].fillna(
                merged[col])

    source_conditions = []
    source_values = []
    for col, label in zip(SIZE_COLS, ["TEM", "SEM"]):
        if col in merged.columns:
            source_conditions.append(merged[col].notna())
            source_values.append(label)

    if source_conditions:
        merged["particle_size_source"] = np.select(
            source_conditions, source_values, default=pd.NA)

    # ── 8. 임시 컬럼 제거 ─────────────────────────────────────────────────────
    merged.drop(columns=["_doi"], inplace=True, errors="ignore")

    # ── 9. 병합 후 커버리지 ───────────────────────────────────────────────────
    coverage(merged, "병합 후")

    # ── 10. 저장 ──────────────────────────────────────────────────────────────
    merged.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT_CSV}  ({len(merged):,}행)")

    comp = merged["particle_size_primary_nm"].notna()
    pct  = comp.sum() / len(merged) * 100
    print(f"\n복합 입자크기 커버리지: {comp.sum():,}/{len(merged):,} = {pct:.1f}%")
    if pct >= 80:
        print("  ✓ 목표 80% 달성!")
    else:
        print(f"  → 목표(80%)까지 {80-pct:.1f}%p 부족")

    src_dist = merged.get("particle_size_source", pd.Series(dtype=str)).value_counts()
    if not src_dist.empty:
        print("\n[입자크기 출처 분포]")
        for src, cnt in src_dist.items():
            print(f"  {src}: {cnt:,}샘플")


if __name__ == "__main__":
    main()
