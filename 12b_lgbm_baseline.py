"""
12b_lgbm_baseline.py — Stage 3-b: LightGBM + SHAP + Optuna

12_model.py(HistGBM) 대비 성능 비교용 베이스라인.
LightGBM 네이티브 범주형 처리 + SHAP 피처 중요도 + Optuna 하이퍼파라미터 탐색.

실행:
  python 12b_lgbm_baseline.py           # 학습 + SHAP
  python 12b_lgbm_baseline.py --tune    # Optuna 탐색 포함 (~10분 추가)

필요 패키지:
  pip install lightgbm shap optuna
"""
import os, sys, warnings, pickle, argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

# ── 12_model.py 공통 모듈 동적 임포트 ─────────────────────────────────────────
import importlib.util
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "m12", os.path.join(_SCRIPT_DIR, "12_model.py"))
m12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m12)

BASE_DIR             = m12.BASE_DIR
MODEL_DIR            = os.path.join(BASE_DIR, "output", "model")
os.makedirs(MODEL_DIR, exist_ok=True)

NUMERIC_FEATURES     = m12.NUMERIC_FEATURES
CATEGORICAL_FEATURES = m12.CATEGORICAL_FEATURES
FEATURES             = m12.FEATURES
TARGET_COMPOSITE     = m12.TARGET_COMPOSITE
TARGET_SIZE          = m12.TARGET_SIZE
TARGET_XRD           = m12.TARGET_XRD
TARGET_MORPH         = m12.TARGET_MORPH
_LOG_TARGETS         = m12._LOG_TARGETS

# ── 패키지 임포트 ─────────────────────────────────────────────────────────────
try:
    import lightgbm as lgb
except ImportError:
    sys.exit("lightgbm 미설치: pip install lightgbm")
try:
    import shap
except ImportError:
    sys.exit("shap 미설치: pip install shap")

from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, f1_score
from sklearn.preprocessing import LabelEncoder
import matplotlib.font_manager as _fm

_avail_fonts = {f.name for f in _fm.fontManager.ttflist}
for _fn in ["Malgun Gothic", "NanumGothic", "NanumBarunGothic", "AppleGothic", "DejaVu Sans"]:
    if _fn in _avail_fonts:
        plt.rcParams["font.family"] = _fn
        break
plt.rcParams["axes.unicode_minus"] = False


# ── 범주형 인코딩 ─────────────────────────────────────────────────────────────
def encode_cats(df: pd.DataFrame):
    """LightGBM 범주형 피처용 정수 라벨 인코딩."""
    encoders = {}
    df_enc = df.copy()
    for col in CATEGORICAL_FEATURES:
        le = LabelEncoder()
        df_enc[col] = le.fit_transform(df_enc[col].astype(str))
        encoders[col] = le
    return df_enc, encoders


def safe_encode(df: pd.DataFrame, encoders: dict) -> pd.DataFrame:
    """학습 외 데이터에 대한 안전한 인코딩 (미지 범주 → 0)."""
    df_enc = df.copy()
    for col in CATEGORICAL_FEATURES:
        le = encoders[col]
        known = set(le.classes_)
        df_enc[col] = df_enc[col].astype(str).apply(
            lambda x: le.transform([x])[0] if x in known else 0
        )
    return df_enc


# ── LightGBM 모델 빌더 ────────────────────────────────────────────────────────
def build_lgbm(kind: str, params: dict = None):
    defaults = dict(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    if params:
        defaults.update(params)
    if kind == "clf":
        return lgb.LGBMClassifier(**defaults, class_weight="balanced")
    return lgb.LGBMRegressor(**defaults)


# ── 평가 함수 (GroupKFold 교차검증) ──────────────────────────────────────────
def evaluate_lgbm(df: pd.DataFrame, target: str, kind: str,
                  params: dict = None) -> dict:
    sub = df.dropna(subset=[target]).copy()

    if kind == "clf":
        sub = sub[sub[target].apply(
            lambda v: isinstance(v, str) and v.strip() != "")]
        vc = sub[target].value_counts()
        sub[target] = sub[target].where(
            sub[target].isin(vc[vc >= 10].index), "other")
        vc2 = sub[target].value_counts()
        sub = sub[sub[target].isin(vc2[vc2 >= 10].index)].copy()

    n_papers = sub["doi"].nunique()
    if len(sub) < 20 or n_papers < 3:
        print(f"  [{target}] 표본 부족 — 스킵")
        return {}

    sub_enc, encoders = encode_cats(sub)
    X      = sub_enc[FEATURES]
    groups = sub["doi"]

    use_log = (kind == "reg" and target in _LOG_TARGETS)
    y_raw   = sub[target].values.copy()
    y       = np.log(y_raw) if use_log else y_raw.copy()

    # GroupKFold 수동 교차검증 (LightGBM cat_feature 파라미터 전달용)
    n_splits = min(5, n_papers)
    cv      = GroupKFold(n_splits=n_splits)
    pred_y  = np.zeros(len(sub)) if kind == "reg" else np.empty(len(sub), dtype=object)
    fold_maes = []

    for fold, (tr_idx, val_idx) in enumerate(cv.split(X, y, groups)):
        m = build_lgbm(kind, params)
        m.fit(
            X.iloc[tr_idx], y[tr_idx],
            categorical_feature=CATEGORICAL_FEATURES,
        )
        p = m.predict(X.iloc[val_idx])
        pred_y[val_idx] = p
        if kind == "clf":
            fold_maes.append((y[val_idx] == p).mean())   # 폴드 정확도
        else:
            fold_maes.append(mean_absolute_error(y[val_idx], p))

    # 점수 출력
    if kind == "clf":
        acc = (pred_y == y).mean()
        f1  = f1_score(y, pred_y, average="macro", zero_division=0)
        print(f"  [{target}] acc={acc:.3f}  macroF1={f1:.3f}"
              f"  fold-acc={np.mean(fold_maes):.3f}±{np.std(fold_maes):.3f}"
              f"  (n={len(sub)}, papers={n_papers})")
        result = {"acc": acc, "f1": f1}
    else:
        if use_log:
            pred_nm  = np.exp(pred_y)
            mae_nm   = mean_absolute_error(y_raw, pred_nm)
            rmse_nm  = np.sqrt(mean_squared_error(y_raw, pred_nm))
            mdae_nm  = np.median(np.abs(y_raw - pred_nm))
            r2_nm    = r2_score(y_raw, pred_nm)
            r2_log   = r2_score(y, pred_y)
            print(f"  [{target}] log-R²={r2_log:.3f} | "
                  f"nm-MAE={mae_nm:.2f}  RMSE={rmse_nm:.2f}  MdAE={mdae_nm:.2f}nm"
                  f"  nm-R²={r2_nm:.3f}"
                  f"  fold-MAE={np.mean(fold_maes):.3f}±{np.std(fold_maes):.3f}"
                  f"  (n={len(sub)}, papers={n_papers})")
            result = {"r2_log": r2_log, "r2_nm": r2_nm,
                      "mae_nm": mae_nm, "rmse_nm": rmse_nm, "mdae_nm": mdae_nm}
        else:
            mae  = mean_absolute_error(y, pred_y)
            rmse = np.sqrt(mean_squared_error(y, pred_y))
            mdae = np.median(np.abs(y - pred_y))
            r2   = r2_score(y, pred_y)
            print(f"  [{target}] MAE={mae:.4f}  RMSE={rmse:.4f}  MdAE={mdae:.4f}  R²={r2:.3f}")
            result = {"r2": r2, "mae": mae, "rmse": rmse, "mdae": mdae}

    # 전체 재학습
    final_model = build_lgbm(kind, params)
    final_model.fit(X, y, categorical_feature=CATEGORICAL_FEATURES)

    # SHAP 분석
    _shap_plot(final_model, X, target, kind)

    # 저장
    model_path = os.path.join(MODEL_DIR, f"lgbm_{target}_{kind}.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({"model": final_model, "encoders": encoders}, f)
    print(f"    저장: {model_path}")

    return result


# ── SHAP 시각화 ───────────────────────────────────────────────────────────────
def _shap_plot(model, X: pd.DataFrame, target: str, kind: str):
    try:
        explainer   = shap.TreeExplainer(model)
        shap_vals   = explainer.shap_values(X)
        # 이진/다중 분류: 리스트 반환 → 첫 번째 클래스 사용
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[0]

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # 좌: bar (평균 |SHAP|)
        mean_abs = np.abs(shap_vals).mean(axis=0)
        top_idx  = np.argsort(mean_abs)[-15:]
        axes[0].barh(
            [FEATURES[i] for i in top_idx],
            mean_abs[top_idx],
            color="#E87C4C"
        )
        axes[0].set_xlabel("Mean |SHAP value|")
        axes[0].set_title(f"SHAP Importance — {target}")

        # 우: beeswarm (상위 15 피처)
        plt.sca(axes[1])
        shap.summary_plot(
            shap_vals[:, top_idx],
            X.iloc[:, top_idx],
            plot_type="dot",
            show=False,
            max_display=15,
        )
        axes[1].set_title(f"SHAP Beeswarm — {target}")

        plt.tight_layout()
        path = os.path.join(MODEL_DIR, f"shap_{target}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"    SHAP 저장: {path}")
    except Exception as e:
        print(f"    SHAP 오류: {e}")


# ── Optuna 하이퍼파라미터 탐색 ─────────────────────────────────────────────────
def tune(df: pd.DataFrame, target: str, kind: str,
         n_trials: int = 60) -> dict:
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("  optuna 미설치 — pip install optuna")
        return {}

    sub = df.dropna(subset=[target]).copy()
    sub_enc, encoders = encode_cats(sub)
    X      = sub_enc[FEATURES]
    groups = sub["doi"]
    use_log = (kind == "reg" and target in _LOG_TARGETS)
    y_raw  = sub[target].values.copy()
    y      = np.log(y_raw) if use_log else y_raw

    def objective(trial):
        params = {
            "n_estimators":      trial.suggest_int("n_estimators", 100, 1000),
            "learning_rate":     trial.suggest_float("lr", 0.01, 0.15, log=True),
            "num_leaves":        trial.suggest_int("num_leaves", 15, 127),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 60),
            "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        }
        cv = GroupKFold(n_splits=min(5, groups.nunique()))
        maes = []
        for tr, val in cv.split(X, y, groups):
            m = build_lgbm(kind, params)
            m.fit(X.iloc[tr], y[tr],
                  categorical_feature=CATEGORICAL_FEATURES)
            maes.append(mean_absolute_error(y[val], m.predict(X.iloc[val])))
        return np.mean(maes)

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    best = study.best_params
    print(f"  최적 MAE: {study.best_value:.4f}")
    print(f"  최적 파라미터: {best}")
    return best


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true",
                        help="Optuna 하이퍼파라미터 탐색 (particle_size_primary_nm 기준)")
    parser.add_argument("--trials", type=int, default=60,
                        help="Optuna 시도 횟수 (기본 60)")
    args = parser.parse_args()

    print("=" * 60)
    print("LightGBM + SHAP 베이스라인 — Stage 3-b")
    print("=" * 60)

    df_raw = m12.load_data()
    df     = m12.preprocess(df_raw)
    if "confidence" in df.columns:
        df = df[df["confidence"].isin(["high", "medium", "unknown", ""])]

    print(f"\n전처리 후: {len(df):,}행  |  논문: {df['doi'].nunique():,}편\n")

    best_params = None
    if args.tune:
        print(f"[Optuna] particle_size_primary_nm 탐색 ({args.trials} trials)...")
        best_params = tune(df, TARGET_COMPOSITE, "reg", n_trials=args.trials)

    print("─" * 40)
    print("LightGBM 평가")
    print("─" * 40)

    results = {}
    for target, kind in [
        (TARGET_COMPOSITE, "reg"),
        (TARGET_SIZE,      "reg"),
        (TARGET_XRD,       "reg"),
        (TARGET_MORPH,     "clf"),
    ]:
        label = {TARGET_COMPOSITE: "[회귀] composite 입자크기",
                 TARGET_SIZE:      "[회귀] TEM 입자크기",
                 TARGET_XRD:       "[회귀] XRD 결정자 크기",
                 TARGET_MORPH:     "[분류] 형태"}.get(target, target)
        print(f"\n{label}")
        p = best_params if (kind == "reg" and target == TARGET_COMPOSITE) else None
        results[target] = evaluate_lgbm(df, target, kind, params=p)

    # HistGBM vs LightGBM 비교 요약
    print("\n" + "─" * 40)
    print("비교 요약 (HistGBM 기준값 vs LightGBM)")
    print("─" * 40)
    baseline = {
        TARGET_COMPOSITE: {"r2_nm": -0.060, "mae_nm": 23.61},
        TARGET_SIZE:      {"r2_nm": -0.054, "mae_nm": 26.36},
        TARGET_XRD:       {"r2_nm": -0.050, "mae_nm":  9.15},
    }
    for t, b in baseline.items():
        lgbm_r = results.get(t, {})
        r2_lgbm = lgbm_r.get("r2_nm", float("nan"))
        mae_lgbm = lgbm_r.get("mae_nm", float("nan"))
        delta_r2  = r2_lgbm  - b["r2_nm"]
        delta_mae = mae_lgbm - b["mae_nm"]
        print(f"  {t:<32} R²: {b['r2_nm']:+.3f} → {r2_lgbm:+.3f} "
              f"({delta_r2:+.3f})  |  MAE: {b['mae_nm']:.1f} → {mae_lgbm:.1f}nm "
              f"({delta_mae:+.1f})")

    print("\n" + "=" * 60)
    print("완료. 결과 디렉토리:", MODEL_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
