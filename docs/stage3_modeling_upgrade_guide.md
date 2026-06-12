# 3단계 예측·역설계 모델 — 설계 노트 & 업그레이드 가이드

> 목적: 작업 중인 파이썬 파이프라인에 **예측·역설계 단계**를 추가/업그레이드할 때 참고·이식할 수 있도록 정리. 입력은 2단계 출력 `ceria_samples.csv`(1행 = 1시편). 기준 구현은 `ceria_model.py`.

---

## 1. 한눈에 보는 동작

- **(A) 정방향 모델** — 형상은 **분류(classification)**, 크기·종횡비는 **회귀(regression)**로 따로 학습. (CMP 확장: Ce³⁺·표면화학, 그리고 연계 성능 지표 — §5)
- **(B) 해석** — `permutation importance`(필요 시 SHAP)로 어떤 합성 변수가 결과를 좌우하는지 정량화.
- **(C) 역설계** — 학습한 정방향 모델을 **점수 함수**로 써서, 목표(형상·크기 등)를 만족하는 합성 조건 후보를 역으로 탐색.
- **(D) 능동학습** — 예측 불확실성이 가장 큰 조건 = 다음에 해보면 정보량이 큰 실험을 제안.

근거 선례: TiO₂에서 DoE로 공정 변수 영향을 조사한 뒤 ML로 크기·다분산도·종횡비를 예측하고, **역공학으로 원하는 결과 특성 → 최적 합성 조건**을 도출(Pellegrino et al., *Sci. Rep.* 2020). 이 "역설계"가 곧 *원하는 크기·형상을 위한 조건 예측*이다.

---

## 2. 꼭 지킬 설계 의도 (왜 이렇게 했나)

- **타깃 분리.** 형상(범주)과 크기/종횡비(연속)는 성질이 달라 **분류 모델·회귀 모델을 따로** 둔다.
- **작고 결측 많은 문헌 데이터 → 트리 기반 + native NaN.** 문헌 데이터는 보통 수백~수천 행에 빈 칸이 많다. **HistGradientBoosting**(결측 native 처리)이 적합하고, feature importance로 해석도 된다. (대안: Random Forest / XGBoost)
- **논문 단위 GroupKFold(누수 방지) — 가장 중요.** 같은 논문의 시편들은 조건을 공유하므로, 무작위 분할하면 train/test에 같은 논문이 섞여 성능이 **과대평가**된다. 반드시 `paper_doi`로 묶어 분할한다.
- **역설계 = 정방향 모델을 점수 함수로.** 별도 역모델을 학습하는 대신, 정방향 모델로 후보 조건을 채점해 상위를 고른다(투명·안정). 더 정교하게는 베이지안 최적화로 목표 영역을 탐색.
- **한계 직시 → 하이브리드.** 문헌 마이닝 데이터만으로는 신뢰할 모델이 잘 안 나온다: 보고 형식 제각각, **실패 실험 미보고로 인한 성공 편향(success bias)**, 희소성. 합성–구조 관계 예측 자체가 핵심 난제이며 덜 탐구된 영역이다. **가장 강력한 운용은 문헌으로 prior를 잡고, 본인의 소규모 DoE/능동학습 실험으로 보강하는 하이브리드.**

---

## 3. 업그레이드 체크리스트 (기존 파이프라인에 적용)

- [ ] **타깃 분리**: 형상 분류기 + 크기 회귀기(+ 종횡비/Ce³⁺ 회귀기) 별도 학습.
- [ ] **HistGradientBoosting**(결측 native) 기본 모델 + 범주형 OneHot 파이프라인.
- [ ] **논문 단위 `GroupKFold`** 교차검증으로 누수 차단(정직한 성능).
- [ ] **`permutation importance`**로 변수 영향력 출력(선택: SHAP).
- [ ] **전처리 규칙**: 범위값 → 중앙값, 단위 정규화(M, ℃, h), `capping_present` 같은 파생 피처, 희소 클래스 통합.
- [ ] **`confidence` 활용**: 낮은 신뢰도 행은 필터링하거나 표본 가중치로 반영.
- [ ] **역설계**: 후보 공간 생성 → 정방향 모델 채점 → 상위 조건 추천(선택: 베이지안 최적화).
- [ ] **능동학습**: 불확실성(엔트로피) 큰 조건을 다음 실험으로 제안하는 루프.

선택(있으면 더 좋은) 업그레이드:

- [ ] **SHAP**로 인자별 기여 방향까지 해석.
- [ ] **베이지안 최적화**(`scikit-optimize`/`optuna`)로 역설계 탐색 고도화.
- [ ] **불확실성 정량화**(conformal prediction 등)로 예측 신뢰구간 제공.
- [ ] **데이터/모델 버전 관리**로 코퍼스 갱신 시 재현성 확보.
- [ ] **CMP 확장**(§5): 입자 인자 → 성능 지표 2단 모델, 형상 vs 크기 우선순위.

---

## 4. 드롭인 코드 조각

> `pip install pandas scikit-learn numpy`

### 4.1 전처리 (범위→중앙값, 단위 정규화, 파생 피처)

```python
def _to_M(value, unit):
    """농도를 mol/L(M)로 정규화. 모르면 NaN."""
    import pandas as pd, numpy as np
    if pd.isna(value): return np.nan
    u = ("" if pd.isna(unit) else str(unit).lower().strip())
    if u in ("mm", "mmol/l"): return float(value) / 1000.0
    return float(value)  # M/mol·L⁻¹ 또는 미상은 값 그대로

def resolve_range(row, point, is_range, lo, hi):
    """범위면 중앙값, 점값이면 그대로."""
    if bool(row.get(is_range)) and not pd.isna(row.get(lo)):
        return (float(row[lo]) + float(row[hi])) / 2
    return row.get(point)
# 예) size_nm = resolve_range(r, "size_nm_value", "size_is_range", "size_nm_min", "size_nm_max")
# capping_present = 0 if (없음/none) else 1   ← 파생 이진 피처
```

### 4.2 모델 파이프라인 (HGB + OneHot, 결측 native)

```python
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

NUMERIC = ["precursor_conc_M", "mineralizer_conc_M", "temperature_C", "time_h", "pH", "capping_present"]
CATEGORICAL = ["method", "precursor", "mineralizer", "capping_agent", "solvent"]
FEATURES = NUMERIC + CATEGORICAL

def build_estimator(kind):
    pre = ColumnTransformer([
        ("num", "passthrough", NUMERIC),                 # HGB가 NaN 직접 처리
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="constant", fill_value="unknown")),
            ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), CATEGORICAL),
    ])
    model = (HistGradientBoostingClassifier(random_state=0) if kind == "clf"
             else HistGradientBoostingRegressor(random_state=0))
    return Pipeline([("pre", pre), ("model", model)])
```

### 4.3 논문 단위 GroupKFold 평가 + 변수 영향력

```python
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.inspection import permutation_importance
from sklearn.metrics import f1_score, mean_absolute_error, r2_score
import pandas as pd

def evaluate(df, target, kind, min_class=5):
    d = df.dropna(subset=[target]).copy()
    if kind == "clf":                       # 희소 클래스 통합
        vc = d[target].value_counts()
        d[target] = d[target].where(d[target].isin(vc[vc >= min_class].index), "other")
    if len(d) < 20 or d["paper_doi"].nunique() < 3:
        print(f"[{target}] 표본 부족 — 데이터를 더 모으세요."); return None

    X, y, groups = d[FEATURES], d[target], d["paper_doi"]
    cv = GroupKFold(n_splits=min(5, d["paper_doi"].nunique()))
    est = build_estimator(kind)
    pred = cross_val_predict(est, X, y, groups=groups, cv=cv)   # ← 논문 단위 분할(누수 차단)
    if kind == "clf":
        print(f"[{target}] acc {(pred==y).mean():.2f} | macroF1 {f1_score(y,pred,average='macro'):.2f}")
    else:
        print(f"[{target}] MAE {mean_absolute_error(y,pred):.1f} | R² {r2_score(y,pred):.2f}")

    est.fit(X, y)                            # 전체로 재학습 → 해석·역설계에 사용
    scoring = "f1_macro" if kind == "clf" else "neg_mean_absolute_error"
    imp = permutation_importance(est, X, y, n_repeats=10, random_state=0, scoring=scoring)
    print("  영향력:", pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False).head(5).to_dict())
    return est
```

### 4.4 역설계 (정방향 모델을 점수 함수로)

```python
import numpy as np
CONTROLLABLE = ["method", "mineralizer", "mineralizer_conc_M", "temperature_C", "time_h", "capping_agent"]

def candidate_space(df, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    cand = pd.DataFrame(index=range(n))
    for c in CONTROLLABLE:                       # 관측 범위에서 후보 샘플링
        col = df[c].dropna()
        cand[c] = (rng.choice(col.unique(), n) if c in CATEGORICAL
                   else rng.uniform(col.min(), col.max(), n)) if len(col) else np.nan
    for c in FEATURES:                           # 나머지는 최빈/중앙값
        if c not in cand:
            cand[c] = df[c].mode().iloc[0] if c in CATEGORICAL else df[c].median()
    cand["capping_present"] = cand["capping_agent"].apply(
        lambda x: 0 if (pd.isna(x) or str(x).lower() in ("none","unknown")) else 1)
    return cand

def inverse_design(clf, reg, df, target_morph, target_size=None, top_k=5):
    cand = candidate_space(df); X = cand[FEATURES]
    classes = list(clf.named_steps["model"].classes_)
    p = clf.predict_proba(X)[:, classes.index(target_morph)]
    score = p
    if reg is not None and target_size is not None:           # 형상 확률 × 크기 근접도
        size = reg.predict(X)
        score = p * np.exp(-((size - target_size) ** 2) / (2 * (0.2 * target_size) ** 2))
        cand["pred_size"] = size
    cand["score"] = score
    return cand.sort_values("score", ascending=False).head(top_k)
# 고도화: 후보를 무작위로 뽑는 대신 베이지안 최적화(scikit-optimize/optuna)로 score를 최대화.
```

### 4.5 능동학습 (불확실성 큰 조건 제안)

```python
def suggest_experiments(clf, df, top_k=5):
    cand = candidate_space(df, seed=1)
    proba = clf.predict_proba(cand[FEATURES])
    cand["uncertainty"] = -(proba * np.log(proba + 1e-12)).sum(axis=1)   # 엔트로피
    return cand.sort_values("uncertainty", ascending=False).head(top_k)
# 이 후보를 직접 실험 → 결과를 데이터에 되먹임 → 모델 재학습(active-learning loop).
```

---

## 5. CMP 확장 (성능 지표 + 형상/크기 우선순위)

### 5.1 입자 인자 → CMP 성능 지표 (2단 모델)

- **직접 예측(입자 인자):** 크기·분포 / 형상·노출면 / Ce³⁺·산소공공.
- **연계 예측(CMP 성능):** SiO₂ 제거율(MRR) / SiO₂·Si₃N₄ 선택비 / 스크래치·결함 / 표면 거칠기(Ra/Sa).
- **주의:** 성능 지표는 **슬러리·공정(pH·압력·패드)** 조건에도 의존한다. 따라서 **입자 인자 + 공정 변수를 함께 입력**하거나, **"입자 → 성능" 2단 모델**로 구성한다. "합성 조건만으로 MRR이 결정된다"는 식의 과한 주장은 피한다.

### 5.2 형상 vs 1차입자 크기 — 연마율 우선순위 (확률·통계)

문헌·특허의 효과를 가중해 ΔMRR 기여 우선순위를 확률로 표현한다.

```python
# 증거 가중치: 보고빈도 × 효과 방향 일관성 × 표준화 효과크기 × 연구 품질
# 사후확률: P(인자 우선 | 증거) ∝ Σ w_i  (Dirichlet/Beta 프레이밍으로 불확실성도 표현)
def evidence_weighted_priority(records):
    """records: [{factor, n_reports, consistency(0~1), effect_size, quality(0~1)}, ...]"""
    w = {}
    for r in records:
        w[r["factor"]] = w.get(r["factor"], 0) + (
            r["n_reports"] * r["consistency"] * abs(r["effect_size"]) * r["quality"])
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}   # 인자별 사후 우선확률
```

- 문헌 경향: **ΔMRR에는 1차입자 크기가 1순위**(강하고 일관된 직접 의존, 단 최적 크기 존재·크면 결함↑), **형상은 2순위**(비단조적). 단 **목표가 선택비면 형상이 1순위**가 될 수 있다 → 목표 지표에 따라 우선순위가 바뀐다.
- 역설계 연계: 위 우선순위에 따라 **1순위 레버(크기)부터** 탐색 공간을 좁혀 들어간다.

---

## 6. 특징(features)·타깃 — 1단계 §5 인자와의 연결

모델 입력 피처는 1단계 가이드 §5의 형상·크기 조절 팩터에서 그대로 가져온다.

- **입력 피처:** 합성법 / Ce 전구체·음이온 / 전구체·반응물 농도 / 염기 종류·농도 / pH(+조절제) / 온도 / 시간·숙성 / 첨가제(계면활성제·캡핑) 종류·농도 / 용매 / 산화제(H₂O₂) / 소성 T·시간 / 에너지 보조 / 도판트 / (있으면) 공정 변수.
- **타깃:** 형상(분류), 크기·분포(회귀), 종횡비(회귀), Ce³⁺·산소공공(회귀) — (CMP) 연계로 MRR·선택비·결함·Ra.
- 데이터가 늘면 `NUMERIC`/`CATEGORICAL` 목록에 위 인자 컬럼을 추가하면 그대로 학습에 반영된다.

---

## 7. 한계와 권장 운용

- **성공 편향**(실패 실험 미보고), **희소성**, **보고 형식 불일치**가 문헌 데이터의 본질적 한계다.
- 그래서 문헌 마이닝은 **prior(사전)** 로만 쓰고, **본인의 소규모 DoE + 능동학습 루프**로 모델을 키우는 하이브리드가 가장 신뢰도가 높다: 모델이 제안한 불확실 조건을 실험 → 결과를 데이터에 추가 → 재학습.

---

### 부록 — 핵심 참고 문헌

| 역할 | 문헌 |
|---|---|
| 세리아 형상 제어(합성 기반) | Mai et al., *J. Phys. Chem. B* (2005) |
| 합성 레시피 텍스트마이닝 데이터셋 | Kononova et al., *Sci. Data* (2019, GitHub 공개) |
| 나노입자 추출 데이터셋(직접 템플릿) | Cruse et al., *Sci. Data* (2022) |
| ML 예측 + 역설계(TiO₂ 선례) | Pellegrino et al., *Sci. Rep.* (2020) |
| 합성–구조 관계가 덜 탐구됨(최근 지적) | 최근(2026) 합성–구조 예측 연구 |
