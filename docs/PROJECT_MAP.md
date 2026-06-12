# CeO2 합성 논문 파이프라인 — 프로젝트 맵

> 마지막 갱신: 2026-06-05

---

## 프로젝트 목적

1900~2026년 CeO2(세리아) 나노입자 합성 관련 논문 ~4,400편에서
합성 조건(방법, 전구체, 용매, 온도, 시간, 입자크기, 형태 등)과 측정 결과를 자동 추출하여
ML 학습 데이터셋을 구축한다.

최종 목표: **"합성 조건 → 입자 특성" 예측 모델** 학습용 데이터셋

---

## 전체 데이터 흐름

```
[1단계] 논문 수집
  OpenAlex / Crossref / Semantic Scholar API
        ↓ 중복 제거 (DOI + OpenAlex ID)
  output/papers_metadata.xlsx   (메타데이터 중간 저장)
        ↓ Unpaywall OA URL 보완
  PDF 다운로드 → pdf/
  텍스트 추출 → text/

[2단계] 합성조건 추출
  pipeline.py 셀 11~15
  정규식(src/) + OpenAI gpt-4o-mini 보완
        ↓
  output/ceria_synthesis_database.xlsx   (메인 DB, 시트: 합성조건)

[3단계] 후처리 (run_post_pipeline.py)
  run_cell17  키워드 보완 (합성방법/형태/결정상)
  run_cell19  완성도 점수 & 합성논문 분류
  run_cell21  정규화 (표기 통일, 단위 정합성)
  run_cell22  ML 데이터셋 JSONL 생성
        ↓
  output/ceria_dataset_full.jsonl
  output/ceria_dataset_quality.jsonl   (완성도 ≥40%)

[4단계] 샘플별 추출 (run_sample_extraction.py)
  전문(full-text) 보유 논문 대상
  OpenAI gpt-4o-mini로 시편 단위 조건→결과 1:1 매칭
        ↓
  output/ceria_samples.jsonl
```

---

## 파일 역할 일람

### 실행 스크립트

| 파일 | 역할 | 실행 시간 |
|---|---|---|
| `pipeline.py` | 전체 파이프라인 (수집→추출, 셀 1~15) | 수 시간 |
| `run_post_pipeline.py` | 후처리 4단계 일괄 실행 | ~수분 |
| `run_cell17.py` | 초록 키워드로 빈 필드 보완 | ~1분 |
| `run_cell19.py` | 완성도 점수 계산 & 합성논문 분류 | ~1분 |
| `run_cell21.py` | 데이터 정규화 (단위·표기 통일) | ~1분 |
| `run_cell22.py` | ML 데이터셋 JSONL 생성 | ~1분 |
| `run_sample_extraction.py` | 시편별 조건→결과 매칭 (OpenAI) | ~6시간, ~$1.60 |
| `run_download_extra.py` | 추가 PDF 다운로드 재시도 | 수 시간 |
| `add_triage_tags.py` | 기존 Excel에 triage 태그 사후 추가 | ~수초 |
| `dashboard.py` | Streamlit 실시간 현황 대시보드 | — |

### 분석 스크립트

| 파일 | 역할 |
|---|---|
| `check_completeness.py` | 완성도 점수 분포 분석 |
| `check_fulltext.py` | 전문 접근 가능 여부 분석 |
| `test_particle_size.py` | 입자크기 추출 정확도 검증 |

### src/ 라이브러리

| 파일 | 역할 |
|---|---|
| `src/extract_ceria_rules.py` | 정규식 기반 합성조건 추출 (핵심 로직) |
| `src/experiment_parser.py` | 실험 블록 파서 |
| `src/ceria_dictionary.py` | Ce전구체 / 용매 / 첨가제 사전 |
| `src/dopant_dictionary.py` | 도핑 원소 사전 |
| `src/quantity_extractor.py` | 수치 추출기 |

### output/ 산출물

| 파일 | 설명 |
|---|---|
| `papers_metadata.xlsx` | 수집 단계 중간 저장 (메타데이터만) |
| `ceria_synthesis_database.xlsx` | 메인 DB — 4,388편, 시트: 합성조건 |
| `ceria_dataset_full.jsonl` | ML 데이터셋 전체 |
| `ceria_dataset_quality.jsonl` | 완성도 ≥40% 필터링본 (211편) |
| `ceria_samples.jsonl` | 시편별 추출 결과 |
| `sample_extraction_cache.json` | 샘플 추출 진행 상황 (재시작용) |
| `ceria_dataset_stats.txt` | 데이터셋 통계 요약 |
| `llm_cache.json` | LLM 응답 캐시 |

---

## 주요 설계 결정

### 입자 크기 — 1차 입자만 추출
`src/extract_ceria_rules.py`의 `extract_particle_size()`는 TEM/SEM 측정 1차 입자만.
명시적 제외: DLS(유체역학적 직경), 기공 크기, 박막 두께, 발광 피크.

### 완성도 점수 (MAX_SCORE = 22.0)
`run_cell19.py`에서 계산. 현재 ≥40% = 211편(4.8%)만 해당.
희귀 필드(BET, pH, 도핑 농도 등)가 점수를 낮추는 주요 원인.

### OA 분기
`is_oa` / `open_access_url` 필드로 분기:
- OA(전문 확보) → 시편 단위 1:1 매칭 정확도 높음
- 비-OA(초록만) → 메타데이터 레벨 추출만 가능

### triage 태그 (2026-06-05 추가)
`tagged_methods` / `tagged_morphologies` 컬럼:
제목+초록 키워드 매칭으로 합성법·형상 사전 분류.
목적: 추출 우선순위 결정(형상 태그 있는 논문부터 → 빈 결과 감소).

### 재시작 가능 설계
- `run_download_extra.py`: SAVE_INTERVAL=50편마다 Excel 저장
- `run_sample_extraction.py`: `sample_extraction_cache.json`으로 done_dois 추적

---

## 현재 수치 (2026-06-05 기준)

| 항목 | 수치 |
|---|---|
| 총 논문 | 4,388편 |
| 전문(full text) 보유 | ~1,990편 |
| 초록만 보유 | ~2,398편 |
| ML 데이터셋 (완성도 ≥40%) | 211편 |
| 샘플별 추출 완료 | 소규모 테스트(--limit 20)만 |

---

## 실행 환경

- Python 3.11.15, conda 환경: `test`
- 셸: **CMD만 사용** (PowerShell 보안 정책 차단)
- `.env`: `OPENAI_API_KEY` 설정됨, `ANTHROPIC_API_KEY` 비어있음
- 기본 실행:
  ```cmd
  conda activate test
  python <script>.py
  ```
