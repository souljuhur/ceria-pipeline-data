# CeO2 파이프라인 작업일지

> 최신 항목이 위에 온다. 날짜는 YYYY-MM-DD 형식.

---

## 2026-06-05

### [1] 문헌 수집 triage 업그레이드 (`stage1_collection_upgrade_guide.md` 적용)
- `pipeline.py` — `OPENALEX_FIELDS`에 `best_oa_location` 추가 (더 정확한 PDF URL)
- `pipeline.py` — `METHOD_KEYWORDS` / `MORPHOLOGY_KEYWORDS` 사전 + `_tag_keywords()` 함수 추가
- `pipeline.py` — 3개 파서 모두에 `is_oa`, `oa_status`, `tagged_methods`, `tagged_morphologies` 컬럼 추가
- `pipeline.py` — triage 태그 **12종으로 확장**: `tagged_mineralizer`, `tagged_additives`, `tagged_solvent`, `tagged_assist`, `tagged_dopant` 5종 추가
- `pipeline.py` — OpenAlex 요청 **지수 백오프** (최대 4회 재시도, 429/5xx 자동 대기) + polite pool User-Agent 헤더
- `add_triage_tags.py` 신규 작성 — 기존 `ceria_synthesis_database.xlsx` 4,388편에 태그 컬럼 **사후 추가** 스크립트

### [2] 프로젝트 문서화
- `PROJECT_MAP.md` 신규 작성 — 전체 데이터 흐름, 파일 역할 일람, 설계 결정 기록
- `WORKLOG.md` 신규 작성 — 날짜별 작업 일지 (현재 파일)

### [3] Streamlit 대시보드 대폭 개선 (`dashboard.py`)
- **사이드바 메뉴** 추가 — 📊 개요 / 🔍 DB 탐색 / 🧪 샘플 결과 3페이지 분리
- **자동 새로고침(30초) 제거** → 사이드바 수동 🔄 버튼으로 교체
- **triage 태그 시각화** — 합성방법 태그 / 형상 태그 / is_oa 도넛 차트 추가
- **🔍 DB 탐색 페이지** — 제목·DOI 검색 + 연도·합성방법·OA·완성도 필터 + 테이블
- **🧪 샘플 결과 페이지** — 추출 진행률 바 + 합성방법·TEM·BET 필터
- **is_oa 차트를 도넛으로 변경** (2범주는 도넛이 더 효과적)
- `대시보드 실행.bat` 신규 작성 — 더블클릭으로 서버 시작

### [4] 탐색적 분석 (`quick_analysis.py`)
- 신규 작성 — 현재 DB 기반 입자크기 예측 인자 탐색 스크립트
- **5개 그래프 생성** (`output/analysis/`)
  - `01_method_vs_size.png` — 합성방법별 TEM 입자크기 박스플롯
  - `02_temp_vs_size.png` — 합성온도 vs TEM 크기 산점도 (r=-0.116)
  - `03_calcination_vs_size.png` — 하소온도 vs TEM 크기 산점도 (r=-0.058)
  - `04_correlation_heatmap.png` — 수치 인자 간 상관관계 히트맵
  - `05_morphology_vs_size.png` — 형태별 TEM 입자크기 박스플롯
- **주요 인사이트**:
  - TEM 유효 데이터 528편, 중앙값 12.3 nm
  - 합성온도↔XRD 결정자 크기 상관 r=0.64 (유의미)
  - pH↔XRD 크기 r=-0.50 (데이터 46편으로 신뢰도 낮음)
  - 형태별: Cube < Sphere < Hollow < Rod 순으로 크기 증가
  - 온도 단독으로는 TEM 입자크기 예측 불가 (r<0.15)

### [5] 역설계용 컬럼 체계 세분화
- `src/extract_ceria_rules.py` — 4개 추출 함수 신규 추가:
  `extract_mineralizer()`, `extract_capping_agent()`, `extract_chelating_agent()`, `extract_oxidant()`
- `run_cell17.py` — 새 컬럼 키워드 보완 섹션 추가 (6~9번)
- `run_cell19.py` — `FIELD_WEIGHTS`를 3범주(재료/방법/결과)로 재구성, MAX_SCORE 확장
- **새 컬럼**: `mineralizer`, `capping_agent`, `chelating_agent`, `oxidant`

### [6] 시편 추출 스키마 업그레이드 (`stage2_extraction_upgrade_guide.md` 적용)
- `run_sample_extraction.py` 시스템 프롬프트 전면 개정:
  - 1:1 cross-section linking 규칙 명문화
  - `discriminator` 필드 추가 (시편 식별자)
  - `confidence` 필드 추가 (high/medium/low)
  - `conditions_evidence` / `results_evidence` 필드 추가
  - `paper_has_synthesis` 래퍼 포맷으로 변경
- JSON 파싱: 새 포맷 우선 + 구 포맷 폴백 (하위 호환 유지)
- **CSV 출력 추가**: `output/ceria_samples.csv` (1행=1시편, ML 직접 입력)

### [7] ML 역설계 파이프라인 신규 작성 (`stage3_modeling_upgrade_guide.md` 적용)
- `ceria_model.py` 신규 작성:
  - **정방향 분류기**: 합성조건 → 입자 형태 (HistGradientBoosting)
  - **정방향 회귀기**: 합성조건 → TEM/XRD 입자크기
  - **논문 단위 GroupKFold** 교차검증 (누수 방지)
  - **Permutation Importance** 피처 영향력 분석 + PNG 저장
  - **역설계**: 목표 형태·크기 → 합성 조건 후보 Top 10 도출
  - **능동학습**: 불확실성 최대 조건 5개 제안 (다음 실험 가이드)

---

### 미완료 (다음 세션으로)
- `add_triage_tags.py` 실행 미완료 (pandas 없는 환경에서 오류 — 올바른 환경 활성화 후 재실행 필요)
- `sample_extraction_cache.json` 삭제 후 `run_sample_extraction.py` 전체 실행 (~6시간, ~$1.60)
- `run_sample_extraction.py` 완료 후 `ceria_model.py` 실행 (역설계 파이프라인)

---

## 2026-06-01 ~ 2026-06-04

### 완료
- **파이프라인 전체 구축**
  - 논문 수집: OpenAlex / Crossref / Semantic Scholar API (총 6,400편 → 중복 제거 후 4,388편)
  - PDF 다운로드: Unpaywall OA URL + 직접 URL 재시도
  - 텍스트 추출: pdfplumber → PyMuPDF 폴백 (~1,990편 전문 확보)
  - 합성조건 추출: 정규식(`src/`) + OpenAI gpt-4o-mini 보완
  - 메인 DB 생성: `output/ceria_synthesis_database.xlsx` (4,388편)

- **후처리 파이프라인 완성** (`run_post_pipeline.py`)
  - `run_cell17`: 초록 키워드로 합성방법/형태/결정상 빈 필드 보완
  - `run_cell19`: 완성도 점수 계산 (MAX_SCORE=22.0), 합성논문 분류
  - `run_cell21`: 데이터 정규화 (단위·표기 통일)
  - `run_cell22`: ML 데이터셋 JSONL 생성
  - 산출: `ceria_dataset_quality.jsonl` (완성도 ≥40%, 211편)

- **샘플별 추출기 제작** (`run_sample_extraction.py`)
  - OpenAI gpt-4o-mini로 시편 단위 조건→결과 1:1 매칭
  - `--limit 20` 소규모 테스트 완료
  - 캐시 기반 재시작 가능 구조

- **Streamlit 대시보드** (`dashboard.py`) 제작
  - 수집 현황, 완성도 분포, 샘플 추출 진행률 실시간 확인

- **src/ 라이브러리 정비**
  - `extract_ceria_rules.py`: 1차 입자만 추출 (DLS·기공크기·박막두께 제외)
  - `ceria_dictionary.py` / `dopant_dictionary.py` / `quantity_extractor.py` 완성

---

## 작업 예정 (백로그)

| 우선순위 | 항목 | 예상 비용/시간 | 선행 조건 |
|---|---|---|---|
| **즉시** | `add_triage_tags.py` 실행 — 기존 DB 태그 추가 | ~수초 | conda test 환경 활성화 |
| **즉시** | 캐시 삭제 후 `run_sample_extraction.py` 전체 실행 | ~6시간, ~$1.60 | 캐시 파일 삭제 필수 |
| 높음 | `ceria_model.py` 실행 — 역설계 파이프라인 | ~수분 | sample extraction 완료 후 |
| 중간 | `run_cell17.py` 재실행 — 새 컬럼(mineralizer 등) DB 반영 | ~수분 | — |
| 중간 | 완성도 낮은 필드 추출 규칙 개선 (BET, pH, 도핑 농도 등) | 미정 | — |
| 낮음 | 쿼리 확장 후 재수집 (전구체별·첨가제별·형상별) | 미정 | — |

### 즉시 실행 순서
```cmd
:: 1. 기존 Excel에 새 태그 컬럼 추가
conda activate test
cd /d "d:\머신러닝 교육\ceria_pipeline_data"
python add_triage_tags.py

:: 2. 새 컬럼(mineralizer 등) DB 반영
python run_cell17.py

:: 3. 캐시 초기화 후 샘플 추출 전체 실행
del output\sample_extraction_cache.json
python run_sample_extraction.py

:: 4. 추출 완료 후 역설계 파이프라인 실행
python ceria_model.py
```
