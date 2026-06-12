# CeO2 합성 논문 파이프라인

CeO2(세리아) 나노입자 합성 논문(1990~2026년, 7,278편)에서 합성조건과 측정결과를 자동 추출하여 ML 학습 데이터셋으로 구축하는 프로젝트.

---

## 실행 환경

- **Python**: `C:\Users\K10756\AppData\Local\anaconda3\envs\test\python.exe` ← **반드시 이 경로 사용**
  - `d:\머신러닝 교육\.conda\python.exe`는 base Python (numpy 없음) — **사용 금지**
- **셸**: PowerShell은 보안 정책으로 차단됨. **Bash 도구(Git Bash) 사용** (Claude Code 기준)
- subprocess 호출 시 반드시 `sys.executable` 사용 (하드코딩 금지)
- `.env` 파일: `OPENAI_API_KEY` 설정됨
- `PYTHONIOENCODING=utf-8` + `PYTHONUNBUFFERED=1` 환경변수 필요

```bash
# Claude Code Bash 도구에서 실행 방법
PYTHON="/c/Users/K10756/AppData/Local/anaconda3/envs/test/python.exe"
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" "/d/머신러닝 교육/ceria_pipeline_data/<script>.py"
```

```cmd
# 사용자가 직접 CMD에서 실행할 경우
conda activate test
python <script>.py
```

---

## 파일 구조 (번호 순서 = 실행 순서)

```
ceria_pipeline_data/
│
├── main.py              ★ 마스터 실행기 — python main.py 로 전체 파이프라인 실행
├── pipeline.py          초기 논문 수집 (OpenAlex, 1회성 — 이미 완료, 0_collect.py로 대체)
├── run_weekly.py        주간 자동화 (매주 월요일, 별도 실행)
│
│  ── [Stage 0] 논문 수집 ────────────────────────────────────────────
├── 0_collect.py         다층 쿼리 논문 수집 (OpenAlex, 40개 쿼리, 커서 페이지네이션)
├── 0_merge_new.py       수집 결과를 Excel DB에 병합 (DOI 중복 제거)
│
│  ── [Stage 1] 전문 수집 ────────────────────────────────────────────
├── 1_download.py        비-OA PDF 다운로드 (PMC + Semantic Scholar + Sci-Hub)
│
│  ── [Stage 2] 데이터 추출 ──────────────────────────────────────────
├── 2_extract.py         GPT-4o-mini 합성조건 추출
├── 3_merge.py           샘플CSV + 논문Excel 병합
├── 4_extract_targeted.py  핵심 13필드 집중 재추출 (병렬 20workers, 19차 8→13)
├── 5_table_extract.py   PDF 표/그림 기반 입자크기 보완 (vision GPT)
│
│  ── [Stage 3] 후처리 + 출력 ────────────────────────────────────────
├── 6_fill_keywords.py   키워드 기반 빈 필드 보완
├── 7_calc_completeness.py 완성도 점수 계산
├── 8_normalize_data.py  데이터 정규화 + 파생 피처 생성 (anion_type, solvent_type)
├── 9_add_tags.py        OA/방법/형태 태그 추가
├── 10_build_dataset.py  ML 데이터셋 JSONL 생성
├── 11_format_excel.py   열람용 Excel 서식 생성
│
│  ── [Stage 4] ML 학습 + 역설계 ─────────────────────────────────────
├── 12_model.py          HistGBM ML 모델 학습 + Q10/Q90 분위수 + 역설계 + 능동학습
├── 12c_gpr_model.py     DKL-GP (Deep Kernel Learning) 불확실성 정량화
├── 12d_catboost_model.py CatBoost + Optuna + SHAP (19차 --tune log-R²=+0.087)
│
│  ── 대시보드 ───────────────────────────────────────────────────────
├── 13_dashboard.py      Streamlit 대시보드 (5개 탭)
│
│  ── 공통 라이브러리 ────────────────────────────────────────────────
├── src/
│   ├── extract_ceria_rules.py
│   ├── experiment_parser.py
│   ├── ceria_dictionary.py
│   ├── dopant_dictionary.py
│   └── quantity_extractor.py
│
│  ── 유틸리티 (utils/) ──────────────────────────────────────────────
├── utils/
│   ├── check_completeness.py    완성도 점수 분포 분석
│   ├── check_fulltext.py        전문 접근 여부 분석
│   ├── quick_analysis.py        탐색적 분석
│   ├── repair_excel.py          Excel 손상 복구 (일회성)
│   ├── reset_vision_cache.py    vision 캐시 초기화
│   ├── run_auto_continue.py     다운로드 후 자동 이어달리기
│   ├── run_download_extra.py    추가 PDF 다운로드 (보조)
│   └── test_particle_size.py    입자크기 단위 테스트
│
│  ── 출력 ───────────────────────────────────────────────────────────
├── output/
│   ├── ceria_synthesis_database.xlsx         원본 DB (파이프라인 전용)
│   ├── ceria_synthesis_database_display.xlsx  서식 열람본
│   ├── ceria_samples_merged_display.xlsx      샘플 서식본 (녹색테마)
│   ├── ceria_samples.csv/jsonl
│   ├── ceria_samples_merged.csv
│   ├── ceria_dataset_full.jsonl
│   ├── ceria_dataset_quality.jsonl
│   ├── pipeline_state.json                   체크포인트 상태
│   ├── llm_cache.json                        2_extract.py 추출 캐시
│   ├── targeted_extraction_cache.json        4_extract_targeted.py 캐시
│   ├── noa_download_cache.json               1_download.py 캐시
│   ├── table_extraction_cache.json           5_table_extract.py 캐시
│   ├── weekly_state.json
│   ├── logs/
│   └── model/                               ML 모델 pkl + PNG + CSV
│       ├── performance_history.json          세션별 모델 성능 이력 (자동 누적)
│       ├── dkl_particle_size_primary_nm.pt   DKL-GP 모델 가중치
│       ├── catboost_particle_size_primary_nm_reg.pkl
│       └── (기타 pkl/png/csv)
├── pdf/                                     다운로드된 PDF (4,161개)
└── text/                                    추출된 텍스트 (5,426개)
```

---

## ⚠️ Excel 파일 두 종류 — 반드시 구분

| 파일 | 용도 | 비고 |
|------|------|------|
| `ceria_synthesis_database.xlsx` | **파이프라인 전용 원본** | 모든 스크립트가 읽는 파일. 서식 없음 |
| `ceria_synthesis_database_display.xlsx` | **열람용 서식본** | 11_format_excel.py 출력. 요약행/테두리/정렬 포함 |

`11_format_excel.py`는 원본을 수정하지 않고 `_display.xlsx`만 생성한다.

---

## 현재 진행 상황 (2026-06-12 기준 — 19차 세션 완료)

> ⚠️ **논문 수집 중단**: 0_collect.py, 0_merge_new.py, run_weekly.py — 별도 지시 전까지 실행 금지

| 항목 | 수치 |
|------|------|
| 총 논문 | **7,278편** — 수집 중단, 현재 자료로 개선에 집중 |
| 전문(full text) 보유 | **5,426편 (74.5%)** — text/ 파일 기준 |
| PDF 파일 | **4,161개** (pdf/ 폴더) |
| GPT 추출 완료 | **5,415편** (llm_cache 기준) |
| 추출 샘플 수 | **8,185행** (CSV, 8,175 usable) |
| 1차 입자크기 커버리지 (TEM+SEM) | **40.5%** (3,311/8,185) |
| ML 모델 피처 수 | **32개** (21 수치 + 11 범주형) |
| ML 모델 R² (primary_nm, HistGBM) | **-0.031** (MAE=32.88nm, n=3307) |
| ML 모델 R² (primary_nm, CatBoost) | **+0.087** (MAE=31.31nm, n=3311) ← **19차 --tune 개선** |
| ML 모델 R² (primary_nm, DKL-GP) | **+0.264** (MAE=29.86nm, PICP=0.830, n=3307) |
| per-method 최고 R² | HistGBM sol-gel **+0.111** (nm 기준) |
| 추출 필드 수 | **13개** ← **19차 +5** (capping_agent, chelating_agent, atmosphere, calcination_temperature_c, crystallite_size_xrd_nm) |
| Excel 열 수 | **48열** (11_format_excel.py 기준) |

### 최신 모델 성능 비교 (19차 기준, particle_size_primary_nm)

| 모델 | log-R² | nm-MAE | RMSE | MdAE | n |
|------|--------|--------|------|------|---|
| HistGBM | -0.031 | 32.88 | 75.59 | 11.15 | 3307 |
| CatBoost (--tune) | **+0.087** | 31.31 | 75.35 | 9.65 | 3311 |
| DKL-GP (inducing=512) | **+0.264** | 29.86 | 76.27 | 8.18 | 3307 |

### 19차 CatBoost --tune 결과 (particle_size_primary_nm 기준)

| 타겟 | 18차 | 19차 (--tune) | 변화 |
|------|------|--------------|------|
| particle_size_primary_nm | +0.061 | **+0.087** | +0.026 ✓ |
| particle_size_tem_nm | +0.089 | **+0.100** | +0.011 ✓ |
| crystallite_size_xrd_nm | +0.142 | **+0.159** | +0.017 ✓ |

Optuna 최적 파라미터 (60회 탐색): iterations=707, lr=0.0495, depth=7, l2_leaf_reg=2.18

> ※ DKL-GP: 18차/19차 모두 epoch 25 조기수렴. +0.300 회복 미완. 재실행 시 회복 가능성 있음

---

## 실행 순서

### 전체 실행 (권장 — main.py 한 번으로 끝)
```bash
python main.py                    # 전체 파이프라인 (완료 단계 자동 건너뜀)
python main.py --status           # 현재 진행 상황 확인
python main.py --dashboard        # Streamlit 대시보드 실행
```

### 단계별 실행
```bash
python main.py --stage 2          # 2단계(데이터 추출)만 실행
python main.py --from 3           # 3단계(후처리)부터 끝까지
python main.py --reset --from 2   # 2단계부터 강제 재실행
python main.py --reset --stage 3  # 3단계만 강제 재실행
```

> **⚠️ 주의**: `--from N`의 N은 **Stage 번호(1~4)**, 스크립트 번호가 아님
> - Stage 1: 1_download.py
> - Stage 2: 2_extract → 3_merge → 4_extract_targeted → 5_table_extract
> - Stage 3: 6_fill_keywords ~ 11_format_excel
> - Stage 4: 12_model.py

체크포인트: `output/pipeline_state.json` — 중단 후 재실행 시 완료된 단계 자동 건너뜀

### 개별 스크립트 직접 실행
```bash
python 1_download.py                # PDF 다운로드 (--scihub, --dry-run)
python 2_extract.py                 # GPT 합성조건 추출
python 3_merge.py                   # 샘플 병합
python 4_extract_targeted.py        # 핵심 13필드 재추출 (--reset, --dry-run)
python 5_table_extract.py           # 표/그림 입자크기 보완
python 6_fill_keywords.py           # 키워드 보완
python 7_calc_completeness.py       # 완성도 점수
python 8_normalize_data.py          # 데이터 정규화 + 파생 피처
python 9_add_tags.py                # OA/방법/형태 태그
python 10_build_dataset.py          # ML 데이터셋 JSONL 생성
python 11_format_excel.py           # 열람용 Excel 서식
python 12_model.py                  # HistGBM ML 모델 + 역설계 + 능동학습
python 12c_gpr_model.py --target particle_size_primary_nm --inducing 512 --epochs 300
python 12d_catboost_model.py        # CatBoost (--tune: Optuna 탐색, --no-permethod: 빠른 실행)
streamlit run 13_dashboard.py       # 대시보드 (http://localhost:8501)
```

### 다음 세션 시작 시

```bash
PYTHON="/c/Users/K10756/AppData/Local/anaconda3/envs/test/python.exe"

# 1. 후처리 + HistGBM ML (4_extract_targeted 13필드 반영 — Stage 3부터)
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/main.py" --from 3

# 2. DKL-GP 재학습 — inducing=512 필수 (256 → 성능 저하)
#    18/19차 모두 epoch 25 조기수렴 → 재실행 시 +0.300 회복 가능성 있음
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/12c_gpr_model.py" \
  --target particle_size_primary_nm --inducing 512 --epochs 300

# 3. CatBoost (--tune 최적 파라미터 이미 저장됨, 재학습은 일반 실행으로)
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/12d_catboost_model.py"

# 4. 대시보드 확인
streamlit run 13_dashboard.py
```

---

## 대시보드 탭 구성 (5개)

| 탭 | 내용 |
|----|------|
| 📊 개요 | 전체 통계, OA 비율, 태그 분포, 필드 채움률, 연도별 논문 분포, CMP 현황 |
| 🔍 DB 탐색 | 7,278편 검색/필터 (연도·합성법·OA여부·완성도) |
| 🧪 샘플 결과 | 샘플 추출 진행률, 합성법 분포, 샘플 목록 |
| 📈 ML 결과 | 성능 이력 차트(3종 모델), 피처 중요도, HistGBM Q10/Q90, DKL-GP σ, 합성조건 예측 UI, 역설계, 능동학습 |
| ⚙️ 운영 현황 | 열별 데이터 수 테이블, PMC/Sci-Hub 현황, 주간 이력 |

사이드바: 🔄 새로고침 버튼 + 📥 서식 Excel 다운로드 버튼 + 파일 최종 수정 시각 표시

---

## 설계 원칙

### Excel 읽기 — 요약행 자동 감지
`format_excel.py` 실행 후 원본이 오염된 경우를 대비해 `_load_xlsx()` 함수 사용:
```python
def _load_xlsx(path):
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)
```

### subprocess 호출 규칙
```python
import sys, os
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
subprocess.run([sys.executable, script], env=env, ...)
# ❌ PYTHON = r"d:\머신러닝 교육\.conda\python.exe"  ← 금지
# ❌ PYTHON = r"C:\Users\K10756\...\python.exe"      ← 금지 (하드코딩)
```

### 입자 크기 추출 (1차 입자만)
TEM/SEM 측정값만 추출. DLS/hydrodynamic/z-average/pore size 명시적 제외.
`_DLS_EXCL` 패턴이 `6_fill_keywords.py`와 `src/experiment_parser.py` 양쪽에 적용.

### morphology "other" 처리
GPT가 반환한 `"other"` 형태값 → 제목 키워드로 2차 재분류:
- `8_normalize_data.py`: TITLE_MORPH_KW 딕셔너리로 Excel 수정
- `13_dashboard.py`: `_norm_morph()` 함수로 on-the-fly 정규화

### particle_size_primary_nm 파생 규칙 (구명: particle_size_composite)
**TEM → SEM 우선순위** (1차 입자 크기; XRD 결정자 크기는 제외).
유효 범위: TEM/SEM 0.3~500nm. XRD 결정자 크기는 별도 `crystallite_size_xrd_nm` 컬럼으로만 유지.
`combine_first()` 벡터화 방식 사용 (apply 금지).

> **컬럼명 변경 이력**: `particle_size_composite` → `particle_size_primary_nm` (2026-06-10)
> 이전 57.3%는 XRD 결정자 크기 포함 오기준. **40.5%가 17차 기준 정확한 TEM+SEM 수치.**

### ML 모델 구성 (12_model.py)
- **피처**: **32개** (21 수치 + **11 범주형**)
- **범주형 피처**: synthesis_method, anion_type, ce_precursor, solvent_type, solvent, mineralizer, capping_agent, chelating_agent, oxidant, dopant, atmosphere
- **인코더**: TargetEncoder(shuffle=True, cv=5) — shuffle=False+random_state 조합 금지
- **회귀기**: HistGradientBoostingRegressor — 소그룹(n<200)은 early_stopping=False 자동 전환
- **early_stopping=False 시 n_iter_no_change 주의**: 파라미터 자체를 제외해야 함 (None 불가)
  ```python
  reg_es_kwargs = {"validation_fraction": 0.15, "n_iter_no_change": 25} if use_es else {}
  model = HistGradientBoostingRegressor(**common_kwargs, early_stopping=use_es, **reg_es_kwargs)
  ```
- **분류기**: HistGradientBoostingClassifier(early_stopping=False, max_iter=200) — max_iter=500은 ~25분, clf_kwargs로 override
  ```python
  clf_kwargs = {**common_kwargs, "max_iter": 200}  # common_kwargs의 max_iter=500 override
  model = HistGradientBoostingClassifier(**clf_kwargs, early_stopping=use_es, n_iter_no_change=25)
  ```
- **검증**: GroupKFold(n_splits=5) by DOI
- **물리 피처**: log_synth_temp, log_synth_time, thermal_budget, has_mineralizer, has_dopant
- **파생 피처**: anion_type (ce_precursor → 이온 분류), solvent_type (solvent → 용매 분류)
- **per-method 분리 모델**: `evaluate_per_method()` — n≥80 방법별 독립 학습
- **피처 중요도 상위**: synthesis_method(22.9%) > solvent(11.9%) > ce_precursor(10.6%) > capping_agent(6.8%) > synthesis_temperature_c(5.7%)
- **predict_synthesis_conditions()**: 목표 크기·형태 입력 → 추천 합성조건 반환 API (대시보드에서 importlib 호출)
  - 전처리 자동 적용: `if "log_synth_temp" not in df.columns: df = preprocess(df.copy())`
  - 3가지 모드: size_only / morph_only / combined

### DKL-GP 모델 구성 (12c_gpr_model.py)
- 아키텍처: [범주형 임베딩 + 수치형] → NN 특징 추출기 → Sparse GP (SVGP)
- **num_dim 반드시 동적 계산**: `train_dkl`에서 `num_dim = num_tr.shape[1]` (하드코딩 금지)
  ```python
  num_dim = num_tr.shape[1]  # NUMERIC_FEATURES 실제 개수 자동 계산
  model = DKLModel(cat_cardinalities, n_inducing=n_inducing, num_dim=num_dim)
  ```
- **17차 기준 성능**: log-R²=**0.300**, nm-MAE=29.47nm, PICP(90%)=0.841, σ 중앙값=22.86nm
- **inducing points**: **512 필수** (256 → n=3307에서 mean predictor 수렴, log-R²≈0)
  - 실행 명령: `python 12c_gpr_model.py --target particle_size_primary_nm --inducing 512 --epochs 300`
- **성능 이력 자동저장**: 실행 완료 시 `output/model/performance_history.json`에 `dkl_gp` 필드 업데이트

### CatBoost 모델 구성 (12d_catboost_model.py)
- **특징**: 범주형 피처 native 처리 (TargetEncoder 불필요), NaN native 지원, Ordered boosting
- **19차 기준 성능 (--tune, Optuna 60회)**:
  - particle_size_primary_nm: log-R²=**+0.087** (nm-MAE=31.31, RMSE=75.35, MdAE=9.65, n=3311)
  - particle_size_tem_nm: log-R²=**+0.100** (nm-MAE=28.29, n=3141)
  - crystallite_size_xrd_nm: log-R²=**+0.159** (nm-MAE=10.00, n=1743)
  - morphology(clf): acc=0.247, macroF1=0.093 (n=4442) — SHAP 오류 무시 가능
- **Optuna 최적 파라미터**: iterations=707, learning_rate=0.0495, depth=7, l2_leaf_reg=2.18, random_strength=4.39
- **ArrowStringArray 주의**: clf용 y 변환 시 `np.asarray(sub[target].values)` 필수
  ```python
  y_raw = np.asarray(sub[target].values)   # ArrowStringArray → numpy 변환
  y     = np.log(y_raw.astype(float)) if use_log else y_raw.copy()
  ```
- **성능 이력 자동저장**: 실행 완료 시 `output/model/performance_history.json`에 `catboost` 필드 업데이트
- **Optuna 튜닝**: `python 12d_catboost_model.py --tune` (60회 탐색, ~2.5시간 실소요)

### 성능 이력 관리 (performance_history.json)
- 위치: `output/model/performance_history.json`
- 구조: 세션별 항목 배열 — session_label, run_date, n_samples, n_papers, histgbm, dkl_gp, catboost
- **자동저장**: `12c_gpr_model.py` 완료 시 dkl_gp 필드, `12d_catboost_model.py` 완료 시 catboost 필드 업데이트
- **12_model.py**: `_save_performance_history(df)` → histgbm 필드 업데이트
- 대시보드 ML 탭에서 3종 모델 log-R² / MAE 추이 차트로 시각화

### anion_type 파생 규칙 (8_normalize_data.py)
ce_precursor 문자열 → 이온 유형 분류. Unicode 첨자 정규화(`_UNICODE_SUB`) 필수.
순서: ammonium_nitrate → nitrate → chloride → acetate → sulfate → carbonate → acetylacetonate → alkoxide → oxalate → hydroxide → carboxylate → mof → oxide → metal_ion → other

### solvent_type 파생 규칙 (8_normalize_data.py)
혼합 용매 패턴 먼저 매칭 (aqueous_alcohol → aqueous_polyol → alcohol_polyol → 단일 용매).
- **aqueous**: water, deionized, distilled, DDH2O, Milli-Q 등
- **alcohol**: ethanol, methanol, isopropanol, n-butanol 등
- **polyol**: ethylene glycol(EG), diethylene glycol(DEG), glycerol (PEG 제외 — capping agent)
- **polar_aprotic**: DMF, DMSO, NMP, acetone, THF, dioxane 등
- **nonpolar**: toluene, xylene, benzene, hexane, octadecene 등
- **oleylamine**: oleylamine, OAm, oleic acid
- **ionic_liquid**: [EMIM], [BMIM] 등
- **제외**: organic_acid (acetic acid/citric acid는 chelating agent, 용매 아님)

---

## 주요 스크립트 사용법

### 1_download.py (Stage 1)
```bash
python 1_download.py --dry-run          # 대상 확인만
python 1_download.py                    # PMC + Unpaywall + Semantic Scholar (합법)
python 1_download.py --scihub           # + Sci-Hub (저작권 주의)
python 1_download.py --scihub --reset   # 캐시 초기화 후 전체 재시도
```
수집 순서: 기존PDF추출 → Unpaywall → PMC → Semantic Scholar → Sci-Hub(옵션)
- `--scihub` 모드: `skip_set = failed_set` (Sci-Hub까지 실패한 것만 제외)
- 일반 모드: `done_dois` 전체 skip
- 캐시: `output/noa_download_cache.json`
- `cloudscraper` 라이브러리 필요: `pip install cloudscraper`

### 4_extract_targeted.py (Stage 2)
```bash
python 4_extract_targeted.py --dry-run   # 대상 확인
python 4_extract_targeted.py             # 실제 추출 (기본 20 workers)
python 4_extract_targeted.py --reset     # 캐시 초기화 후 재시도 (~$2, ~32분)
```
- **추출 필드 (13개)**: synthesis_method, ce_precursor, solvent, synthesis_temperature_c, ph_synthesis, ce_concentration_M, mineralizer_concentration_M, synthesis_volume_mL, **capping_agent, chelating_agent, atmosphere, calcination_temperature_c, crystallite_size_xrd_nm** (19차 +5)
- **방법**: GPT-4o-mini + ThreadPoolExecutor(20 workers) 병렬 처리
- **속도**: ~32분 (2,901편 기준), **비용**: ~$0.0010/편
- **캐시**: `output/targeted_extraction_cache.json`
- **프롬프트 개선 (19차)**: mmol→M 변환 계산, pH 문맥 패턴, Results 섹션 포함, max_tokens 280→600
- **텍스트 추출 개선 (19차)**: Experimental + Results/Characterization 섹션 병행 추출
- rate limit 429 오류 시 지수 백오프 (1→2→4→8초) 자동 재시도

### 0_collect.py + 0_merge_new.py (신규 논문 수집)

> ⚠️ **수집 중단** — 별도 지시 전까지 실행 금지 (2026-06-12 결정)
> 현재 7,278편 보유. 추가 수집 대신 기존 자료 품질 개선에 집중.

```bash
# 실행 금지 (지시 시까지)
# python 0_collect.py
# python 0_merge_new.py
```
- 병합 전 자동 백업: `ceria_synthesis_database_backup_before_merge.xlsx`
- 14차 세션에서 4,388 → **7,278편** (+2,890편) 달성 — 수집 완료

---

## 데이터 흐름 (전체)

```
논문 수집 (OpenAlex / Crossref / SemanticScholar)
    ↓ 0_collect.py (40개 다층 쿼리)
ceria_synthesis_database.xlsx (7,278편)
    ↓ 1_download.py [--scihub]  ← PMC→Semantic Scholar→Sci-Hub  [완료: 74.5%]
text/ 폴더 (5,426편, 74.5%)
    ↓ 2_extract.py (GPT-4o-mini)                                  [완료: 5,415편]
ceria_samples.jsonl
    ↓ 3_merge.py
    ↓ 4_extract_targeted.py (13필드 재추출, 20workers)          [19차 8→13필드]
    ↓ 5_table_extract.py  [표/PDF 기반 입자크기 보완]
ceria_samples_merged.csv (8,185행)
    ↓ 6_fill_keywords.py → 7_calc_completeness.py → 8_normalize_data.py
    ↓ 9_add_tags.py → 10_build_dataset.py
ceria_dataset_full.jsonl / ceria_dataset_quality.jsonl
    ↓ 11_format_excel.py
ceria_synthesis_database_display.xlsx (열람용)
    ↓ 12_model.py (32 피처, per-method 분리 모델) → HistGBM log-R²=-0.031
    ↓ 12c_gpr_model.py (DKL-GP, inducing=512)     → log-R²=+0.264, PICP=0.830
    ↓ 12d_catboost_model.py --tune (CatBoost)      → log-R²=+0.087 [최고 tabular, 19차]
output/model/ (pkl + PNG + CSV + performance_history.json)
```

### 1차 입자크기 커버리지 계층 구분

| 기준 | 파일 | 커버리지 | 비고 |
|------|------|---------|------|
| ceria_samples_merged.csv (ML 기준) | CSV | **40.5%** (3,307/8,175) | TEM+SEM만, XRD 제외 |
| ceria_synthesis_database.xlsx (Excel paper-level) | Excel | ~8.4% (TEM) | 논문 단위, 다른 지표 |

---

## 버그 수정 통합 이력

| 세션 | 파일 | 버그 | 수정 |
|------|------|------|------|
| 18차 | **12_model.py** | HistGBMClassifier max_iter=500 + early_stopping=False → morphology clf ~25분 소요 | `clf_kwargs = {**common_kwargs, "max_iter": 200}` clf만 200 override |
| 17차 | **12d_catboost_model.py** | CatBoost clf `predict()` → `(n,1)` shape → `pred_y[val_idx]` shape mismatch | `np.asarray(m.predict(...)).ravel()` |
| 17차 | **12d_catboost_model.py** | `y[tr_idx]` → `ArrowStringArray` → CatBoost clf 오류 | `np.asarray(sub[target].values)` 변환 |
| 17차 | **12_model.py** `inverse_design()` | `pd.to_numeric` 없이 Arrow string quantile → `ArrowNotImplementedError` | `vals = pd.to_numeric(df[col], errors="coerce").dropna(); float(vals.quantile(...))` |
| 16차 | **12c_gpr_model.py** | `DKLModel(num_dim=15)` 하드코딩 → NUMERIC_FEATURES 18개와 불일치 → matmul 오류 | `train_dkl`에서 `num_dim = num_tr.shape[1]` 자동 계산 |
| 16차 | **12_model.py** | `evaluate_per_method()`: `n_iter_no_change=None` → sklearn `[1,inf)` 범위 오류 | `reg_es_kwargs = {...} if use_es else {}` 조건부 kwargs |
| 15차 | **12_model.py** | `suggest_experiments_size()`: numpy 배열에 `.clip(lower=0)` (pandas 구문) → `TypeError` | `np.clip(q90_nm - q10_nm, 0, None)` |
| 15차 | **main.py** | `--reset --from N`: `not args.from_stage`가 `not 3` = False → force 항상 False | `args.stage is None or stage["num"] == args.stage` |
| 14차 | **1_download.py** | `done_dois`에 실패 논문도 추가 → `--scihub` 재시도 불가 | `--scihub`: `skip_set = failed_set`; 일반: `done_dois` skip |
| 14차 | **1_download.py** | `✓`/`✗` 문자 cp949 인코딩 오류 | `sys.stdout.reconfigure(encoding='utf-8')` |
| 13차 | **12_model.py** | `evaluate_per_method()` 소그룹: early_stopping window 크기 초과 | `build_pipeline(kind, early_stopping=(len≥200))` 파라미터화 |
| 13차 | **4_extract_targeted.py** | 순차 처리 1~2시간 병목 | `ThreadPoolExecutor(20 workers)` 병렬화 + 지수 백오프 |
| 10차 | **run_weekly.py** | `host_venue` deprecated → OpenAlex 400 오류 | `primary_location.source.display_name` |
| 10차 | **8_normalize_data.py** | anion_type "other" 과다 — CeO2·Unicode 첨자 미처리 | oxide/metal_ion/carboxylate/mof 패턴 추가; `_UNICODE_SUB` |
| 10차 | **8_normalize_data.py** | organic_acid/PEG 용매 분류 오류 | organic_acid, PEG 패턴 제거 |
| 9차 | **6_fill_keywords.py** | `KeyError: 'abstract'` | `if "abstract" in df.columns` 조건 추가 |
| 6~7차 | **12_model.py** | TargetEncoder `shuffle=False` + `random_state` 충돌 | `shuffle=True` |
| 6~7차 | **12_model.py** | 형태 분류기 early_stopping=True → 희귀 클래스 split 실패 | `early_stopping=False` |
| 6~7차 | **11_format_excel.py** | 원본 Excel에 요약행 추가 → 파이프라인 KeyError | `_display.xlsx` 별도 저장 + 원본 복구 |

---

## 세션 이력 요약

### 7~11차 세션 요약 (2026-06-08~09)

| 세션 | 핵심 작업 |
|------|----------|
| 7차 | Sci-Hub 2차 수집 완료 → 누적 전문 962편 |
| 8차 | PDF 표 추출 완료 (5,953행, composite 57.3%), ceria_model.py R²=-0.064 |
| 9차 | Excel 손상 복구 (repair_excel.py), fill_keywords 버그 수정, ML가능 127→214편 |
| 10차 | run_weekly.py 버그 수정, anion_type 파생 추가, cube 역설계 0.353→0.622 |
| 11차 | 스크립트 번호 체계 (1~13) 도입, main.py 4-Stage 구조 완성 |

### 12차 세션 (2026-06-10)

| 작업 | 결과 |
|------|------|
| `8_normalize_data.py` 실행 | solvent_type 파생 2,166편, anion_type 1,652편 |
| `12_model.py` 실행 (26피처) | R²=-0.060, per-method 분리 모델 추가 |
| `0_collect.py` 신규 작성 | 40개 쿼리, 커서 페이지네이션, JSONL+CSV 출력 |

### 13차 세션 (2026-06-10)

| 작업 | 결과 |
|------|------|
| `4_extract_targeted.py` 전면 재작성 | 20workers 병렬, 1~2시간 → 10~15분 |
| `5_table_extract.py` 실행 | 총 5,953행(+1,592), particle_size 40.0% |
| `main.py --from 3` | 29피처, R²=-0.049 |
| `1_download.py` Semantic Scholar 추가 | 3순위 합법 OA 경로 |

### 14차 세션 (2026-06-10)

| 작업 | 결과 |
|------|------|
| `0_collect.py` 실행 결과 확인 | 4,388 → **7,278편** (+2,890편), 전문 4,173편 |
| `1_download.py --scihub` 버그 수정 + 실행 시작 | done_dois 추적 오류 수정, 2,116편 재시도 |

### 15차 세션 (2026-06-11)

| 작업 | 결과 |
|------|------|
| 대시보드 차트 해설 expander 4개 추가 | HistGBM/SHAP/DKL-GP/탐색분석 탭 |
| 능동학습 탭 전면 재구성 | HistGBM Q10/Q90 vs DKL-GP σ 비교 |
| `12_model.py` Q10/Q90 분위수 회귀 추가 | `build_quantile_pipeline()` + `active_learning_size_histgbm.csv` |
| `4_extract_targeted.py` synthesis_volume_mL 추가 | 8번째 필드 |
| 파이프라인 실행 | 6,236샘플, ML가능 241편, R²=-0.042, TEM R²=+0.008 |
| 버그 수정 2건 | numpy clip, per-method early_stopping |

### 16차 세션 (2026-06-11)

| 작업 | 결과 |
|------|------|
| `5_table_extract.py` 실행 | 14편 신규 → 커버리지 37.7%→**37.8%** |
| `main.py --reset --from 3` | R²=-0.038, sol-gel per-method **+0.111** |
| `12_model.py` 버그 수정 | n_iter_no_change 조건부 kwargs |
| `12c_gpr_model.py` 버그 수정 + 실행 | num_dim 동적 계산, DKL-GP log-R²=**0.307**, σ=21.44nm |
| `1_download.py --scihub` 완료 확인 | 4,173 → **5,426편** (+1,253, 74.5%) |
| `2_extract.py` 실행 시작 | 1,088편 대상, ~$0.87 |

### 17차 세션 (2026-06-11)

| 작업 | 결과 |
|------|------|
| `2_extract.py` 완료 확인 | 8,185샘플 (6,236→+1,949), 커버리지 40.5% |
| `main.py --reset --from 2` | 파이프라인 전체 재실행 완료 |
| `12_model.py` 실행 | HistGBM R²=-0.056, 3311샘플 |
| `12d_catboost_model.py` 신규 작성 + 실행 | CatBoost log-R²=**+0.077** (최초 양수, best tabular) |
| `12c_gpr_model.py --inducing 512 --epochs 300` | DKL-GP log-R²=**+0.300** 회복, PICP=0.841 (256→실패, 512→회복) |
| 대시보드 성능이력 차트 CatBoost 라인 추가 | 3종 모델(HistGBM/DKL-GP/CatBoost) 비교 |
| 합성조건 예측 UI 추가 (ML 탭) | 목표 크기/형태 입력 → 추천 합성조건 (3-모드) |
| `predict_synthesis_conditions()` API 추가 | `12_model.py`, 대시보드 importlib 호출 |
| `performance_history.json` 자동저장 훅 | `12c_gpr_model.py` + `12d_catboost_model.py` |
| 버그 수정 2건 | 12d ArrowStringArray→numpy, 역설계 quantile float 변환 |

### 18차 세션 (2026-06-11)

| 작업 | 결과 |
|------|------|
| `12_model.py` 신규 피처 3개 추가 | synthesis_volume_mL(43.8%), log_synth_volume(43.8%), ce_total_mol(18.5%) → **32피처** |
| `12_model.py` clf max_iter=200 버그수정 | 형태 분류 25분 → ~10분으로 단축 |
| `12_model.py` 실행 | HistGBM R²=**-0.031** (17차 -0.056 → 개선) |
| `12c_gpr_model.py --inducing 512 --epochs 300` | DKL-GP log-R²=**+0.264** (epoch 25 조기수렴, 4분 완료) |
| `12d_catboost_model.py` 실행 | CatBoost log-R²=**+0.061** (tem_nm +0.089, xrd +0.142) |
| HistGBM→DKL-GP→CatBoost 자동 체인 실행 | 백그라운드 chain_runner 스크립트 |

### 19차 세션 (2026-06-12)

| 작업 | 결과 |
|------|------|
| **논문 수집 중단 결정** | 기존 7,278편으로 ML 품질 개선에 집중 (별도 지시 전 수집 금지) |
| `12c_gpr_model.py` 재실행 | DKL-GP log-R²=**+0.262** (epoch 25 조기수렴 반복, +0.300 미회복) |
| `12d_catboost_model.py --tune` | Optuna 60회 탐색 (~2.5시간), CatBoost log-R²=**+0.087** (+0.026 개선) |
| `4_extract_targeted.py` 프롬프트 개선 + 필드 확장 | **8→13 필드** 추가: capping_agent, chelating_agent, atmosphere, calcination_temperature_c, crystallite_size_xrd_nm |
| `4_extract_targeted.py --reset` 실행 (2,901편) | atmosphere +1,211행, calcination_temp +1,274행, crystallite_size_xrd +892행, capping_agent +615행 |
| `5_table_extract.py` 실행 | 캐시 완료(0 신규) — 기존 PDF 모두 처리됨 |
| 다음 단계 대기 | `main.py --from 3` 실행 예정 |

---

## 미완료 항목 (우선순위 순)

1. **[즉시]** `main.py --from 3` — 4_extract_targeted 13필드 반영 후처리 + ML 전체 재학습
2. **[선택]** `12c_gpr_model.py --inducing 512 --epochs 300` 재실행 — 18/19차 epoch 25 조기수렴 반복, +0.300 회복 목표
3. **[저우선]** Task Scheduler `setup_auto.py` + 데스크탑 아이콘 `launcher.bat`

---

## 주간 자동화 (run_weekly.py)

매주 월요일 09:00 실행 예정. 수동 실행도 가능.
```bash
python run_weekly.py
```
동작: OpenAlex 신규 논문 수집 → Excel 추가 → OA PDF 다운로드 → 후처리 → ML 재학습
- OpenAlex API: `primary_location.source.display_name` 사용 (`host_venue` 폐기됨)
- 상태 파일: `output/weekly_state.json`
- 로그: `output/logs/weekly_YYYYMMDD_HHMMSS.log`
- Task Scheduler 등록(`setup_auto.py`) 미완성
