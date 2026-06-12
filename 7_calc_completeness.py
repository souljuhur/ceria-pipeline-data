"""
calc_completeness.py — [Stage 2] 완성도 점수 계산 & 합성 논문 분류

- 도핑 농도/화학식/pH/전구체농도 추출
- 데이터 검증 (data_quality_flags)
- 완성도 점수 (completeness_score, 0~100%)
- 합성 논문 분류 (is_synthesis_paper)

이전 이름: run_cell19.py
"""
import pandas as pd, os, re

_BASE = r"d:\머신러닝 교육\ceria_pipeline_data"
_PATH = os.path.join(_BASE, "output", "ceria_synthesis_database.xlsx")
df19 = pd.read_excel(_PATH, sheet_name=0)
total19 = len(df19)
print(f"로드: {total19:,}편\n")

def _empty19(v):
    return pd.isna(v) or str(v).strip().lower() in ("", "nan", "none")

def _text19(row):
    return " ".join([str(row.get("title","") or ""), str(row.get("abstract","") or "")])

# ── 1. 도핑 농도 & Ce-도펀트 화학식 ──────────────────────────────────────────
_CONC_MOL = re.compile(r'(\d+(?:\.\d+)?)\s*(?:mol|at|mole|atomic)\s*%', re.I)
_CONC_X   = re.compile(r'\bx\s*=\s*(\d*\.?\d+)', re.I)
_FORMULA  = re.compile(
    r'Ce[_\s]?(\d*\.?\d+)\s*([A-Z][a-z]?)[_\s]?(\d*\.?\d+)\s*O[_\s]?\d*(?:[_\s]?-?\s*[δd])?',
    re.I
)

if "dopant_concentration" not in df19.columns:
    df19["dopant_concentration"] = None
if "dopant_formula" not in df19.columns:
    df19["dopant_formula"] = None

cnt_dc = cnt_df = 0
for idx, row in df19.iterrows():
    txt = _text19(row)
    if _empty19(row.get("dopant_formula")):
        mf = _FORMULA.search(txt)
        if mf:
            df19.at[idx, "dopant_formula"] = mf.group(0).strip()
            cnt_df += 1
            if _empty19(row.get("dopant_concentration")):
                try:
                    frac = float(mf.group(3))
                    if 0 < frac < 1:
                        df19.at[idx, "dopant_concentration"] = f"{frac*100:.1f} mol%"
                        cnt_dc += 1
                except (ValueError, IndexError):
                    pass
    if _empty19(row.get("dopant_concentration")):
        mc = _CONC_MOL.search(txt)
        if mc:
            try:
                v = float(mc.group(1))
                if 0 < v <= 100:
                    df19.at[idx, "dopant_concentration"] = f"{v} mol%"
                    cnt_dc += 1
            except (ValueError, IndexError):
                pass
    if _empty19(row.get("dopant_concentration")):
        mx = _CONC_X.search(txt)
        if mx:
            try:
                v = float(mx.group(1))
                if 0 < v < 1:
                    df19.at[idx, "dopant_concentration"] = f"x={v}"
                    cnt_dc += 1
            except (ValueError, IndexError):
                pass

print(f"  dopant_formula       추가: {cnt_df:,}편")
print(f"  dopant_concentration 추가: {cnt_dc:,}편")

# ── 2. 합성 pH ────────────────────────────────────────────────────────────────
_PH_RE = [
    re.compile(r'pH\s+(?:was\s+)?(?:adjusted\s+to\s+|set\s+to\s+|of\s+|=\s*|≈\s*)?(\d+(?:\.\d+)?)', re.I),
    re.compile(r'pH\s*[=:≈]\s*(\d+(?:\.\d+)?)', re.I),
    re.compile(r'(?:to|at)\s+pH\s+(\d+(?:\.\d+)?)', re.I),
]
if "ph_synthesis" not in df19.columns:
    df19["ph_synthesis"] = None

cnt_ph = 0
for idx, row in df19.iterrows():
    if not _empty19(row.get("ph_synthesis")):
        continue
    txt = _text19(row)
    for pat in _PH_RE:
        m = pat.search(txt)
        if m:
            try:
                v = float(m.group(1))
                if 0 <= v <= 14:
                    df19.at[idx, "ph_synthesis"] = v
                    cnt_ph += 1
                    break
            except (ValueError, IndexError):
                pass
print(f"  ph_synthesis         추가: {cnt_ph:,}편")

# ── 3. 전구체 몰농도 ──────────────────────────────────────────────────────────
_PREC_CONC = [
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:M|mol/L|mmol/L|mM)\b', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*mol(?:ar)?\s+(?:solution|concentration)', re.I),
]
if "precursor_concentration" not in df19.columns:
    df19["precursor_concentration"] = None

cnt_pc = 0
for idx, row in df19.iterrows():
    if not _empty19(row.get("precursor_concentration")):
        continue
    txt = _text19(row)
    for pat in _PREC_CONC:
        m = pat.search(txt)
        if m:
            df19.at[idx, "precursor_concentration"] = m.group(0).strip()
            cnt_pc += 1
            break
print(f"  precursor_concentration 추가: {cnt_pc:,}편")

# ── 4. 데이터 검증 ────────────────────────────────────────────────────────────
VALID_RANGES = {
    "synthesis_temperature_c":   (0,    1500),
    "calcination_temperature_c": (50,   1600),
    "drying_temperature_c":      (20,   500),
    "synthesis_time_h":          (0.01, 1000),
    "calcination_time_h":        (0.01, 200),
    "particle_size_tem_nm":      (0.3,  1000),
    "particle_size_sem_nm":      (0.3,  5000),
    "crystallite_size_xrd_nm":   (0.3,  500),
    "bet_surface_area":          (0.1,  1500),
    "ph_synthesis":              (0,    14),
}
df19["data_quality_flags"] = ""
cnt_flags = 0
for idx, row in df19.iterrows():
    flags = []
    for col, (lo, hi) in VALID_RANGES.items():
        v = row.get(col)
        if _empty19(v):
            continue
        try:
            fv = float(v)
            if not (lo <= fv <= hi):
                flags.append(f"{col}={fv}(범위:{lo}-{hi})")
        except (ValueError, TypeError):
            pass
    if flags:
        df19.at[idx, "data_quality_flags"] = "; ".join(flags)
        cnt_flags += 1
print(f"  data_quality_flags   이상값: {cnt_flags:,}편")

# ── 5. 완성도 점수 ────────────────────────────────────────────────────────────
FIELD_WEIGHTS = {
    # ── 실험 재료
    "synthesis_method":          2.0,
    "ce_precursor":              2.0,
    "solvent":                   1.5,
    "mineralizer":               1.5,
    "capping_agent":             1.0,
    "chelating_agent":           0.5,
    "oxidant":                   0.5,
    "additive":                  0.5,
    "dopant":                    1.0,
    "dopant_concentration":      1.0,
    # ── 실험 방법/절차
    "synthesis_temperature_c":   1.5,
    "synthesis_time_h":          1.5,
    "ph_synthesis":              1.0,
    "atmosphere":                1.0,
    "calcination_temperature_c": 1.0,
    "calcination_time_h":        0.5,
    # ── 결과
    "particle_size_tem_nm":      1.5,
    "crystallite_size_xrd_nm":   1.5,
    "particle_size_sem_nm":      1.0,
    "bet_surface_area":          1.0,
    "morphology":                1.5,
    "crystal_phase":             1.0,
}
MAX_SCORE = sum(FIELD_WEIGHTS.values())

df19["completeness_score"] = df19.apply(
    lambda row: round(
        sum(w for f, w in FIELD_WEIGHTS.items() if not _empty19(row.get(f)))
        / MAX_SCORE * 100, 1
    ), axis=1
)
score_mean = df19["completeness_score"].mean()
score_ge50 = (df19["completeness_score"] >= 50).sum()
print(f"  completeness_score   평균: {score_mean:.1f}% | 50%이상: {score_ge50:,}편")

# ── 6. 합성 논문 분류 ─────────────────────────────────────────────────────────
_SYNTH_KW = [
    "synthesized", "prepared", "fabricated", "synthesis", "preparation",
    "hydrothermal", "sol-gel", "precipitation", "calcin", "autoclave",
    "ce(no3)", "cecl", "cerium nitrate", "cerium chloride",
]
_NON_SYNTH_KW = [
    "review", "theoretical", "dft calculation", "molecular dynamics",
    "computational", "simulation", "first-principles",
]
df19["is_synthesis_paper"] = df19.apply(
    lambda row: (
        any(kw in _text19(row).lower() for kw in _SYNTH_KW) and
        not any(kw in _text19(row).lower() for kw in _NON_SYNTH_KW)
    ), axis=1
)
synth_count = df19["is_synthesis_paper"].sum()
print(f"  is_synthesis_paper   합성논문: {synth_count:,}편 / {total19:,}편")

# ── 7. 저장 ───────────────────────────────────────────────────────────────────
_xl = pd.ExcelFile(_PATH)
_sheets = {s: _xl.parse(s) for s in _xl.sheet_names
           if s not in ("합성조건", "Sheet1")}
_xl.close()

with pd.ExcelWriter(_PATH, engine="openpyxl") as _w:
    df19.to_excel(_w, sheet_name="합성조건", index=False)
    for _sn, _sd in _sheets.items():
        _sd.to_excel(_w, sheet_name=_sn, index=False)

print(f"\n저장 완료: {_PATH}")
print(f"\n── 최종 채움률 ─────────────────────────────────────────")
for col in ["synthesis_method", "ce_precursor", "dopant_concentration",
            "dopant_formula", "ph_synthesis", "precursor_concentration",
            "completeness_score"]:
    if col in df19.columns:
        if col == "completeness_score":
            print(f"  {col:<32} 평균 {df19[col].mean():.1f}%")
        else:
            n = df19[col].replace("", pd.NA).notna().sum()
            print(f"  {col:<32} {n:>5,}  ({n/total19*100:.1f}%)")
