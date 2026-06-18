"""
ceria_model.py — Stage 3: 예측·역설계 파이프라인

입력(우선순위 순):
  1. output/ceria_samples_merged.csv  (run_merge_samples.py + run_table_extraction 출력)
  2. output/ceria_samples.csv         (run_sample_extraction.py 출력)
  3. output/ceria_samples.jsonl

출력: output/model/ 폴더
  model_<target>_reg.pkl / model_<target>_clf.pkl  — 학습된 모델 (pickle)
  importance_<target>.png                           — 피처 중요도 그래프
  inverse_design_*.csv                              — 역설계 결과
  active_learning_suggestions.csv                  — 능동학습 실험 제안

실행:
  conda activate test
  pip install scikit-learn numpy pandas matplotlib
  python ceria_model.py

저장된 모델 불러오기:
  import pickle
  with open("output/model/model_particle_size_composite_reg.pkl", "rb") as f:
      model = pickle.load(f)
  pred = model.predict(X_new)
"""
import os, json, warnings, pickle, re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as _fm
warnings.filterwarnings("ignore")

_avail_fonts = {f.name for f in _fm.fontManager.ttflist}
for _fn in ["Malgun Gothic", "NanumGothic", "NanumBarunGothic", "AppleGothic", "DejaVu Sans"]:
    if _fn in _avail_fonts:
        plt.rcParams["font.family"] = _fn
        break
plt.rcParams["axes.unicode_minus"] = False

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# TargetEncoder: sklearn >= 1.3 에서 지원 (OHE보다 고빈도 범주형에 훨씬 효과적)
try:
    from sklearn.preprocessing import TargetEncoder
    _HAS_TARGET_ENC = True
except ImportError:
    _HAS_TARGET_ENC = False

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
BASE_DIR    = r"d:\머신러닝 교육\ceria_pipeline_data"
MERGED_PATH = os.path.join(BASE_DIR, "output", "ceria_samples_merged.csv")  # 병합본 우선
CSV_PATH    = os.path.join(BASE_DIR, "output", "ceria_samples.csv")
JSONL_PATH  = os.path.join(BASE_DIR, "output", "ceria_samples.jsonl")
MODEL_DIR   = os.path.join(BASE_DIR, "output", "model")
os.makedirs(MODEL_DIR, exist_ok=True)

_METRICS_CACHE: dict = {}  # evaluate() 결과를 수집; _save_performance_history()에서 읽음

# ── 피처 정의 ─────────────────────────────────────────────────────────────────
NUMERIC_FEATURES = [
    # ── 기본 합성 조건 ────────────────────────────────────────────────────────
    "synthesis_temperature_c",
    "synthesis_time_h",
    "ph_synthesis",
    "calcination_temperature_c",
    "calcination_time_h",
    "dopant_concentration_mol_pct",
    # ── 농도 피처 (R² 개선 최대 기여 예상) ──────────────────────────────────
    "ce_concentration_M",           # Ce 전구체 몰농도 (mol/L)
    "mineralizer_concentration_M",  # 광화제/침전제 몰농도 (mol/L)
    "ce_to_mineralizer_ratio",      # Ce/광화제 몰 비율 (파생)
    # ── 반응 스케일 피처 (synthesis_volume_mL 기반) ───────────────────────────
    "synthesis_volume_mL",          # 반응 볼륨 (mL)
    "log_synth_volume",             # log(반응 볼륨) — 열전달/믹싱 스케일 효과
    "ce_total_mol",                 # Ce 전구체 총 mol량 = 농도 × 부피 (물질량 스케일)
    # ── 이진 파생 피처 ────────────────────────────────────────────────────────
    "capping_present",      # 캡핑제 유무
    "has_mineralizer",      # 광화제 유무 (형태/크기에 강하게 영향)
    "has_dopant",           # 도핑 유무 (입자크기 감소 효과)
    # ── 물리 기반 log 변환 피처 ──────────────────────────────────────────────
    "log_synth_temp",       # log(합성온도) — Arrhenius 핵생성 속도
    "log_synth_time",       # log(합성시간) — Ostwald ripening: d ∝ t^(1/3)
    "log_calc_temp",        # log(하소온도) — 입자 성장: d ∝ exp(-Q/RT)
    # ── 상호작용 피처 (조건의 결합 효과) ─────────────────────────────────────
    "thermal_budget",       # 합성온도 × 합성시간 (열 에너지 투입량)
    "calc_thermal_budget",  # 하소온도 × 하소시간 (소결 정도)
    # ── 측정값 피처 (BET ↔ 입자크기 강한 역상관) ─────────────────────────────
    "bet_surface_area_m2g",
]

CATEGORICAL_FEATURES = [
    "synthesis_method",
    "anion_type",        # ce_precursor 음이온 계열 (nitrate/chloride/acetate 등)
    "ce_precursor",
    "solvent_type",      # 용매 계열 (aqueous/alcohol/polyol/polar_aprotic 등)
    "solvent",
    "mineralizer",
    "capping_agent",
    "chelating_agent",
    "oxidant",
    "dopant",
    "atmosphere",
]

# anion_type 파생 패턴 (normalize_data.py와 동일하게 유지)
_UNICODE_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_ANION_PATTERNS = [
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
    ("oxide",            r"^ceo2$|^ceo$|cezro|\bcerium oxide\b|\bceria\b"),
    ("metal_ion",        r"^ce$|^ce metal$|^ce\d?\+$|ce\(iii\)|ce\(iv\)|^ce3\+$|^ce4\+$"),
]

def _derive_anion(val: str) -> str:
    import re
    if not val or val == "unknown":
        return "unknown"
    v = val.translate(_UNICODE_SUB).lower().strip()
    for anion, pat in _ANION_PATTERNS:
        if re.search(pat, v, re.I):
            return anion
    return "other"

_SOLVENT_PATTERNS = [
    ("aqueous_alcohol",  r"water.*eth|eth.*water|water.*methanol|methanol.*water"
                         r"|water.*isoprop|isoprop.*water|water.*propanol|propanol.*water"
                         r"|h2o.*eth|eth.*h2o|aqueous.*alcohol"),
    ("aqueous_polyol",   r"water.*glycol|glycol.*water|water.*glycerol|glycerol.*water"
                         r"|h2o.*glycol|glycol.*h2o"),
    ("alcohol_polyol",   r"ethanol.*glycol|glycol.*ethanol|methanol.*glycol"),
    ("aqueous",          r"^water$|deion|distill|di\s*water|dw\b|ddw|ddh2o|milli.?q"
                         r"|\bh2o\b|ultrapure water|tap water|aqueous solution"
                         r"|double distill|triple distill|nanopure"),
    ("alcohol",          r"\bethanol\b|absolute ethanol|95%.ethanol|c2h5oh"
                         r"|\bmethanol\b|ch3oh|\bisopropanol\b|\bipa\b"
                         r"|2-propanol|isopropyl alcohol|1-butanol|2-butanol"
                         r"|n-propanol|1-propanol|tert-butanol|\bbutanol\b"),
    ("polyol",           r"ethylene glycol|\beg\b|diethylene glycol|\bdeg\b"
                         r"|propylene glycol|triethylene glycol|\bteg\b"
                         r"|\bglycerol\b|\bglycerine\b"),
    ("polar_aprotic",    r"\bdmf\b|dimethylformamide|\bdmso\b|dimethyl sulfoxide"
                         r"|\bnmp\b|n-methyl.2-pyrrolidone|\bacetonitrile\b|\bmecn\b"
                         r"|\bacetone\b|\bdioxane\b|thf\b|tetrahydrofuran"),
    ("nonpolar",         r"\btoluene\b|\bxylene\b|\bbenzene\b|\bhexane\b"
                         r"|\bheptane\b|\boctane\b|\bcyclohexane\b|\bdecane\b"
                         r"|\boctadecene\b|1-octadecene|\bdecalin\b|kerosene"),
    ("oleylamine",       r"oleylamine|\boam\b|oleic acid|\boia\b|1-octadecanol"
                         r"|trioctylphosphine|\btop\b|\btopo\b"),
    ("ionic_liquid",     r"\[emim\]|\[bmim\]|\[hmim\]|ionic liquid"),
]

def _derive_solvent(val: str) -> str:
    import re
    if not val or val == "unknown":
        return "unknown"
    v = re.sub(r"[;/,+]", " ", val.translate(_UNICODE_SUB).lower().strip())
    for stype, pat in _SOLVENT_PATTERNS:
        if re.search(pat, v, re.I):
            return stype
    return "other"

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# 타깃
TARGET_COMPOSITE = "particle_size_primary_nm"  # 1차 입자 (TEM→SEM)
TARGET_SIZE      = "particle_size_tem_nm"     # TEM 단독 (엄밀 분석용)
TARGET_XRD       = "crystallite_size_xrd_nm"
TARGET_BET       = "bet_surface_area_m2g"
TARGET_MORPH     = "morphology"               # 분류


# ── 데이터 로드 ────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    """병합 CSV → 원본 CSV → JSONL 순으로 로드."""
    if os.path.exists(MERGED_PATH):
        df = pd.read_csv(MERGED_PATH, low_memory=False)
        print(f"병합 CSV 로드: {len(df):,}행  (run_merge_samples.py 출력)")
    elif os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH, low_memory=False)
        print(f"CSV 로드: {len(df):,}행  (병합본 없음 — run_merge_samples.py 실행 권장)")
    elif os.path.exists(JSONL_PATH):
        rows = []
        with open(JSONL_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    flat = {
                        "doi":   rec.get("doi", ""),
                        "title": rec.get("title", ""),
                        "sample_id":     rec.get("sample_id", ""),
                        "discriminator": rec.get("discriminator", ""),
                        "confidence":    rec.get("confidence", "medium"),
                    }
                    flat.update(rec.get("materials") or {})
                    flat.update(rec.get("procedure") or {})
                    flat.update(rec.get("characterization") or {})
                    rows.append(flat)
                except Exception:
                    pass
        df = pd.DataFrame(rows)
        print(f"JSONL 로드: {len(df):,}행")
    else:
        raise FileNotFoundError(
            f"데이터 파일 없음.\n  CSV: {CSV_PATH}\n  JSONL: {JSONL_PATH}\n"
            "  먼저 run_sample_extraction.py를 실행하세요."
        )
    return df


# ── 전처리 ────────────────────────────────────────────────────────────────────
def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 수치 컬럼 강제 변환 (없는 컬럼은 NaN으로 생성)
    size_cols = [TARGET_COMPOSITE, TARGET_SIZE, TARGET_XRD, TARGET_BET,
                 "particle_size_sem_nm"]
    for col in NUMERIC_FEATURES + size_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif col not in size_cols:  # 피처 컬럼만 생성 (타깃은 없어도 됨)
            df[col] = np.nan

    # ── 이상값 제거 (1차 입자 0.3~500 nm) ───────────────────────────────────────
    for col in [TARGET_SIZE, "particle_size_sem_nm"]:
        if col in df.columns:
            df.loc[~df[col].between(0.3, 500), col] = np.nan
    # XRD Scherrer: 2~150 nm (< 2nm 물리적 불가, > 150nm Scherrer 한계 초과)
    if TARGET_XRD in df.columns:
        n_before = df[TARGET_XRD].notna().sum()
        df.loc[~df[TARGET_XRD].between(2, 150), TARGET_XRD] = np.nan
        n_removed = n_before - df[TARGET_XRD].notna().sum()
        if n_removed:
            print(f"  [품질] XRD Scherrer 범위(2~150nm) 이탈 제거: {n_removed}건")

    # ── 교차 필드 물리 검증 ───────────────────────────────────────────────────
    # XRD 결정자 크기는 일반적으로 TEM 입자 크기보다 작거나 같음
    # (다결정 입자: 1개 입자 안에 여러 결정자). XRD > TEM×1.5 이면 의심 → null 처리
    if TARGET_XRD in df.columns and TARGET_SIZE in df.columns:
        suspicious = (df[TARGET_XRD] > df[TARGET_SIZE] * 1.5) & \
                     df[TARGET_XRD].notna() & df[TARGET_SIZE].notna()
        n_sus = suspicious.sum()
        if n_sus:
            df.loc[suspicious, TARGET_XRD] = np.nan
            print(f"  [품질] XRD > TEM×1.5 의심 데이터 제거: {n_sus}건")

    # 합성온도 유효 범위 검증
    if "synthesis_temperature_c" in df.columns:
        df.loc[~df["synthesis_temperature_c"].between(0, 1500),
               "synthesis_temperature_c"] = np.nan
    if "calcination_temperature_c" in df.columns:
        df.loc[~df["calcination_temperature_c"].between(50, 1600),
               "calcination_temperature_c"] = np.nan

    # 복합 입자크기 생성: TEM → SEM (XRD 결정자 크기는 1차 입자 아님)
    if TARGET_COMPOSITE not in df.columns or df[TARGET_COMPOSITE].isna().all():
        df[TARGET_COMPOSITE] = pd.to_numeric(df.get(TARGET_SIZE), errors="coerce")
        if "particle_size_sem_nm" in df.columns:
            df[TARGET_COMPOSITE] = df[TARGET_COMPOSITE].fillna(
                pd.to_numeric(df["particle_size_sem_nm"], errors="coerce"))
    # composite도 이상값 제거
    if TARGET_COMPOSITE in df.columns:
        df.loc[~df[TARGET_COMPOSITE].between(0.3, 500), TARGET_COMPOSITE] = np.nan

    # ── 파생 이진 피처 ──────────────────────────────────────────────────────────
    def _is_empty(series_val):
        return pd.isna(series_val) or str(series_val).strip().lower() in (
            "", "none", "null", "unknown", "nan")

    for bin_col, src_col in [("capping_present", "capping_agent"),
                               ("has_mineralizer", "mineralizer"),
                               ("has_dopant",      "dopant")]:
        if src_col in df.columns:
            df[bin_col] = df[src_col].apply(lambda x: 0.0 if _is_empty(x) else 1.0)
        else:
            df[bin_col] = np.nan

    # ── 물리 기반 log 변환 피처 ──────────────────────────────────────────────
    for src, dst in [("synthesis_temperature_c",   "log_synth_temp"),
                      ("synthesis_time_h",           "log_synth_time"),
                      ("calcination_temperature_c",  "log_calc_temp")]:
        if src in df.columns:
            df[dst] = np.log(df[src].clip(lower=1))   # clip(1) avoids log(0)
        else:
            df[dst] = np.nan

    # ── 상호작용 피처 ────────────────────────────────────────────────────────
    for t_col, h_col, dst in [
        ("synthesis_temperature_c",  "synthesis_time_h",    "thermal_budget"),
        ("calcination_temperature_c","calcination_time_h",  "calc_thermal_budget"),
    ]:
        if t_col in df.columns and h_col in df.columns:
            df[dst] = df[t_col] * df[h_col]
        else:
            df[dst] = np.nan

    # BET: 없으면 NaN으로 생성 (HistGB는 NaN 처리 기본 지원)
    if "bet_surface_area_m2g" not in df.columns:
        df["bet_surface_area_m2g"] = np.nan
    else:
        df["bet_surface_area_m2g"] = pd.to_numeric(df["bet_surface_area_m2g"], errors="coerce")
        df.loc[~df["bet_surface_area_m2g"].between(1, 1500), "bet_surface_area_m2g"] = np.nan

    # ── 농도 피처 (4_extract_targeted.py 에서 추출된 신규 피처) ─────────────
    for c_col in ["ce_concentration_M", "mineralizer_concentration_M"]:
        if c_col in df.columns:
            df[c_col] = pd.to_numeric(df[c_col], errors="coerce")
            df.loc[~df[c_col].between(0.001, 20, inclusive="both"), c_col] = np.nan
        else:
            df[c_col] = np.nan

    if "ce_concentration_M" in df.columns and "mineralizer_concentration_M" in df.columns:
        ce_c  = df["ce_concentration_M"]
        min_c = df["mineralizer_concentration_M"]
        valid = ce_c.notna() & min_c.notna() & (min_c > 0)
        df["ce_to_mineralizer_ratio"] = np.nan
        df.loc[valid, "ce_to_mineralizer_ratio"] = (ce_c / min_c).where(valid)
        df.loc[~df["ce_to_mineralizer_ratio"].between(0.01, 100, inclusive="both"),
               "ce_to_mineralizer_ratio"] = np.nan
    else:
        df["ce_to_mineralizer_ratio"] = np.nan

    # ── 반응 볼륨 + ce_total_mol 파생 ───────────────────────────────────────
    if "synthesis_volume_mL" in df.columns:
        df["synthesis_volume_mL"] = pd.to_numeric(df["synthesis_volume_mL"], errors="coerce")
        df.loc[~df["synthesis_volume_mL"].between(0.5, 10000, inclusive="both"),
               "synthesis_volume_mL"] = np.nan
    else:
        df["synthesis_volume_mL"] = np.nan

    valid_vol = df["synthesis_volume_mL"].notna() & (df["synthesis_volume_mL"] > 0)
    df["log_synth_volume"] = np.nan
    df.loc[valid_vol, "log_synth_volume"] = np.log(df.loc[valid_vol, "synthesis_volume_mL"])

    df["ce_total_mol"] = np.nan
    if "ce_concentration_M" in df.columns:
        ce_c_num = pd.to_numeric(df["ce_concentration_M"], errors="coerce")
        valid_total = ce_c_num.notna() & valid_vol
        df.loc[valid_total, "ce_total_mol"] = (ce_c_num * df["synthesis_volume_mL"] / 1000).where(valid_total)
        df.loc[~df["ce_total_mol"].between(0.0001, 100, inclusive="both"), "ce_total_mol"] = np.nan

    # ── anion_type 파생 (ce_precursor 음이온 계열) ───────────────────────────
    if "ce_precursor" in df.columns:
        df["anion_type"] = (
            df["ce_precursor"].fillna("unknown").astype(str)
            .str.strip().str.lower()
            .map(_derive_anion)
        )
    else:
        df["anion_type"] = "unknown"

    # ── solvent_type 파생 (용매 계열) ────────────────────────────────────────
    if "solvent" in df.columns:
        df["solvent_type"] = (
            df["solvent"].fillna("unknown").astype(str)
            .str.strip().str.lower()
            .map(_derive_solvent)
        )
    else:
        df["solvent_type"] = "unknown"

    # ── 범주형 컬럼 — null → "unknown" ───────────────────────────────────────
    for col in CATEGORICAL_FEATURES:
        if col not in df.columns:
            df[col] = "unknown"
        else:
            df[col] = df[col].fillna("unknown").astype(str).str.strip().str.lower()

    # doi → group key
    if "doi" not in df.columns:
        df["doi"] = "unknown"
    df["doi"] = df["doi"].fillna("unknown").astype(str)

    return df


# ── 모델 빌더 ─────────────────────────────────────────────────────────────────
def build_pipeline(kind: str, early_stopping: bool = None) -> Pipeline:
    """
    kind='clf' or 'reg'

    범주형 인코딩:
    - sklearn >= 1.3: TargetEncoder (목표값 평균으로 인코딩, 고빈도 범주에 최적)
    - sklearn < 1.3: OHE 폴백

    HistGradientBoosting 개선점:
    - early_stopping=True: 과적합 방지, 최적 반복 수 자동 결정
    - learning_rate=0.05: 보수적 학습률 (정확도↑, 과적합↓)
    - max_leaf_nodes=31: 기본값 유지 (복잡도 균형)
    """
    if _HAS_TARGET_ENC:
        _target_type = "multiclass" if kind == "clf" else "continuous"
        cat_transformer = TargetEncoder(
            target_type=_target_type,
            smooth="auto",    # 빈도수 기반 자동 정규화
            cv=5,             # fold 내 leakage 방지
            shuffle=True,     # random_state 사용 시 shuffle=True 필수
            random_state=42,
        )
    else:
        cat_transformer = Pipeline([
            ("imp", SimpleImputer(strategy="constant", fill_value="unknown")),
            ("oh",  OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])

    pre = ColumnTransformer([
        ("num", "passthrough", NUMERIC_FEATURES),
        ("cat", cat_transformer, CATEGORICAL_FEATURES),
    ], remainder="drop")

    # Early stopping: validation_fraction 15% 홀드아웃으로 최적 반복 자동 탐색
    common_kwargs = dict(
        random_state=42,
        max_iter=500,
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=20,   # 소그룹 과적합 방지
    )
    if kind == "clf":
        # 분류기: early_stopping 비활성 — fold별 희귀 클래스로 stratified split 실패 방지
        # max_iter=200 (형태 acc≈0.24로 성능 제한적, 500은 ~20분 소요)
        use_es = False if early_stopping is None else early_stopping
        clf_kwargs = {**common_kwargs, "max_iter": 200}
        model = HistGradientBoostingClassifier(
            **clf_kwargs,
            early_stopping=use_es,
            n_iter_no_change=25,
        )
    else:
        use_es = True if early_stopping is None else early_stopping
        reg_es_kwargs = {"validation_fraction": 0.15, "n_iter_no_change": 25} if use_es else {}
        model = HistGradientBoostingRegressor(
            **common_kwargs,
            early_stopping=use_es,
            **reg_es_kwargs,
        )

    return Pipeline([("pre", pre), ("model", model)])



# 로그 변환 대상 타깃 (입자크기는 log-normal 분포 → log 공간에서 학습)
_LOG_TARGETS = {TARGET_COMPOSITE, TARGET_SIZE, TARGET_XRD}


# ── 평가 (논문 단위 GroupKFold — 누수 방지) ──────────────────────────────────
def evaluate(df: pd.DataFrame, target: str, kind: str,
             min_class: int = 5) -> Pipeline | None:
    sub = df.dropna(subset=[target]).copy()

    if kind == "clf":
        # 숫자값(오염 데이터) 제거 — morphology에 12.0 같은 값이 섞이는 경우 방어
        sub = sub[sub[target].apply(
            lambda v: isinstance(v, str) and v.strip() != ""
        )].copy()
        # 희귀 클래스 → "other" 통합 (fold 내 최소 2샘플 보장용으로 min_class=10)
        vc = sub[target].value_counts()
        sub[target] = sub[target].where(
            sub[target].isin(vc[vc >= max(min_class, 10)].index), "other"
        )
        # "other" 자체도 희귀하면 제거
        vc2 = sub[target].value_counts()
        sub = sub[sub[target].isin(vc2[vc2 >= 10].index)].copy()

    n_papers = sub["doi"].nunique()
    if len(sub) < 20 or n_papers < 3:
        print(f"  [{target}] 표본 부족({len(sub)}행, {n_papers}논문) — 데이터 더 수집 후 재실행")
        return None

    X, groups = sub[FEATURES], sub["doi"]
    n_splits = min(5, n_papers)
    cv = GroupKFold(n_splits=n_splits)
    est = build_pipeline(kind)

    # 입자크기 회귀: log 공간에서 학습 (log-normal 분포 대응, 정확도 향상)
    use_log = (kind == "reg" and target in _LOG_TARGETS)
    if use_log:
        y_raw = sub[target].values.copy()
        y = np.log(y_raw)
    else:
        y = sub[target]

    # 폴드별 예측 (전체 평가용)
    pred_y = cross_val_predict(est, X, y, groups=groups, cv=cv)

    # 폴드별 점수 (안정성 확인용)
    fold_scoring = "f1_macro" if kind == "clf" else "neg_mean_absolute_error"
    try:
        fold_scores = cross_val_score(est, X, y, groups=groups, cv=cv,
                                      scoring=fold_scoring, n_jobs=-1)
        score_mean = fold_scores.mean()
        score_std  = fold_scores.std()
    except Exception:
        fold_scores = np.array([])
        score_mean = score_std = np.nan

    if kind == "clf":
        acc = (pred_y == y).mean()
        f1  = f1_score(y, pred_y, average="macro", zero_division=0)
        print(f"  [{target}] acc={acc:.3f}  macroF1={f1:.3f}"
              f"  fold_f1={score_mean:.3f}±{score_std:.3f}"
              f"  (n={len(sub)}, papers={n_papers})")
    else:
        mae = mean_absolute_error(y, pred_y)
        r2  = r2_score(y, pred_y)
        if use_log:
            pred_nm  = np.exp(pred_y)
            mae_nm   = mean_absolute_error(y_raw, pred_nm)
            rmse_nm  = np.sqrt(mean_squared_error(y_raw, pred_nm))
            mdae_nm  = np.median(np.abs(y_raw - pred_nm))
            r2_nm    = r2_score(y_raw, pred_nm)
            fold_mae_nm = -score_mean if not np.isnan(score_mean) else np.nan
            print(f"  [{target}] log-R²={r2:.3f} | "
                  f"nm-MAE={mae_nm:.2f}  RMSE={rmse_nm:.2f}  MdAE={mdae_nm:.2f}nm"
                  f"  nm-R²={r2_nm:.3f}"
                  f"  fold-MAE={fold_mae_nm:.3f}±{score_std:.3f}"
                  f"  (n={len(sub)}, papers={n_papers})")
            _METRICS_CACHE[target] = {
                "log_r2": float(r2), "r2_nm": float(r2_nm),
                "mae_nm": float(mae_nm), "rmse_nm": float(rmse_nm),
                "mdae_nm": float(mdae_nm), "n": int(len(sub)), "n_papers": int(n_papers),
            }
        else:
            rmse = np.sqrt(mean_squared_error(y, pred_y))
            mdae = np.median(np.abs(y - pred_y))
            print(f"  [{target}] MAE={mae:.4f}  RMSE={rmse:.4f}  MdAE={mdae:.4f}  R²={r2:.3f}"
                  f"  fold-MAE={-score_mean:.4f}±{score_std:.4f}"
                  f"  (n={len(sub)}, papers={n_papers})")

    # 전체 데이터로 재학습 (log 공간)
    est.fit(X, y)

    # 모델 저장 (pickle)
    model_file = os.path.join(MODEL_DIR, f"model_{target}_{kind}.pkl")
    try:
        with open(model_file, "wb") as _f:
            pickle.dump(est, _f)
        print(f"    모델 저장: {model_file}")
    except Exception as _e:
        print(f"    모델 저장 실패: {_e}")

    # 피처 중요도
    scoring = "f1_macro" if kind == "clf" else "neg_mean_absolute_error"
    try:
        imp = permutation_importance(
            est, X, y, n_repeats=8, random_state=42, scoring=scoring, n_jobs=-1
        )
        importance = pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False)
        print(f"    상위 피처: {importance.head(5).to_dict()}")
        _plot_importance(importance, target)
    except Exception as e:
        print(f"    피처 중요도 계산 오류: {e}")

    return est


def _save_performance_history(df: pd.DataFrame) -> None:
    """HistGBM 평가 결과를 output/model/performance_history.json에 누적 저장."""
    if not _METRICS_CACHE:
        return
    from datetime import datetime
    hist_path = os.path.join(MODEL_DIR, "performance_history.json")
    if os.path.exists(hist_path):
        with open(hist_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []

    today_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    today_date = today_str[:10]

    # coverage_pct 계산
    target_col = "particle_size_primary_nm"
    coverage_pct = None
    if target_col in df.columns:
        coverage_pct = round(float(df[target_col].notna().mean() * 100), 1)

    entry = {
        "session_label": "auto",
        "run_date": today_str,
        "n_samples": int(len(df)),
        "n_papers": int(df["doi"].nunique()) if "doi" in df.columns else None,
        "n_features": len(FEATURES),
        "coverage_pct": coverage_pct,
        "note": "auto-saved",
        "histgbm": {k: v for k, v in _METRICS_CACHE.items()},
        "dkl_gp": None,
        "lgbm": None,
        "catboost": None,
    }

    # 같은 날짜(auto) 항목 대체
    history = [h for h in history if not (h.get("session_label") == "auto" and h.get("run_date", "")[:10] == today_date)]
    history.append(entry)

    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  성능 이력 저장: {hist_path}")


def _plot_importance(importance: pd.Series, target: str):
    top = importance.head(12)
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#E87C4C" if v > 0 else "#4C9BE8" for v in top.values]
    ax.barh(top.index[::-1], top.values[::-1], color=colors[::-1])
    ax.set_xlabel("Permutation Importance (mean)", fontsize=11)
    ax.set_title(f"Feature Importance — {target}", fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(MODEL_DIR, f"importance_{target}.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"    저장: {path}")


# ── 역설계 (정방향 모델로 후보 채점) ─────────────────────────────────────────
def inverse_design(
    clf: Pipeline | None,
    reg: Pipeline | None,
    df: pd.DataFrame,
    target_morph: str | None = None,
    target_size_nm: float | None = None,
    top_k: int = 10,
) -> pd.DataFrame:
    """
    목표 형상(target_morph) + 목표 크기(target_size_nm)를
    동시에 만족하는 합성 조건 후보를 역탐색.
    """
    rng = np.random.default_rng(0)
    n_cand = 5000

    cand = pd.DataFrame(index=range(n_cand))

    for col in NUMERIC_FEATURES:
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(vals) == 0:
            cand[col] = np.nan
        else:
            cand[col] = rng.uniform(float(vals.quantile(0.05)), float(vals.quantile(0.95)), n_cand)

    for col in CATEGORICAL_FEATURES:
        vals = df[col].dropna()
        vals = vals[vals != "unknown"]
        if len(vals) == 0:
            cand[col] = "unknown"
        else:
            cand[col] = rng.choice(vals.unique(), n_cand)

    # 파생 피처 생성 (학습 데이터와 동일한 변환 적용)
    def _is_empty_val(x):
        return pd.isna(x) or str(x).lower() in ("none", "unknown", "")

    cand["capping_present"] = cand["capping_agent"].apply(
        lambda x: 0.0 if _is_empty_val(x) else 1.0)
    cand["has_mineralizer"] = cand["mineralizer"].apply(
        lambda x: 0.0 if _is_empty_val(x) else 1.0)
    cand["has_dopant"] = cand["dopant"].apply(
        lambda x: 0.0 if _is_empty_val(x) else 1.0)

    # 물리 기반 log 변환
    for src, dst in [("synthesis_temperature_c", "log_synth_temp"),
                      ("synthesis_time_h",         "log_synth_time"),
                      ("calcination_temperature_c","log_calc_temp")]:
        cand[dst] = np.log(cand[src].clip(lower=1))

    # 상호작용 피처
    cand["thermal_budget"]      = cand["synthesis_temperature_c"] * cand["synthesis_time_h"]
    cand["calc_thermal_budget"] = cand["calcination_temperature_c"] * cand["calcination_time_h"]

    # BET: 후보 데이터는 BET 없음 → NaN
    cand["bet_surface_area_m2g"] = np.nan

    X_cand = cand[FEATURES]
    score  = np.ones(n_cand)

    if clf is not None and target_morph is not None:
        try:
            classes = list(clf.named_steps["model"].classes_)
            if target_morph in classes:
                p = clf.predict_proba(X_cand)[:, classes.index(target_morph)]
                score *= p
                cand["pred_morph_prob"] = p
        except Exception:
            pass

    if reg is not None and target_size_nm is not None:
        try:
            pred_log = reg.predict(X_cand)
            # 모델이 log 공간에서 학습됐으므로 목표도 log 공간으로 변환해 점수화
            # σ = 0.3 in log-space ≈ ±35% 허용 범위 (log-normal 적합)
            target_log = np.log(target_size_nm)
            size_score = np.exp(-((pred_log - target_log) ** 2) / (2 * 0.3 ** 2))
            pred_size  = np.exp(pred_log)   # nm 단위로 역변환 (출력용)
            score *= size_score
            cand["pred_size_nm"] = pred_size
        except Exception:
            pass

    cand["score"] = score
    result = (cand.sort_values("score", ascending=False)
                  .head(top_k)
                  .reset_index(drop=True))

    show_cols = (["score"] +
                 [c for c in ["pred_morph_prob", "pred_size_nm"] if c in result.columns] +
                 ["synthesis_method", "mineralizer", "capping_agent",
                  "synthesis_temperature_c", "synthesis_time_h",
                  "ph_synthesis", "calcination_temperature_c",
                  "ce_precursor", "solvent", "dopant"])
    show_cols = [c for c in show_cols if c in result.columns]
    return result[show_cols]


# ── 능동학습 — 불확실성 큰 조건 제안 ─────────────────────────────────────────
def suggest_experiments(clf: Pipeline, df: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    """
    분류 모델의 엔트로피(불확실성)가 가장 높은 후보 조건 제안.
    이 조건들을 실험하면 모델 개선 효과가 가장 크다.
    """
    rng = np.random.default_rng(1)
    n_cand = 3000
    cand = pd.DataFrame(index=range(n_cand))

    for col in NUMERIC_FEATURES:
        vals = df[col].dropna()
        cand[col] = (rng.uniform(vals.quantile(0.05), vals.quantile(0.95), n_cand)
                     if len(vals) > 0 else np.nan)
    for col in CATEGORICAL_FEATURES:
        vals = df[col].dropna()
        vals = vals[vals != "unknown"]
        cand[col] = (rng.choice(vals.unique(), n_cand) if len(vals) > 0 else "unknown")

    # inverse_design과 동일한 파생 피처 생성 (미생성 시 FEATURES 인덱스 불일치로 크래시)
    def _is_empty_val(x):
        return pd.isna(x) or str(x).lower() in ("none", "unknown", "")

    cand["capping_present"] = cand["capping_agent"].apply(
        lambda x: 0.0 if _is_empty_val(x) else 1.0)
    cand["has_mineralizer"] = cand["mineralizer"].apply(
        lambda x: 0.0 if _is_empty_val(x) else 1.0)
    cand["has_dopant"] = cand["dopant"].apply(
        lambda x: 0.0 if _is_empty_val(x) else 1.0)

    for src, dst in [("synthesis_temperature_c", "log_synth_temp"),
                      ("synthesis_time_h",         "log_synth_time"),
                      ("calcination_temperature_c","log_calc_temp")]:
        cand[dst] = np.log(cand[src].clip(lower=1))

    cand["thermal_budget"]      = cand["synthesis_temperature_c"] * cand["synthesis_time_h"]
    cand["calc_thermal_budget"] = cand["calcination_temperature_c"] * cand["calcination_time_h"]
    cand["bet_surface_area_m2g"] = np.nan

    proba = clf.predict_proba(cand[FEATURES])
    cand["uncertainty"] = -(proba * np.log(proba + 1e-12)).sum(axis=1)
    return (cand.sort_values("uncertainty", ascending=False)
                .head(top_k)
                .reset_index(drop=True)
                [["uncertainty", "synthesis_method", "mineralizer",
                  "synthesis_temperature_c", "synthesis_time_h",
                  "capping_agent", "ph_synthesis"]])


# ── 대시보드용 실시간 예측 API ────────────────────────────────────────────────
def predict_synthesis_conditions(
    df: pd.DataFrame,
    target_size_nm: float | None = None,
    target_morph: str | None = None,
    model_dir: str = MODEL_DIR,
    top_k: int = 10,
) -> dict:
    """
    대시보드에서 호출: 희망 크기(nm)와 형태를 입력받아
    ① 크기 전용  ② 형태 전용  ③ 크기+형태 조합 추천 조건을 반환.

    df는 raw CSV(ceria_samples_merged.csv)를 그대로 전달해도 됨.
    내부에서 preprocess()를 적용해 파생 피처를 자동 생성한다.

    Returns
    -------
    dict with keys:
      'size_only'  : pd.DataFrame | None — 크기 목표 최적 Top-K
      'morph_only' : pd.DataFrame | None — 형태 목표 최적 Top-K
      'combined'   : pd.DataFrame | None — 크기+형태 조합 Top-K
      'metadata'   : dict  — has_reg, has_clf, morph_classes 등
    """
    # raw CSV → 파생 피처 포함 전처리 (load_data()와 동일 경로)
    if "log_synth_temp" not in df.columns:
        df = preprocess(df.copy())

    reg: Pipeline | None = None
    clf: Pipeline | None = None

    _reg_p = os.path.join(model_dir, "model_particle_size_primary_nm_reg.pkl")
    _clf_p = os.path.join(model_dir, "model_morphology_clf.pkl")

    if os.path.exists(_reg_p):
        with open(_reg_p, "rb") as _f:
            reg = pickle.load(_f)
    if os.path.exists(_clf_p):
        with open(_clf_p, "rb") as _f:
            clf = pickle.load(_f)

    morph_classes: list = []
    if clf is not None:
        try:
            morph_classes = list(clf.named_steps["model"].classes_)
        except Exception:
            pass

    # ① 크기 전용 (형태 제약 없음)
    size_only = None
    if reg is not None and target_size_nm is not None:
        size_only = inverse_design(
            clf=None, reg=reg, df=df,
            target_morph=None, target_size_nm=float(target_size_nm), top_k=top_k,
        )

    # ② 형태 전용 (크기 제약 없음)
    morph_only = None
    if clf is not None and target_morph:
        morph_only = inverse_design(
            clf=clf, reg=None, df=df,
            target_morph=target_morph, target_size_nm=None, top_k=top_k,
        )

    # ③ 크기 + 형태 조합 (동시 최적화)
    combined = None
    both_ok = (reg is not None or clf is not None) and (
        target_size_nm is not None or bool(target_morph)
    )
    if both_ok:
        combined = inverse_design(
            clf=clf, reg=reg, df=df,
            target_morph=target_morph if target_morph else None,
            target_size_nm=float(target_size_nm) if target_size_nm is not None else None,
            top_k=top_k,
        )

    return {
        "size_only":  size_only,
        "morph_only": morph_only,
        "combined":   combined,
        "metadata": {
            "has_reg":       reg is not None,
            "has_clf":       clf is not None,
            "target_size_nm": target_size_nm,
            "target_morph":  target_morph,
            "morph_classes": morph_classes,
        },
    }


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("CeO₂ 합성 ML 파이프라인 — Stage 3")
    print(f"  TargetEncoder: {'사용 (sklearn ≥1.3)' if _HAS_TARGET_ENC else '미사용 (OHE 폴백)'}")
    print(f"  피처 수: {len(FEATURES)} ({len(NUMERIC_FEATURES)} 수치 + {len(CATEGORICAL_FEATURES)} 범주형)")
    print("=" * 60)

    df_raw = load_data()
    df     = preprocess(df_raw)

    # confidence 필터 — low 제외 (있을 경우)
    if "confidence" in df.columns:
        before = len(df)
        df = df[df["confidence"].isin(["high", "medium", "unknown", ""])]
        print(f"confidence 필터: {before} → {len(df)}행 (low 제외)")

    print(f"\n전처리 후: {len(df):,}행  |  논문: {df['doi'].nunique():,}편")

    # 새 파생 피처 유효율 확인
    derived_cols = ["log_synth_temp", "thermal_budget", "has_mineralizer",
                    "has_dopant", "bet_surface_area_m2g"]
    print("\n[파생 피처 유효율]")
    for c in derived_cols:
        if c in df.columns:
            n = df[c].notna().sum()
            print(f"  {c:<28} {n:,}행 ({n/len(df)*100:.1f}%)")

    # 타깃별 유효 데이터 수
    print()
    for t in [TARGET_COMPOSITE, TARGET_SIZE, TARGET_XRD, TARGET_BET, TARGET_MORPH]:
        if t in df.columns:
            n = df[t].notna().sum()
            pct = n / len(df) * 100
            print(f"  {t}: {n:,}행 ({pct:.1f}%)")

    print("\n" + "─" * 40)
    print("모델 학습 & 평가 (논문 단위 GroupKFold)")
    print("─" * 40)

    # 회귀 — 복합 입자크기 (최대 커버리지 — 역설계 핵심 모델)
    print("\n[회귀] 복합 입자크기 예측 (TEM+XRD+SEM, 최대 커버리지)")
    reg_composite = evaluate(df, TARGET_COMPOSITE, "reg")

    # 회귀 — TEM 단독 (엄밀 분석용)
    print("\n[회귀] TEM 입자크기 예측 (TEM 단독)")
    reg_tem = evaluate(df, TARGET_SIZE, "reg")

    # 회귀 — XRD 결정자 크기
    print("\n[회귀] XRD 결정자 크기 예측")
    reg_xrd = evaluate(df, TARGET_XRD, "reg")

    # 분류 — 형태
    print("\n[분류] 입자 형태 예측")
    try:
        clf_morph = evaluate(df, TARGET_MORPH, "clf")
    except MemoryError as _me:
        print(f"  [SKIP] 형태 분류 OOM 오류 — 회귀 결과는 저장됨: {_me}")
        clf_morph = None


    print("\n" + "─" * 40)
    print("역설계 (목표 조건 탐색)")
    print("─" * 40)

    reg_best = reg_composite or reg_tem  # 복합 모델 우선, 없으면 TEM 단독
    if reg_best is not None or clf_morph is not None:
        print("\n목표: 형태=cube, 크기≈10nm")
        result = inverse_design(
            clf=clf_morph,
            reg=reg_best,
            df=df,
            target_morph="cube",
            target_size_nm=10.0,
            top_k=10,
        )
        print(result.to_string())
        out_path = os.path.join(MODEL_DIR, "inverse_design_cube_10nm.csv")
        result.to_csv(out_path, index=False)
        print(f"\n역설계 결과 저장: {out_path}")

        print("\n목표: 형태=rod, 크기≈30nm")
        result2 = inverse_design(
            clf=clf_morph,
            reg=reg_best,
            df=df,
            target_morph="rod",
            target_size_nm=30.0,
            top_k=10,
        )
        print(result2.to_string())
        out_path2 = os.path.join(MODEL_DIR, "inverse_design_rod_30nm.csv")
        result2.to_csv(out_path2, index=False)
        print(f"역설계 결과 저장: {out_path2}")

    print("\n" + "─" * 40)
    print("능동학습 — 다음 실험 제안 (형태 불확실성)")
    print("─" * 40)

    # 형태 능동학습 — 분류 엔트로피
    if clf_morph is not None:
        suggestions = suggest_experiments(clf_morph, df, top_k=5)
        print("\n형태 불확실성 최대 조건 (분류 모델 개선 효과 최대):")
        print(suggestions.to_string())
        morph_path = os.path.join(MODEL_DIR, "active_learning_morph_histgbm.csv")
        suggestions.to_csv(morph_path, index=False)
        print(f"저장: {morph_path}")
        # 하위호환 — 기존 파일명도 유지
        suggestions.to_csv(os.path.join(MODEL_DIR, "active_learning_suggestions.csv"), index=False)

    _save_performance_history(df)

    print("\n" + "=" * 60)
    print("완료. 결과 디렉토리:", MODEL_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
