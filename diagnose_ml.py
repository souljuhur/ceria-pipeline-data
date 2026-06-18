"""
diagnose_ml.py — CeO2 합성 ML 진단 스크립트

진단 1: 동일 85/15 DOI split → 4개 모델 공정 비교 (DKL-GP vs GBM 격차 진위)
진단 2: 조건별 내부 분산 → 노이즈 천장 R² 추정 ("데이터냐 방법이냐" 판단)
진단 3: method-mean baseline + Ridge + CatBoost feature ablation
진단 5: 구간별 잔차 분석 (0–20 / 20–50 / 50+nm)
진단 6: TEM vs SEM systematic bias

실행:
  python diagnose_ml.py            # 전체 (1~3, 5~6)
  python diagnose_ml.py --diag 1   # 특정 진단만
  python diagnose_ml.py --diag 1 2 3
"""

import argparse
import importlib.util
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "output", "model")
OUT_PATH  = os.path.join(MODEL_DIR, "diagnose_results.json")

SEED = 42
TARGET = "particle_size_primary_nm"

# ── 12_model.py 임포트 ────────────────────────────────────────────────────────
def _import_m12():
    spec = importlib.util.spec_from_file_location("m12",
               os.path.join(BASE_DIR, "12_model.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

# ── 공통 유틸 ──────────────────────────────────────────────────────────────────
def log_r2(y_true, y_pred):
    lt = np.log(np.clip(np.asarray(y_true, dtype=float), 1e-6, None))
    lp = np.log(np.clip(np.asarray(y_pred, dtype=float), 1e-6, None))
    ss_res = np.sum((lt - lp) ** 2)
    ss_tot = np.sum((lt - lt.mean()) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def nm_mae(y_true, y_pred):
    return float(mean_absolute_error(y_true, y_pred))


def _hline(char="─", n=62):
    print(char * n)


def _load_and_prep(m12):
    """데이터 로드 + 전처리 (12_model.py 재사용)"""
    df_raw = m12.load_data()

    # 품질 필터 (12_model.py와 동일)
    df = m12.preprocess(df_raw.copy())

    # 유효 타깃만
    df = df[df[TARGET].notna() & (df[TARGET] > 0)].copy()
    df["_log_target"] = np.log(df[TARGET])
    return df


def _same_split(df):
    """DKL-GP와 동일한 GroupShuffleSplit(0.15, seed=42)"""
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED)
    tr_idx, te_idx = next(gss.split(df, groups=df["doi"]))
    return tr_idx, te_idx


# ──────────────────────────────────────────────────────────────────────────────
# 진단 1: 동일 split에서 GBM 재평가 → DKL-GP(23차 기록)와 비교
# ──────────────────────────────────────────────────────────────────────────────
def diag1(df, m12):
    print("\n" + "=" * 62)
    print("진단 1  동일 85/15 DOI split — GBM vs DKL-GP 공정 비교")
    print("=" * 62)
    print("  DKL-GP : GroupShuffleSplit(test_size=0.15, seed=42)  [단일 split]")
    print("  GBM 계열: GroupKFold(5)                               [5-fold CV]")
    print("  → GBM 3종을 같은 단일 split으로 재평가해 비교합니다.\n")

    tr_idx, te_idx = _same_split(df)
    print(f"  학습: {len(tr_idx):,}행  |  평가: {len(te_idx):,}행  (DOI 단위 분리 확인)")

    FEATS = m12.NUMERIC_FEATURES + m12.CATEGORICAL_FEATURES

    # ── DOI 누설 검증 ────────────────────────────────────────────────────────
    tr_dois = set(df.iloc[tr_idx]["doi"])
    te_dois = set(df.iloc[te_idx]["doi"])
    overlap = tr_dois & te_dois
    print(f"  DOI 누설 검증: {'❌ 누설 ' + str(len(overlap)) + '개!' if overlap else '✓ 없음'}\n")

    ytr_log = df.iloc[tr_idx]["_log_target"].values.astype(float)
    yte_nm  = df.iloc[te_idx][TARGET].values.astype(float)

    results_samesplit = {}

    # ── HistGBM ───────────────────────────────────────────────────────────────
    print("  [1/3] HistGBM …")
    try:
        pipe = m12.build_pipeline("reg", early_stopping=False)
        pipe.fit(df.iloc[tr_idx][FEATS], ytr_log)
        pred_nm = np.exp(pipe.predict(df.iloc[te_idx][FEATS]))
        r2  = log_r2(yte_nm, pred_nm)
        mae = nm_mae(yte_nm, pred_nm)
        results_samesplit["HistGBM"] = {"log_r2": r2, "mae_nm": mae}
        print(f"       log-R²={r2:+.3f}  MAE={mae:.1f}nm")
    except Exception as e:
        print(f"       오류: {e}")
        results_samesplit["HistGBM"] = {"error": str(e)}

    # ── LightGBM ──────────────────────────────────────────────────────────────
    print("  [2/3] LightGBM …")
    try:
        import lightgbm as lgb
        from sklearn.preprocessing import TargetEncoder
        te = TargetEncoder(smooth="auto", cv=5, shuffle=True, random_state=SEED)

        Xtr = df.iloc[tr_idx][FEATS].copy()
        Xte = df.iloc[te_idx][FEATS].copy()
        for c in m12.CATEGORICAL_FEATURES:
            Xtr[c] = Xtr[c].astype(str)
            Xte[c] = Xte[c].astype(str)

        Xtr_enc = te.fit_transform(Xtr, ytr_log)
        Xte_enc = te.transform(Xte)

        model = lgb.LGBMRegressor(
            n_estimators=500, learning_rate=0.05,
            max_depth=6, num_leaves=31,
            random_state=SEED, verbose=-1
        )
        model.fit(Xtr_enc, ytr_log)
        pred_nm = np.exp(model.predict(Xte_enc))
        r2  = log_r2(yte_nm, pred_nm)
        mae = nm_mae(yte_nm, pred_nm)
        results_samesplit["LightGBM"] = {"log_r2": r2, "mae_nm": mae}
        print(f"       log-R²={r2:+.3f}  MAE={mae:.1f}nm")
    except Exception as e:
        print(f"       오류: {e}")
        results_samesplit["LightGBM"] = {"error": str(e)}

    # ── CatBoost ──────────────────────────────────────────────────────────────
    print("  [3/3] CatBoost …")
    try:
        import catboost as cb
        bp_path = os.path.join(MODEL_DIR, "catboost_best_params.json")
        bp = json.load(open(bp_path)) if os.path.exists(bp_path) else {}

        Xtr_cb = df.iloc[tr_idx][FEATS].copy()
        Xte_cb = df.iloc[te_idx][FEATS].copy()
        for c in m12.CATEGORICAL_FEATURES:
            Xtr_cb[c] = Xtr_cb[c].fillna("__NA__").astype(str)
            Xte_cb[c] = Xte_cb[c].fillna("__NA__").astype(str)
        cat_idx = [list(Xtr_cb.columns).index(c)
                   for c in m12.CATEGORICAL_FEATURES if c in Xtr_cb.columns]

        model = cb.CatBoostRegressor(
            iterations=bp.get("iterations", 500),
            learning_rate=bp.get("learning_rate", 0.05),
            depth=bp.get("depth", 6),
            l2_leaf_reg=bp.get("l2_leaf_reg", 3),
            random_seed=SEED, verbose=0
        )
        model.fit(Xtr_cb, ytr_log, cat_features=cat_idx)
        pred_nm = np.exp(model.predict(Xte_cb))
        r2  = log_r2(yte_nm, pred_nm)
        mae = nm_mae(yte_nm, pred_nm)
        results_samesplit["CatBoost"] = {"log_r2": r2, "mae_nm": mae}
        print(f"       log-R²={r2:+.3f}  MAE={mae:.1f}nm")
    except Exception as e:
        print(f"       오류: {e}")
        results_samesplit["CatBoost"] = {"error": str(e)}

    # ── 비교표 ────────────────────────────────────────────────────────────────
    print()
    _hline()
    print(f"  {'모델':<15} {'동일split log-R²':>18} {'5-fold log-R² (기록)':>22} {'차이':>8}")
    _hline()
    recorded = {"HistGBM": 0.006, "LightGBM": 0.087, "CatBoost": 0.092}
    for name, rec in recorded.items():
        ss = results_samesplit.get(name, {})
        r2 = ss.get("log_r2", float("nan"))
        diff = r2 - rec
        flag = "  ← 큰 격차!" if abs(diff) > 0.05 else ""
        print(f"  {name:<15} {r2:>+18.3f} {rec:>+22.3f} {diff:>+8.3f}{flag}")
    print(f"  {'DKL-GP':<15} {'(단일split 기록)':>18} {0.277:>+22.3f} {'기준':>8}")
    _hline()

    print("""
  판단 기준:
    동일split GBM ≈ 5-fold GBM (차이 < 0.05)
      → DKL-GP +0.277 vs CatBoost +0.092 격차가 실제 (평가 불일치 아님)
    동일split GBM >> 5-fold GBM (차이 > 0.05)
      → 5-fold가 DKL-GP 단일split보다 보수적 → 격차 과장 가능성
""")
    return results_samesplit


# ──────────────────────────────────────────────────────────────────────────────
# 진단 2: 노이즈 천장 R² 추정
# ──────────────────────────────────────────────────────────────────────────────
def diag2(df):
    print("\n" + "=" * 62)
    print("진단 2  노이즈 천장 R² — \"데이터 한계\" vs \"방법 한계\"")
    print("=" * 62)

    col_target = TARGET
    col_method = "synthesis_method"
    col_temp   = "synthesis_temperature_c"
    col_pre    = "anion_type"          # ce_precursor의 이온 유형 (coverage 높음)

    sub = df[[col_target, col_method, col_temp, col_pre, "doi"]].dropna(
        subset=[col_target, col_method]
    ).copy()

    # ── Level-1: synthesis_method만으로 그룹 ─────────────────────────────────
    total_var = np.var(np.log(sub[col_target].values), ddof=1)
    within_l1 = sub.groupby(col_method)[col_target].apply(
        lambda v: np.var(np.log(v.values), ddof=1) if len(v) > 1 else 0.0
    )
    n_per     = sub.groupby(col_method)[col_target].count()
    within_l1_weighted = (within_l1 * (n_per - 1)).sum() / (len(sub) - len(n_per))
    ceiling_l1 = max(0.0, 1 - within_l1_weighted / total_var)

    print(f"\n  [Level 1] synthesis_method 그룹 ({n_per.shape[0]}개 방법)")
    print(f"  전체 log-분산: {total_var:.4f}")
    print(f"  그룹내 log-분산: {within_l1_weighted:.4f}")
    print(f"  천장 R² (method 기반): {ceiling_l1:+.3f}")

    # ── Level-2: method + anion_type ─────────────────────────────────────────
    sub["_grp2"] = sub[col_method] + "|" + sub[col_pre].fillna("unk")
    grp2_cnt = sub["_grp2"].value_counts()
    sub2 = sub[sub["_grp2"].isin(grp2_cnt[grp2_cnt >= 3].index)]
    if len(sub2) > 10:
        within_l2 = sub2.groupby("_grp2")[col_target].apply(
            lambda v: np.var(np.log(v.values), ddof=1) if len(v) > 1 else 0.0
        )
        n2 = sub2.groupby("_grp2")[col_target].count()
        wl2 = (within_l2 * (n2 - 1)).sum() / (len(sub2) - len(n2))
        ceiling_l2 = max(0.0, 1 - wl2 / total_var)
        print(f"\n  [Level 2] method + anion_type 그룹 ({len(n2)}개)")
        print(f"  그룹내 log-분산: {wl2:.4f}")
        print(f"  천장 R² (method+anion): {ceiling_l2:+.3f}")
    else:
        ceiling_l2 = ceiling_l1

    # ── Level-3: method + anion_type + temp_bin(±25°C) ───────────────────────
    sub3 = sub2.copy()
    sub3["_temp_bin"] = (sub3[col_temp].fillna(-999) / 25).round() * 25
    sub3["_grp3"] = sub3["_grp2"] + "|T" + sub3["_temp_bin"].astype(str)
    grp3_cnt = sub3["_grp3"].value_counts()
    sub3 = sub3[sub3["_grp3"].isin(grp3_cnt[grp3_cnt >= 3].index)]
    if len(sub3) > 10:
        within_l3 = sub3.groupby("_grp3")[col_target].apply(
            lambda v: np.var(np.log(v.values), ddof=1) if len(v) > 1 else 0.0
        )
        n3 = sub3.groupby("_grp3")[col_target].count()
        wl3 = (within_l3 * (n3 - 1)).sum() / (len(sub3) - len(n3))
        ceiling_l3 = max(0.0, 1 - wl3 / total_var)
        print(f"\n  [Level 3] method + anion + temp(±25°C) 그룹 ({len(n3)}개)")
        print(f"  그룹내 log-분산: {wl3:.4f}")
        print(f"  천장 R² (method+anion+temp): {ceiling_l3:+.3f}")
    else:
        ceiling_l3 = ceiling_l2

    # ── DOI 내 다중 시편 분산 (같은 논문 안에서의 변동) ──────────────────────
    doi_cnt = sub.groupby("doi")[col_target].count()
    multi_doi = doi_cnt[doi_cnt >= 3].index
    sub_multi = sub[sub["doi"].isin(multi_doi)]
    if len(sub_multi) > 10:
        within_doi = sub_multi.groupby("doi")[col_target].apply(
            lambda v: np.var(np.log(v.values), ddof=1) if len(v) > 1 else 0.0
        )
        n_doi = sub_multi.groupby("doi")[col_target].count()
        wdoi  = (within_doi * (n_doi - 1)).sum() / (len(sub_multi) - len(n_doi))
        ceiling_doi = max(0.0, 1 - wdoi / total_var)
        print(f"\n  [DOI내 시편] n≥3인 논문 {len(multi_doi)}편, 시편 {len(sub_multi)}개")
        print(f"  DOI내 log-분산: {wdoi:.4f}  (의도적 변수 변경 포함 → 상한선 낙관적)")
        print(f"  천장 R² (DOI내): {ceiling_doi:+.3f}")
    else:
        ceiling_doi = None

    print()
    _hline()
    print("  요약")
    _hline()
    print(f"  Level 1 (method만):             천장 R² ≈ {ceiling_l1:+.3f}")
    print(f"  Level 2 (method+anion):         천장 R² ≈ {ceiling_l2:+.3f}")
    print(f"  Level 3 (method+anion+temp):    천장 R² ≈ {ceiling_l3:+.3f}")
    if ceiling_doi is not None:
        print(f"  DOI내 다중시편 (낙관적):          천장 R² ≈ {ceiling_doi:+.3f}")
    print()
    print("  판단 기준:")
    best = max(ceiling_l1, ceiling_l2, ceiling_l3)
    if best < 0.35:
        print(f"  천장 {best:.2f} < 0.35 → DKL-GP +0.277은 이미 천장 근처.")
        print("  R² 더 짜내기보다 per-method 모델·불확실성·역설계 품질 개선이 우선.")
    elif best < 0.55:
        print(f"  천장 {best:.2f} (0.35~0.55) → 중간 지점. 피처 발굴 여지 있음.")
        print("  농도·시간 등 현재 추출 안 된 변수 확보 시 개선 가능.")
    else:
        print(f"  천장 {best:.2f} > 0.55 → 신호가 남아 있음. 모델·피처가 병목.")
    _hline()
    return {"ceiling_l1": ceiling_l1, "ceiling_l2": ceiling_l2,
            "ceiling_l3": ceiling_l3, "ceiling_doi": ceiling_doi}


# ──────────────────────────────────────────────────────────────────────────────
# 진단 3: method-mean baseline + Ridge + ablation
# ──────────────────────────────────────────────────────────────────────────────
def diag3(df, m12):
    print("\n" + "=" * 62)
    print("진단 3  Baseline + Ablation — 피처가 실제로 기여하는가")
    print("=" * 62)

    FEATS    = m12.NUMERIC_FEATURES + m12.CATEGORICAL_FEATURES
    NUM_ONLY = m12.NUMERIC_FEATURES

    kf = GroupKFold(n_splits=5)
    groups = df["doi"].values
    y_nm  = df[TARGET].values.astype(float)
    y_log = np.log(y_nm)

    def _cv_logr2(pred_fn):
        """5-fold GroupKFold에서 OOF log-R² 계산"""
        oof = np.full(len(df), np.nan)
        for tr_idx, te_idx in kf.split(df, groups=groups):
            preds = pred_fn(df.iloc[tr_idx], df.iloc[te_idx], y_log[tr_idx])
            oof[te_idx] = preds
        valid = ~np.isnan(oof)
        return log_r2(y_nm[valid], oof[valid])

    results = {}

    # ── (a) 전체 평균 ──────────────────────────────────────────────────────────
    print("  [a] 전체 평균 (R²=0 기준) …")
    def pred_global(tr, te, ytr):
        return np.exp(np.full(len(te), np.mean(ytr)))
    r2_global = _cv_logr2(pred_global)
    print(f"      log-R²={r2_global:+.3f}  (이론값=0)")
    results["global_mean"] = r2_global

    # ── (b) synthesis_method 그룹 평균 ────────────────────────────────────────
    print("  [b] synthesis_method 그룹 평균 …")
    def pred_method_mean(tr, te, ytr):
        method_means = {}
        for m, grp in tr.groupby("synthesis_method"):
            idx = grp.index
            method_means[m] = np.mean(ytr[np.isin(tr.index, idx)])
        global_m = np.mean(ytr)
        preds = []
        for _, row in te.iterrows():
            preds.append(method_means.get(row["synthesis_method"], global_m))
        return np.exp(np.array(preds))
    r2_method = _cv_logr2(pred_method_mean)
    print(f"      log-R²={r2_method:+.3f}")
    results["method_mean"] = r2_method

    # ── (c) Ridge (수치 피처 only) ────────────────────────────────────────────
    print("  [c] Ridge 선형회귀 (수치 피처 only) …")
    def pred_ridge(tr, te, ytr):
        Xtr = tr[NUM_ONLY].values.astype(float)
        Xte = te[NUM_ONLY].values.astype(float)
        col_means = np.nanmean(Xtr, axis=0)
        for i in range(Xtr.shape[1]):
            Xtr[np.isnan(Xtr[:, i]), i] = col_means[i]
            Xte[np.isnan(Xte[:, i]), i] = col_means[i]
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(Xtr)
        Xte = scaler.transform(Xte)
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xtr, ytr)
        return np.exp(ridge.predict(Xte))
    r2_ridge = _cv_logr2(pred_ridge)
    print(f"      log-R²={r2_ridge:+.3f}")
    results["ridge_numeric_only"] = r2_ridge

    # ── (d) CatBoost 전체 32피처 (5-fold, 빠른 버전) ─────────────────────────
    print("  [d] CatBoost 전체 32피처 (빠른 CV) …")
    try:
        import catboost as cb
        bp_path = os.path.join(MODEL_DIR, "catboost_best_params.json")
        bp = json.load(open(bp_path)) if os.path.exists(bp_path) else {}

        def pred_catboost_full(tr, te, ytr):
            Xtr = tr[FEATS].copy(); Xte = te[FEATS].copy()
            for c in m12.CATEGORICAL_FEATURES:
                Xtr[c] = Xtr[c].fillna("__NA__").astype(str)
                Xte[c] = Xte[c].fillna("__NA__").astype(str)
            cat_idx = [list(Xtr.columns).index(c)
                       for c in m12.CATEGORICAL_FEATURES if c in Xtr.columns]
            # 진단용: 100회로 제한 (5-fold × 3세트 = OOM 방지)
            model = cb.CatBoostRegressor(
                iterations=100,
                learning_rate=bp.get("learning_rate", 0.05),
                depth=min(bp.get("depth", 6), 5),
                random_seed=SEED, verbose=0, thread_count=2
            )
            model.fit(Xtr, ytr, cat_features=cat_idx)
            return np.exp(model.predict(Xte))

        r2_cb_full = _cv_logr2(pred_catboost_full)
        print(f"      log-R²={r2_cb_full:+.3f}")
        results["catboost_32feat"] = r2_cb_full

        # ── (e) CatBoost 상위 10 수치 피처 only (ablation) ────────────────────
        print("  [e] CatBoost 수치 피처 top-10 only (ablation) …")
        TOP10_NUM = [
            "synthesis_temperature_c", "synthesis_time_h", "calcination_temperature_c",
            "ce_concentration_M", "log_synth_temp", "log_calc_temp",
            "thermal_budget", "has_mineralizer", "has_dopant", "capping_present",
        ]

        def pred_catboost_num10(tr, te, ytr):
            Xtr = tr[TOP10_NUM].copy(); Xte = te[TOP10_NUM].copy()
            model = cb.CatBoostRegressor(
                iterations=100,
                learning_rate=bp.get("learning_rate", 0.05),
                depth=min(bp.get("depth", 6), 5),
                random_seed=SEED, verbose=0, thread_count=2
            )
            model.fit(Xtr, ytr)
            return np.exp(model.predict(Xte))

        r2_num10 = _cv_logr2(pred_catboost_num10)
        print(f"      log-R²={r2_num10:+.3f}")
        results["catboost_num10_ablation"] = r2_num10

        # ── (f) synthesis_method 원핫 + 수치 피처 (method만 추가) ─────────────
        print("  [f] CatBoost 수치 only + synthesis_method (method 기여도 분리) …")
        NUM_PLUS_METHOD = TOP10_NUM + ["synthesis_method"]

        def pred_cb_method_num(tr, te, ytr):
            Xtr = tr[NUM_PLUS_METHOD].copy()
            Xte = te[NUM_PLUS_METHOD].copy()
            Xtr["synthesis_method"] = Xtr["synthesis_method"].fillna("__NA__").astype(str)
            Xte["synthesis_method"] = Xte["synthesis_method"].fillna("__NA__").astype(str)
            cat_idx = [list(Xtr.columns).index("synthesis_method")]
            model = cb.CatBoostRegressor(
                iterations=100,
                learning_rate=bp.get("learning_rate", 0.05),
                depth=min(bp.get("depth", 6), 5),
                random_seed=SEED, verbose=0, thread_count=2
            )
            model.fit(Xtr, ytr, cat_features=cat_idx)
            return np.exp(model.predict(Xte))

        r2_method_num = _cv_logr2(pred_cb_method_num)
        print(f"      log-R²={r2_method_num:+.3f}")
        results["catboost_method_plus_num"] = r2_method_num

    except ImportError:
        print("      CatBoost 미설치 — 건너뜀")
    except Exception as e:
        print(f"      CatBoost CV 오류 ({type(e).__name__}) — 건너뜀")

    # ── 비교표 ────────────────────────────────────────────────────────────────
    print()
    _hline()
    print("  비교표")
    _hline()
    labels = [
        ("(a) 전체 평균",                  "global_mean"),
        ("(b) method 그룹 평균",           "method_mean"),
        ("(c) Ridge (수치only)",           "ridge_numeric_only"),
        ("(e) CatBoost 수치 top-10만",     "catboost_num10_ablation"),
        ("(f) CatBoost 수치+method",       "catboost_method_plus_num"),
        ("(d) CatBoost 전체 32피처",       "catboost_32feat"),
        ("    CatBoost 전체 (23차 기록)",  "__recorded__"),
    ]
    for label, key in labels:
        if key == "__recorded__":
            val = 0.092
        else:
            val = results.get(key)
        if val is not None:
            bar = "█" * max(0, int((val + 0.1) * 40))
            print(f"  {label:<35} {val:>+7.3f}  {bar}")
    _hline()

    # ── 판단 ──────────────────────────────────────────────────────────────────
    r2_b = results.get("method_mean", 0)
    r2_d = results.get("catboost_32feat", results.get("catboost_method_plus_num", 0))
    diff = r2_d - r2_b
    print(f"\n  전체 32피처 vs method 그룹평균 차이: {diff:+.3f}")
    if diff < 0.03:
        print("  → 나머지 피처들이 method 외엔 거의 기여 안 함.")
        print("    합성법별 층화 모델 강화, 농도 등 핵심 피처 확보 우선.")
    else:
        print("  → 피처가 method 이상의 정보를 제공함. 현재 방향 유지 가능.")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 진단 5: 구간별 잔차 분석
# ──────────────────────────────────────────────────────────────────────────────
def diag5(df, m12):
    print("\n" + "=" * 62)
    print("진단 5  구간별 잔차 분석 (0–20 / 20–50 / 50+nm)")
    print("=" * 62)

    FEATS = m12.NUMERIC_FEATURES + m12.CATEGORICAL_FEATURES

    # LightGBM 5-fold OOF 예측 (CatBoost OOM 방지)
    print("  LightGBM 5-fold OOF 예측 생성 중 …")
    try:
        import lightgbm as lgb
        from sklearn.preprocessing import TargetEncoder as TE

        kf = GroupKFold(n_splits=5)
        groups = df["doi"].values
        y_nm   = df[TARGET].values.astype(float)
        y_log  = np.log(y_nm)
        oof    = np.full(len(df), np.nan)

        for fold_i, (tr_idx, te_idx) in enumerate(kf.split(df, groups=groups)):
            Xtr = df.iloc[tr_idx][FEATS].copy()
            Xte = df.iloc[te_idx][FEATS].copy()
            for c in m12.CATEGORICAL_FEATURES:
                Xtr[c] = Xtr[c].astype(str)
                Xte[c] = Xte[c].astype(str)
            te_enc = TE(smooth="auto", cv=5, shuffle=True, random_state=SEED)
            Xtr_e = te_enc.fit_transform(Xtr, y_log[tr_idx])
            Xte_e = te_enc.transform(Xte)
            model = lgb.LGBMRegressor(
                n_estimators=300, learning_rate=0.05,
                max_depth=6, num_leaves=31,
                random_state=SEED, verbose=-1
            )
            model.fit(Xtr_e, y_log[tr_idx])
            oof[te_idx] = np.exp(model.predict(Xte_e))
            print(f"    fold {fold_i+1}/5 완료")

        # 구간별 통계
        bins = [(0, 20, "0–20nm (소립자)"),
                (20, 50, "20–50nm (중립자)"),
                (50, 500, "50+nm  (대립자)")]

        print()
        _hline()
        print(f"  {'구간':<22} {'n':>6} {'RMSE':>9} {'MAE':>9} {'MAPE':>9} {'log-R²':>8}")
        _hline()
        range_results = {}
        for lo, hi, label in bins:
            mask = (y_nm >= lo) & (y_nm < hi) & ~np.isnan(oof)
            if mask.sum() < 5:
                continue
            yt = y_nm[mask]; yp = oof[mask]
            rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
            mae  = float(np.mean(np.abs(yt - yp)))
            mape = float(np.mean(np.abs((yt - yp) / yt)) * 100)
            lr2  = log_r2(yt, yp)
            print(f"  {label:<22} {mask.sum():>6} {rmse:>9.1f} {mae:>9.1f} {mape:>8.1f}% {lr2:>+8.3f}")
            range_results[label] = {"n": int(mask.sum()), "rmse": rmse,
                                    "mae": mae, "mape": mape, "log_r2": lr2}
        _hline()
        print("\n  판단: RMSE/MAPE가 특정 구간에서 폭증하면 그 구간 분리 모델 권장.")
        return range_results

    except ImportError:
        print("  CatBoost 미설치 — 건너뜀")
        return {}
    except Exception as e:
        print(f"  오류: {e}")
        return {}


# ──────────────────────────────────────────────────────────────────────────────
# 진단 6: TEM vs SEM systematic bias
# ──────────────────────────────────────────────────────────────────────────────
def diag6(df_raw):
    print("\n" + "=" * 62)
    print("진단 6  TEM vs SEM Systematic Bias")
    print("=" * 62)

    tem_col = "particle_size_tem_nm"
    sem_col = "particle_size_sem_nm"

    tem = pd.to_numeric(df_raw.get(tem_col, pd.Series(dtype=float)), errors="coerce").dropna()
    sem = pd.to_numeric(df_raw.get(sem_col, pd.Series(dtype=float)), errors="coerce").dropna()

    # 범위 필터
    tem = tem[(tem >= 0.3) & (tem <= 500)]
    sem = sem[(sem >= 0.3) & (sem <= 500)]

    print(f"\n  TEM 데이터: n={len(tem):,}")
    print(f"  SEM 데이터: n={len(sem):,}")

    if len(tem) < 10 or len(sem) < 10:
        print("  데이터 부족 — 건너뜀")
        return {}

    for name, vals in [("TEM", tem), ("SEM", sem)]:
        p = np.percentile(vals, [25, 50, 75])
        print(f"\n  {name}: 평균={vals.mean():.1f}nm  중앙값={p[1]:.1f}nm"
              f"  IQR=[{p[0]:.1f}, {p[2]:.1f}]  std={vals.std():.1f}nm")

    med_diff = tem.median() - sem.median()
    mean_diff = tem.mean() - sem.mean()
    print(f"\n  TEM − SEM  중앙값 차이: {med_diff:+.1f}nm")
    print(f"  TEM − SEM  평균 차이:   {mean_diff:+.1f}nm")

    # 같은 DOI에 TEM+SEM 둘 다 있는 논문 비교
    if tem_col in df_raw.columns and sem_col in df_raw.columns and "doi" in df_raw.columns:
        both = df_raw[["doi", tem_col, sem_col]].copy()
        both[tem_col] = pd.to_numeric(both[tem_col], errors="coerce")
        both[sem_col] = pd.to_numeric(both[sem_col], errors="coerce")
        both = both.dropna(subset=[tem_col, sem_col])
        both = both[(both[tem_col].between(0.3, 500)) & (both[sem_col].between(0.3, 500))]
        if len(both) >= 5:
            paired_diff = (both[tem_col] - both[sem_col]).median()
            print(f"\n  동일 DOI 내 TEM vs SEM 쌍 ({len(both)}개): 중앙값 차이={paired_diff:+.1f}nm")

    _hline()
    threshold = 5.0
    if abs(med_diff) > threshold:
        print(f"  중앙값 차이 {med_diff:+.1f}nm > {threshold}nm")
        print("  → TEM/SEM 혼합 타깃에 측정법 편향 존재.")
        print("    'measurement_method' 피처 추가 또는 TEM 전용 타깃 분리 권장.")
    else:
        print(f"  중앙값 차이 {med_diff:+.1f}nm ≤ {threshold}nm → 혼합 사용 타당.")
    _hline()
    return {"tem_median": float(tem.median()), "sem_median": float(sem.median()),
            "median_diff": float(med_diff)}


# ──────────────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ML 진단 스크립트")
    parser.add_argument("--diag", nargs="*", type=int,
                        help="실행할 진단 번호 (예: --diag 1 2 3). 미지정 시 전체 실행.")
    args = parser.parse_args()

    run_all = args.diag is None
    run = lambda n: run_all or n in (args.diag or [])

    print("=" * 62)
    print("  CeO2 합성 ML 진단 스크립트")
    print("=" * 62)

    print("\n  데이터 로드 + 전처리 …")
    m12 = _import_m12()
    df_raw = m12.load_data()
    df     = m12.preprocess(df_raw.copy())
    df     = df[df[TARGET].notna() & (df[TARGET] > 0)].copy()
    df["_log_target"] = np.log(df[TARGET])
    print(f"  유효 데이터: {len(df):,}행\n")

    all_results = {}

    if run(1):
        all_results["diag1"] = diag1(df, m12)
    if run(2):
        all_results["diag2"] = diag2(df)
    if run(3):
        all_results["diag3"] = diag3(df, m12)
    if run(5):
        all_results["diag5"] = diag5(df, m12)
    if run(6):
        all_results["diag6"] = diag6(df_raw)

    # 결과 저장
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False,
                  default=lambda x: None if isinstance(x, float) and np.isnan(x) else x)
    print(f"\n  결과 저장: {OUT_PATH}")
    print("=" * 62)


if __name__ == "__main__":
    main()
