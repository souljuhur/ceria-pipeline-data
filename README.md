# CeO2 합성 논문 ML 파이프라인

CeO2(세리아) 나노입자 합성 논문(1990~2026년)에서 합성조건과 측정결과를 자동 추출하여  
ML 학습 데이터셋으로 구축하고, 입자 크기 예측 및 역설계를 수행하는 프로젝트.

---

## 프로젝트 현황 (2026-06-17 기준 — 24차 세션 완료)

| 항목 | 수치 |
|------|------|
| 총 논문 (수집) | 7,278편 → **3,860편** (비세리아 필터링 후) |
| 전문(full text) 보유 | **2,879편** (74.5%) |
| GPT 추출 완료 | **5,415편** |
| 추출 샘플 수 | **6,403행** |
| 1차 입자크기 커버리지 (TEM+SEM) | **43.8%** (2,799/6,397 valid rows) |
| ML 모델 피처 수 | **32개** (21 수치 + 11 범주형) |

---

## ML 모델 성능 (23차 기준, particle_size_primary_nm)

| 모델 | log-R² | nm-MAE | n |
|------|--------|--------|---|
| HistGBM (`12_model.py`) | +0.006 | 31.14 | 2,799 |
| LightGBM (`12b_lgbm_baseline.py`) | +0.087 | 29.75 | 2,799 |
| CatBoost (`12d_catboost_model.py`) | +0.092 | 29.56 | 2,800 |
| **DKL-GP** (`12c_gpr_model.py`) | **+0.277** | **28.22** | 2,799 |

- 노이즈 천장 R² = **+0.348** (DIAG-2 기준)
- DKL-GP는 천장의 **79.6%** 도달 → 현재 데이터 한계에 근접

---

## 파이프라인 구조

```
[Stage 0] 논문 수집     0_collect.py → 0_merge_new.py
[Stage 1] 전문 수집     1_download.py (PMC + Semantic Scholar + Sci-Hub)
[Stage 2] 데이터 추출   2_extract.py → 3_merge.py → 4_extract_targeted.py → 5_table_extract.py
[Stage 3] 후처리        6~11번 스크립트 (정규화·태그·Excel·JSONL)
[Stage 4] ML 학습       12_model.py / 12b / 12c / 12d
[대시보드]              13_dashboard.py (Streamlit, 5개 탭)
```

### 전체 실행
```bash
python main.py            # 전체 파이프라인
python main.py --status   # 진행 상황 확인
streamlit run 13_dashboard.py
```

---

## 세션별 진행 이력

### 1~6차 (2026-06-01~08) — 파이프라인 기초 구축
- OpenAlex/Crossref/Semantic Scholar로 논문 4,388편 수집
- PDF 다운로드 + 텍스트 추출 파이프라인 완성
- GPT-4o-mini 합성조건 추출 + 완성도 점수 체계
- Streamlit 대시보드 기초 제작

### 7~11차 (2026-06-08~09) — 수집 확장 + 파이프라인 체계화
- Sci-Hub 2차 수집 완료 → 전문 962편
- PDF 표 추출 완성 (5,953행)
- 스크립트 번호 체계 (1~13) + main.py 4-Stage 구조 확립
- Excel 손상 복구, anion_type 파생 피처 추가

### 12차 (2026-06-10) — 데이터 확장
- 8_normalize_data.py: solvent_type 2,166편, anion_type 1,652편 파생
- 0_collect.py 신규 작성 (40개 쿼리, 커서 페이지네이션)
- 12_model.py 첫 실행 (R²=-0.060, 26피처)

### 13~14차 (2026-06-10) — 병렬 처리 + 대규모 수집
- 4_extract_targeted.py 20-worker 병렬화 (1~2시간 → 10~15분)
- 논문 4,388 → **7,278편** (+2,890편) 수집 완료
- 1_download.py --scihub 버그 수정

### 15~16차 (2026-06-11) — ML 개선 + DKL-GP 추가
- 4_extract_targeted.py synthesis_volume_mL 8번째 필드 추가
- 12c_gpr_model.py DKL-GP 신규 작성 (log-R²=+0.307, inducing=512)
- 1_download.py 완료 → 전문 5,426편 (74.5%)
- 대시보드 차트 해설 + 능동학습 탭 추가

### 17차 (2026-06-11) — 대규모 GPT 재추출 + CatBoost 추가
- 2_extract.py 완료 → 샘플 8,185행 (TEM 커버리지 40.5%)
- 12d_catboost_model.py 신규 작성 (log-R²=+0.077, 최초 양수)
- DKL-GP inducing=256 실패 → **512 필수** 확인
- predict_synthesis_conditions() API + 합성조건 예측 UI 추가

### 18차 (2026-06-11) — 피처 확장 (26→32개)
- synthesis_volume_mL, log_synth_volume, ce_total_mol 추가 → **32피처**
- HistGBM R²=-0.031 (17차 -0.056 → 개선)
- DKL-GP log-R²=+0.264 (epoch 25 조기수렴)
- CatBoost log-R²=+0.061

### 19차 (2026-06-12) — CatBoost Optuna 튜닝 + 추출 필드 확장
- **논문 수집 중단 결정** (기존 품질 개선에 집중)
- CatBoost Optuna 60회 탐색 → log-R²=+0.087 (+0.026 개선)
- 4_extract_targeted.py **8→13 필드** 확장 (capping_agent, chelating_agent, atmosphere, calcination_temperature_c, crystallite_size_xrd_nm)
- atmosphere +1,211행, calcination_temp +1,274행 신규 획득

### 20차 (2026-06-12) — function calling 전환 + LightGBM 추가
- 4_extract_targeted.py OpenAI function calling strict=True 전환
- crystallite_size_xrd_nm n=1,743 → **3,015** (+1,272)
- 12b_lgbm_baseline.py 신규 작성 (LightGBM + SHAP, log-R²=+0.032)
- synthesis_method enum 14→20 확장, unidentified_method **469→33행**

### 21차 (2026-06-12) — XRD 노이즈 필터 + DKL-GP early stopping 개선
- XRD between(2, 150) 필터 → xrd R² -0.054 → **-0.004**
- DKL-GP eval_freq=5, patience=10 → log-R²=+0.106 (21차)
- CatBoost XRD importance PNG 추가
- 대시보드 CatBoost 4열 그리드 + 역설계 95% CI (10/30/60nm)

### 22차 (2026-06-15) — DKL-GP 역대 최고 성능
- DKL-GP top-K 체크포인트 + T_max=100 → log-R²=**+0.364** (역대 최고)
- 8_normalize_data.py Section 8b 데이터 품질 필터 추가
- morphology OOM 수정 (try-except MemoryError)
- 전체 ML 재실행: HistGBM -0.040, LightGBM +0.027, CatBoost +0.061

### 23차 (2026-06-16) — 비세리아 논문 정밀 필터링
- filter_offtopic_papers.py 신규 작성 (3단계 필터)
- Excel **7,219 → 3,860편** (3,359편 제거), CSV **8,185 → 6,403행**
- 전체 ML 재학습: HistGBM +0.006, LightGBM +0.087, CatBoost +0.092, DKL-GP +0.277 (MAE **28.22nm** 역대 최저)

### 24차 (2026-06-16) — ML 진단 + 코드 정리
- diagnose_ml.py 신규 작성 (5개 진단)
  - DIAG-1: 동일split vs 5-fold 차이 +0.071 확인
  - DIAG-2: 노이즈 천장 R²=+0.348 (DKL-GP 79.6% 도달)
  - DIAG-3: method-mean baseline +0.011, 피처 기여 +0.081
  - DIAG-5: 0~20nm MAPE=198% (소입자 구간 예측 어려움)
  - DIAG-6: TEM vs SEM 중앙값 격차 -18.5nm (선택편향)
- 12_model.py 불필요 함수 3개 제거
- 대시보드 능동학습 탭 DKL-GP σ 단일 표시로 정리

---

## 미완료 항목

| 우선순위 | 항목 |
|----------|------|
| 선택 | `measurement_method` 피처 추가 — TEM/SEM 편향 보정 |
| 저우선 | Task Scheduler 자동화 (setup_auto.py + launcher.bat) |
| 저우선 | GitHub push (레포지토리 생성 후 진행) |

---

## 실행 환경

- Python: `C:\Users\K10756\AppData\Local\anaconda3\envs\test\python.exe`
- 실행: Bash 도구(Git Bash) 사용 (PowerShell 보안 정책 차단)
- `.env`: `OPENAI_API_KEY` 설정됨

```bash
PYTHON="/c/Users/K10756/AppData/Local/anaconda3/envs/test/python.exe"
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" "/d/머신러닝 교육/ceria_pipeline_data/<script>.py"
```

---

## 주요 출력 파일

| 파일 | 설명 |
|------|------|
| `output/ceria_synthesis_database.xlsx` | 논문 DB 원본 (3,860편) |
| `output/ceria_samples_merged.csv` | ML 학습용 샘플 (6,403행, 32피처) |
| `output/ceria_dataset_full.jsonl` | 전체 ML 데이터셋 |
| `output/model/` | 학습된 모델 pkl + SHAP PNG + performance_history.json |
