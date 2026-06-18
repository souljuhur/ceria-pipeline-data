"""
12d_targeted_design.py — 목표 입자크기별 합성 조건 역설계 (95% 예측 구간)

목적:
  TEM/SEM 1차 입자 크기 (예: 10 / 30 / 60 nm)를 얻기 위한
  최적 습식합성 조건을 LightGBM 분위 회귀로 도출.

방법:
  Q2.5 + Q50 + Q97.5 세 모델 동시 학습 (log-space)
  → 95% 예측 구간 [Q2.5, Q97.5] 를 갖는 후보 조건 탐색

출력:
  output/model/targeted_design_10nm.csv  (목표 크기별)
  output/model/targeted_design_30nm.csv
  output/model/targeted_design_60nm.csv
  output/model/targeted_design_summary.xlsx   (3시트 통합)
  output/model/targeted_design_ci_plot.png    (신뢰구간 시각화)

실행:
  python 12d_targeted_design.py
  python 12d_targeted_design.py --targets 10 30 60
  python 12d_targeted_design.py --targets 10 30 60 --top 8
"""
import os, sys, warnings, argparse
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as _fm
warnings.filterwarnings("ignore")

# 한글 폰트 자동 탐색 (Windows: Malgun Gothic, macOS: AppleGothic, Linux: NanumGothic)
_avail_fonts = {f.name for f in _fm.fontManager.ttflist}
for _fn in ["Malgun Gothic", "NanumGothic", "NanumBarunGothic", "AppleGothic", "DejaVu Sans"]:
    if _fn in _avail_fonts:
        plt.rcParams["font.family"] = _fn
        break
plt.rcParams["axes.unicode_minus"] = False

# ── 12_model.py 공통 모듈 ────────────────────────────────────────────────────
import importlib.util
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "m12", os.path.join(_SCRIPT_DIR, "12_model.py"))
m12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m12)

MODEL_DIR            = os.path.join(m12.BASE_DIR, "output", "model")
os.makedirs(MODEL_DIR, exist_ok=True)

NUMERIC_FEATURES     = m12.NUMERIC_FEATURES
CATEGORICAL_FEATURES = m12.CATEGORICAL_FEATURES
FEATURES             = m12.FEATURES

try:
    import lightgbm as lgb
except ImportError:
    sys.exit("lightgbm 미설치: pip install lightgbm")
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score

# ── 설정 ──────────────────────────────────────────────────────────────────────
# 1차 입자 타깃: TEM → SEM (XRD 결정자 크기 제외)
PRIMARY_TARGET = "particle_size_primary_nm"

# 탐색 대상 습식 합성법
WET_METHODS = {
    "hydrothermal", "solvothermal", "precipitation",
    "co-precipitation", "sol-gel", "wet_chemical",
    "microwave", "sonochemical", "template",
}

# 출력에 포함할 실험 조건 컬럼
DESIGN_COLS = [
    "synthesis_method", "ce_precursor", "solvent",
    "mineralizer", "capping_agent", "chelating_agent",
    "synthesis_temperature_c", "synthesis_time_h", "ph_synthesis",
    "atmosphere",
]

# ── 1. 데이터 로드 + 1차 입자 타깃 생성 ──────────────────────────────────────
def prepare_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    """12_model.preprocess + TEM/SEM 1차 입자 타깃 생성."""
    df = m12.preprocess(df_raw)

    # 1차 입자 크기: 병합본에 이미 있으면 재사용, 없으면 TEM→SEM 파생
    if PRIMARY_TARGET not in df.columns or df[PRIMARY_TARGET].isna().all():
        tem = pd.to_numeric(df.get("particle_size_tem_nm", pd.Series(dtype=float)), errors="coerce")
        sem = pd.to_numeric(df.get("particle_size_sem_nm", pd.Series(dtype=float)), errors="coerce")
        tem_v = tem.where(tem.between(0.3, 500))
        sem_v = sem.where(sem.between(0.3, 500))
        df[PRIMARY_TARGET] = tem_v.combine_first(sem_v)
    else:
        df[PRIMARY_TARGET] = pd.to_numeric(df[PRIMARY_TARGET], errors="coerce")

    # 습식 방법만 유지
    if "synthesis_method" in df.columns:
        df = df[df["synthesis_method"].isin(WET_METHODS)].copy()

    return df


# ── 2. 범주형 라벨 인코딩 ─────────────────────────────────────────────────────
def encode_cats(df: pd.DataFrame):
    encoders, df_enc = {}, df.copy()
    for col in CATEGORICAL_FEATURES:
        le = LabelEncoder()
        df_enc[col] = le.fit_transform(df_enc[col].astype(str))
        encoders[col] = le
    return df_enc, encoders


def safe_encode(df: pd.DataFrame, encoders: dict) -> pd.DataFrame:
    """미지 범주 → 0 으로 안전 인코딩."""
    df_enc = df.copy()
    for col in CATEGORICAL_FEATURES:
        le    = encoders[col]
        known = set(le.classes_)
        df_enc[col] = df_enc[col].astype(str).apply(
            lambda x: int(le.transform([x])[0]) if x in known else 0
        )
    return df_enc


# ── 3. LightGBM 분위 회귀 학습 ───────────────────────────────────────────────
def train_quantile_models(df: pd.DataFrame) -> tuple:
    """Q12.5 / Q50 / Q87.5 세 모델을 log-space 로 학습."""
    sub = df.dropna(subset=[PRIMARY_TARGET]).copy()
    sub = sub[sub[PRIMARY_TARGET] > 0].copy()

    n_rows   = len(sub)
    n_papers = sub["doi"].nunique()
    y_raw    = sub[PRIMARY_TARGET].values.astype(float)
    y_log    = np.log(y_raw)

    print(f"  학습 데이터: {n_rows:,}행  |  논문: {n_papers:,}편")
    print(f"  1차 입자 크기 범위: {y_raw.min():.1f} ~ {y_raw.max():.1f} nm  "
          f"(중앙값 {np.median(y_raw):.1f} nm)")

    if n_rows < 20:
        sys.exit("1차 입자크기(TEM/SEM) 데이터 부족 (< 20행). "
                 "먼저 2_extract.py → 3_merge.py 를 실행하세요.")

    sub_enc, encoders = encode_cats(sub)
    X      = sub_enc[FEATURES]
    groups = sub["doi"]

    # ── LightGBM 분위 회귀 공통 파라미터 ─────────────────────────────────────
    lgbm_params = dict(
        n_estimators=800,
        learning_rate=0.04,
        num_leaves=31,
        min_child_samples=10,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.05,
        reg_lambda=0.1,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )

    models = {}
    for q in [0.025, 0.50, 0.975]:
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, **lgbm_params)
        m.fit(X, y_log, categorical_feature=CATEGORICAL_FEATURES)
        models[q] = m

    # ── GroupKFold 검증 (Q50 기준) ────────────────────────────────────────────
    n_splits  = min(5, n_papers)
    cv        = GroupKFold(n_splits=n_splits)
    oof_log   = np.zeros(n_rows)
    for tr, val in cv.split(X, y_log, groups):
        m_cv = lgb.LGBMRegressor(objective="quantile", alpha=0.50, **lgbm_params)
        m_cv.fit(X.iloc[tr], y_log[tr], categorical_feature=CATEGORICAL_FEATURES)
        oof_log[val] = m_cv.predict(X.iloc[val])

    oof_nm = np.exp(oof_log)
    mae    = mean_absolute_error(y_raw, oof_nm)
    r2     = r2_score(y_raw, oof_nm)
    r2_log = r2_score(y_log, oof_log)
    print(f"  [GroupKFold CV] log-R²={r2_log:.3f}  nm-MAE={mae:.2f} nm  nm-R²={r2:.3f}")

    return models, encoders, sub


# ── 4. 후보 합성 조건 생성 ────────────────────────────────────────────────────
def build_candidates(df: pd.DataFrame, n: int = 100_000) -> pd.DataFrame:
    """관측된 데이터 분포 기반으로 습식합성 후보 조건 생성."""
    rng  = np.random.default_rng(42)
    cand = {}

    # ── 합성법 (습식, 빈도 가중) ─────────────────────────────────────────────
    method_vc = (
        df["synthesis_method"].value_counts(normalize=True)
        .reindex([m for m in WET_METHODS if m in df["synthesis_method"].unique()])
        .dropna()
    )
    if method_vc.empty:
        method_vc = pd.Series({"hydrothermal": 0.5, "precipitation": 0.3, "sol-gel": 0.2})
    cand["synthesis_method"] = rng.choice(
        method_vc.index.tolist(), size=n,
        p=method_vc.values / method_vc.values.sum(),
    )

    # ── 범주형 피처: 관측 빈도 상위 풀에서 샘플링 ────────────────────────────
    def _pool(col, top_k=10, include_empty=True):
        vals = (df[col].replace("unknown", np.nan)
                .dropna().value_counts().head(top_k).index.tolist())
        if include_empty:
            vals = ["unknown"] + vals
        return vals or ["unknown"]

    cand["ce_precursor"]   = rng.choice(_pool("ce_precursor",   8,  False), size=n)
    cand["solvent"]        = rng.choice(_pool("solvent",        8,  False), size=n)
    cand["mineralizer"]    = rng.choice(_pool("mineralizer",    10, True),  size=n)
    cand["capping_agent"]  = rng.choice(_pool("capping_agent",  10, True),  size=n)
    cand["chelating_agent"]= rng.choice(_pool("chelating_agent",8,  True),  size=n)
    cand["oxidant"]        = "unknown"
    cand["dopant"]         = "unknown"
    cand["dopant_concentration_mol_pct"] = np.nan

    atm_pool = _pool("atmosphere", 6, True)
    cand["atmosphere"] = rng.choice(atm_pool, size=n)

    # ── 수치형: 방법에 따른 물리적 범위 ─────────────────────────────────────
    methods = cand["synthesis_method"]
    temp_arr = np.empty(n)
    time_arr = rng.choice([1, 2, 4, 6, 8, 12, 16, 24, 36, 48, 72],
                           size=n).astype(float)
    ph_arr   = rng.uniform(7, 14, n)

    for i, m in enumerate(methods):
        if m in ("hydrothermal", "solvothermal", "microwave"):
            temp_arr[i] = rng.uniform(100, 250)
        elif m in ("precipitation", "co-precipitation", "wet_chemical", "sonochemical"):
            temp_arr[i] = rng.uniform(20, 100)
        elif m == "sol-gel":
            temp_arr[i] = rng.uniform(40, 180)
        elif m == "template":
            temp_arr[i] = rng.uniform(60, 200)
        else:
            temp_arr[i] = rng.uniform(60, 220)

    cand["synthesis_temperature_c"]   = temp_arr
    cand["synthesis_time_h"]          = time_arr
    cand["ph_synthesis"]              = ph_arr
    cand["calcination_temperature_c"] = np.nan
    cand["calcination_time_h"]        = np.nan
    cand["drying_temperature_c"]      = np.nan
    cand["bet_surface_area_m2g"]      = np.nan
    cand["doi"]                       = "candidate"

    cand_df = pd.DataFrame(cand)

    # m12.preprocess 로 파생 피처 자동 계산 (anion_type, solvent_type, log, thermal_budget …)
    cand_df = m12.preprocess(cand_df)
    return cand_df


# ── 5. 역설계 메인 ────────────────────────────────────────────────────────────
def inverse_design(models, encoders, df_train: pd.DataFrame,
                   target_nm_list: list,
                   n_cand: int = 100_000, top_k: int = 5) -> dict:

    print(f"\n후보 조건 {n_cand:,}개 생성 중...")
    cand = build_candidates(df_train, n=n_cand)
    cand_enc = safe_encode(cand, encoders)
    X_cand = cand_enc[FEATURES]

    print("분위 예측 중 (Q2.5 / Q50 / Q97.5)...")
    q025_log = models[0.025].predict(X_cand)
    q50_log  = models[0.500].predict(X_cand)
    q975_log = models[0.975].predict(X_cand)

    # quantile crossing 방지: 세 분위값을 오름차순 정렬
    _stacked  = np.sort(np.stack([q025_log, q50_log, q975_log], axis=1), axis=1)
    q025_log, q50_log, q975_log = _stacked[:, 0], _stacked[:, 1], _stacked[:, 2]

    # log → nm
    cand["q50_nm"]      = np.exp(q50_log)
    cand["q025_nm"]     = np.exp(q025_log)   # 95% CI 하한 (nm)
    cand["q975_nm"]     = np.exp(q975_log)   # 95% CI 상한 (nm)
    cand["ci_width_nm"] = cand["q975_nm"] - cand["q025_nm"]

    # Gaussian 가정 표준편차 추정 (95% CI = ±1.96σ)
    sigma_log = np.maximum((q975_log - q025_log) / (2 * 1.96), 0.01)

    all_results = {}

    for target_nm in target_nm_list:
        target_log = np.log(target_nm)
        tol_frac   = 0.25  # ±25% 허용
        tol_log    = np.log(1 + tol_frac)

        # ── 스코어 계산 ────────────────────────────────────────────────────────
        # ① 95% 구간이 목표를 포함하는지
        in_ci = (q025_log <= target_log) & (target_log <= q975_log)

        # ② P(|log_size - log_target| ≤ tol_log) : Gaussian 근사 확률
        prob = (
            stats.norm.cdf(target_log + tol_log, q50_log, sigma_log)
            - stats.norm.cdf(target_log - tol_log, q50_log, sigma_log)
        )

        # ③ 최종 점수: 구간 포함 보너스 + 확률 + 좁은 CI 선호
        score = (
            in_ci.astype(float) * 2.0
            + prob
            - 0.25 * (q975_log - q025_log)   # 구간 넓을수록 불이익
        )

        cand_t = cand.copy()
        cand_t["_score"]   = score
        cand_t["_prob"]    = prob
        cand_t["_in_ci"]   = in_ci
        cand_t["_target"]  = target_nm

        # ── 다양성 필터: (method, ce_precursor) 중복 최대 2개 ────────────────
        cand_sorted = cand_t.sort_values("_score", ascending=False)
        seen, rows  = {}, []
        for _, r in cand_sorted.iterrows():
            key = (r["synthesis_method"], r["ce_precursor"])
            cnt = seen.get(key, 0)
            if cnt < 2:
                rows.append(r)
                seen[key] = cnt + 1
            if len(rows) >= top_k:
                break

        result_df = pd.DataFrame(rows).reset_index(drop=True)

        # ── 열 정리 + 반올림 ─────────────────────────────────────────────────
        keep_cols = (
            ["_target", "_score", "_in_ci", "_prob", "q50_nm", "q025_nm", "q975_nm", "ci_width_nm"]
            + DESIGN_COLS
        )
        result_df = result_df[[c for c in keep_cols if c in result_df.columns]]
        result_df = result_df.rename(columns={
            "_target":  "목표크기_nm",
            "_score":   "score",
            "_in_ci":   "95%CI내포함",
            "_prob":    f"P(±{int(tol_frac*100)}%)",
            "q50_nm":   "예측중앙값_nm",
            "q025_nm":  "CI하한_nm",
            "q975_nm":  "CI상한_nm",
            "ci_width_nm": "CI폭_nm",
        })
        num_cols = result_df.select_dtypes("number").columns
        result_df[num_cols] = result_df[num_cols].round(2)

        all_results[target_nm] = result_df
        _print_result(result_df, target_nm)

    return all_results


# ── 콘솔 출력 ─────────────────────────────────────────────────────────────────
def _print_result(df: pd.DataFrame, target_nm: float):
    print(f"\n{'='*70}")
    print(f"  목표: {target_nm} nm  (95% 예측 구간 기준 상위 {len(df)}개 조건)")
    print(f"{'='*70}")

    display_cols = [
        "score", "P(±25%)", "예측중앙값_nm", "CI하한_nm", "CI상한_nm",
        "synthesis_method", "ce_precursor", "solvent",
        "mineralizer", "capping_agent",
        "synthesis_temperature_c", "ph_synthesis", "synthesis_time_h",
    ]
    show = [c for c in display_cols if c in df.columns]

    col_map = {
        "score":                    "점수",
        "P(±25%)":                  "P(±25%)",
        "예측중앙값_nm":              "Q50(nm)",
        "CI하한_nm":                 "CI하한",
        "CI상한_nm":                 "CI상한",
        "synthesis_method":         "합성법",
        "ce_precursor":             "Ce전구체",
        "solvent":                  "용매",
        "mineralizer":              "광화제",
        "capping_agent":            "캡핑제",
        "synthesis_temperature_c":  "온도(°C)",
        "ph_synthesis":             "pH",
        "synthesis_time_h":         "시간(h)",
    }

    out = df[show].rename(columns=col_map)
    print(out.to_string(index=True))


# ── 시각화: 목표 크기별 75% 예측 구간 ─────────────────────────────────────────
def plot_ci(all_results: dict):
    n_t  = len(all_results)
    fig, axes = plt.subplots(1, n_t, figsize=(6 * n_t, max(5, 1.5 * max(
        len(df) for df in all_results.values()
    ))))
    if n_t == 1:
        axes = [axes]

    colors = ["#4C9BE8", "#54C89B", "#E87C4C", "#B07DD6", "#F2C94C"]

    for ax, (target_nm, df), color in zip(axes, all_results.items(), colors):
        n_rows = len(df)
        y_pos  = np.arange(n_rows)

        lo = (df["예측중앙값_nm"] - df["CI하한_nm"]).clip(lower=0)
        hi = (df["CI상한_nm"]   - df["예측중앙값_nm"]).clip(lower=0)

        ax.errorbar(
            df["예측중앙값_nm"].values, y_pos,
            xerr=[lo.values, hi.values],
            fmt="o", color=color, markersize=9,
            capsize=6, linewidth=2,
            label="95% 예측 구간",
        )
        ax.axvline(target_nm, color="red", linestyle="--", linewidth=2,
                   label=f"목표: {target_nm} nm")

        # y축 라벨: 합성법 / 온도 / pH / 시간
        def _lbl(r):
            m  = str(r.get("synthesis_method", ""))[:14]
            T  = r.get("synthesis_temperature_c", "")
            pH = r.get("ph_synthesis", "")
            t  = r.get("synthesis_time_h", "")
            cp = str(r.get("ce_precursor", ""))[:16]
            return f"{m}\n{cp}\nT={T:.0f}°C  pH={pH:.0f}  {t:.0f}h"

        labels = [_lbl(row) for _, row in df.iterrows()]
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=7.5)
        ax.invert_yaxis()
        ax.set_xlabel("1차 입자 크기 (nm)", fontsize=12)
        ax.set_title(f"목표 {target_nm} nm\n(95% 예측 구간)", fontsize=13)
        ax.legend(fontsize=9)
        ax.grid(axis="x", linestyle=":", alpha=0.5)

    plt.tight_layout()
    path = os.path.join(MODEL_DIR, "targeted_design_ci_plot.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  시각화: {path}")


# ── 저장 ──────────────────────────────────────────────────────────────────────
def save_results(all_results: dict):
    # 개별 CSV
    for target_nm, df in all_results.items():
        path = os.path.join(MODEL_DIR, f"targeted_design_{int(target_nm)}nm.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  CSV: {path}")

    # 통합 Excel (목표 크기별 시트)
    xlsx = os.path.join(MODEL_DIR, "targeted_design_summary.xlsx")
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        for target_nm, df in all_results.items():
            df.to_excel(writer, sheet_name=f"{int(target_nm)}nm", index=False)
    print(f"  Excel: {xlsx}")

    # 시각화
    plot_ci(all_results)


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="목표 입자크기별 75% 예측구간 합성 조건 역설계"
    )
    parser.add_argument(
        "--targets", nargs="+", type=float, default=[10.0, 30.0, 60.0],
        help="목표 입자 크기 (nm). 예: --targets 10 30 60",
    )
    parser.add_argument(
        "--candidates", type=int, default=100_000,
        help="탐색 후보 수 (기본 100,000)",
    )
    parser.add_argument(
        "--top", type=int, default=5,
        help="목표 크기당 출력할 최상위 조건 수 (기본 5)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  목표 입자크기별 합성 조건 역설계 (LightGBM 95% 예측 구간)")
    print(f"  목표 크기: {args.targets} nm")
    print(f"  탐색 후보: {args.candidates:,}개  |  출력 상위: {args.top}개")
    print("=" * 70)

    print("\n[1] 데이터 로드 + 전처리")
    df_raw = m12.load_data()
    df     = prepare_data(df_raw)

    n_primary = df[PRIMARY_TARGET].notna().sum()
    print(f"  습식 합성 데이터: {len(df):,}행  |  1차 입자 보유: {n_primary:,}행")

    print("\n[2] 분위 회귀 모델 학습 (Q2.5 / Q50 / Q97.5)")
    models, encoders, df_train = train_quantile_models(df)

    print(f"\n[3] 역설계 탐색 (후보 {args.candidates:,}개)")
    results = inverse_design(
        models, encoders, df_train,
        target_nm_list=args.targets,
        n_cand=args.candidates,
        top_k=args.top,
    )

    print("\n[4] 결과 저장")
    save_results(results)

    print("\n" + "=" * 70)
    print("완료.")
    print(f"  출력 폴더: {MODEL_DIR}")
    print("  targeted_design_{{30,40,50}}nm.csv  /  targeted_design_summary.xlsx")
    print("=" * 70)


if __name__ == "__main__":
    main()
