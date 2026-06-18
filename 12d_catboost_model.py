"""
12d_catboost_model.py — Stage 3-d: CatBoost + Optuna + SHAP

12_model.py(HistGBM), 12b_lgbm_baseline.py(LightGBM) 대비 성능 비교.
CatBoost 장점:
  - 범주형 피처 전처리 없이 native 처리 (encoding 불필요)
  - NaN native 지원
  - Ordered boosting으로 예측 편향(target leakage) 방지
  - SHAP 지원

실행:
  python 12d_catboost_model.py              # 학습 + SHAP + per-method
  python 12d_catboost_model.py --tune       # Optuna 하이퍼파라미터 탐색 (~15분)
  python 12d_catboost_model.py --no-permethod  # per-method 생략

필요 패키지:
  pip install catboost shap optuna
"""
import os, sys, warnings, pickle, argparse, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as _fm
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
TARGET_COMPOSITE     = m12.TARGET_COMPOSITE   # particle_size_primary_nm
TARGET_SIZE          = m12.TARGET_SIZE
TARGET_XRD           = m12.TARGET_XRD
TARGET_MORPH         = m12.TARGET_MORPH
_LOG_TARGETS         = m12._LOG_TARGETS

# ── 패키지 임포트 ─────────────────────────────────────────────────────────────
try:
    from catboost import CatBoostRegressor, CatBoostClassifier, Pool
except ImportError:
    sys.exit("catboost 미설치: pip install catboost")

try:
    import shap
    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False
    print("  shap 미설치 (pip install shap) — SHAP 분석 생략")

from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, f1_score

_avail_fonts = {f.name for f in _fm.fontManager.ttflist}
for _fn in ["Malgun Gothic", "NanumGothic", "NanumBarunGothic", "AppleGothic", "DejaVu Sans"]:
    if _fn in _avail_fonts:
        plt.rcParams["font.family"] = _fn
        break
plt.rcParams["axes.unicode_minus"] = False

# cat_features 인덱스: FEATURES 리스트에서 범주형 피처의 위치
_CAT_IDX = [FEATURES.index(c) for c in CATEGORICAL_FEATURES]


# ── CatBoost 모델 빌더 ────────────────────────────────────────────────────────
def build_catboost(kind: str, params: dict = None) -> object:
    """
    CatBoost 모델 생성.
    - 범주형 피처는 cat_features 인덱스로 전달 (인코딩 불필요)
    - NaN: allow_writing_files=False + nan_mode='Min'(regressor 기본)
    - verbose=0: 학습 로그 비활성
    """
    defaults = dict(
        iterations=600,
        learning_rate=0.05,
        depth=6,
        l2_leaf_reg=3.0,
        random_strength=1.0,
        bagging_temperature=1.0,
        border_count=128,
        random_seed=42,
        verbose=0,
        allow_writing_files=False,
        cat_features=_CAT_IDX,
    )
    if params:
        defaults.update(params)

    if kind == "clf":
        return CatBoostClassifier(**defaults, auto_class_weights="Balanced")
    return CatBoostRegressor(**defaults)


# ── 데이터 준비 (CatBoost용 — 범주형을 str로 유지) ───────────────────────────
def prepare_X(df: pd.DataFrame) -> pd.DataFrame:
    """
    CatBoost는 범주형을 str로, 수치형은 float로 전달.
    NaN은 수치형에서 np.nan 유지 (CatBoost native 처리).
    """
    X = df[FEATURES].copy()
    for col in NUMERIC_FEATURES:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    for col in CATEGORICAL_FEATURES:
        X[col] = X[col].fillna("unknown").astype(str).str.strip().str.lower()
    return X


# ── GroupKFold 교차검증 평가 ──────────────────────────────────────────────────
def evaluate(df: pd.DataFrame, target: str, kind: str,
             params: dict = None, tag: str = "CatBoost") -> dict:
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
        print(f"  [{target}] 표본 부족 — 스킵 (n={len(sub)}, papers={n_papers})")
        return {}

    X      = prepare_X(sub)
    groups = sub["doi"]
    use_log = (kind == "reg" and target in _LOG_TARGETS)
    y_raw  = np.asarray(sub[target].values)   # ArrowStringArray → numpy 변환
    y      = np.log(y_raw.astype(float)) if use_log else y_raw.copy()

    n_splits = min(5, n_papers)
    cv = GroupKFold(n_splits=n_splits)
    pred_y = np.zeros(len(sub)) if kind == "reg" else np.empty(len(sub), dtype=object)
    fold_scores = []

    for fold, (tr_idx, val_idx) in enumerate(cv.split(X, y, groups)):
        m = build_catboost(kind, params)
        m.fit(X.iloc[tr_idx], y[tr_idx])
        p = np.asarray(m.predict(X.iloc[val_idx])).ravel()
        pred_y[val_idx] = p
        if kind == "clf":
            fold_scores.append((y[val_idx] == p).mean())
        else:
            fold_scores.append(mean_absolute_error(y[val_idx], p))

    # 결과 출력
    if kind == "clf":
        acc = (pred_y == y).mean()
        f1  = f1_score(y, pred_y, average="macro", zero_division=0)
        print(f"  [{tag}][{target}] acc={acc:.3f}  macroF1={f1:.3f}"
              f"  fold-acc={np.mean(fold_scores):.3f}±{np.std(fold_scores):.3f}"
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
            print(f"  [{tag}][{target}] log-R²={r2_log:.3f} | "
                  f"nm-MAE={mae_nm:.2f}  RMSE={rmse_nm:.2f}  MdAE={mdae_nm:.2f}nm"
                  f"  nm-R²={r2_nm:.3f}"
                  f"  fold-MAE={np.mean(fold_scores):.3f}±{np.std(fold_scores):.3f}"
                  f"  (n={len(sub)}, papers={n_papers})")
            result = {"r2_log": r2_log, "r2_nm": r2_nm,
                      "mae_nm": mae_nm, "rmse_nm": rmse_nm, "mdae_nm": mdae_nm}
        else:
            mae  = mean_absolute_error(y, pred_y)
            rmse = np.sqrt(mean_squared_error(y, pred_y))
            mdae = np.median(np.abs(y - pred_y))
            r2   = r2_score(y, pred_y)
            print(f"  [{tag}][{target}] MAE={mae:.4f}  RMSE={rmse:.4f}  MdAE={mdae:.4f}  R²={r2:.3f}"
                  f"  (n={len(sub)}, papers={n_papers})")
            result = {"r2": r2, "mae": mae, "rmse": rmse, "mdae": mdae}

    # 최종 전체 재학습
    final_model = build_catboost(kind, params)
    final_model.fit(X, y)

    # SHAP 분석
    _shap_plot(final_model, X, target, kind)

    # 모델 저장
    model_path = os.path.join(MODEL_DIR, f"catboost_{target}_{kind}.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(final_model, f)
    print(f"    저장: {model_path}")

    return result


# ── SHAP 시각화 ───────────────────────────────────────────────────────────────
def _shap_plot(model, X: pd.DataFrame, target: str, kind: str):
    if not _HAS_SHAP:
        return
    try:
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[0]

        mean_abs = np.abs(shap_vals).mean(axis=0)
        top_idx  = np.argsort(mean_abs)[-15:]

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle(f"CatBoost SHAP — {target}", fontsize=13, fontweight="bold", y=1.02)

        axes[0].barh(
            [FEATURES[i] for i in top_idx],
            mean_abs[top_idx],
            color="#3A86FF"
        )
        axes[0].set_xlabel("Mean |SHAP value|")
        axes[0].set_title("Importance", fontsize=11)

        plt.sca(axes[1])
        shap.summary_plot(
            shap_vals[:, top_idx],
            X.iloc[:, top_idx],
            plot_type="dot",
            show=False,
            max_display=15,
        )
        axes[1].set_title("Beeswarm", fontsize=11)

        plt.tight_layout()
        path = os.path.join(MODEL_DIR, f"catboost_shap_{target}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"    SHAP 저장: {path}")
    except Exception as e:
        print(f"    SHAP 오류: {e}")


# ── Optuna 하이퍼파라미터 탐색 ────────────────────────────────────────────────
def tune(df: pd.DataFrame, target: str, kind: str,
         n_trials: int = 60) -> dict:
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("  optuna 미설치 — pip install optuna")
        return {}

    sub = df.dropna(subset=[target]).copy()
    if len(sub) < 20:
        return {}

    X      = prepare_X(sub)
    groups = sub["doi"]
    use_log = (kind == "reg" and target in _LOG_TARGETS)
    y_raw  = sub[target].values.copy()
    y      = np.log(y_raw) if use_log else y_raw

    def objective(trial):
        params = {
            "iterations":         trial.suggest_int("iterations", 200, 1000),
            "learning_rate":      trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "depth":              trial.suggest_int("depth", 4, 10),
            "l2_leaf_reg":        trial.suggest_float("l2_leaf_reg", 1.0, 10.0, log=True),
            "random_strength":    trial.suggest_float("random_strength", 0.1, 5.0),
            "bagging_temperature":trial.suggest_float("bagging_temperature", 0.0, 2.0),
            "border_count":       trial.suggest_categorical("border_count", [32, 64, 128, 254]),
        }
        cv = GroupKFold(n_splits=min(5, groups.nunique()))
        scores = []
        for tr, val in cv.split(X, y, groups):
            m = build_catboost(kind, params)
            m.fit(X.iloc[tr], y[tr])
            p = m.predict(X.iloc[val])
            if kind == "clf":
                scores.append(1.0 - (y[val] == p).mean())
            else:
                scores.append(mean_absolute_error(y[val], p))
        return np.mean(scores)

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    best = study.best_params
    print(f"\n  Optuna 최적 파라미터 ({n_trials}회 탐색):")
    for k, v in best.items():
        print(f"    {k}: {v}")
    return best


# ── per-method 분리 모델 ──────────────────────────────────────────────────────
def evaluate_per_method(df: pd.DataFrame, target: str,
                        params: dict = None, min_n: int = 80):
    """합성법별 독립 CatBoost 학습 (n >= min_n 방법만)."""
    sub = df.dropna(subset=[target, "synthesis_method"]).copy()
    methods = sub["synthesis_method"].value_counts()
    eligible = methods[methods >= min_n].index.tolist()

    if not eligible:
        print(f"  per-method: n>={min_n} 방법 없음")
        return

    print(f"\n[per-method CatBoost] {target}  (n>={min_n}인 {len(eligible)}개 방법)")
    results = []
    for method in eligible:
        mdf = sub[sub["synthesis_method"] == method].copy()
        n   = len(mdf)
        np_ = mdf["doi"].nunique()
        if np_ < 3:
            continue

        X      = prepare_X(mdf)
        groups = mdf["doi"]
        use_log = target in _LOG_TARGETS
        y_raw  = mdf[target].values.copy()
        y      = np.log(y_raw) if use_log else y_raw

        n_splits = min(5, np_)
        cv = GroupKFold(n_splits=n_splits)
        preds = np.zeros(n)

        for tr_idx, val_idx in cv.split(X, y, groups):
            m = build_catboost("reg", params)
            m.fit(X.iloc[tr_idx], y[tr_idx])
            preds[val_idx] = m.predict(X.iloc[val_idx])

        if use_log:
            pred_nm = np.exp(preds)
            r2_log  = r2_score(y, preds)
            mae_nm  = mean_absolute_error(y_raw, pred_nm)
            r2_nm   = r2_score(y_raw, pred_nm)
            print(f"  {method:<35s} n={n:4d}  log-R²={r2_log:+.3f}"
                  f"  nm-MAE={mae_nm:.1f}nm  nm-R²={r2_nm:+.3f}")
            results.append({"method": method, "n": n,
                            "r2_log": r2_log, "r2_nm": r2_nm, "mae_nm": mae_nm})
        else:
            r2  = r2_score(y, preds)
            mae = mean_absolute_error(y, preds)
            print(f"  {method:<35s} n={n:4d}  R²={r2:+.3f}  MAE={mae:.2f}")
            results.append({"method": method, "n": n, "r2": r2, "mae": mae})

    if results:
        path = os.path.join(MODEL_DIR, f"catboost_permethod_{target}.csv")
        pd.DataFrame(results).to_csv(path, index=False)
        print(f"  per-method 저장: {path}")


# ── 피처 중요도 바 차트 ───────────────────────────────────────────────────────
def plot_feature_importance(model, target: str):
    try:
        importances = model.get_feature_importance()
        idx = np.argsort(importances)[-20:]
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh([FEATURES[i] for i in idx], importances[idx], color="#3A86FF")
        ax.set_xlabel("Feature Importance (CatBoost)")
        ax.set_title(f"CatBoost — {target}")
        plt.tight_layout()
        path = os.path.join(MODEL_DIR, f"catboost_importance_{target}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"    중요도 저장: {path}")
    except Exception as e:
        print(f"    중요도 오류: {e}")


# ── HistGBM vs LightGBM vs CatBoost 비교표 ────────────────────────────────────
def print_comparison(cb_results: dict):
    """output/model 폴더의 기존 결과와 CatBoost 성능 비교."""
    print("\n" + "="*65)
    print("  모델 성능 비교 (particle_size_primary_nm, log-R²)")
    print("="*65)

    # 기존 결과 파일에서 로드 시도
    summary_path = os.path.join(MODEL_DIR, "model_comparison_summary.csv")
    rows = []

    # HistGBM 결과 (pipeline_state.json에서)
    state_path = os.path.join(BASE_DIR, "output", "pipeline_state.json")
    try:
        import json
        with open(state_path) as f:
            state = json.load(f)
        hist_r2 = state.get("ml_r2_primary", "N/A")
        rows.append({"model": "HistGBM (12_model.py)",
                     "log_r2": hist_r2, "note": "NaN-native, TargetEncoder"})
    except Exception:
        rows.append({"model": "HistGBM", "log_r2": "N/A", "note": ""})

    # CatBoost 결과
    if cb_results:
        rows.append({
            "model": "CatBoost (12d)",
            "log_r2":   cb_results.get("r2_log", "N/A"),
            "mae_nm":   cb_results.get("mae_nm", "N/A"),
            "note": "native cat, ordered boosting"
        })

    for r in rows:
        print(f"  {r['model']:<35s} log-R²={r.get('log_r2','N/A')}"
              f"  {r.get('note','')}")
    print("="*65)

    pd.DataFrame(rows).to_csv(summary_path, index=False)
    print(f"  비교표 저장: {summary_path}")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CatBoost ML 모델")
    parser.add_argument("--tune",         action="store_true",
                        help="Optuna 하이퍼파라미터 탐색 (~15분)")
    parser.add_argument("--no-permethod", action="store_true",
                        help="per-method 분리 모델 생략")
    parser.add_argument("--trials",       type=int, default=60,
                        help="Optuna 탐색 횟수 (기본 60)")
    args = parser.parse_args()

    print("="*60)
    print("  CatBoost 모델 — CeO2 합성 파이프라인")
    print("="*60)

    # ── 데이터 로드 + 전처리 ────────────────────────────────────────────────
    df_raw = m12.load_data()
    df     = m12.preprocess(df_raw)
    print(f"  전처리 완료: {len(df):,}행")

    # ── Optuna 튜닝 (또는 저장된 파라미터 로드) ────────────────────────────────
    BEST_PARAMS_PATH = os.path.join(MODEL_DIR, "catboost_best_params.json")
    best_params = None
    if args.tune:
        print(f"\n[Optuna 탐색] {TARGET_COMPOSITE} ({args.trials}회)")
        best_params = tune(df, TARGET_COMPOSITE, "reg", n_trials=args.trials)
        if best_params:
            with open(BEST_PARAMS_PATH, "w", encoding="utf-8") as _pf:
                json.dump(best_params, _pf, indent=2)
            print(f"  최적 파라미터 저장: {BEST_PARAMS_PATH}")
    elif os.path.exists(BEST_PARAMS_PATH):
        with open(BEST_PARAMS_PATH, "r", encoding="utf-8") as _pf:
            best_params = json.load(_pf)
        print(f"  저장된 최적 파라미터 로드: {BEST_PARAMS_PATH}")

    # ── 주요 타깃 평가 ───────────────────────────────────────────────────────
    print(f"\n[CatBoost 평가]")
    results = {}

    # 1차 입자크기 (TEM+SEM, log-scale)
    r = evaluate(df, TARGET_COMPOSITE, "reg", params=best_params)
    results[TARGET_COMPOSITE] = r

    # TEM 단독
    r_tem = evaluate(df, TARGET_SIZE, "reg", params=best_params)
    results[TARGET_SIZE] = r_tem

    # XRD 결정자 크기
    r_xrd = evaluate(df, TARGET_XRD, "reg", params=best_params)
    results[TARGET_XRD] = r_xrd

    # 형태 분류
    r_morph = evaluate(df, TARGET_MORPH, "clf", params=best_params,
                       tag="CatBoost-clf")
    results[TARGET_MORPH] = r_morph

    # ── 피처 중요도 (전체 재학습 모델 사용) ────────────────────────────────
    print("\n[피처 중요도]")
    for _fi_target in [TARGET_COMPOSITE, TARGET_XRD]:
        try:
            sub_fi = df.dropna(subset=[_fi_target]).copy()
            X_fi   = prepare_X(sub_fi)
            y_fi   = np.log(sub_fi[_fi_target].values.astype(float))
            fi_model = build_catboost("reg", best_params)
            fi_model.fit(X_fi, y_fi)
            plot_feature_importance(fi_model, _fi_target)
        except Exception as e:
            print(f"  피처 중요도 오류 ({_fi_target}): {e}")

    # ── per-method 분리 모델 ─────────────────────────────────────────────────
    if not args.no_permethod:
        evaluate_per_method(df, TARGET_COMPOSITE, params=best_params)

    # ── 비교표 출력 ──────────────────────────────────────────────────────────
    print_comparison(results.get(TARGET_COMPOSITE, {}))

    # ── 성능 이력 자동저장 ───────────────────────────────────────────────────────
    try:
        from datetime import datetime
        hist_path = os.path.join(MODEL_DIR, "performance_history.json")
        ph = []
        if os.path.exists(hist_path):
            with open(hist_path, "r", encoding="utf-8") as _hf:
                ph = json.load(_hf)
        today_str  = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        today_date = today_str[:10]
        cb_metrics = {}
        for tgt_key, res in results.items():
            if res and "r2_log" in res:
                cb_metrics[tgt_key] = {
                    "log_r2":  float(res["r2_log"]),
                    "mae_nm":  float(res.get("mae_nm", 0)),
                    "rmse_nm": float(res.get("rmse_nm", 0)),
                    "mdae_nm": float(res.get("mdae_nm", 0)),
                    "n":       int(len(df.dropna(subset=[tgt_key]))),
                }
        updated = False
        for entry in ph:
            if entry.get("run_date", "")[:10] == today_date and entry.get("session_label") == "auto":
                entry["catboost"] = cb_metrics
                updated = True
                break
        if not updated:
            ph.append({
                "session_label": "auto",
                "run_date": today_str,
                "n_samples": None, "n_papers": None, "n_features": None,
                "coverage_pct": None, "note": "CatBoost auto-saved",
                "histgbm": None, "dkl_gp": None, "lgbm": None,
                "catboost": cb_metrics,
            })
        with open(hist_path, "w", encoding="utf-8") as _hf:
            json.dump(ph, _hf, ensure_ascii=False, indent=2)
        print(f"  성능 이력 저장: {hist_path}")
    except Exception as _he:
        print(f"  성능 이력 저장 실패(무시): {_he}")

    print("\n완료. 결과 디렉토리:", MODEL_DIR)


if __name__ == "__main__":
    main()
