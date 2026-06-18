#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CeO2 합성 논문 파이프라인 — 데이터 품질 점검 스크립트
대상: output/ceria_samples_merged.csv
"""

import sys
import os
import re
import pandas as pd
import numpy as np

# 출력 인코딩 설정
sys.stdout.reconfigure(encoding="utf-8")

CSV_PATH = r"d:\머신러닝 교육\ceria_pipeline_data\output\ceria_samples_merged.csv"

def load_csv():
    df = pd.read_csv(CSV_PATH, low_memory=False, dtype=str)
    print(f"[로드 완료] {len(df):,}행 x {len(df.columns)}열")
    return df

def to_num(series):
    """문자열 컬럼을 숫자로 강제 변환 (변환 불가 → NaN)"""
    return pd.to_numeric(series, errors="coerce")

def show_samples(df, mask, cols, label, max_n=10):
    sub = df[mask][cols].head(max_n)
    if sub.empty:
        return
    print(f"\n  [샘플 {label} — 최대 {max_n}건]")
    print(sub.to_string(index=False))

def sep(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def check_ce_precursor(df):
    sep("1. ce_precursor — 비-Ce 화합물 감지")
    col = "ce_precursor"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    valid = df[col].notna() & (df[col].str.strip() != "") & (df[col].str.lower() != "none") & (df[col].str.lower() != "nan")
    sub = df[valid]
    total = len(sub)
    print(f"  유효 값 수: {total:,}")

    # ce/cerium/ceo 미포함
    ce_pattern = re.compile(r"\bce\b|cerium|ceo|ce\(|ce2|ceiv|ceiii", re.IGNORECASE)
    bad_mask = valid & ~df[col].str.contains(ce_pattern, na=False)
    bad = df[bad_mask]
    print(f"  'ce/cerium' 미포함 값: {len(bad):,}건")
    if len(bad) > 0:
        vals = bad[col].value_counts().head(20)
        print("\n  상위 값 빈도:")
        for v, c in vals.items():
            print(f"    {c:5d}건  {v}")
    else:
        print("  -> 이상치 없음")

def check_solvent(df):
    sep("2. solvent — 비-용매 값 감지")
    col = "solvent"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    valid = df[col].notna() & (df[col].str.strip() != "") & (~df[col].str.lower().isin(["none", "nan", "n/a", "null"]))
    sub = df[valid]
    total = len(sub)
    print(f"  유효 값 수: {total:,}")

    # 숫자만 있는 값
    num_mask = valid & df[col].str.strip().str.match(r"^-?\d+(\.\d+)?$")
    print(f"  순수 숫자 값: {num_mask.sum():,}건")
    if num_mask.sum() > 0:
        show_samples(df, num_mask, [col, "doi"], "숫자값")

    # 온도로 보이는 값 (°C, degree, temperature 포함)
    temp_mask = valid & df[col].str.contains(r"°C|degree|temperature|\btemp\b|℃", na=False, case=False)
    print(f"  온도처럼 보이는 값: {temp_mask.sum():,}건")
    if temp_mask.sum() > 0:
        show_samples(df, temp_mask, [col, "doi"], "온도값")

    # Ce 전구체처럼 보이는 값
    ce_in_sol = valid & df[col].str.contains(r"\bce\b|cerium|ce\(", na=False, case=False)
    print(f"  Ce화합물이 용매로 기록: {ce_in_sol.sum():,}건")
    if ce_in_sol.sum() > 0:
        show_samples(df, ce_in_sol, [col, "doi"], "Ce화합물-용매")

    # 10자 이상의 비일반 값 (복합 문자열)
    unusual = valid & (df[col].str.len() > 80)
    print(f"  과도하게 긴 값 (>80자): {unusual.sum():,}건")
    if unusual.sum() > 0:
        show_samples(df, unusual, [col], "긴값")

def check_synthesis_temperature(df):
    sep("3. synthesis_temperature_c — 범위 이탈 및 문자열 혼재")
    col = "synthesis_temperature_c"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    # 문자열 혼재 (변환 불가)
    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패 (문자열 혼재): {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열")

    # 범위 이탈
    below = numeric.notna() & (numeric < 0)
    above = numeric.notna() & (numeric > 2000)
    print(f"  0 미만: {below.sum():,}건")
    print(f"  2000 초과: {above.sum():,}건")
    if below.sum() > 0:
        show_samples(df, below, [col, "doi"], "0미만")
    if above.sum() > 0:
        show_samples(df, above, [col, "doi"], "2000초과")

    # 정상 통계
    valid_num = numeric.dropna()
    print(f"\n  정상 범위 통계 (n={len(valid_num):,}):")
    print(f"    min={valid_num.min():.1f}, Q1={valid_num.quantile(.25):.1f}, "
          f"median={valid_num.median():.1f}, Q3={valid_num.quantile(.75):.1f}, max={valid_num.max():.1f}")

def check_ph(df):
    sep("4. ph_synthesis — 범위 이탈 (0~14 외)")
    col = "ph_synthesis"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패: {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열")

    below = numeric.notna() & (numeric < 0)
    above = numeric.notna() & (numeric > 14)
    print(f"  0 미만: {below.sum():,}건")
    print(f"  14 초과: {above.sum():,}건")
    if below.sum() > 0:
        show_samples(df, below, [col, "doi"], "0미만")
    if above.sum() > 0:
        show_samples(df, above, [col, "doi"], "14초과")

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  정상 범위 통계 (n={len(valid_num):,}):")
        print(f"    min={valid_num.min():.2f}, median={valid_num.median():.2f}, max={valid_num.max():.2f}")

def check_concentration(df, col, label, max_val=10):
    sep(f"5/6. {col} — 비정상값 (>{max_val}M, 음수)")
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패: {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열")

    neg = numeric.notna() & (numeric < 0)
    high = numeric.notna() & (numeric > max_val)
    print(f"  음수: {neg.sum():,}건")
    print(f"  {max_val}M 초과: {high.sum():,}건")
    if neg.sum() > 0:
        show_samples(df, neg, [col, "doi"], "음수")
    if high.sum() > 0:
        show_samples(df, high, [col, "doi"], f"{max_val}M초과")

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  통계 (n={len(valid_num):,}): "
              f"min={valid_num.min():.4f}, median={valid_num.median():.4f}, "
              f"Q99={valid_num.quantile(.99):.4f}, max={valid_num.max():.4f}")

def check_volume(df):
    sep("7. synthesis_volume_mL — 음수, 비정상 큰 값")
    col = "synthesis_volume_mL"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패: {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열")

    neg = numeric.notna() & (numeric < 0)
    high = numeric.notna() & (numeric > 100_000)
    print(f"  음수: {neg.sum():,}건")
    print(f"  100,000mL 초과: {high.sum():,}건")
    if neg.sum() > 0:
        show_samples(df, neg, [col, "doi"], "음수")
    if high.sum() > 0:
        show_samples(df, high, [col, "doi"], "100k초과")

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  통계 (n={len(valid_num):,}): "
              f"min={valid_num.min():.1f}, median={valid_num.median():.1f}, "
              f"Q99={valid_num.quantile(.99):.1f}, max={valid_num.max():.1f}")

def check_text_field(df, col, label, bad_patterns, good_examples=None):
    """capping_agent, chelating_agent, atmosphere 공통 점검"""
    sep(f"  {label} ({col})")
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    valid = df[col].notna() & (df[col].str.strip() != "") & (~df[col].str.lower().isin(["none", "nan", "n/a", "null"]))
    sub = df[valid]
    print(f"  유효 값 수: {len(sub):,}건")
    print(f"  고유 값 수: {df[col].nunique():,}개")

    # 고유값 빈도 상위 20개
    print("\n  상위 20개 값:")
    top20 = df[valid][col].value_counts().head(20)
    for v, c in top20.items():
        print(f"    {c:5d}건  {repr(v)}")

    # 숫자 값
    num_mask = valid & df[col].str.strip().str.match(r"^-?\d+(\.\d+)?$")
    print(f"\n  순수 숫자 값: {num_mask.sum():,}건")
    if num_mask.sum() > 0:
        show_samples(df, num_mask, [col, "doi"], "숫자")

    for pat_label, pattern in bad_patterns:
        bad = valid & df[col].str.contains(pattern, na=False, case=False)
        print(f"  [{pat_label}]: {bad.sum():,}건")
        if bad.sum() > 0:
            show_samples(df, bad, [col, "doi"], pat_label, max_n=5)

def check_calcination_temperature(df):
    sep("11. calcination_temperature_c — 범위 이탈")
    col = "calcination_temperature_c"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패: {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열")

    below = numeric.notna() & (numeric < 0)
    above = numeric.notna() & (numeric > 2000)
    print(f"  0 미만: {below.sum():,}건")
    print(f"  2000 초과: {above.sum():,}건")
    if below.sum() > 0:
        show_samples(df, below, [col, "doi"], "0미만")
    if above.sum() > 0:
        show_samples(df, above, [col, "doi"], "2000초과")

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  통계 (n={len(valid_num):,}): "
              f"min={valid_num.min():.0f}, Q1={valid_num.quantile(.25):.0f}, "
              f"median={valid_num.median():.0f}, Q3={valid_num.quantile(.75):.0f}, "
              f"max={valid_num.max():.0f}")

def check_xrd_size(df):
    sep("12. crystallite_size_xrd_nm — 현황 (2~150nm 필터 적용 전 원본)")
    col = "crystallite_size_xrd_nm"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패 (문자열): {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열", max_n=10)

    below2 = numeric.notna() & (numeric < 2)
    above150 = numeric.notna() & (numeric > 150)
    in_range = numeric.notna() & numeric.between(2, 150)
    print(f"\n  2nm 미만: {below2.sum():,}건  (Scherrer 물리적 한계)")
    print(f"  2~150nm (정상): {in_range.sum():,}건")
    print(f"  150nm 초과: {above150.sum():,}건")
    if below2.sum() > 0:
        show_samples(df, below2, [col, "doi"], "2nm미만", max_n=5)
    if above150.sum() > 0:
        show_samples(df, above150, [col, "doi"], "150nm초과", max_n=10)

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  전체 통계 (n={len(valid_num):,}): "
              f"min={valid_num.min():.2f}, median={valid_num.median():.2f}, max={valid_num.max():.2f}")

def check_synthesis_time(df):
    sep("13. synthesis_time_h — 음수, 비정상 큰 값")
    col = "synthesis_time_h"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패: {non_numeric.sum():,}건")
    if non_numeric.sum() > 0:
        show_samples(df, non_numeric, [col, "doi"], "문자열")

    neg = numeric.notna() & (numeric < 0)
    high = numeric.notna() & (numeric > 10_000)
    suspect = numeric.notna() & (numeric > 1_000) & (numeric <= 10_000)
    print(f"  음수: {neg.sum():,}건")
    print(f"  >10,000h: {high.sum():,}건")
    print(f"  1000~10000h (의심): {suspect.sum():,}건")
    if neg.sum() > 0:
        show_samples(df, neg, [col, "doi"], "음수")
    if high.sum() > 0:
        show_samples(df, high, [col, "doi"], "10000h초과")
    if suspect.sum() > 0:
        show_samples(df, suspect, [col, "doi"], "1000~10000h", max_n=5)

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  통계 (n={len(valid_num):,}): "
              f"min={valid_num.min():.2f}, Q99={valid_num.quantile(.99):.2f}, max={valid_num.max():.2f}")

def check_particle_size_primary(df):
    sep("14. particle_size_primary_nm — 현황 (0.3~500nm 필터 적용 전 원본)")
    col = "particle_size_primary_nm"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    raw = df[col]
    numeric = to_num(raw)
    valid_raw = raw.notna() & (raw.str.strip() != "") & (~raw.str.lower().isin(["none", "nan", "n/a"]))
    non_numeric = valid_raw & numeric.isna()
    print(f"  유효 원본 값: {valid_raw.sum():,}건")
    print(f"  숫자 변환 실패: {non_numeric.sum():,}건")

    below = numeric.notna() & (numeric < 0.3)
    above = numeric.notna() & (numeric > 500)
    in_range = numeric.notna() & numeric.between(0.3, 500)
    print(f"\n  0.3nm 미만: {below.sum():,}건")
    print(f"  0.3~500nm (정상): {in_range.sum():,}건")
    print(f"  500nm 초과: {above.sum():,}건")
    if below.sum() > 0:
        show_samples(df, below, [col, "doi"], "0.3nm미만", max_n=5)
    if above.sum() > 0:
        show_samples(df, above, [col, "doi"], "500nm초과", max_n=10)

    valid_num = numeric.dropna()
    if len(valid_num) > 0:
        print(f"\n  전체 통계 (n={len(valid_num):,}): "
              f"min={valid_num.min():.2f}, median={valid_num.median():.2f}, max={valid_num.max():.2f}")

def check_capping_agent(df):
    sep("8. capping_agent — 비-캡핑제 값 감지")
    col = "capping_agent"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    valid = df[col].notna() & (df[col].str.strip() != "") & (~df[col].str.lower().isin(["none", "nan", "n/a", "null", "no", "not specified", "not mentioned"]))
    sub = df[valid]
    print(f"  유효 값 수: {len(sub):,}건")

    # 상위 30개
    print("\n  상위 30개 고유값:")
    top30 = sub[col].value_counts().head(30)
    for v, c in top30.items():
        print(f"    {c:5d}건  {repr(v)}")

    # Ce 전구체 패턴
    ce_pat = sub[col].str.contains(r"\bce\b|cerium|ce\(|ce2|ceiv|ceiii|ceno3|cecl", na=False, case=False)
    print(f"\n  Ce화합물 패턴: {ce_pat.sum():,}건")
    if ce_pat.sum() > 0:
        show_samples(df[valid], ce_pat, [col, "doi"], "Ce화합물")

    # 용매 패턴
    solv_pat = sub[col].str.contains(r"\bwater\b|\bethanol\b|\bmethanol\b|\bacetone\b|distilled|deionized", na=False, case=False)
    print(f"  용매 패턴: {solv_pat.sum():,}건")
    if solv_pat.sum() > 0:
        show_samples(df[valid], solv_pat, [col, "doi"], "용매패턴")

    # 숫자
    num_pat = sub[col].str.strip().str.match(r"^-?\d+(\.\d+)?$")
    print(f"  순수 숫자: {num_pat.sum():,}건")
    if num_pat.sum() > 0:
        show_samples(df[valid], num_pat, [col, "doi"], "숫자")

def check_chelating_agent(df):
    sep("9. chelating_agent — 비-킬레이트제 값 감지")
    col = "chelating_agent"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    valid = df[col].notna() & (df[col].str.strip() != "") & (~df[col].str.lower().isin(["none", "nan", "n/a", "null", "no", "not specified", "not mentioned"]))
    sub = df[valid]
    print(f"  유효 값 수: {len(sub):,}건")

    print("\n  상위 30개 고유값:")
    top30 = sub[col].value_counts().head(30)
    for v, c in top30.items():
        print(f"    {c:5d}건  {repr(v)}")

    # Ce 전구체 패턴
    ce_pat = sub[col].str.contains(r"\bce\b|cerium|ce\(", na=False, case=False)
    print(f"\n  Ce화합물 패턴: {ce_pat.sum():,}건")
    if ce_pat.sum() > 0:
        show_samples(df[valid], ce_pat, [col, "doi"], "Ce화합물")

    # 용매 패턴
    solv_pat = sub[col].str.contains(r"\bwater\b|\bethanol\b|\bmethanol\b", na=False, case=False)
    print(f"  용매 패턴: {solv_pat.sum():,}건")
    if solv_pat.sum() > 0:
        show_samples(df[valid], solv_pat, [col, "doi"], "용매패턴")

    # 숫자
    num_pat = sub[col].str.strip().str.match(r"^-?\d+(\.\d+)?$")
    print(f"  순수 숫자: {num_pat.sum():,}건")

def check_atmosphere(df):
    sep("10. atmosphere — 유효하지 않은 값")
    col = "atmosphere"
    if col not in df.columns:
        print(f"  컬럼 없음: {col}")
        return

    valid = df[col].notna() & (df[col].str.strip() != "") & (~df[col].str.lower().isin(["none", "nan", "n/a", "null"]))
    sub = df[valid]
    print(f"  유효 값 수: {len(sub):,}건")
    print(f"  고유 값 수: {sub[col].nunique():,}개")

    print("\n  전체 고유값 빈도 (상위 40개):")
    topall = sub[col].value_counts().head(40)
    for v, c in topall.items():
        print(f"    {c:5d}건  {repr(v)}")

    # 유효 atmosphere 키워드
    valid_atm = ["air", "nitrogen", "n2", "argon", "ar", "oxygen", "o2",
                 "hydrogen", "h2", "vacuum", "ambient", "inert", "helium",
                 "he", "co2", "nh3", "forming gas", "steam", "co", "reducing"]
    valid_pat = "|".join(valid_atm)
    invalid_mask = ~sub[col].str.lower().str.contains(valid_pat, na=False)
    print(f"\n  비표준 atmosphere: {invalid_mask.sum():,}건")
    if invalid_mask.sum() > 0:
        print("\n  비표준 atmosphere 값:")
        inv_vals = sub[invalid_mask][col].value_counts().head(30)
        for v, c in inv_vals.items():
            print(f"    {c:5d}건  {repr(v)}")

    # 숫자
    num_pat = sub[col].str.strip().str.match(r"^-?\d+(\.\d+)?$")
    print(f"\n  순수 숫자: {num_pat.sum():,}건")
    if num_pat.sum() > 0:
        show_samples(df[valid], num_pat, [col, "doi"], "숫자")

def main():
    print("CeO2 합성 논문 파이프라인 — 데이터 품질 점검")
    print("=" * 70)

    df = load_csv()

    # 컬럼 목록 확인
    print("\n[컬럼 목록]")
    for i, c in enumerate(df.columns):
        print(f"  {i:2d}: {c}")

    check_ce_precursor(df)
    check_solvent(df)
    check_synthesis_temperature(df)
    check_ph(df)
    check_concentration(df, "ce_concentration_M", "ce농도", max_val=10)
    check_concentration(df, "mineralizer_concentration_M", "mineralizer농도", max_val=30)
    check_volume(df)
    check_capping_agent(df)
    check_chelating_agent(df)
    check_atmosphere(df)
    check_calcination_temperature(df)
    check_xrd_size(df)
    check_synthesis_time(df)
    check_particle_size_primary(df)

    print("\n\n" + "=" * 70)
    print("  점검 완료")
    print("=" * 70)

if __name__ == "__main__":
    main()
