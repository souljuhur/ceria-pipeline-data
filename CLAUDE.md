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
├── run_weekly.py        월간 자동화 (매월 1일, 별도 실행)
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
├── 4_extract_targeted.py  핵심 15필드 집중 재추출 (병렬 20workers, 29차 13→15)
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
├── audit_extraction_accuracy.py 추출 정확도 자동 감사 (32차 신규) — 재추출 후 상시 실행
│                                Tier1(무료,전수) 원문대조 / Tier2(GPT 샘플) 의미검증
│                                `4_extract_targeted.py` 완료 후 자동 실행 (--skip-audit로 생략)
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
│   ├── sample_extraction_cache.json          2_extract.py 추출 캐시
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

## 현재 진행 상황 (2026-07-16 기준 — 34차 세션 완료)

> ⚠️ **논문 수집 중단**: 0_collect.py, 0_merge_new.py, run_weekly.py — 별도 지시 전까지 실행 금지

| 항목 | 수치 |
|------|------|
| 총 논문 (수집) | 7,278편 → **3,860편** (23차 비세리아 필터링 후: 3,359편 제거) |
| 전문(full text) 보유 | **2,879편** (text/ 기준, 필터 후) — 32차: 손상 1,954개 파일 PyMuPDF로 재추출(내용 갱신, 편수 동일) |
| PDF 파일 | **4,161개** (pdf/ 폴더 — 필터 대상 외) |
| GPT 추출 완료 | **2,879편** (26차 2_extract.py 전면 재작성 후) |
| 추출 샘플 수 | **8,819행** (26차 재추출 — 25차 6,403 → +2,416) |
| 1차 입자크기 커버리지 (TEM+SEM) | **48.4%** (4,249/8,819 valid rows) ← 26차 |
| crystallite_size_xrd_nm 샘플 수 | **n=3,586~3,595** (32차 재추출 후 — 29차 3,421 → +165, 모델별 상이) |
| ML 모델 피처 수 | **33개** (21 수치 + **12 범주형**) |
| ML 모델 R² (primary_nm, HistGBM) | **-0.050** (MAE=28.88nm, n=4249) ← **32차** (31차 -0.063 대비 개선) |
| ML 모델 R² (primary_nm, LightGBM) | **+0.018** (MAE=28.41nm, n=4249) ← **34차 재실행** (31차 +0.016 대비 거의 동일) |
| ML 모델 R² (primary_nm, CatBoost) | **+0.123** (MAE=26.76nm, n=4259) ← **34차 `--tune` 재탐색 완료** (32차 +0.107 대비 개선, 60회 탐색·9시간56분) |
| ML 모델 R² (primary_nm, DKL-GP) | **+0.072** (MAE=24.70nm, PICP=0.821, n=4249) ← **34차 재학습**(시드 고정 후) — 32차 +0.020 대비 큰 폭 회복, 31차(+0.072)와 거의 동일값 |
| ML 모델 R² (xrd_nm, HistGBM) | **+0.0017** (MAE=10.62nm, n=3586) ← **32차** (거의 동일) |
| ML 모델 R² (xrd_nm, LightGBM) | **+0.052** (MAE=10.41nm, n=3586) ← **34차 재실행** (31차 +0.077 대비 하락) |
| ML 모델 R² (xrd_nm, CatBoost) | **+0.099** (MAE=10.20nm, n=3595) ← **34차 `--tune` 재탐색 완료** (32차 +0.085 대비 개선) |
| unidentified_method 행 수 | **286행** (28차 Section 1c 77행 복구 — 26차 363행) |
| ce_precursor Non-Ce 정제 | **214행 NULL 처리** (28차 Section 1d — 도펀트·식물추출물 등 오분류 제거) |
| ce_precursor="CeO2" 오분류 | **12.3% → 3.5%** (32차 — 프롬프트 화이트리스트 버그 수정 + 의심값 재추출) |
| 추출 정확도 감사 tier1 ce_precursor flag | **41.6% → 23.4%** (34차 — 명칭↔화학식 동치 매칭 추가, 3,413→1,924건. 표본 검토로 대부분 과탐 확인) |
| 추출 정확도 감사 (33차, tier2 GPT 20편) | 14건 flag → 원문대조 결과 **13건 오탐**(감사관 자기모순/과탐), 실제 이슈 후보 1건(다중조건 논문 값 혼선) |
| 추출 필드 수 | **15개** (29차: synthesis_time_h·morphology 추가) |
| Excel 열 수 | **48열** (11_format_excel.py 기준) |

### 최신 모델 성능 비교 (32차 기준, particle_size_primary_nm)

| 모델 | log-R² | nm-MAE | RMSE | MdAE | n | vs 31차 |
|------|--------|--------|------|------|---|---------|
| HistGBM | **-0.050** | 28.88 | 67.31 | 9.37 | 4249 | **+0.013** |
| LightGBM (12b) | +0.018 | 28.41 | 66.45 | 8.84 | 4249 | **34차 재실행, +0.002** |
| CatBoost | **+0.123** | 26.76 | 66.00 | 8.27 | 4259 | **34차 `--tune` 재탐색 완료, 32차 대비 +0.016** |
| DKL-GP (inducing=512) | **+0.072** | 24.70 | 63.89 | 7.72 | 4249 | **거의 동일** (34차 시드 고정 재학습, 32차 +0.020 대비 +0.052 회복) |

> **34차 (2026-07-15~16)**: 32차 데이터로 LightGBM(12b)·LightGBM 역설계(12d_targeted_design) 재실행 —
> primary_nm log-R² +0.018(거의 동일), **xrd_nm +0.052(31차 +0.077 대비 하락)**. `audit_extraction_accuracy.py`
> tier1 매칭 로직에 화학명↔화학식 동치 검사 추가(nitrate/chloride/sulfate/hexahydrate 등) →
> ce_precursor flag **41.6%→23.4%**로 감소(표본 검토: 28건 중 11건 심층 확인, 10건이 "cerium nitrate
> hexahydrate" 같은 산문 화학명을 GPT가 정확히 formula로 변환한 것이 원인인 과탐, 1건만 실제 의심).
> **CatBoost `--tune` 32차 데이터 재탐색 완료** (60회, 실소요 9시간56분 — 트라이얼당 5~14분으로 예상보다
> 오래 걸림): primary_nm **+0.107→+0.123**, xrd_nm **+0.085→+0.099** 둘 다 개선. 신규 best_params:
> iterations=740, lr=0.02159, depth=6(29차 depth=9보다 얕음), l2_leaf_reg=2.169, random_strength=1.110,
> bagging_temperature=1.545, border_count=254 — `catboost_best_params.json` 갱신됨.
> **DKL-GP: `torch.manual_seed(42)` 시드 고정 후 재학습 → log-R²=+0.072 (32차 +0.020 대비 회복, 31차 +0.072와
> 거의 동일값)**. 기존 코드는 NN 초기화·유도점 초기화·DataLoader 셔플이 전혀 시드 고정되지 않아 동일 데이터로도
> 재실행 시 log-R²가 크게 달라질 수 있었음(val set n=661로 작고 기저 R²도 0에 가까워 노이즈 민감도 높음) —
> **시드를 고정하자 27차→32차 3연속 하락의 "하락"이 재현되지 않고 31차 수준으로 돌아온 것으로 보아, 32차의
> +0.020은 데이터 품질 변화가 아니라 학습 노이즈(운 나쁜 시드)였을 가능성이 매우 높음**. epoch 20에서 best
> (val-MAE=0.8409), ep70 조기종료 → top-3 버퍼 중 ep50 선택. PICP(90%)=0.821.
>
> **32차 (2026-07-09~10, 커밋 885f6aa)**: `ce_precursor="CeO2"` 오분류 버그(프롬프트가 CeO2를 유효 전구체
> 예시로 잘못 포함 — 최종 생성물명이 전구체로 오추출됨, 12.3%→3.5% 개선) + PDF 텍스트 손상(pdfplumber
> `(cid:N)` 깨짐, 코퍼스 36%→0%) 근본 원인 수정. 손상 텍스트 1,954개 파일 PyMuPDF로 재추출 후 전 모델
> 재학습. **HistGBM은 개선**(-0.063→-0.050)했으나 **DKL-GP는 큰 폭 하락**(+0.072→+0.020),
> CatBoost도 소폭 하락(+0.123→+0.107 — best_params.json은 6/28 데이터 기준 그대로 사용, 재탐색 안 함).
> 텍스트/전구체 품질 자체는 개선됐으나 ML 지표는 아직 일관되게 반영되지 않음 — 34차에서 DKL-GP 시드
> 미고정 문제를 유력 원인으로 특정(위 34차 항목 참고).
>
> **31차**: 30차 버그 수정(safe_encode collision·fold 내부 인코딩·val-only 평가·농도 필터) 반영한
> 전 모델 재학습. LightGBM +0.016(+0.003), DKL-GP +0.072(+0.019) 소폭 개선.
> HistGBM·CatBoost는 동일 수준 유지. DKL-GP ep70 조기종료→ep30 선택(val-MAE=0.8699 @ep20).

> **29차**: `4_extract_targeted.py --reset` 재추출 (2,547편, 8분) — morphology +150행, synthesis_time_h +50행,
> crystallite_size_xrd_nm +273행(3,148→3,421). 전 모델 재학습 + CatBoost --tune (60회).
> 성능이 27차 대비 전반적 하락: ce_precursor 정제(214행 NULL) 및 데이터 분포 변화가 원인으로 추정.
> DKL-GP val-MAE=0.8560(ep20)으로 val 기준은 개선됐으나 log-R²는 +0.053으로 큰 폭 하락.

> **27차**: DKL-GP 26차 재학습 완료 (n=4,249, ep75 조기종료→ep25 선택). log-R² **+0.321 (역대 최고)**,
> MAE **25.37nm (전체 모델 최저)**. CatBoost --tune 26차 데이터 재탐색 → depth=8 신규 best_params,
> log-R²=+0.138로 소폭 개선.

### 32차 crystallite_size_xrd_nm 성능

| 모델 | 31차 | 32차/34차 | n | 비고 |
|------|------|------|---|------|
| HistGBM | +0.002 | **+0.0017** | 3,586 | 거의 동일, n +165 (PDF 재추출 효과, 32차) |
| LightGBM | +0.077 | **+0.052** | 3,586 | **34차 재실행 — 하락, 원인 규명 완료(아래 참고, fold 구성 민감도)** |
| CatBoost | +0.062 | **+0.099** | 3,595 | **34차 `--tune` 재탐색 완료 — 개선** (32차 +0.085 대비 +0.014) |

> **XRD 노이즈 필터 효과** (21차 기준): `12_model.py`에 `between(2, 150)` 필터 → 26차 72건 제거
> 물리적 근거: Scherrer equation 유효 범위 2~150nm (< 2nm 불가, > 150nm Scherrer 한계 초과)

> **LightGBM xrd_nm 34차 하락 원인 규명** — `12b_lgbm_baseline.py`의 `GroupKFold(n_splits=5)`는
> `shuffle=False`(기본값)로 논문(DOI) 그룹을 크기순 그리디 배분하는 **완전 결정론적** 알고리즘이라
> DKL-GP처럼 "시드 미고정" 문제는 아님. 대신 **논문 1,144편 규모에서 log-R²≈0인 약한 신호를 5-fold로
> 나누다 보니, 어떤 논문이 우연히 검증 폴드에 포함되는지에 따라 결과가 크게 흔들리는 구조적 불안정성**이
> 원인으로 확인됨: 동일한 34차 데이터에 `shuffle=True`로 20가지 다른 fold 구성을 시도한 결과
> log-R²가 **-0.016~+0.069(스프레드 0.084, 평균 0.032, std 0.020)**로 널뛰었고, 34차 기본값(+0.052)은
> 이 정상 변동 범위 안에 있었음. 31차(+0.077) 대비 하락폭(0.025)은 이 스프레드(0.084)보다 훨씬 작아
> **데이터 품질 저하가 아니라 fold 구성 노이즈**로 결론. 진단 스크립트는 세션 스크래치패드에만 저장(파이프라인
> 미포함). 개선하려면 `evaluate_lgbm()`의 GroupKFold를 여러 시드로 반복해 평균±표준편차로 보고하는 방식
> 권장(현재는 1회 CV 결과만 보고 — DKL-GP 사례와 마찬가지로 이런 소규모·약신호 타겟은 단일 실행값의
> 세션 간 비교가 오해를 부를 수 있음).

> ※ DKL-GP 34차: `torch.manual_seed(42)` 시드 고정 후 재학습. ep20 best(val-MAE=0.8409), ep70 조기종료
>    → top-3 버퍼 중 ep50 선택(val-MAE=0.8563) → log-R²=**+0.072**, 실측 MAE=24.70nm, PICP(90%)=0.821.
>    **32차(+0.020) 대비 +0.052 회복, 31차(+0.072)와 거의 동일값** — 시드 고정만으로 27차→32차 3연속
>    하락의 "하락"이 재현되지 않았다는 점에서, 32차의 저조한 값은 데이터 품질 저하가 아니라 학습 노이즈
>    (운 나쁜 초기화/셔플 시드)였을 가능성이 매우 높다는 34차 가설을 뒷받침함.
>
> ※ DKL-GP 32차 (시드 미고정 상태): ep?? 조기종료, val-MAE 기준 선택 → log-R²=**+0.020**, 실측
>    MAE=24.24nm, PICP=0.812. 위 34차 재학습 결과와 비교하면 데이터는 동일한데 시드만 고정해도 결과가
>    크게 달라짐이 확인됨.
>
> ※ DKL-GP 31차: ep70 조기종료(patience=10), top-3 버퍼 중 ep30 선택 → log-R²=**+0.072**
>    val-MAE best=0.8464(ep20). 29차(+0.053) 대비 +0.019 개선 — safe_encode·val-only 수정 효과.
>
> ※ DKL-GP 29차: ep70 조기종료(patience=10), top-3 버퍼 중 ep25 선택 → log-R²=**+0.053**
>    val-MAE best=0.8560(ep20). 27차 대비 큰 폭 하락 — ce_precursor 정제 후 데이터 분포 변화 추정.

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

### 29차 CatBoost --tune 결과 (저장된 최적 파라미터 — catboost_best_params.json)

Optuna 최적 파라미터 (60회 탐색, 29차 데이터 n=4,259 기준): iterations=295, lr=0.06900, depth=9
(이전 27차 파라미터: iterations=669, lr=0.02444, depth=8 — catboost_best_params.json으로 갱신됨)
> 파라미터가 크게 달라진 이유: ce_precursor 정제 후 데이터 분포 변화로 최적점 이동.

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
python 4_extract_targeted.py        # 핵심 15필드 재추출 (--reset, --dry-run)
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

34차 완료 (LightGBM 재실행·audit 매칭 개선·DKL-GP 시드 고정+재학습·CatBoost `--tune` 재탐색 전부 완료).
- 성능 현황: HistGBM **-0.050**(32차) / LightGBM **+0.018**(34차 재실행) / CatBoost **+0.123**(34차 `--tune` 완료) / DKL-GP **+0.072**(34차 재학습)
- 34차 완료: LightGBM(12b)·LightGBM 역설계(12d_targeted_design) 32차 데이터로 재실행 (xrd_nm +0.052로 하락 — 원인 규명 완료: GroupKFold 20시드 재검증 결과 스프레드 0.084로 데이터 품질 문제 아닌 fold 구성 노이즈로 결론)
- 34차 완료: `audit_extraction_accuracy.py` 매칭 로직 개선 — ce_precursor flag 41.6%→**23.4%** (화학명↔화학식 동치 검사 추가)
- 34차 완료: `12c_gpr_model.py`에 `torch.manual_seed(42)` 등 시드 고정 추가 + DKL-GP 재학습 → log-R²=**+0.072**(32차 +0.020 대비 회복, 31차 +0.072와 거의 동일). **결론: 27→32차 3연속 하락은 데이터 품질 저하가 아니라 학습 시드 미고정으로 인한 노이즈였을 가능성이 매우 높음**
- 34차 완료: CatBoost `--tune` 32차 데이터 재탐색 완료 (60회, 실소요 9시간56분 — 예상(2.5~3시간)보다 훨씬 오래 걸림, 트라이얼당 5~14분). primary_nm **+0.107→+0.123**, xrd_nm **+0.085→+0.099** 개선. `catboost_best_params.json` 갱신됨(depth 9→6)
- GitHub: 34차 커밋 완료(`eeccdb2`, `a465354`, gitpython 우회) — push는 여전히 CMD에서 `git push origin main` 실행 필요 (origin 대비 여러 commit ahead)
- CatBoost segfault: 모델 저장 후 cleanup 단계에서 발생 — pkl 파일은 정상, 기능상 문제 없음 (지속 관찰 중)
- **34차 핵심 결론**: DKL-GP(+0.020→+0.072, 시드 미고정)와 LightGBM xrd_nm(+0.052, fold 구성 민감도) 둘 다 "27~34차 성능 하락"이 실제 데이터 품질 저하가 아니라 **평가 방법의 노이즈**였음을 시사. 향후 세션 간 성능 비교 시 log-R² 델타가 ~0.05 미만이면 노이즈 가능성을 먼저 의심할 것 (특히 crystallite_size_xrd_nm, 소규모·약신호 타겟)
- `audit_extraction_accuracy.py` tier1 ce_precursor flag는 34차 매칭 개선으로 41.6%→23.4%까지 감소 — 잔여 23.4%도 상당수 추가 화학명 변형(예: 다른 어순의 ceric ammonium nitrate, 드문 수화물 표기) 과탐일 가능성, 완전 해소는 아님
- 대시보드 사이드바 브랜딩을 그라디언트 카드 스타일로 개선(`13_dashboard.py`), `dashboard.bat`+데스크탑 바로가기 추가 — 사용자 편의 기능, 파이프라인 로직과 무관

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

### safe_encode / encode_cats 설계 원칙 (12b_lgbm_baseline.py, 12d_targeted_design.py)
- **fold 내부 인코딩** (30차 도입): data leakage 방지를 위해 `encode_cats`를 CV 루프 안으로 이동
  ```python
  for tr_idx, val_idx in cv.split(sub, y, groups):
      _tr_enc, _enc_fold = encode_cats(sub.iloc[tr_idx].copy())
      _val_enc           = safe_encode(sub.iloc[val_idx].copy(), _enc_fold)
  ```
- **unknown 처리**: `len(le.classes_)` — 0으로 매핑하면 첫 번째 실제 범주(알파벳 순 최소값)와 충돌 (30차 수정)
  ```python
  unk = len(le.classes_)
  lambda x, _le=le, _known=known, _unk=unk: int(_le.transform([x])[0]) if x in _known else _unk
  ```
  > 람다 클로저 캡처 버그 주의: 루프 변수 `le`, `known`, `unk`는 반드시 기본인자로 바인딩해야 함

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

### ce_precursor 유효성 검증 (8_normalize_data.py — 28차 추가)

`Section 1c`: unidentified_method 행 중 targeted cache에 유효한 synthesis_method가 있으면 복구 (77행 회복).  
`Section 1d`: ce_precursor Non-Ce 화합물 → NULL 처리.

```python
def _is_ce_compound(val) -> bool:
    if pd.isna(val): return False
    s = str(val).strip()
    parts = re.split(r"[;,]", s)
    for p in parts:
        p = p.strip()
        if re.match(r"ce", p, re.IGNORECASE): return True          # Ce로 시작
        if re.search(r"\b(cerium|cerous|ceric)\b", p, re.IGNORECASE): return True
        if re.search(r"\(nh4\)[\d\s]*\[?ce", p, re.IGNORECASE): return True   # (NH4)2Ce...
        if re.search(r"(?<![a-z])ce(?![a-z])", p, re.IGNORECASE): return True  # 단독 Ce
    return False
# 결과: 214행 Non-Ce → NULL (도펀트 전구체, 식물추출물, 귀금속 전구체 등 오분류)
```

**`4_extract_targeted.py` ce_precursor 프롬프트 강화 (28차)**: Ce 화합물만 추출, 아래 제외 명시:
- 도펀트/공금속 염: La, Sm, Gd, Nd, Pr, Eu, Zr, Fe, Ni, Co, Cu, Ti, Sn 등
- 귀금속 전구체: HAuCl4, H2PtCl6, AgNO3 등
- 지지체/기판 산화물: TiO2, ZrO2, SiO2, SnO2, Al2O3 등
- 유기 첨가물/폴리머: PEI, TEMED, cellulose, PVP 등
- 식물/생물 추출물: leaf extract, plant extract 등

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
- **추출 필드 (15개)**: synthesis_method, ce_precursor, solvent, synthesis_temperature_c, ph_synthesis, ce_concentration_M, mineralizer_concentration_M, synthesis_volume_mL, capping_agent, chelating_agent, atmosphere, calcination_temperature_c, crystallite_size_xrd_nm, **synthesis_time_h, morphology** (29차 +2)
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
    ↓ 4_extract_targeted.py (15필드 재추출, 20workers)          [29차 13→15필드]
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
| ceria_samples_merged.csv (ML 기준, 26차 이후) | CSV | **48.4%** (4,249/8,819) | TEM+SEM만, XRD 제외 |
| ceria_synthesis_database.xlsx (Excel paper-level) | Excel | ~8.4% (TEM) | 논문 단위, 다른 지표 |

---

## 버그 수정 통합 이력

| 세션 | 파일 | 버그 | 수정 |
|------|------|------|------|
| 34차 | **12c_gpr_model.py** | `torch.manual_seed` 등 랜덤 시드 미고정 — NN 초기화·유도점 초기화·DataLoader 셔플이 매 실행마다 달라져 동일 데이터로도 log-R²가 크게 변동, 세션 간 성능 비교가 데이터 변화 때문인지 학습 노이즈 때문인지 구분 불가 | `torch.manual_seed(42)` + `np.random.seed(42)` + `torch.cuda.manual_seed_all(42)` 추가 |
| 34차 | **audit_extraction_accuracy.py** | Tier1 `_value_found_in_text()`가 화학식 리터럴 문자열만 대조 — 논문이 "cerium nitrate hexahydrate"처럼 산문 화학명으로 서술하면 GPT가 정확히 표준 화학식으로 변환해도 과탐(false positive) 발생 (ce_precursor flag 41.6%) | `_ce_precursor_alt_match()` 추가 — 음이온(nitrate/chloride/sulfate 등)·수화물(hexahydrate 등) 명칭 동치 검사, flag 41.6%→23.4%로 감소 |
| 32차 | **2_extract.py**, **4_extract_targeted.py** | ce_precursor 스키마 설명에 `CeO2`를 유효 전구체 예시로 포함 — 논문 전체에서 계속 언급되는 최종 생성물명(CeO2)이 시작 시약으로 오추출됨 (ML 데이터셋 12.3% 영향) | 스키마 예시에서 `CeO2` 제거, "CeO2를 기본값으로 추측하지 말 것" 경고 추가 — 사전제작 CeO2 분말을 재용해한 경우만 예외 허용 |
| 32차 | **4_extract_targeted.py** | 기존 ce_precursor="CeO2" 값이 위 버그로 오분류된 채 캐시에 남아 재추출 대상에서 누락됨 | main()에 의심값(`== "CeO2"`) 자동 NULL 초기화 로직 추가 → 재추출 대상 자동 편입 |
| 32차 | **1_download.py** | pdfplumber가 서브셋 폰트 PDF에서 `(cid:N)` 플레이스홀더를 남겨 텍스트 코퍼스의 36%에서 화학식·수치 파싱 방해 | PyMuPDF(fitz)를 1차 추출기로, pdfplumber는 실패 시 폴백으로 전환 |
| 30차 | **2_extract.py** | `print(f"  출력: {OUT_JSONL}")` 가 `if __name__ == "__main__":` 블록 밖(column 0)에 위치 → import 시 항상 실행됨 | 들여쓰기 4칸 추가로 가드 안으로 이동 |
| 30차 | **setup_auto.py** | `PYTHON_EXE = sys.executable` — 잘못된 conda 환경에서 실행 시 Task Scheduler에 base Python 경로가 등록돼 월간 자동화 무음 실패 가능 | `if "envs\\test" not in PYTHON_EXE` 검증 추가, 불일치 시 즉시 SystemExit |
| 30차 | **run_weekly.py** | post_steps 설명 문자열이 `"핵심 13필드 재추출"` — 29차 이후 15필드로 확장됐으나 라벨 미갱신 | `"핵심 15필드 재추출"` 로 수정 |
| 30차 | **12b_lgbm_baseline.py** | `safe_encode`에서 미지 범주를 `0`으로 매핑 — `LabelEncoder` 정렬상 첫 번째 실제 범주(예: `"air"`)와 정수 충돌, OOF 예측 무음 오염 | unknown을 `len(le.classes_)` (기존 범위 밖 정수)로 변경; 람다 클로저 캡처 버그(`le`, `known`, `unk` 기본인자 바인딩)도 함께 수정 |
| 30차 | **12d_targeted_design.py** | 동일 — `safe_encode` unknown → `0` | 동일 수정 적용 |
| 29차 | **7_calc_completeness.py** | `_TMP = _PATH + ".tmp"` — pandas ExcelWriter가 `.tmp` 확장자를 유효하지 않은 엔진으로 인식 (`ValueError: Invalid extension`) | `_TMP = _PATH + "_tmp.xlsx"` 로 변경 |
| 29차 | **9_add_tags.py** | 동일 — `_tmp_path = EXCEL_PATH + ".tmp"` | `_tmp_path = EXCEL_PATH + "_tmp.xlsx"` 로 변경 |
| 28차 | **8_normalize_data.py** | unidentified_method 363행 — targeted cache에 유효 method 있어도 복구 안 됨 (`_is_empty()`가 "other"를 비어있다고 보지 않음) | Section 1c 추가: cache 조회로 77행 복구 (363→286) |
| 28차 | **8_normalize_data.py** | ce_precursor에 도펀트 전구체·식물추출물 등 비세리아 물질 혼입 (265/8,791 행, ~3%) | Section 1d `_is_ce_compound()` 추가: 214행 NULL 처리 |
| 28차 | **4_extract_targeted.py** | ce_precursor 프롬프트 불충분 — 도펀트/귀금속/지지체/유기첨가물 제외 명시 없음 | ce_precursor 스키마 설명 강화 (5개 유형 명시 제외) |
| 28차 | **.git 권한** | CMD/Bash에서 `git add` 실패: `Unable to create index.lock: Permission denied` (Windows ACL) | gitpython `repo.index.add()` + `repo.index.commit()`으로 우회 커밋 (e28b5c6b) |
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

### 7~24차 세션 요약 (2026-06-08~16) — 파이프라인 구축 단계

> 세션별 원본 상세 기록은 git 이력(`git log`)과 이전 CLAUDE.md 커밋에서 확인 가능. 아래는 구간별 핵심 성과만 압축.

| 구간 | 핵심 성과 |
|------|----------|
| 7~11차 | Sci-Hub 수집 완료(전문 962편), PDF 표 추출(5,953행), Excel 손상 복구, **스크립트 번호 체계(1~13) 도입 + main.py 4-Stage 구조 완성** |
| 12~14차 | 논문 수집 4,388→**7,278편** 확대(`0_collect.py` 신규), `4_extract_targeted.py` 20workers 병렬화(1~2시간→10~15분), PDF 다운로드 74.5%(5,426편) 완료 |
| 15~18차 | 추출 필드 8→13개 확장, **DKL-GP·CatBoost·LightGBM 신규 도입**(log-R² 최초 양수 달성 — CatBoost +0.077, DKL-GP +0.300), 대시보드 ML탭·역설계 UI·`performance_history.json` 자동화 구축 |
| 19~20차 | **논문 수집 중단 결정**(7,278편으로 확정, 이후 품질 개선에 집중), OpenAI function calling(`strict=True`) 전환으로 수치 타입 보장, CatBoost Optuna 튜닝 도입, GitHub 로컬 커밋 설정 |
| 21~22차 | **XRD 노이즈 필터**(2~150nm) 도입, **DKL-GP top-K 체크포인트 + T_max=100**(log-R² 역대최고 +0.364 달성), 데이터 품질 필터(Section 8b), morphology OOM 수정 |
| 23~24차 | **비세리아 논문 정밀 필터링**(`filter_offtopic_papers.py` 신규 — Excel 7,219→**3,860편**), `diagnose_ml.py` 5종 진단 신설 — DKL-GP가 노이즈 천장(R²=+0.348)의 79.6%에 도달해 있음을 확인(데이터 자체의 예측 한계 규명) |

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

### 29차 세션 (2026-06-29)

| 작업 | 결과 |
|------|------|
| **`4_extract_targeted.py --reset` 재추출** | 2,547편, 8.1분 — morphology **+150행**, synthesis_time_h **+50행**, crystallite_size_xrd_nm **+52행** |
| **버그 수정 2건** | `7_calc_completeness.py`, `9_add_tags.py`: `.tmp` → `_tmp.xlsx` (ExcelWriter 확장자 오류) |
| **`main.py --reset --from 3` 재실행** | Stage 3~4 완료. crystallite_size_xrd_nm n=3,148→**3,421** (+273) |
| **HistGBM 재학습** | primary_nm **-0.063** (MAE=28.70, n=4,249) |
| **LightGBM 재학습** | primary_nm **+0.013**, xrd_nm **+0.077** (개선) |
| **CatBoost --tune** (60회, ~3시간) | 신규 params: iter=295, lr=0.069, depth=9. primary_nm **+0.123** |
| **DKL-GP 재학습** | ep70 조기종료→ep25 선택, log-R²=**+0.053** (27차 +0.321 대비 하락) |

### 30차 세션 (2026-07-07)

| 작업 | 결과 |
|------|------|
| **멀티-에이전트 코드 리뷰** | 8개 각도 × 병렬 분석 — CONFIRMED 2건·PLAUSIBLE 3건·REFUTED 3건 |
| **`pipeline.py` / `docs/PROJECT_MAP.md` 삭제** | 구버전 노트북식 파이프라인·구버전 문서 정리 |
| **`13_dashboard.py` Streamlit API 업데이트** | `width="stretch"` → `use_container_width=True` (전체 적용) |
| **`1_download.py` 컬럼명 수정** | `open_access_url` → `oa_url` (Excel 실제 컬럼명과 일치, 기존 bug fix) |
| **`12_model.py` 피처 중요도 개선** | 전체 데이터 대신 첫 fold val set 기준으로 계산 (train bias 방지) |
| **`12b_lgbm_baseline.py` fold 내부 인코딩** | `encode_cats`를 fold 안으로 이동, `safe_encode` 적용 (data leakage 방지) |
| **`12c_gpr_model.py` val-only 평가 전환** | 전체 데이터 대신 val_idx(15%)만으로 R²·MAE·PICP 계산 (train 편향 제거) |
| **`12d_targeted_design.py` fold 내부 인코딩** | 동일 leakage 방지 적용 |
| **`8_normalize_data.py` 농도 범위 조정** | ce_concentration_M: >15M → 0.001~5M / mineralizer: >30M → 0.001~15M |
| **`2_extract.py` 모듈화 리팩터링** | 실행 코드 전체를 `if __name__ == "__main__":` 가드 안으로 이동 |
| **`run_weekly.py` 타임아웃 확장 + 단계 추가** | `4_extract_targeted.py`·`5_table_extract.py` 자동화 포함, timeout 900→1800s |
| **버그 수정 5건** (30차 신규) | 아래 버그 수정 이력 참조 |

### 31차 세션 (2026-07-07)

| 작업 | 결과 |
|------|------|
| **전 모델 재학습** (30차 버그 수정 반영) | `main.py --reset --from 3` → HistGBM + LightGBM + CatBoost + DKL-GP |
| **LightGBM 개선** | primary +0.016 (29차 +0.013 → +0.003), safe_encode fold 내부 인코딩 효과 |
| **DKL-GP 개선** | primary +0.072 (29차 +0.053 → +0.019), val-only 평가 + safe_encode 수정 효과 |
| **HistGBM·CatBoost** | 동일 수준 유지 (primary -0.063 / +0.123, xrd +0.002 / +0.062) |
| **CatBoost segfault** | 모든 pkl 저장 완료 후 cleanup 단계에서 발생 — 모델 자체 정상 |

### 32차 세션 (2026-07-09~10, 커밋 885f6aa)

| 작업 | 결과 |
|------|------|
| **ce_precursor="CeO2" 오분류 근본 원인 수정** (`2_extract.py`, `4_extract_targeted.py`) | 프롬프트 화이트리스트 버그(최종 생성물명을 전구체로 오추출) 수정, 의심값 자동 NULL 재추출 로직 추가 → **12.3%→3.5%** |
| **PDF 텍스트 손상 근본 원인 수정** (`1_download.py`) | pdfplumber `(cid:N)` 깨짐 → PyMuPDF 우선 추출로 전환, 코퍼스 영향 **36%→0%** |
| 손상 텍스트 재추출 | text/ 1,954개 파일 PyMuPDF로 재추출 |
| `4_extract_targeted.py --reset` + 전 모델 재학습 | crystallite_size_xrd_nm n=3,421→**3,586~3,595**(+165) |
| **HistGBM** | primary_nm **-0.050** (31차 -0.063 대비 +0.013 개선) |
| **CatBoost** (best_params 재탐색 없이 재사용) | primary_nm **+0.107** (31차 +0.123 대비 -0.016), xrd **+0.085** (31차 +0.062 대비 개선) |
| **DKL-GP** | primary_nm **+0.020** (31차 +0.072 대비 -0.052 큰 폭 하락) — 원인 미조사 |
| LightGBM (12b), LightGBM 역설계 (12d_targeted_design) | 미재실행 (31차 값 유지) |

### 33차 세션 (2026-07-13)

| 작업 | 결과 |
|------|------|
| **32차 미문서화 작업 검증** | git log·performance_history.json·pipeline_state.json 대조로 32차(커밋 885f6aa) 성능 변화 확인 및 본 문서 반영 |
| **`audit_extraction_accuracy.py` 신규 도구 커밋** | Tier1(원문대조 전수) + Tier2(GPT 샘플 의미검증) 2단계 감사, `4_extract_targeted.py`에 자동 실행 훅 추가(`--skip-audit`로 생략 가능) |
| **Tier1 결과 확인** | ce_precursor 41.6%(3,413/8,210) 원문 미검출 flag — 정규화 매칭 한계로 인한 과탐 가능성, 미확정 |
| **Tier2 결과 수동 검증 (원문 대조)** | GPT flag 14건 중 **13건 오탐**(감사관 자체 계산·인정과 모순되는 flag 다수) 확인, 실제 검토 필요 1건(다중 온도조건 논문에서 최적조건 아닌 중간값 추출) 확정 |
| **`.gitignore`에 `text_backup_pdfplumber/` 추가** | PyMuPDF 전환 전 백업본(103MB, 1,954개 파일) 커밋 방지 |
| **커밋** (`b40ce1c1`) | `.gitignore`, `4_extract_targeted.py`, `audit_extraction_accuracy.py` — push는 미실행 (CMD 필요) |

### 34차 세션 (2026-07-15)

| 작업 | 결과 |
|------|------|
| **LightGBM(12b_lgbm_baseline.py) 32차 데이터 재실행** | primary_nm log-R²=**+0.018**(31차 +0.016과 거의 동일), xrd_nm log-R²=**+0.052**(31차 +0.077 대비 하락 — 원인은 아래에서 규명) |
| **LightGBM 역설계(12d_targeted_design.py) 재실행** | GroupKFold log-R²=+0.062, 10/30/60nm 역설계 조건 갱신 (targeted_design_*.csv) |
| **`audit_extraction_accuracy.py` tier1 ce_precursor 표본 검토** | 28건 무작위 표본 중 11건 원문 심층 대조 — 10건이 "cerium nitrate hexahydrate" 등 산문 화학명을 GPT가 정확한 화학식으로 변환한 것이 원인인 **과탐**, 1건만 실제 의심(합성 서술 없이 기성 nanoceria 사용 논문) |
| **`_ce_precursor_alt_match()` 매칭 로직 추가** | 음이온(nitrate/chloride/sulfate/acetate/carbonate/oxalate/hydroxide/acetylacetonate)·수화물(mono~deca)·ammonium ceric nitrate 명칭↔화학식 동치 검사 → ce_precursor flag **41.6%→23.4%** (3,413→1,924건) |
| **`12c_gpr_model.py` 랜덤 시드 고정 + DKL-GP 재학습** | `torch.manual_seed(42)` 등 추가 후 재학습 → log-R²=**+0.072**(32차 +0.020 대비 +0.052 회복, 31차 +0.072와 거의 동일). 27→32차 3연속 하락이 데이터 품질 문제가 아니라 **학습 시드 미고정으로 인한 노이즈**였음을 강력히 뒷받침 |
| **CatBoost `--tune` 32차 데이터 재탐색** (완료) | 60회 Optuna 탐색, 실소요 **9시간56분**(트라이얼당 5~14분, 예상보다 오래 걸림). primary_nm **+0.107→+0.123**, xrd_nm **+0.085→+0.099** 둘 다 개선. 신규 params: iterations=740, lr=0.0216, depth=6 (29차 depth=9보다 얕음) |
| **LightGBM xrd_nm 34차 하락 원인 규명** | 동일 34차 데이터에 `GroupKFold(shuffle=True)` 20가지 시드로 재검증 → log-R² **-0.016~+0.069(스프레드 0.084)**로 요동. 31차↔34차 차이(0.025)가 이 스프레드보다 작아 **데이터 품질 저하가 아니라 fold 구성 노이즈**로 결론 (DKL-GP와 결론은 같으나 메커니즘은 다름 — 학습 시드가 아니라 소규모·약신호 타겟의 GroupKFold 그룹 배분 민감도) |
| **대시보드 사이드바 브랜딩 개선** (`13_dashboard.py`) | 사용자 요청으로 `st.title` 대신 그라디언트 카드 스타일(아이콘 배지 + CeO₂ 화학식 첨자 + 서브타이틀) 적용 |
| **`dashboard.bat` + 데스크탑 바로가기 추가** | 메뉴 선택 없이 더블클릭으로 바로 대시보드 실행 (`launcher.bat`과 별도, 대시보드 전용) |
| GitHub push | 미실행 (CMD 필요, 사용자 안내) |

---

## 미완료 항목 (우선순위 순)

1. **[검토]** audit tier1 잔여 23.4% ce_precursor flag — 34차 매칭 개선 이후에도 남은 flag가 추가 화학명 변형(어순이 다른 ammonium cerium nitrate, 드문 수화물 표기 등) 때문인 과탐인지, 진짜 오류인지 추가 표본 검토 필요.
2. **[저우선]** GitHub push — CMD에서 직접 실행 필요:
   ```cmd
   cd "d:\머신러닝 교육\ceria_pipeline_data"
   git push origin main
   ```
   > 주의: `git add/commit`은 index.lock Permission denied → **gitpython 사용 권장**
   > `python -c "import git; r=git.Repo('.'); r.index.add([...]); r.index.commit('msg')"`

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
