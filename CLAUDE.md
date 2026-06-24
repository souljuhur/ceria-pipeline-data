# CeO2 합성 논문 파이프라인

CeO2(세리아) 나노입자 합성 논문(1990~2026년, 수집 7,278편 → 정제 후 3,860편)에서 합성조건과 측정결과를 자동 추출하여 ML 학습 데이터셋으로 구축하는 프로젝트.

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

> ⚠️ `cmd.exe /c "..." 2>&1` 방식은 Python stdout이 캡처되지 않음 (cmd 헤더만 출력).
> 반드시 Bash 도구로 직접 실행할 것. 한글 경로는 `/d/머신러닝 교육/...` 형식으로 정상 동작.

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
├── 12_model.py          HistGBM ML 모델 학습 + 역설계 + 능동학습 (형태 엔트로피)
├── 12b_lgbm_baseline.py LightGBM + SHAP 베이스라인 (20차 신규)
├── 12c_gpr_model.py     DKL-GP (Deep Kernel Learning) 불확실성 정량화
├── 12d_catboost_model.py CatBoost + Optuna + SHAP (19차 --tune log-R²=+0.087)
├── 12d_targeted_design.py LightGBM 95% 예측구간 역설계 (목표: 10/30/60nm)
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
│  ── 데이터 정제 ─────────────────────────────────────────────────────
├── filter_offtopic_papers.py    非세리아 논문 정밀 필터링 (23차 신규)
│                                3단계: HTML 디코딩 키워드 + 명백非세리아 + 본문 전구체 체크
├── diagnose_ml.py               ML 진단 스크립트 (24차 신규) — 5개 진단
│                                DIAG-1 동일split / DIAG-2 노이즈천장 / DIAG-3 baseline
│                                DIAG-5 구간잔차 / DIAG-6 TEM-SEM bias
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
│       ├── catboost_crystallite_size_xrd_nm_reg.pkl
│       ├── catboost_importance_particle_size_primary_nm.png
│       ├── catboost_importance_crystallite_size_xrd_nm.png  ← 21차 신규
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

## 현재 진행 상황 (2026-06-23 기준 — 27차 세션 완료)

> ⚠️ **논문 수집 중단**: 0_collect.py, 0_merge_new.py, run_weekly.py — 별도 지시 전까지 실행 금지

| 항목 | 수치 |
|------|------|
| 총 논문 (수집) | 7,278편 → **3,860편** (23차 비세리아 필터링 후: 3,359편 제거) |
| 전문(full text) 보유 | **2,879편** (text/ 기준, 필터 후) |
| PDF 파일 | **4,161개** (pdf/ 폴더 — 필터 대상 외) |
| GPT 추출 완료 | **2,879편** (26차 2_extract.py 전면 재작성 후) |
| 추출 샘플 수 | **8,819행** (26차 재추출 — 25차 6,403 → +2,416) |
| 1차 입자크기 커버리지 (TEM+SEM) | **48.4%** (4,249/8,819 valid rows) ← 26차 |
| crystallite_size_xrd_nm 샘플 수 | **n=3,148** (26차, 25차 n=2,490 → +658) |
| ML 모델 피처 수 | **33개** (21 수치 + **12 범주형**) |
| ML 모델 R² (primary_nm, HistGBM) | **-0.031** (MAE=28.37nm, n=4249) ← **26차** |
| ML 모델 R² (primary_nm, LightGBM) | **+0.023** (MAE=28.15nm, n=4249) ← **26차** |
| ML 모델 R² (primary_nm, CatBoost) | **+0.138** (MAE=26.64nm, n=4259) ← **27차 tabular 최고** |
| ML 모델 R² (primary_nm, DKL-GP) | **+0.321** (MAE=25.37nm, PICP=0.851, n=4249) ← **27차 전체 최고** |
| ML 모델 R² (xrd_nm, HistGBM) | **+0.006** (MAE=11.03nm, n=3148) ← **26차** |
| ML 모델 R² (xrd_nm, LightGBM) | **+0.024** (MAE=11.08nm, n=3148) ← **26차** |
| ML 모델 R² (xrd_nm, CatBoost) | **+0.126** (MAE=10.51nm, n=3157) ← **27차** |
| unidentified_method 행 수 | **363행** (26차 재추출 후 — 25차 33행에서 증가) |
| 추출 필드 수 | **13개** (function calling strict=True 전환 완료) |
| Excel 열 수 | **48열** (11_format_excel.py 기준) |

### 최신 모델 성능 비교 (27차 기준, particle_size_primary_nm)

| 모델 | log-R² | nm-MAE | RMSE | MdAE | n | vs 26차 |
|------|--------|--------|------|------|---|---------|
| HistGBM | **-0.031** | 28.37 | 66.08 | 9.26 | 4249 | 동일 |
| LightGBM (12b) | **+0.023** | 28.15 | 65.48 | 8.92 | 4249 | 동일 |
| CatBoost | **+0.138** | **26.64** | 65.89 | 7.95 | 4259 | +0.006 (신규 params) |
| DKL-GP (inducing=512) | **+0.321** | **25.37** | 66.71 | 6.44 | 4249 | +0.031 (n +1,450) |

> **27차**: DKL-GP 26차 재학습 완료 (n=4,249, ep75 조기종료→ep25 선택). log-R² +0.321 (역대 최고 갱신),
> MAE **25.37nm (전체 모델 최저)**. CatBoost --tune 26차 데이터 재탐색 → depth=8 신규 best_params,
> log-R²=+0.138로 소폭 개선.

### 27차 crystallite_size_xrd_nm 성능

| 모델 | 25차 | 26차 | 27차 | n | 비고 |
|------|------|------|------|---|------|
| HistGBM | +0.012 | +0.006 | **+0.006** | 3,148 | 동일 |
| LightGBM | +0.004 | +0.024 | **+0.024** | 3,148 | 동일 |
| CatBoost | +0.075 | +0.107 | **+0.126** | 3,157 | **+0.019 추가 개선** (신규 params) |

> **XRD 노이즈 필터 효과** (21차 기준): `12_model.py`에 `between(2, 150)` 필터 → 26차 72건 제거
> 물리적 근거: Scherrer equation 유효 범위 2~150nm (< 2nm 불가, > 150nm Scherrer 한계 초과)

> ※ DKL-GP 27차: ep75 조기종료(patience=10), top-3 버퍼 중 ep25 선택 → log-R²=**+0.321** (log-R² 역대 최고 갱신)
>    val-MAE best=0.8657(ep25). n=4,249 (26차 +1,450행 효과). 실측 MAE **25.37nm(역대 최저)**, MdAE=6.44nm, PICP=0.851.
>
> ※ DKL-GP 25차: ep75 조기종료(patience=10), top-3 버퍼(ep25/ep30) 중 ep30 선택 → log-R²=**+0.290**
>    val-MAE best=0.8133(ep25). particle_size_source 피처 추가 효과 +0.013 개선.
>    실측 MAE 28.03nm, MdAE=6.85nm, PICP=0.845.
>
> ※ DKL-GP 23차: ep75 조기종료(patience=10), top-3 버퍼(ep20/ep25/ep30) 중 ep30 선택 → log-R²=**+0.277**
>    val-MAE best=0.8378(ep25). 22차(+0.364)보다 낮은 이유: 데이터 분포 변화(n=3307→2799).
>
> ※ DKL-GP 22차: top-K 체크포인트 버퍼 + T_max=100 적용. ep70 조기종료, ep30 선택 → log-R²=**+0.364** (log-R² 역대 최고)
>    T_max=100으로 초기 빠른 수렴 유도.

### 27차 CatBoost --tune 결과 (저장된 최적 파라미터 — catboost_best_params.json)

Optuna 최적 파라미터 (60회 탐색, 26차 데이터 n=4,259 기준): iterations=669, lr=0.02444, depth=8, l2_leaf_reg=3.489, random_strength=2.417, bagging_temperature=1.913, border_count=254
(이전 26차 파라미터: iterations=636, lr=0.0341, depth=9 — catboost_best_params.json으로 갱신됨)

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
python 12b_lgbm_baseline.py         # LightGBM + SHAP
python 12c_gpr_model.py --target particle_size_primary_nm --inducing 512 --epochs 300
python 12d_catboost_model.py        # CatBoost (--tune: Optuna 탐색, --no-permethod: 빠른 실행)
python 12d_targeted_design.py       # LightGBM 95% CI 역설계 (10/30/60nm)
streamlit run 13_dashboard.py       # 대시보드 (http://localhost:8501)
```

### 다음 세션 시작 시

27차 완료 상태. 전 모델 재학습 완료.
- HistGBM -0.031 / LightGBM +0.023 / CatBoost **+0.138** / DKL-GP **+0.321** (역대 최고)
- DKL-GP MAE **25.37nm** (전체 모델 최저, MdAE=6.44nm, PICP=0.851, n=4,249)
- CatBoost XRD +0.126 (26차 +0.107 → +0.019 추가 개선, 신규 depth=8 params)
- 다음 개선 후보: unidentified_method 363행 원인 분석 및 재추출 검토

필요시 재학습:

```bash
PYTHON="/c/Users/K10756/AppData/Local/anaconda3/envs/test/python.exe"

# 1. 후처리 재실행 (데이터 변경 시)
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/main.py" --reset --from 3

# 2. DKL-GP 재학습 (top-K 버퍼 + T_max=100 적용됨)
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/12c_gpr_model.py" \
  --target particle_size_primary_nm --inducing 512 --epochs 300

# 3. CatBoost 재학습
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/12d_catboost_model.py"

# 4. LightGBM
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$PYTHON" \
  "/d/머신러닝 교육/ceria_pipeline_data/12b_lgbm_baseline.py"

# 5. 대시보드 확인
streamlit run 13_dashboard.py
```

> ⚠️ DKL-GP 첫 실행 시 메모리 부족(OOM)으로 실패할 수 있음.
> 원인: 이전 모델(HistGBM/LightGBM/CatBoost) 실행 직후 메모리 잔류.
> 해결: 다른 모델 완료 후 잠시 대기 후 재실행하면 정상 동작.

---

## 대시보드 탭 구성 (5개)

| 탭 | 내용 |
|----|------|
| 📊 개요 | 전체 통계, OA 비율, 태그 분포, 필드 채움률, 연도별 논문 분포, CMP 현황 |
| 🔍 DB 탐색 | 7,278편 검색/필터 (연도·합성법·OA여부·완성도) |
| 🧪 샘플 결과 | 샘플 추출 진행률, 합성법 분포, 샘플 목록 |
| 📈 ML 결과 | 성능 이력 차트(3종 모델), 피처 중요도, DKL-GP σ 능동학습, 합성조건 예측 UI, 역설계, 형태 능동학습 |
| ⚙️ 운영 현황 | 열별 데이터 수 테이블, PMC/Sci-Hub 현황, 주간 이력 |

사이드바: 🔄 새로고침 버튼 + 📥 서식 Excel 다운로드 버튼 + 파일 최종 수정 시각 표시

### 대시보드 ML 탭 주요 구성 (24차 기준)

- **HistGBM 피처 중요도**: primary_nm · xrd_nm 2개만 표시 (`_IMP_SHOW` 필터)
- **LightGBM SHAP**: 수치형 피처 한정, primary_nm · xrd_nm — 4열 그리드 (Importance+Beeswarm × 2타겟)
- **CatBoost 피처 중요도 & SHAP**: 4열 그리드 (Importance+SHAP × 2타겟, primary_nm · xrd_nm)
  - `catboost_importance_crystallite_size_xrd_nm.png` 21차 신규 추가
- **DKL-GP**: particle_size_primary_nm 단독, full-width 표시
- **수치 상관관계 히트맵**: CSV 샘플 기반, 10개 컬럼 (Ce농도·합성부피·건조온도 추가, BET 제거)
- **역설계 목표**: 10 / 30 / 60 nm, **95% 예측 구간** (Q2.5/Q97.5)
- **능동학습 (입자크기)**: DKL-GP σ 단일 표시 — HistGBM Q10/Q90 섹션 24차 제거
- **능동학습 (형태)**: HistGBM 분류 엔트로피 기반 (`active_learning_morph_histgbm.csv`)

---

## 코드 작성 전 검토 체크리스트

사용자에게 실행을 요청하기 전 반드시 아래 10개 항목을 점검한다.
(반복적으로 실행 오류가 발생했던 패턴 — TargetEncoder shuffle, format_excel.py KeyError, 캐시 문제 등)

1. **import 누락/미사용** — 사용하는 라이브러리가 모두 import되어 있는가
2. **변수명 불일치** — 하드코딩된 문자열이 상수·컬럼명과 일치하는가
3. **재실행 멱등성** — 같은 스크립트를 두 번 실행해도 안전한가 (덮어쓰기, 중복 추가 등)
4. **NA/None/NaN 처리** — pandas NA, numpy nan, None 세 가지 모두 고려했는가
5. **파일 존재·형식 fallback** — 파일이 이미 있거나 다른 형식일 때 대응하는가
6. **루프 안 불필요한 연산** — import, 반복 계산, 파일 열기가 루프 밖으로 빠져있는가
7. **엣지 케이스** — 제로 나눗셈, 빈 리스트 인덱스, 빈 DataFrame 처리
8. **외부 의존성** — 라이브러리 설치 여부, API 접속 가능 여부
9. **컬럼명 가드** — `if col in df.columns` 방어 코드 적용
10. **파일 잠금** — Excel이 열려있을 때 저장 시도하지 않는가

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

### XRD 결정자 크기 품질 필터 (12_model.py — 21차 추가)
```python
# TEM/SEM: 0.3~500nm (기존)
for col in [TARGET_SIZE, "particle_size_sem_nm"]:
    df.loc[~df[col].between(0.3, 500), col] = np.nan

# XRD Scherrer: 2~150nm (21차 추가 — 기존 0.3~500nm 공유에서 분리)
# 근거: < 2nm 물리적 불가, > 150nm Scherrer equation 적용 한계 초과
if TARGET_XRD in df.columns:
    df.loc[~df[TARGET_XRD].between(2, 150), TARGET_XRD] = np.nan
    # 21차: 74건 제거 → n: 3,015 → 2,947, HistGBM R²: -0.054 → -0.004
```

### ML 모델 구성 (12_model.py)
- **피처**: **33개** (21 수치 + **12 범주형**)
- **범주형 피처**: synthesis_method, anion_type, ce_precursor, solvent_type, solvent, mineralizer, capping_agent, chelating_agent, oxidant, dopant, atmosphere, **particle_size_source** (25차 추가)
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
- **피처 중요도 상위 (23차)**: synthesis_method(15.1%) > capping_agent(15.1%) > solvent(10.2%) > ce_concentration_M(7.3%) > ce_precursor(7.2%)
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
- **inducing points**: **512 필수** (256 → n=3307에서 mean predictor 수렴, log-R²≈0)
  - 실행 명령: `python 12c_gpr_model.py --target particle_size_primary_nm --inducing 512 --epochs 300`
- **Early stopping + top-K 체크포인트 (22차 개선)**:
  ```python
  eval_freq        = 5   # 5 epoch마다 검증
  patience         = 10  # 10회 연속 미개선 시 종료 (= 50 epoch)
  CKPT_BUFFER_SIZE = 3   # val-MAE 상위 3개 checkpoint 보존
  t_max            = min(n_epochs, 100)  # CosineAnnealingLR T_max=100 고정
  # early stop 후: top-3 중 최신 epoch 사용 (val/test 불일치 극복)
  chosen = max(ckpt_buffer, key=lambda x: x[1])  # 최신 epoch 선택
  ```
  - 22차 결과: epoch 20 best(val-MAE=0.9294), epoch 70 종료 → top-3=[ep20,ep25,ep30] → **ep30 선택**
  - log-R²=**+0.364** (역대 최고, 21차 +0.106 대비 3.4배 개선)
- **성능 이력 자동저장**: 실행 완료 시 `output/model/performance_history.json`에 `dkl_gp` 필드 업데이트

### CatBoost 모델 구성 (12d_catboost_model.py)
- **특징**: 범주형 피처 native 처리 (TargetEncoder 불필요), NaN native 지원, Ordered boosting
- **26차 기준 성능 (26차 best_params 적용)**:
  - particle_size_primary_nm: log-R²=**+0.132** (nm-MAE=26.71, n=4259) ← 26차
  - crystallite_size_xrd_nm: log-R²=**+0.107** (nm-MAE=10.58, n=3157) ← 26차 개선
- **26차 Optuna 최적 파라미터** (25차 n=2,800 기준 탐색): iterations=636, learning_rate=0.0341, depth=9, l2_leaf_reg=1.815, random_strength=1.311, bagging_temperature=0.726, border_count=254
- **ArrowStringArray 주의**: clf용 y 변환 시 `np.asarray(sub[target].values)` 필수
  ```python
  y_raw = np.asarray(sub[target].values)   # ArrowStringArray → numpy 변환
  y     = np.log(y_raw.astype(float)) if use_log else y_raw.copy()
  ```
- **피처 중요도 저장 (21차 개선)**: primary_nm + xrd_nm 두 타겟 모두 루프 처리
  ```python
  for _fi_target in [TARGET_COMPOSITE, TARGET_XRD]:   # 21차: xrd_nm 추가
      fi_model.fit(X_fi, np.log(sub_fi[_fi_target].values.astype(float)))
      plot_feature_importance(fi_model, _fi_target)
      # → catboost_importance_particle_size_primary_nm.png
      # → catboost_importance_crystallite_size_xrd_nm.png (신규)
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
- **방법 (20차 개선)**: OpenAI **function calling** (`strict=True`, `tool_choice`) — JSON 파싱 불안정성 제거, 수치 타입 보장
  - synthesis_temperature_c = 150 (int, 보장) vs 이전 "150°C" (문자열 혼재)
  - synthesis_method: enum 리스트로 제한 (hallucination 감소)
  - 모든 필드: `anyOf: [type, null]` nullable 스키마
- **속도**: ~32분 (2,901편 기준), **비용**: ~$0.0010/편
- **캐시**: `output/targeted_extraction_cache.json`
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
    ↓ 12_model.py (32피처, XRD 2~150nm 필터)  → HistGBM primary -0.040 / xrd -0.004 [21차]
    ↓ 12b_lgbm_baseline.py (LightGBM + SHAP)   → primary +0.032 / xrd -0.003 [21차]
    ↓ 12c_gpr_model.py (DKL-GP, inducing=512)  → primary +0.106 (early stop ep20) [21차]
    ↓ 12d_catboost_model.py (CatBoost)          → primary +0.056 [21차]
    ↓ 12d_targeted_design.py (LightGBM 95% CI) → 10/30/60nm 역설계 [21차]
output/model/ (pkl + PNG + CSV + performance_history.json)
```

### 1차 입자크기 커버리지 계층 구분

| 기준 | 파일 | 커버리지 | 비고 |
|------|------|---------|------|
| ceria_samples_merged.csv (ML 기준, 23차 이후) | CSV | **43.8%** (2,799/6,397) | TEM+SEM만, XRD 제외 |
| ceria_synthesis_database.xlsx (Excel paper-level) | Excel | ~8.4% (TEM) | 논문 단위, 다른 지표 |

---

## 버그 수정 통합 이력

| 세션 | 파일 | 버그 | 수정 |
|------|------|------|------|
| 24차 | **12_model.py** | `build_quantile_pipeline`/`evaluate_per_method`/`suggest_experiments_size` — 메모리 소모 대비 효용 낮음 (per-method mostly R²<0, Q10/Q90 구간내 예측 불가) | 3개 함수 + 호출부 완전 제거 |
| 24차 | **13_dashboard.py** | 능동학습 탭에 HistGBM Q10/Q90 섹션 유지 — 관련 csv 이제 생성 안 됨 | DKL-GP σ 단일 표시로 교체 |
| 22차 | **12_model.py** | morphology HistGBMClassifier `cross_val_predict` OOM → 이후 역설계·history저장 불가 | `try/except MemoryError` 추가, clf_morph=None 폴백 |
| 22차 | **13_dashboard.py** | particle_size_primary_nm 채움률 = 0% (JSONL에 없는 파생 필드), TEM/SEM 개별 노출 | rows 순회로 TEM OR SEM 합산 계산, GROUPS에서 개별 TEM/SEM 제거 |
| 22차 | **8_normalize_data.py** | CSV 품질 필터 없음 — chelating_agent에 HNO3/NH4OH, atmosphere 미정규화, ph>14 혼입 | Section 8b 추가: chelating 30건·capping 7건·atmosphere 821건·ph>14 5건·ce>15M 4건 제거 |
| 21차 | **12_model.py** | XRD 결정자 크기 0.3~500nm 필터 → 이상치 허용 (최대 2030nm) | `between(2, 150)` 별도 필터, 74건 제거 |
| 21차 | **12c_gpr_model.py** | eval_freq=25로 epoch 25만 평가 → val/test best 불일치 탐지 불가 | eval_freq=5, patience=10으로 세밀한 early stopping |
| 21차 | **12d_catboost_model.py** | XRD 피처 중요도 PNG 미생성 (primary_nm만 저장) | 루프로 [TARGET_COMPOSITE, TARGET_XRD] 둘 다 저장 |
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

### 20차 세션 (2026-06-12)

| 작업 | 결과 |
|------|------|
| `8_normalize_data.py` synthesis_method "other" 복구 3단계 개선 | 341행 신규 분류, 469행 → `unidentified_method` |
| `4_extract_targeted.py` OpenAI function calling 전환 (`strict=True`) | crystallite_size_xrd_nm n=1,743→3,015 (+1,272), 수치 타입 보장 |
| `main.py --from 3` + `12_model.py` 재실행 | HistGBM log-R²=-0.040, crystallite_size 성능 하락 (노이즈 영향) |
| `12b_lgbm_baseline.py` 신규 작성 + 실행 | LightGBM log-R²=**+0.032** (신규 추가), SHAP 수치형 필터 |
| `12d_catboost_model.py` 재실행 (best_params 재사용) | CatBoost log-R²=+0.056 (데이터 변화로 19차 +0.087 대비 하락) |
| `12c_gpr_model.py --inducing 512 --epochs 300` 재실행 | DKL-GP log-R²=**+0.235**, epoch 25 조기수렴 4번째 반복 |
| 대시보드 SHAP 2개 타겟 필터 | primary_nm · xrd_nm만, 수치형 피처 한정, 해설 텍스트 업데이트 |
| GitHub 로컬 커밋 설정 | GitPython으로 .git 초기화 + 커밋 (push는 사용자 CMD 실행 필요) |
| junk title 필터 추가 | "Review for", 저널 형식 title 제거 |

### 21차 세션 (2026-06-12)

| 작업 | 결과 |
|------|------|
| **XRD 노이즈 필터 추가** (`12_model.py`) | `between(2, 150)` 별도 적용, 74건 제거, n=3,015→2,947 |
| `main.py --reset --from 3` 재실행 | HistGBM xrd -0.054→**-0.004** (XRD 필터 효과 확인) |
| **DKL-GP early stopping 개선** (`12c_gpr_model.py`) | eval_freq=5, patience=10 → epoch 70 종료(best=ep20), log-R²=**+0.106** |
| `12b_lgbm_baseline.py` 재실행 | LightGBM primary +0.032(동일), xrd **-0.003** |
| `12d_catboost_model.py` 재실행 | CatBoost primary **+0.056**, xrd **+0.068** (n=2,951 — XRD 필터 적용, 20차 +0.011 대비 개선) |
| **CatBoost XRD importance 추가** (`12d_catboost_model.py`) | 루프로 primary+xrd 둘 다 저장, `catboost_importance_crystallite_size_xrd_nm.png` 신규 |
| **대시보드 수치 상관관계 히트맵 개선** (`13_dashboard.py`) | Excel→CSV 전환, BET 제거, Ce농도·합성부피·건조온도 추가 (10개 컬럼) |
| **대시보드 CatBoost 4열 그리드 레이아웃** | Importance+SHAP × 2타겟 나란히 표시 |
| **역설계 목표 갱신** (`12d_targeted_design.py`) | 20/40/50nm → **10/30/60nm**, 75%CI → **95%CI** (Q2.5/Q97.5) |

### 22차 세션 (2026-06-15)

| 작업 | 결과 |
|------|------|
| **DKL-GP top-K 체크포인트 + T_max=100** (`12c_gpr_model.py`) | val/test epoch 불일치 해결, ep30 선택 → log-R²=**+0.364** (log-R² 역대 최고) |
| **synthesis_method enum 14→20 확장** (`4_extract_targeted.py`) | impregnation, electrodeposition, flame_spray, deposition_precipitation, microemulsion, green_synthesis 추가 |
| **ce_precursor 설명 개선** (`4_extract_targeted.py`) | Ce 화합물만 추출, 도펀트/지지체 산화물 명시 제외 |
| `4_extract_targeted.py --reset` 재실행 | synthesis_method +34행(잔여 5), unidentified_method **469→33행** |
| **데이터 품질 필터 Section 8b 추가** (`8_normalize_data.py`) | chelating_agent 30건·capping_agent 7건·atmosphere CSV 821건·ph>14 5건·ce>15M 4건·mineralizer>30M 2건 제거 |
| **12_model.py morphology OOM 수정** | try-except MemoryError 추가 → 이후 역설계·능동학습·history저장 정상 실행 |
| **대시보드 particle_size 채움률 수정** (`13_dashboard.py`) | particle_size_primary_nm = TEM OR SEM 합산으로 계산, 개별 TEM/SEM 표시 삭제 |
| 전체 ML 재실행 (22차 품질필터 후) | HistGBM -0.040, LightGBM **+0.027**, CatBoost **+0.061**, DKL-GP **+0.364** |
| `performance_history.json` 수동 업데이트 | 22차 전 모델(HistGBM·LightGBM·CatBoost·DKL-GP) 결과 반영 |

### 23차 세션 (2026-06-16)

| 작업 | 결과 |
|------|------|
| **비세리아 논문 정밀 필터링** (`filter_offtopic_papers.py` 신규) | OpenAlex References에만 CeO2 언급된 논문 제거. 3단계 필터 구현 |
| 필터 실행 결과 | Excel **7,219 → 3,860편** (3,359편 제거), CSV **8,185 → 6,403행** |
| `main.py --reset --from 3` + 전체 ML 재학습 | HistGBM **+0.006**, LightGBM **+0.087**, CatBoost **+0.092**, DKL-GP **+0.277** (MAE 28.22nm) |

### 24차 세션 (2026-06-16)

| 작업 | 결과 |
|------|------|
| **ML 진단 스크립트 작성+실행** (`diagnose_ml.py` 신규) | 5개 진단: 동일split/노이즈천장/baseline/구간잔차/TEM-SEM bias |
| **DIAG-1 동일 split 검증** | HistGBM 동일split=+0.077 vs 5-fold=+0.006 (+0.071 차). DKL-GP +0.277 우위 실질적 (5-fold 등가 ≈ +0.22) |
| **DIAG-2 노이즈 천장** | method+anion+temp 천장 R²=**+0.348**. DKL-GP는 천장의 **79.6%** 도달 → 데이터 한계 |
| **DIAG-3 baseline ablation** | method-mean=+0.011, Ridge=+0.029 vs CatBoost 32피처=+0.092. 피처 기여 +0.081 확인 |
| **DIAG-5 구간별 잔차** | 0–20nm MAPE=198%, 20–50nm MAPE=47%, 50+nm MAPE=78%. 구간 내 정밀 예측 불가 → 대분류 수준 |
| **DIAG-6 TEM vs SEM bias** | TEM 중앙값 11.5nm vs SEM 30.0nm (격차 -18.5nm — 주로 선택편향). 동일DOI 쌍은 -4.5nm |
| **`12_model.py` 불필요 코드 제거** | `build_quantile_pipeline`, `evaluate_per_method`, `suggest_experiments_size` 삭제 |
| **`13_dashboard.py` 능동학습 탭 정리** | HistGBM Q10/Q90 섹션 제거, DKL-GP σ 기반으로 단일화 |

### 25차 세션 (2026-06-21)

| 작업 | 결과 |
|------|------|
| **`particle_size_source` 피처 추가** (`12_model.py`) | CATEGORICAL_FEATURES에 추가, 피처 수 32→**33개** (12 범주형) |
| **`8_normalize_data.py` Section 8c 추가** | `particle_size_primary_nm` 있고 `particle_size_source` 없는 157행 백필 (TEM+137, SEM+20) |
| **`5_table_extract.py` 수정** | composite 재계산 시 `particle_size_source` 동기화 누락 버그 수정 |
| **전체 ML 재학습** (HistGBM + LightGBM + CatBoost) | HistGBM **+0.047**, LightGBM **+0.106**, CatBoost **+0.130** (tabular 역대 최고) |
| XRD 성능 변화 | HistGBM +0.012, LightGBM +0.004, CatBoost **+0.075** (개선) |
| **DKL-GP 재학습** (`12c_gpr_model.py`, ep75 조기종료→ep30 선택) | log-R²=**+0.290** (23차 +0.277 → +0.013), MAE=**28.03nm** (역대 최저 갱신) |

### 26차 세션 (2026-06-22)

| 작업 | 결과 |
|------|------|
| **`2_extract.py` 전면 재작성** | function calling `strict=True` + CRITICAL ACCURACY RULES(A~F) 추가, max_chars 12k→16k, max_tokens 2500→4096, ThreadPoolExecutor(20workers) |
| 재추출 결과 | **8,819 샘플** (25차 6,403 → +2,416, +37.7%), 오류 1건 (2,879편 처리) |
| particle_size 커버리지 | **48.4%** (4,249/8,819) — 5_table_extract 후 25차 43.8% → +4.6%p |
| **전체 파이프라인 재실행** (`main.py --reset --from 2`) | Stage 2~4 완료. unidentified_method 363행 (more accurate extraction) |
| **HistGBM 재학습** | primary_nm **-0.031** (n=4,249), xrd **+0.006** (n=3,148) — n 증가, R² 일시 하락 |
| **LightGBM 재학습** | primary_nm **+0.023** (n=4,249), xrd **+0.024** (n=3,148) |
| **CatBoost --tune** (25차 데이터) | Optuna 60회: depth=9, iter=636, lr=0.034 → **신규 best_params.json 갱신** |
| **CatBoost 재학습** (신규 params) | primary_nm **+0.132** (n=4,259), xrd **+0.107** (n=3,157, +0.032 개선) |
| DKL-GP 재학습 | 미완 (메모리 확보 후 재실행 필요) |

### 27차 세션 (2026-06-23)

| 작업 | 결과 |
|------|------|
| **DKL-GP 26차 재학습** (`12c_gpr_model.py`, n=4,249) | ep75 조기종료→ep25 선택, log-R²=**+0.321** (역대 최고 갱신), MAE=**25.37nm** (역대 최저) |
| **CatBoost --tune** (26차 데이터 n=4,259) | Optuna 60회: depth=8, iter=669, lr=0.02444 → **신규 best_params.json 갱신** |
| **CatBoost 재학습** (신규 params) | primary_nm **+0.138** (+0.006), xrd **+0.126** (+0.019 추가 개선) |

---

## 미완료 항목 (우선순위 순)

1. **[저우선]** unidentified_method 363행 원인 분석 — 26차 재추출 후 363행 발생 (25차 33행). 원인 파악 후 재추출 검토
2. **[저우선]** Task Scheduler `setup_auto.py` + 데스크탑 아이콘 `launcher.bat`
3. **[저우선]** GitHub push — 사용자가 CMD에서 직접 실행 필요:
   ```
   cd "d:\머신러닝 교육\ceria_pipeline_data"
   git remote add origin https://github.com/souljuhur/ceria-pipeline-data.git
   git push -u origin main
   ```

---

## 월간 자동화 (run_weekly.py)

매월 1일 09:00 실행 (2026-08-01부터 시작). 수동 실행도 가능.
```bash
python run_weekly.py
```
동작: OpenAlex 신규 논문 수집 → Excel 추가 → OA PDF 다운로드 → 후처리 → ML 재학습
- OpenAlex API: `primary_location.source.display_name` 사용 (`host_venue` 폐기됨)
- 상태 파일: `output/weekly_state.json`
- 로그: `output/logs/monthly_scheduler.log`
- Task Scheduler: `CeriaPipelineMonthly` 등록 완료 (setup_auto.py)
  - 다음 실행: 2026-08-01 09:00
  - 관리: `python setup_auto.py --status / --remove`
