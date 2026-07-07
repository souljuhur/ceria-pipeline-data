"""
normalize_data.py — [Stage 2] 데이터 정규화

- synthesis_method 표기 통일 (대소문자, 변형 표기 → 표준명)
- morphology 표기 통일 + "other" 재분류 (제목 키워드 기반)
- 수치 단위 정합성 검증 (nm, °C, h)
- dopant 표기 정리 (원소 기호 통일)
- crystal_phase 표준화

이전 이름: run_cell21.py
"""
import json
import pandas as pd, os, re
from pathlib import Path

_BASE     = r"d:\머신러닝 교육\ceria_pipeline_data"
_PATH     = os.path.join(_BASE, "output", "ceria_synthesis_database.xlsx")
_CSV_PATH = os.path.join(_BASE, "output", "ceria_samples_merged.csv")
_TEXT_DIR = Path(_BASE) / "text"

df = pd.read_excel(_PATH, sheet_name=0)
total = len(df)
print(f"로드: {total:,}편\n")

# samples CSV도 병렬 로드
_has_csv = os.path.exists(_CSV_PATH)
df_csv   = pd.read_csv(_CSV_PATH, low_memory=False) if _has_csv else None
if df_csv is not None:
    print(f"CSV 로드: {len(df_csv):,}행\n")

# ── 1. synthesis_method 표준화 ─────────────────────────────────────────────────
METHOD_MAP = {
    # ── hydrothermal ──────────────────────────────────────────────────────────
    "hydrothermal":                        "hydrothermal",
    "hydrothermal synthesis":              "hydrothermal",
    "hydrothermal method":                 "hydrothermal",
    "hydrothermal process":                "hydrothermal",
    "hydrothermal route":                  "hydrothermal",
    "hydrothermal treatment":              "hydrothermal",
    "supercritical hydrothermal":          "hydrothermal",
    "hydrothermal co-precipitation":       "hydrothermal",
    # ── solvothermal ──────────────────────────────────────────────────────────
    "solvothermal":                        "solvothermal",
    "solvothermal synthesis":              "solvothermal",
    "solvothermal method":                 "solvothermal",
    "polyol-mediated synthesis":           "solvothermal",
    "polyol method":                       "solvothermal",
    "polyol synthesis":                    "solvothermal",
    # ── sol-gel ───────────────────────────────────────────────────────────────
    "sol-gel":                             "sol-gel",
    "sol gel":                             "sol-gel",
    "solgel":                              "sol-gel",
    "sol–gel":                             "sol-gel",
    "sol-gel synthesis":                   "sol-gel",
    "sol-gel method":                      "sol-gel",
    "sol-gel process":                     "sol-gel",
    "pechini":                             "sol-gel",
    "modified pechini":                    "sol-gel",
    "pechini method":                      "sol-gel",
    "citrate gel":                         "sol-gel",
    "citrate-gel":                         "sol-gel",
    "citrate sol-gel":                     "sol-gel",
    "citrate complexation":                "sol-gel",
    "polymeric precursor method":          "sol-gel",
    "polymer complexation":                "sol-gel",
    # ── co-precipitation ──────────────────────────────────────────────────────
    "co-precipitation":                    "co-precipitation",
    "co precipitation":                    "co-precipitation",
    "coprecipitation":                     "co-precipitation",
    "co-precipitation method":             "co-precipitation",
    "chemical co-precipitation":           "co-precipitation",
    "co-precipitation-hydrothermal":       "co-precipitation",
    "forced cohydrolysis":                 "co-precipitation",
    "dropwise addition":                   "co-precipitation",
    # ── precipitation ─────────────────────────────────────────────────────────
    "precipitation":                       "precipitation",
    "chemical precipitation":              "precipitation",
    "wet precipitation":                   "precipitation",
    "homogeneous precipitation":           "precipitation",
    # ── combustion ────────────────────────────────────────────────────────────
    "combustion":                          "combustion",
    "solution combustion":                 "combustion",
    "combustion synthesis":                "combustion",
    "auto-combustion":                     "combustion",
    "autocombustion":                      "combustion",
    "self-combustion":                     "combustion",
    "solution combustion synthesis":       "combustion",
    "gel combustion":                      "combustion",
    "gel-combustion":                      "combustion",
    "sol-gel combustion":                  "combustion",
    "microwave combustion":                "combustion",
    "glycine nitrate":                     "combustion",
    "glycine nitrate process":             "combustion",
    "gnp":                                 "combustion",
    "citrate-nitrate combustion":          "combustion",
    "urea-nitrate combustion":             "combustion",
    # ── microwave ─────────────────────────────────────────────────────────────
    "microwave":                           "microwave",
    "microwave synthesis":                 "microwave",
    "microwave-assisted":                  "microwave",
    "microwave assisted":                  "microwave",
    "microwave hydrothermal":              "microwave",
    "microwave irradiation":               "microwave",
    "microwave-assisted hydrothermal":     "microwave",
    "microwave-hydrothermal":              "microwave",
    "microwave-assisted solvothermal":     "microwave",
    "microwave-assisted synthesis":        "microwave",
    # ── thermal_decomposition ─────────────────────────────────────────────────
    "thermal decomposition":               "thermal_decomposition",
    "thermal_decomposition":               "thermal_decomposition",
    "thermal_decomp":                      "thermal_decomposition",
    "thermolysis":                         "thermal_decomposition",
    "pyrolysis":                           "thermal_decomposition",
    "calcination":                         "thermal_decomposition",
    "molten flux":                         "thermal_decomposition",
    "alkaline fusion":                     "thermal_decomposition",
    # ── spray_pyrolysis ───────────────────────────────────────────────────────
    "spray pyrolysis":                     "spray_pyrolysis",
    "spray_pyrolysis":                     "spray_pyrolysis",
    "spray synthesis":                     "spray_pyrolysis",
    "aerosol pyrolysis":                   "spray_pyrolysis",
    # ── flame_spray (새 카테고리) ─────────────────────────────────────────────
    "flame spray pyrolysis":               "flame_spray",
    "flame-assisted spray pyrolysis":      "flame_spray",
    "flame spray":                         "flame_spray",
    "flame synthesis":                     "flame_spray",
    "flame spray synthesis":               "flame_spray",
    "fsp":                                 "flame_spray",
    # ── mechanochemical ───────────────────────────────────────────────────────
    "mechanochemical":                     "mechanochemical",
    "ball milling":                        "mechanochemical",
    "ball-milling":                        "mechanochemical",
    "mechanochemical synthesis":           "mechanochemical",
    "mechanical alloying":                 "mechanochemical",
    "planetary ball milling":              "mechanochemical",
    "mechanical milling":                  "mechanochemical",
    "high-energy ball milling":            "mechanochemical",
    # ── sonochemical ──────────────────────────────────────────────────────────
    "sonochemical":                        "sonochemical",
    "sonochemical synthesis":              "sonochemical",
    "ultrasound":                          "sonochemical",
    "ultrasound-assisted":                 "sonochemical",
    "ultrasonication":                     "sonochemical",
    "ultrasonication-assisted":            "sonochemical",
    "ultrasonic irradiation":              "sonochemical",
    "sonication":                          "sonochemical",
    # ── template ──────────────────────────────────────────────────────────────
    "template":                            "template",
    "template-assisted":                   "template",
    "hard template":                       "template",
    "soft template":                       "template",
    "template method":                     "template",
    "nanocasting":                         "template",
    # ── wet_chemical ──────────────────────────────────────────────────────────
    "wet chemical":                        "wet_chemical",
    "wet-chemical":                        "wet_chemical",
    "wet chemistry":                       "wet_chemical",
    "chemical synthesis":                  "wet_chemical",
    "reflux":                              "wet_chemical",
    "reflux method":                       "wet_chemical",
    "chemical reduction":                  "wet_chemical",
    # ── impregnation (새 카테고리) ────────────────────────────────────────────
    "impregnation":                        "impregnation",
    "wet impregnation":                    "impregnation",
    "incipient wetness impregnation":      "impregnation",
    "incipient wetness":                   "impregnation",
    "wet_impregnation":                    "impregnation",
    "wet-impregnation":                    "impregnation",
    "wetness impregnation":                "impregnation",
    "co-impregnation":                     "impregnation",
    "coimpregnation":                      "impregnation",
    "impregnation method":                 "impregnation",
    "impregnation-reduction":              "impregnation",
    "dry impregnation":                    "impregnation",
    # ── deposition_precipitation (새 카테고리) ────────────────────────────────
    "deposition-precipitation":            "deposition_precipitation",
    "deposition–precipitation":       "deposition_precipitation",
    "deposition precipitation":            "deposition_precipitation",
    "deposition-precipitation method":     "deposition_precipitation",
    "colloidal deposition":                "deposition_precipitation",
    # ── microemulsion (새 카테고리) ───────────────────────────────────────────
    "microemulsion":                       "microemulsion",
    "reverse microemulsion":               "microemulsion",
    "water-in-oil microemulsion":          "microemulsion",
    "w/o microemulsion":                   "microemulsion",
    "oil-in-water microemulsion":          "microemulsion",
    # ── green_synthesis (새 카테고리) ─────────────────────────────────────────
    "green synthesis":                     "green_synthesis",
    "green-synthesis":                     "green_synthesis",
    "biosynthesis":                        "green_synthesis",
    "biogenic synthesis":                  "green_synthesis",
    "biogenic":                            "green_synthesis",
    "plant-mediated synthesis":            "green_synthesis",
    "biological synthesis":                "green_synthesis",
    "bio-synthesis":                       "green_synthesis",
    # ── electrodeposition (새 카테고리) ───────────────────────────────────────
    "electrodeposition":                   "electrodeposition",
    "electrosynthesis":                    "electrodeposition",
    "electrochemical synthesis":           "electrodeposition",
    "electrochemical deposition":          "electrodeposition",
    # ── electrospinning (새 카테고리) ─────────────────────────────────────────
    "electrospinning":                     "electrospinning",
    "electrospun":                         "electrospinning",
    # ── pvd (새 카테고리) ─────────────────────────────────────────────────────
    "sputtering":                          "pvd",
    "magnetron sputtering":                "pvd",
    "dc sputtering":                       "pvd",
    "rf sputtering":                       "pvd",
    "pulsed laser deposition":             "pvd",
    "pld":                                 "pvd",
    "physical vapor deposition":           "pvd",
    # ── ald (새 카테고리) ─────────────────────────────────────────────────────
    "atomic layer deposition":             "ald",
    # ── cvd (새 카테고리) ─────────────────────────────────────────────────────
    "chemical vapor deposition":           "cvd",
    "mocvd":                               "cvd",
    "pecvd":                               "cvd",
    # ── continuous_flow (새 카테고리) ─────────────────────────────────────────
    "continuous flow hydrothermal":        "continuous_flow",
    "continuous hydrothermal synthesis":   "continuous_flow",
    "continuous flow synthesis":           "continuous_flow",
    "continuous hydrothermal":             "continuous_flow",
    # ── freeze_drying (새 카테고리) ───────────────────────────────────────────
    "freeze drying":                       "freeze_drying",
    "freeze-drying":                       "freeze_drying",
    "lyophilization":                      "freeze_drying",
    "freeze-dry":                          "freeze_drying",
    # ── ion_exchange (새 카테고리) ────────────────────────────────────────────
    "ion exchange":                        "ion_exchange",
    "ion-exchange":                        "ion_exchange",
    "ion exchange method":                 "ion_exchange",
}

def _apply_method_map(series):
    """METHOD_MAP 벡터화 적용"""
    def _f(val):
        if pd.isna(val) or not str(val).strip():
            return val
        v = str(val).strip().lower()
        if ";" in v:
            v = v.split(";")[0].strip()
        return METHOD_MAP.get(v, val)
    return series.apply(_f)

# Excel DB 정규화
orig_xl = df["synthesis_method"].copy()
df["synthesis_method"] = _apply_method_map(df["synthesis_method"])
cnt_m = (df["synthesis_method"] != orig_xl).sum()
print(f"  synthesis_method 정규화 (Excel): {cnt_m:,}건")

# CSV 정규화
if df_csv is not None and "synthesis_method" in df_csv.columns:
    orig_csv = df_csv["synthesis_method"].copy()
    df_csv["synthesis_method"] = _apply_method_map(df_csv["synthesis_method"])
    cnt_csv_m = (df_csv["synthesis_method"].fillna("") != orig_csv.fillna("")).sum()
    print(f"  synthesis_method 정규화 (CSV):  {cnt_csv_m:,}행")

# ── 1b. 'other' 텍스트 기반 재분류 (CSV 전용) ─────────────────────────────────
# 전문 파일을 스캔해서 GPT가 'other'로 분류한 샘플의 실제 합성법 복구

# targeted 캐시 로드 (0단계 fallback용)
_TARGETED_CACHE_PATH = os.path.join(_BASE, "output", "targeted_extraction_cache.json")
_targeted_cache: dict = {}
if os.path.exists(_TARGETED_CACHE_PATH):
    try:
        with open(_TARGETED_CACHE_PATH, encoding="utf-8") as _f:
            _targeted_cache = json.load(_f)
    except Exception:
        pass

_VALID_METHODS = {
    "hydrothermal", "precipitation", "sol-gel", "co-precipitation",
    "solvothermal", "combustion", "microwave", "impregnation",
    "thermal_decomposition", "wet_chemical", "green_synthesis",
    "deposition_precipitation", "microemulsion", "electrodeposition",
    "template", "mechanochemical", "spray_pyrolysis", "sonochemical",
    "flame_spray", "freeze_drying", "pvd", "electrospinning", "ald", "cvd",
    "continuous_flow", "ion_exchange",
}
# ── 복구 패턴: 고유/특이적 방법 (전체 텍스트 검색 허용 — 오탐 낮음) ────────────
_RECOVERY_PATTERNS_DISTINCTIVE = [
    ("ald",                  ["atomic layer deposition"]),
    ("cvd",                  ["chemical vapor deposition", "mocvd", "pecvd",
                              "metal-organic cvd"]),
    ("pvd",                  ["magnetron sputtering", "dc sputtering", "rf sputtering",
                              "pulsed laser deposition", "physical vapor deposition"]),
    ("flame_spray",          ["flame spray pyrolysis", "flame spray synthesis",
                              "fsp process", "flame synthesis of", "flame-assisted spray"]),
    ("electrodeposition",    ["electrodeposition", "electrosynthesis"]),
    ("continuous_flow",      ["continuous hydrothermal", "continuous flow hydrothermal"]),
    ("freeze_drying",        ["freeze dry", "freeze-dry", "lyophiliz"]),
    ("deposition_precipitation", ["deposition-precipitation", "deposition precipitation"]),
    ("microemulsion",        ["reverse microemulsion", "water-in-oil", "w/o microemulsion",
                              "reverse micelle"]),
    ("green_synthesis",      ["green synthesis", "biosynthesis", "biogenic synthesis",
                              "plant extract synthesis", "plant-mediated synthesis"]),
    ("electrospinning",      ["electrospinning"]),
    ("impregnation",         ["incipient wetness impregnation", "wet impregnation method"]),
    ("ion_exchange",         ["ion exchange synthesis", "ion-exchange synthesis"]),
    ("pvd",                  ["vapor phase synthesis", "vapour phase synthesis",
                              "vapor-phase synthesis"]),
    ("spray_pyrolysis",      ["spray-pyrolysis method", "aerosol decomposition"]),
    ("template",             ["hard-template synthesis", "soft-template synthesis",
                              "nanotemplating"]),
]

# ── 복구 패턴: 일반 방법 (실험 섹션 내 구체적 문구만 허용 — 오탐 방지) ─────────
_RECOVERY_PATTERNS_COMMON = [
    ("mechanochemical",    ["ball milling synthesis", "mechanochemical synthesis",
                            "prepared by ball milling", "mechanical alloying synthesis"]),
    ("spray_pyrolysis",    ["spray pyrolysis synthesis", "spray-pyrolysis synthesis",
                            "aerosol pyrolysis", "prepared by spray pyrolysis"]),
    ("microwave",          ["microwave-assisted synthesis", "microwave irradiation synthesis",
                            "microwave-assisted hydrothermal", "prepared using microwave"]),
    ("combustion",         ["solution combustion synthesis", "auto-combustion synthesis",
                            "gel combustion synthesis", "self-propagating combustion",
                            "prepared by solution combustion"]),
    ("sol-gel",            ["pechini method", "citrate complexation method",
                            "modified pechini", "sol-gel synthesis was",
                            "prepared by sol-gel", "synthesized by sol-gel"]),
    ("solvothermal",       ["solvothermal synthesis was", "prepared by solvothermal",
                            "polyol synthesis", "polyol method"]),
    ("hydrothermal",       ["prepared by hydrothermal", "synthesized by hydrothermal",
                            "hydrothermal synthesis was", "hydrothermal method was",
                            "hydrothermal process was"]),
    ("precipitation",      ["prepared by precipitation", "co-precipitation synthesis",
                            "coprecipitation synthesis", "chemical precipitation synthesis"]),
    ("template",           ["template synthesis", "hard template method",
                            "soft template method", "nanocasting method"]),
    ("sonochemical",       ["sonochemical synthesis", "prepared by sonochemical",
                            "ultrasound-assisted synthesis"]),
    ("thermal_decomposition", ["thermal decomposition synthesis",
                               "thermolysis synthesis", "calcination synthesis"]),
]

# 실험 섹션 헤더 키워드 (우선순위 순)
_EXP_SECTION_KWS = [
    "experimental section", "experimental procedure", "materials and methods",
    "2. experimental", "3. experimental", "2.1. synthesis", "2.1 synthesis",
    "preparation of ceo2", "preparation of ceria", "synthesis of ceo2",
    "synthesis of ceria", "sample preparation", "nanoparticle synthesis",
]

def _safe_fname(doi):
    return str(doi).replace("/", "_").replace(":", "_")

def _find_exp_snippet(text: str) -> str:
    """실험 섹션 시작점 탐색 후 최대 8000자 반환. 없으면 처음 6000자."""
    for kw in _EXP_SECTION_KWS:
        idx = text.find(kw)
        if idx != -1:
            return text[idx:idx + 8000]
    return text[:6000]

# DOI → tagged_methods 매핑 (Excel DB, 보조 신호)
_doi_to_tags: dict = {}
if "tagged_methods" in df.columns and "doi" in df.columns:
    for _, _row in df[["doi", "tagged_methods"]].dropna(subset=["doi"]).iterrows():
        _d = str(_row["doi"]).strip()
        _t = str(_row.get("tagged_methods", "")).strip()
        if _d and _t and _t != "nan":
            _doi_to_tags[_d] = _t

def _recover_method_v2(doi: str) -> str | None:
    """4단계 합성법 복구:
    0단계 — targeted 추출 캐시에서 유효 메서드 직접 조회
    1단계 — 실험 섹션에서 고유 방법 + 일반 방법 탐색
    2단계 — 전체 텍스트에서 고유 방법만 탐색 (오탐 방지)
    3단계 — tagged_methods 단일 태그 보조 신호
    """
    # ── 0단계: targeted 캐시 직접 조회 ─────────────────────────────────────────
    cache_entry = _targeted_cache.get(doi, {})
    if cache_entry:
        raw_m = None
        if isinstance(cache_entry, dict):
            raw_m = cache_entry.get("synthesis_method")
        elif isinstance(cache_entry, list) and cache_entry:
            raw_m = cache_entry[0].get("synthesis_method") if isinstance(cache_entry[0], dict) else None
        if raw_m and str(raw_m).strip().lower() not in ("other", "null", "none", ""):
            m = str(raw_m).strip()
            if m in _VALID_METHODS:
                return m

    txt_path = _TEXT_DIR / f"{_safe_fname(doi)}.txt"

    # ── 1·2단계: 텍스트 탐색 ────────────────────────────────────────────────
    if txt_path.exists():
        try:
            text = txt_path.read_text(encoding="utf-8", errors="replace").lower()
            exp_section = _find_exp_snippet(text)

            # 1a. 실험 섹션 내 고유 방법
            for method, kws in _RECOVERY_PATTERNS_DISTINCTIVE:
                for kw in kws:
                    if kw in exp_section:
                        return method

            # 1b. 실험 섹션 내 일반 방법 (구체적 문구)
            for method, phrases in _RECOVERY_PATTERNS_COMMON:
                for phrase in phrases:
                    if phrase in exp_section:
                        return method

            # 2. 전체 텍스트: 고유 방법만
            for method, kws in _RECOVERY_PATTERNS_DISTINCTIVE:
                for kw in kws:
                    if kw in text:
                        return method
        except Exception:
            pass

    # ── 3단계: tagged_methods 단일 태그 fallback ────────────────────────────
    tags_raw = _doi_to_tags.get(str(doi).strip(), "")
    if tags_raw and tags_raw != "nan":
        tags = [t.strip() for t in tags_raw.split("|") if t.strip()]
        if len(tags) == 1:
            return METHOD_MAP.get(tags[0], tags[0])

    return None

if df_csv is not None and "synthesis_method" in df_csv.columns and "doi" in df_csv.columns:
    other_mask = df_csv["synthesis_method"].astype(str).str.strip().str.lower() == "other"
    other_idx  = df_csv.index[other_mask]
    recovered  = 0
    unidentified = 0
    method_counter: dict = {}

    for idx in other_idx:
        doi = df_csv.at[idx, "doi"]
        if pd.isna(doi):
            df_csv.at[idx, "synthesis_method"] = "unidentified_method"
            unidentified += 1
            continue
        method = _recover_method_v2(str(doi).strip())
        if method:
            df_csv.at[idx, "synthesis_method"] = method
            method_counter[method] = method_counter.get(method, 0) + 1
            recovered += 1
        else:
            df_csv.at[idx, "synthesis_method"] = "unidentified_method"
            unidentified += 1

    print(f"\n  'other' 재분류 (개선):")
    print(f"    복구 성공: {recovered}행")
    for m, n in sorted(method_counter.items(), key=lambda x: -x[1]):
        print(f"      {m:30s} +{n}행")
    print(f"    판별 불가 → unidentified_method: {unidentified}행")

# ── 1c. 기존 unidentified_method 행 → targeted 캐시 재조회 (0단계만) ──────────
if df_csv is not None and "synthesis_method" in df_csv.columns and "doi" in df_csv.columns:
    unk_mask = df_csv["synthesis_method"].astype(str).str.strip() == "unidentified_method"
    unk_idx  = df_csv.index[unk_mask]
    rescued  = 0
    rescue_counter: dict = {}

    for idx in unk_idx:
        doi = df_csv.at[idx, "doi"]
        if pd.isna(doi):
            continue
        # targeted 캐시 0단계만 적용 (텍스트 재탐색은 이전 실행에서 이미 실패)
        cache_entry = _targeted_cache.get(str(doi).strip(), {})
        raw_m = None
        if isinstance(cache_entry, dict):
            raw_m = cache_entry.get("synthesis_method")
        elif isinstance(cache_entry, list) and cache_entry:
            raw_m = cache_entry[0].get("synthesis_method") if isinstance(cache_entry[0], dict) else None
        if raw_m and str(raw_m).strip().lower() not in ("other", "null", "none", ""):
            m = str(raw_m).strip()
            if m in _VALID_METHODS:
                df_csv.at[idx, "synthesis_method"] = m
                rescue_counter[m] = rescue_counter.get(m, 0) + 1
                rescued += 1

    if rescued:
        print(f"\n  unidentified_method → targeted 캐시 복구: {rescued}행")
        for m, n in sorted(rescue_counter.items(), key=lambda x: -x[1]):
            print(f"      {m:30s} +{n}행")
    else:
        print(f"\n  unidentified_method targeted 캐시 복구: 0행")

# ── 1d. ce_precursor 검증 필터 — 非Ce 물질 제거 ─────────────────────────────
# GPT가 도펀트 전구체(La/Ni/Zr 등), 지지체(TiO2/SnO2), 유기 첨가제를 혼동하여
# ce_precursor에 잘못 기입하는 경우를 NULL로 처리한다.

def _is_ce_compound(val) -> bool:
    """Ce 원소를 실제로 포함하는 화합물이면 True."""
    if pd.isna(val):
        return False
    s = str(val).strip().lower()
    if not s or s in ("nan", "none", "null", "n/a", ""):
        return False
    # 세미콜론/쉼표로 분리해 각 성분 검사
    parts = re.split(r"[;,]", s)
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Ce로 시작하는 성분 (CeO2, Ce(NO3)3, CeCl3, CeH2.73, CeIII ... 모두 포함)
        if re.match(r"ce", p, re.IGNORECASE):
            return True
        # cerium / cerous / ceric 단어 포함
        if re.search(r"\b(cerium|cerous|ceric)\b", p, re.IGNORECASE):
            return True
        # (NH4)2Ce... 또는 (NH4)2[Ce... 형태
        if re.search(r"\(nh4\)[\d\s]*\[?ce", p, re.IGNORECASE):
            return True
        # Ce를 원소로 포함하는 복합식: 앞뒤가 비문자인 Ce (예: La0.5Ce0.5O2)
        if re.search(r"(?<![a-z])ce(?![a-z])", p, re.IGNORECASE):
            return True
    return False

if df_csv is not None and "ce_precursor" in df_csv.columns:
    ce_col = df_csv["ce_precursor"].copy()
    nullified = 0
    for idx in df_csv.index:
        val = df_csv.at[idx, "ce_precursor"]
        if pd.notna(val) and str(val).strip() not in ("", "nan", "none"):
            if not _is_ce_compound(val):
                df_csv.at[idx, "ce_precursor"] = None
                nullified += 1
    print(f"\n  [ce_precursor 검증] 非Ce 물질 → NULL 처리: {nullified}행")

# ── 2. morphology 표준화 ──────────────────────────────────────────────────────
MORPH_MAP = {
    "spherical": "sphere",
    "spheres":   "sphere",
    "nanoparticle": "sphere",
    "nanoparticles": "sphere",
    "quasi-spherical": "sphere",
    "nanosphere": "sphere",
    "cubic": "cube",
    "nanocube": "cube",
    "nanocubes": "cube",
    "nanorods": "rod",
    "nanorod": "rod",
    "rod-like": "rod",
    "rod-shaped": "rod",
    "nanowires": "wire",
    "nanowire": "wire",
    "wire-like": "wire",
    "nanoflower": "flower",
    "nanoflowers": "flower",
    "flower-like": "flower",
    "flowerlike": "flower",
    "nanoplates": "plate",
    "nanoplate": "plate",
    "plate-like": "plate",
    "platelet": "plate",
    "octahedral": "octahedron",
    "hollow sphere": "hollow",
    "hollow nanoparticle": "hollow",
    "mesoporous": "porous",
    "nanoporous": "porous",
    "porous nanoparticle": "porous",
}

cnt_mo = 0
for idx, row in df.iterrows():
    orig = row.get("morphology")
    if pd.isna(orig) or not str(orig).strip():
        continue
    v = str(orig).strip().lower()
    if v in MORPH_MAP:
        df.at[idx, "morphology"] = MORPH_MAP[v]
        cnt_mo += 1
print(f"  morphology 정규화: {cnt_mo:,}건")

# ── 2b. "other" 재분류 (제목/초록 키워드 기반 2차 추론) ──────────────────────
TITLE_MORPH_KW = {
    "rod":        ["nanorod", "nano-rod", "rod-shaped", "rod-like", "nanorods"],
    "wire":       ["nanowire", "nano-wire", "wire-like", "nanowires"],
    "cube":       ["nanocube", "nanocubes", "cube-shaped", "cubic nanoparticle"],
    "flower":     ["nanoflower", "flower-like", "flowerlike", "nanoflowers"],
    "plate":      ["nanoplate", "nanoplates", "plate-like", "platelet"],
    "octahedron": ["octahedral", "octahedron"],
    "hollow":     ["hollow sphere", "hollow nanoparticle", "core-shell"],
    "porous":     ["mesoporous", "nanoporous", "porous ceo2", "porous ceria"],
    "sphere":     ["nanosphere", "spherical nanoparticle", "quasi-spherical"],
}
if "morphology" in df.columns:
    other_mask = df["morphology"].fillna("").str.strip().str.lower() == "other"
    hay = (df["title"].fillna("") + " " + df.get("abstract", pd.Series([""] * len(df))).fillna("")).str.lower()
    cnt_mo2 = 0
    for morph, kws in TITLE_MORPH_KW.items():
        pat = "|".join(re.escape(k) for k in kws)
        hit = other_mask & hay.str.contains(pat, na=False, regex=True)
        df.loc[hit, "morphology"] = morph
        other_mask &= ~hit
        cnt_mo2 += int(hit.sum())
    print(f"  morphology 'other' 재분류: {cnt_mo2:,}건")

# ── 3. dopant 표기 정리 ───────────────────────────────────────────────────────
ELEMENT_NAMES = {
    "gadolinium": "Gd", "samarium": "Sm", "lanthanum": "La",
    "yttrium": "Y",     "neodymium": "Nd","praseodymium": "Pr",
    "europium": "Eu",   "zirconium": "Zr","titanium": "Ti",
    "copper": "Cu",     "iron": "Fe",     "manganese": "Mn",
    "cobalt": "Co",     "nickel": "Ni",   "platinum": "Pt",
    "palladium": "Pd",  "gold": "Au",     "aluminum": "Al",
    "silicon": "Si",    "tungsten": "W",  "molybdenum": "Mo",
    "chromium": "Cr",   "silver": "Ag",   "ruthenium": "Ru",
    "terbium": "Tb",    "dysprosium": "Dy","holmium": "Ho",
    "erbium": "Er",     "ytterbium": "Yb","lutetium": "Lu",
}

cnt_d = 0
for idx, row in df.iterrows():
    orig = row.get("dopant")
    if pd.isna(orig) or not str(orig).strip():
        continue
    v = str(orig).strip().lower()
    if v in ELEMENT_NAMES:
        df.at[idx, "dopant"] = ELEMENT_NAMES[v]
        cnt_d += 1
print(f"  dopant 표기 정규화: {cnt_d:,}건")

# ── 4. 수치 필드 타입 강제 변환 ──────────────────────────────────────────────
NUM_COLS = [
    "synthesis_temperature_c", "synthesis_time_h", "calcination_temperature_c",
    "calcination_time_h", "drying_temperature_c", "particle_size_tem_nm",
    "particle_size_sem_nm", "crystallite_size_xrd_nm", "bet_surface_area",
    "ph_synthesis", "ce_concentration_M", "mineralizer_concentration_M",
]

cnt_n = 0
for col in NUM_COLS:
    if col not in df.columns:
        continue
    for idx, val in df[col].items():
        if pd.isna(val) or isinstance(val, (int, float)):
            continue
        s = str(val).strip()
        s = re.sub(r'^[~≈≤≥<>about\s.ca]+', '', s, flags=re.I).strip()
        range_m = re.match(r'^(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)$', s)
        if range_m:
            try:
                avg = (float(range_m.group(1)) + float(range_m.group(2))) / 2
                df.at[idx, col] = round(avg, 2)
                cnt_n += 1
                continue
            except ValueError:
                pass
        try:
            df.at[idx, col] = float(s.split()[0])
            cnt_n += 1
        except (ValueError, IndexError):
            df.at[idx, col] = None

print(f"  수치 필드 정리: {cnt_n:,}건")

# ── 5. crystal_phase 표준화 ───────────────────────────────────────────────────
PHASE_MAP = {
    "fluorite":             "fluorite cubic",
    "cubic fluorite":       "fluorite cubic",
    "face-centered cubic":  "fluorite cubic",
    "fcc":                  "fluorite cubic",
    "cubic (fluorite)":     "fluorite cubic",
    "fluorite (cubic)":     "fluorite cubic",
    "fluorite structure":   "fluorite cubic",
    "cerianite":            "fluorite cubic",
    "ce2o3":                "Ce2O3",
    "cerium(iii) oxide":    "Ce2O3",
}

cnt_p = 0
for idx, row in df.iterrows():
    orig = row.get("crystal_phase")
    if pd.isna(orig) or not str(orig).strip():
        continue
    v = str(orig).strip().lower()
    if v in PHASE_MAP:
        df.at[idx, "crystal_phase"] = PHASE_MAP[v]
        cnt_p += 1
print(f"  crystal_phase 정규화: {cnt_p:,}건")

# ── 5b. atmosphere 정규화 ─────────────────────────────────────────────────────
# 가스 분위기 표기 통일, 용기 조건/오분류 → None
# 순서 중요: H2/Ar·H2/N2 혼합 가스 → 단독 H2보다 먼저 매칭
ATMOSPHERE_PATTERNS = [
    # ── 대기 / 개방계 ──────────────────────────────────────────────────────────
    ("air",    r"^air$|atmospheric air|^ambient$|^atmospheric$|atmospheric pressure"
               r"|dry air|synthetic air|static air|open air|lab air|ambient air"
               r"|^normal$|^standard$|normal atmospheric|room condition|room air"
               r"|circulating air|^air atmosphere$"),
    # ── 질소 ──────────────────────────────────────────────────────────────────
    ("N2",     r"^n2$|^nitrogen$|nitrogen atmosphere|^n2 atmosphere$|^n2 gas$"
               r"|pure nitrogen|dried? nitrogen|nitrogen flow|^inert \(n2\)$"
               r"|dried? n2|^n$"),
    # ── 아르곤 ────────────────────────────────────────────────────────────────
    ("Ar",     r"^ar$|^argon$|argon atmosphere|ar atmosphere|pure argon"
               r"|moisture.?free argon|dry argon"),
    # ── 산소 / 산화 분위기 ────────────────────────────────────────────────────
    ("O2",     r"^o2$|^oxygen$|dry oxygen|^o2/he$|^o2/n2$|oxygen atmosphere"
               r"|^oxidant$|^oxidative$|^oxidizing$|oxygen flow|o2 sparging"
               r"|oxygen pressure|\bbar o2\b|volume.*o2|%.*o2/he|o2.*volume"
               r"|ambient oxygen|high.?temperature oxidizing"
               r"|helium.*oxygen|oxygen.*helium|ar.*o2|o2.*ar|^o$"),
    # ── H2/Ar 혼합 (단독 H2·Ar 전에 매칭) ────────────────────────────────────
    ("H2/Ar",  r"h2/ar|h2-ar|ar.?h2|h2.?ar|\d+%\s*h2/ar|forming gas"
               r"|ar.?5%.*h2|5%.*h2.*ar|93%.ar.*h|h2/ar flow|^ar-h2$"
               r"|h2 and ar"),
    # ── H2/N2 혼합 ────────────────────────────────────────────────────────────
    ("H2/N2",  r"h2/n2|h2-n2|n/h2|\d+%\s*h2/n2|n2\s*h2\s*gas|n2.*h2 gas"),
    # ── 수소 / 환원 분위기 ────────────────────────────────────────────────────
    ("H2",     r"^h2$|^hydrogen$|^reducing$|^reductive$|h2 atmosphere|pure hydrogen"
               r"|\bbar h2\b|humidified h2|flowing h2?|^h$|^h2 flow$"),
    # ── 진공 ──────────────────────────────────────────────────────────────────
    ("vacuum", r"vacuum|uhv|ultra.?high vacuum|low.?pressure|low gas pressure"
               r"|secondary vacuum|dynamic vacuum|vacuum.?assisted|absence of oxygen"),
    # ── CO2 / 초임계 ──────────────────────────────────────────────────────────
    ("CO2",    r"co2|supercritical"),
    # ── 불특정 불활성 (He 포함) ───────────────────────────────────────────────
    ("inert",  r"^inert$|^inert gas$|^he$|^helium$|anaerobic"),
]

# 가스 분위기가 아닌 오분류 → None
_ATM_INVALID = {
    "autoclave", "autogenous pressure", "room temperature", "other",
    "n/a", "na", "-", "",
    "magnetic field",           # 외부 자기장 조건
    "dark", "dark environment", "protected from light",  # 광 조건
    "fume chamber",             # 실험 장비
    "platinum crucible",        # 반응 용기
    "highly alkaline", "acidic",  # 용액 조건
    "charcoal powder",          # 시약
    "ice bath", "ice water bath",  # 온도 조건
    "closed system", "pressurized",  # 압력 조건 (가스 정보 없음)
    "static",                   # 비특정
    "closed autoclave",         # 용기 조건
}

def _norm_atmosphere(val):
    if pd.isna(val) or not str(val).strip():
        return val
    v = str(val).strip()
    v_lo = v.lower()
    if v_lo in _ATM_INVALID:
        return None
    for atm, pat in ATMOSPHERE_PATTERNS:
        if re.search(pat, v_lo, re.I):
            return atm
    return v  # 패턴 없으면 원본 유지

if "atmosphere" in df.columns:
    orig_atm = df["atmosphere"].copy()
    df["atmosphere"] = df["atmosphere"].apply(_norm_atmosphere)
    changed  = orig_atm.notna() & (df["atmosphere"] != orig_atm)
    nulled   = orig_atm.notna() & df["atmosphere"].isna()
    cnt_atm  = int(changed.sum()) + int(nulled.sum())
    dist_atm = df["atmosphere"].dropna().value_counts()
    print(f"\n  atmosphere 정규화: {cnt_atm:,}건 (→None 처리: {int(nulled.sum()):,}건)")
    for k, v in dist_atm.items():
        print(f"    {k:<20} {v:>5,}편")

# ── 6. ce_precursor → anion_type 파생 피처 ───────────────────────────────────
_UNICODE_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

ANION_PATTERNS = [
    # ammonium_nitrate 먼저 — nitrate보다 우선
    ("ammonium_nitrate", r"nh4.*no3|ammonium.*nitrate|\bcan\b|ceric ammonium|(nh4)2ce"),
    ("nitrate",          r"no3|nitrate"),
    ("chloride",         r"cecl|\bcl\d|chloride"),
    ("acetate",          r"ch3coo|ch3co2|\boac\b|acetate"),
    ("sulfate",          r"so4|sulfate"),
    ("carbonate",        r"co3|carbonate"),
    ("acetylacetonate",  r"acac|acetylacetonate"),
    ("alkoxide",         r"oipr|oisop|\boet\b|omeo|isopropoxide|ethoxide|methoxide|butoxide|alkoxide"),
    ("oxalate",          r"c2o4|oxalate"),
    ("hydroxide",        r"ce\(oh\)|hydroxide"),
    ("carboxylate",      r"octanoate|hexanoate|2-ethylhex|stearate|oleate|laurate|propanoate|formate"),
    ("mof",              r"\bmof\b|btc\b|bdc\b|uio-|mil-|zif-"),
    # oxide: CeO2 / CeO / CeZrO2 등 — 산화물계 출발 물질
    ("oxide",            r"^ceo2$|^ceo$|cezro|\bcerium oxide\b|\bceria\b"),
    # metal_ion: Ce 금속/이온 표기 (Ce, Ce3+, Ce(III), Ce(IV) 등)
    ("metal_ion",        r"^ce$|^ce metal$|^ce\d?\+$|ce\(iii\)|ce\(iv\)|^ce3\+$|^ce4\+$"),
]

def _derive_anion(val):
    if pd.isna(val) or not str(val).strip():
        return None
    # 유니코드 아래첨자 정규화 (₄→4, ₃→3 등)
    v = str(val).strip().translate(_UNICODE_SUB).lower()
    for anion, pat in ANION_PATTERNS:
        if re.search(pat, v, re.I):
            return anion
    return "other"

if "ce_precursor" in df.columns:
    df["anion_type"] = df["ce_precursor"].apply(_derive_anion)
    n_filled = df["anion_type"].notna().sum()
    dist = df["anion_type"].dropna().value_counts()
    print(f"\n  ce_precursor → anion_type 파생: {n_filled:,}편")
    for k, v in dist.head(8).items():
        print(f"    {k:<20} {v:>5,}편")

# ── 7. solvent → solvent_type 파생 피처 ──────────────────────────────────────
# 혼합 용매 먼저 체크 (water;ethanol 등), 그 다음 단일 용매
SOLVENT_PATTERNS = [
    # ── 혼합계 (순서 중요: 단일 패턴보다 먼저) ───────────────────────────────
    ("aqueous_alcohol",  r"water.*eth|eth.*water|water.*methanol|methanol.*water"
                         r"|water.*isoprop|isoprop.*water|water.*propanol|propanol.*water"
                         r"|h2o.*eth|eth.*h2o|aqueous.*alcohol"),
    ("aqueous_polyol",   r"water.*glycol|glycol.*water|water.*glycerol|glycerol.*water"
                         r"|h2o.*glycol|glycol.*h2o"),
    ("alcohol_polyol",   r"ethanol.*glycol|glycol.*ethanol|methanol.*glycol"),
    # ── 수계 (aqueous) ────────────────────────────────────────────────────────
    ("aqueous",          r"^water$|deion|distill|di\s*water|dw\b|ddw|ddh2o|milli.?q"
                         r"|\bh2o\b|ultrapure water|tap water|aqueous solution"
                         r"|double distill|triple distill|nanopure"),
    # ── 알코올계 ─────────────────────────────────────────────────────────────
    ("alcohol",          r"\bethanol\b|absolute ethanol|95%.ethanol|c2h5oh"
                         r"|\bmethanol\b|ch3oh|\bisopropanol\b|\bipa\b"
                         r"|2-propanol|isopropyl alcohol|1-butanol|2-butanol"
                         r"|n-propanol|1-propanol|tert-butanol|\bbutanol\b"),
    # ── 폴리올계 (EG, DEG, glycerol …) ──────────────────────────────────────
    ("polyol",           r"ethylene glycol|\beg\b|diethylene glycol|\bdeg\b"
                         r"|propylene glycol|triethylene glycol|\bteg\b"
                         r"|\bglycerol\b|\bglycerine\b"),
    # ── 극성 비양성자성 용매 ──────────────────────────────────────────────────
    ("polar_aprotic",    r"\bdmf\b|dimethylformamide|\bdmso\b|dimethyl sulfoxide"
                         r"|\bnmp\b|n-methyl.2-pyrrolidone|\bacetonitrile\b|\bmecn\b"
                         r"|\bacetone\b|\bdioxane\b|thf\b|tetrahydrofuran"),
    # ── 무극성/탄화수소계 ─────────────────────────────────────────────────────
    ("nonpolar",         r"\btoluene\b|\bxylene\b|\bbenzene\b|\bhexane\b"
                         r"|\bheptane\b|\boctane\b|\bcyclohexane\b|\bdecane\b"
                         r"|\boctadecene\b|1-octadecene|\bdecalin\b|kerosene"),
    # ── 올레일아민/올레산계 (열분해법 특유) ────────────────────────────────────
    ("oleylamine",       r"oleylamine|\boam\b|oleic acid|\boia\b|1-octadecanol"
                         r"|trioctylphosphine|\btop\b|\btopo\b"),
    # ── 이온성 액체 ──────────────────────────────────────────────────────────
    ("ionic_liquid",     r"\[emim\]|\[bmim\]|\[hmim\]|ionic liquid|\[emim"),
]

def _derive_solvent(val):
    if pd.isna(val) or not str(val).strip():
        return None
    v = str(val).strip().translate(_UNICODE_SUB).lower()
    # 세미콜론/슬래시 구분자 → 공백으로 통일 (혼합 용매 패턴 매칭용)
    v = re.sub(r"[;/,+]", " ", v)
    for stype, pat in SOLVENT_PATTERNS:
        if re.search(pat, v, re.I):
            return stype
    return "other"

if "solvent" in df.columns:
    df["solvent_type"] = df["solvent"].apply(_derive_solvent)
    n_sol = df["solvent_type"].notna().sum()
    dist_s = df["solvent_type"].dropna().value_counts()
    print(f"\n  solvent → solvent_type 파생: {n_sol:,}편")
    for k, v in dist_s.items():
        print(f"    {k:<20} {v:>5,}편")

# ── 8. ce_to_mineralizer_ratio 파생 피처 ──────────────────────────────────────
if "ce_concentration_M" in df.columns and "mineralizer_concentration_M" in df.columns:
    import numpy as np
    ce_c  = pd.to_numeric(df["ce_concentration_M"],       errors="coerce")
    min_c = pd.to_numeric(df["mineralizer_concentration_M"], errors="coerce")
    valid = ce_c.notna() & min_c.notna() & (min_c > 0)
    df["ce_to_mineralizer_ratio"] = np.nan
    df.loc[valid, "ce_to_mineralizer_ratio"] = (ce_c / min_c).where(valid)
    # 물리적으로 유효한 범위: 0.01 ~ 100 (mol 비율)
    df.loc[~df["ce_to_mineralizer_ratio"].between(0.01, 100, inclusive="both"),
           "ce_to_mineralizer_ratio"] = np.nan
    n_ratio = df["ce_to_mineralizer_ratio"].notna().sum()
    print(f"\n  ce_to_mineralizer_ratio 파생: {n_ratio:,}편")

# ── 8b. CSV 데이터 품질 필터 ─────────────────────────────────────────────────
if df_csv is not None:
    import numpy as np

    # 수치 필드 타입 강제 변환 (문자열 잔재 → float)
    _CSV_NUM_COLS = [
        "ph_synthesis", "ce_concentration_M", "mineralizer_concentration_M",
        "synthesis_temperature_c", "synthesis_time_h", "calcination_temperature_c",
        "synthesis_volume_mL", "crystallite_size_xrd_nm",
    ]
    for _col in _CSV_NUM_COLS:
        if _col in df_csv.columns:
            df_csv[_col] = pd.to_numeric(df_csv[_col], errors="coerce")

    # (1) chelating_agent: 킬레이트제가 아닌 물질 → NaN
    _CHEL_INVALID = {
        "hno3", "nitric acid", "nh4oh", "ammonium hydroxide",
        "naoh", "sodium hydroxide", "koh", "potassium hydroxide",
        "ethanol", "methanol", "isopropanol", "h2o", "water",
        "coconut water", "coconut shell water",
        "h2o2", "hydrogen peroxide", "nh3", "ammonia",
    }
    if "chelating_agent" in df_csv.columns:
        _mask = df_csv["chelating_agent"].dropna().index
        _vals = df_csv.loc[_mask, "chelating_agent"].astype(str).str.strip().str.lower()
        _bad  = _vals.isin(_CHEL_INVALID)
        cnt_chel = int(_bad.sum())
        df_csv.loc[_vals[_bad].index, "chelating_agent"] = None
        print(f"\n  [품질] chelating_agent 비킬레이트제 제거: {cnt_chel:,}건")

    # (2) capping_agent: 캡핑제가 아닌 물질 → NaN
    _CAP_INVALID = {
        "ethanol", "methanol", "isopropanol", "h2o", "water",
        "hno3", "nitric acid", "nh4oh", "naoh", "koh", "h2o2",
    }
    if "capping_agent" in df_csv.columns:
        _mask2 = df_csv["capping_agent"].dropna().index
        _vals2 = df_csv.loc[_mask2, "capping_agent"].astype(str).str.strip().str.lower()
        _bad2  = _vals2.isin(_CAP_INVALID)
        cnt_cap = int(_bad2.sum())
        df_csv.loc[_vals2[_bad2].index, "capping_agent"] = None
        print(f"  [품질] capping_agent 비캡핑제 제거: {cnt_cap:,}건")

    # (3) atmosphere: 동일 _norm_atmosphere 함수로 정규화
    if "atmosphere" in df_csv.columns:
        _orig_atm = df_csv["atmosphere"].copy()
        df_csv["atmosphere"] = df_csv["atmosphere"].apply(_norm_atmosphere)
        _changed = _orig_atm.notna() & (
            df_csv["atmosphere"].fillna("__null__") != _orig_atm.fillna("__null__"))
        print(f"  [품질] atmosphere 정규화 (CSV): {int(_changed.sum()):,}건")

    # (4) ph_synthesis: 물리적 범위 0~14
    if "ph_synthesis" in df_csv.columns:
        _ph = pd.to_numeric(df_csv["ph_synthesis"], errors="coerce")
        _bad_ph = _ph.notna() & ~_ph.between(0, 14)
        cnt_ph = int(_bad_ph.sum())
        df_csv.loc[_bad_ph, "ph_synthesis"] = None
        print(f"  [품질] ph_synthesis 범위 이탈(0~14 외) 제거: {cnt_ph:,}건")

    # (5) ce_concentration_M: 물리적 범위 0.001~5M
    # Ce(NO3)3·6H2O 포화도 ~5M, 1mM 미만은 측정 오류 가능성 높음
    if "ce_concentration_M" in df_csv.columns:
        _ce = pd.to_numeric(df_csv["ce_concentration_M"], errors="coerce")
        _bad_ce = _ce.notna() & ((_ce > 5) | (_ce < 0.001))
        cnt_ce = int(_bad_ce.sum())
        df_csv.loc[_bad_ce, "ce_concentration_M"] = None
        print(f"  [품질] ce_concentration_M 범위 이탈(0.001~5M 외) 제거: {cnt_ce:,}건")

    # (6) mineralizer_concentration_M: 물리적 범위 0.001~15M
    # NaOH 포화도 ~19M이지만 합성에 15M 초과는 극히 드뭄
    if "mineralizer_concentration_M" in df_csv.columns:
        _min = pd.to_numeric(df_csv["mineralizer_concentration_M"], errors="coerce")
        _bad_min = _min.notna() & ((_min > 15) | (_min < 0.001))
        cnt_min = int(_bad_min.sum())
        df_csv.loc[_bad_min, "mineralizer_concentration_M"] = None
        print(f"  [품질] mineralizer_concentration_M 범위 이탈(0.001~15M 외) 제거: {cnt_min:,}건")

# ── 8c. particle_size_source 백필 ─────────────────────────────────────────────
# 5_table_extract.py가 particle_size_primary_nm을 재계산할 때
# particle_size_source를 갱신하지 않아 발생하는 누락 행 보완
if df_csv is not None:
    if "particle_size_source" not in df_csv.columns:
        df_csv["particle_size_source"] = pd.NA
    _miss_src = (
        df_csv["particle_size_primary_nm"].notna() &
        df_csv["particle_size_source"].isna()
    )
    if _miss_src.any():
        _tem_c = "particle_size_tem_nm"
        _sem_c = "particle_size_sem_nm"
        _tem_ok = _miss_src & (df_csv[_tem_c].notna() if _tem_c in df_csv.columns
                               else pd.Series(False, index=df_csv.index))
        _sem_ok = _miss_src & ~_tem_ok & (df_csv[_sem_c].notna() if _sem_c in df_csv.columns
                                          else pd.Series(False, index=df_csv.index))
        df_csv.loc[_tem_ok, "particle_size_source"] = "TEM"
        df_csv.loc[_sem_ok, "particle_size_source"] = "SEM"
        print(f"\n  [백필] particle_size_source: TEM +{int(_tem_ok.sum())}, "
              f"SEM +{int(_sem_ok.sum())} (총 {int(_miss_src.sum())}행)")

# ── CSV 저장 (synthesis_method 정규화 + other 복구 반영) ─────────────────────
if df_csv is not None and _has_csv:
    _tmp = _CSV_PATH.replace(".csv", "_tmp.csv")
    df_csv.to_csv(_tmp, index=False, encoding="utf-8-sig")
    os.replace(_tmp, _CSV_PATH)
    print(f"\nCSV 저장 완료: {_CSV_PATH}")

# ── Excel 저장 ────────────────────────────────────────────────────────────────
_xl = pd.ExcelFile(_PATH)
_sheets = {s: _xl.parse(s) for s in _xl.sheet_names
           if s not in ("합성조건", "Sheet1")}
_xl.close()

with pd.ExcelWriter(_PATH, engine="openpyxl") as _w:
    df.to_excel(_w, sheet_name="합성조건", index=False)
    for _sn, _sd in _sheets.items():
        _sd.to_excel(_w, sheet_name=_sn, index=False)

print(f"\n저장 완료: {_PATH}")

print(f"\n── synthesis_method 분포 (상위 12) ──────────────────────")
if "synthesis_method" in df.columns:
    vc = df["synthesis_method"].dropna().value_counts()
    for m, c in vc.head(12).items():
        print(f"  {m:<30} {c:>5,}편")
