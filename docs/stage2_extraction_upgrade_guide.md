# 2단계 시편 단위 추출 — 설계 노트 & 업그레이드 가이드

> 목적: 작업 중인 파이썬 파이프라인에 **추출(parsing) 단계**를 추가/업그레이드할 때 참고·이식할 수 있도록 정리. 입력은 1단계 출력 `ceria_papers.jsonl`(논문 1건 = 한 줄), 출력은 시편 단위 데이터셋. 기준 구현은 `ceria_extract.py`.

---

## 1. 한눈에 보는 동작

1. 1단계 `jsonl`을 한 줄씩(논문 1건) 읽는다.
2. **입력 분기**: `is_oa`·`pdf_url`을 보고 **OA 논문은 PDF 전문**, 비-OA는 **초록**을 추출 입력으로 쓴다.
3. **LLM tool-use를 강제**해 논문 텍스트 → **시편(sample) 단위 구조화 레코드**로 변환한다(조건+결과를 한 객체로).
4. **출력 두 갈래**: `ceria_samples.jsonl`(논문 단위, 시편 배열 + 출처) / `ceria_samples.csv`(**1행 = 1시편**, 3단계 모델 입력).

---

## 2. 꼭 지킬 설계 의도 — 1:1 매칭 강제 (이 단계의 핵심)

비정형 텍스트를 시편 단위 데이터로 바꾸는 것이 전부다. 아래 원칙을 **프롬프트와 스키마 양쪽에 박아 넣는다.**

- **관측 단위는 시편이지 논문이 아니다.** 논문 1편 → 시편 객체 N개.
- **조건과 결과를 한 객체로 묶어 추출한다.** 조건만/결과만 따로 뽑아 **사후 join 하지 않는다.** "실험 방법"과 "결과 및 논의"를 **함께 읽어** 같은 시편으로 연결(cross-section linking)한다.
- **시편 식별:** 명시적 라벨(예: "CeO2-NC", "S1")이 있으면 그것을 쓰고, 없으면 **변화시킨 변수**(예: "[NaOH]=6 M")를 `discriminator`로 삼는다.
- **결측은 null.** 안 적힌 값은 지어내거나 다른 시편에서 복사하지 않는다.
- **범위값은 `*_min/*_max + is_range` 플래그**로 분리(점값은 null).
- **단위 정규화**(M, ℃, h). 애매하면 원 단위 문자열을 함께 기록.
- **confidence 표시**: 연결이 명시적이면 `high`, 추론했으면 `medium`, 불확실하면 `low`.
- **tool-use 강제**로 구조화 출력을 받는다(마크다운/JSON 파싱 깨짐 없음).

---

## 3. 업그레이드 체크리스트 (기존 파이프라인에 적용)

- [ ] **시편 단위 추출**: 논문 1건 → 시편 객체 배열(조건+결과 동봉).
- [ ] **1:1 매칭 규칙을 시스템 프롬프트에 명문화**(라벨/discriminator, 결측 null, 범위 분리, cross-section linking).
- [ ] **tool-use(함수 호출) 강제**로 평면 스키마 출력(`tool_choice` 고정).
- [ ] **입력 분기**(OA→PDF 전문 / 비-OA→초록), 전문 파서(`pymupdf`) 또는 기관 TDM 경로.
- [ ] **출력 이원화**: `jsonl`(논문 단위) + `csv`(시편 단위 1행=1시편).
- [ ] **이어하기(resume)**: 이미 처리한 DOI 건너뛰기.
- [ ] **검증·신뢰도**: `confidence`/`evidence` 필드, 골든셋 대조.

선택(있으면 더 좋은) 업그레이드:

- [ ] **2패스 비용 전략**: Sonnet 대량 → `confidence=low`만 Opus 재추출.
- [ ] **Batch API**로 수백 편 대량 처리(비용↓).
- [ ] **스키마 확장**(§5): 첨가제·pH·용매·산화제·소성·도판트 + CMP 출력.
- [ ] **표/그림 보완**: 텍스트에 없고 표·TEM 이미지에만 있는 수치는 별도 플래그.

---

## 4. 드롭인 코드 조각

> `pip install anthropic` · `export ANTHROPIC_API_KEY=...`

### 4.1 추출 시스템 프롬프트 (1:1 매칭 규칙)

```text
You convert a paper's text into structured per-SAMPLE synthesis records.
1. 추출 단위는 SAMPLE(시편)이지 논문이 아니다. 시편마다 객체 1개.
2. 각 객체는 조건(CONDITIONS)과 결과(RESULTS)를 함께 담는다. 방법·결과 섹션을
   같이 읽어 같은 시편으로 연결한다. 조건만/결과만 분리 출력 금지.
3. 명시 라벨이 있으면 sample_id로 쓰고, 없으면 '변화시킨 변수'를 discriminator로.
4. 값이 없으면 null(facets는 빈 리스트). 다른 시편 값 복사·창작 금지.
5. 범위는 *_min/*_max + is_range, 점값은 null.
6. 단위는 가능한 한 정규화(min→h 등), 애매하면 원 단위 문자열 보존.
7. evidence는 15단어 미만의 짧은 위치 표시.
8. confidence: 명시적이면 high, 추론은 medium, 불확실은 low.
9. 추출 가능한 시편 합성 데이터가 없으면 paper_has_synthesis=false, 빈 리스트.
```

### 4.2 tool-use 스키마 (시편 = 평면 객체 → CSV 1행에 대응)

```python
SAMPLE_PROPERTIES = {
    "sample_id": {"type": "string"},
    "discriminator": {"type": "string"},
    # 조건
    "method": {"type": ["string", "null"]},
    "precursor": {"type": ["string", "null"]},
    "precursor_conc_value": {"type": ["number", "null"]},
    "precursor_conc_unit": {"type": ["string", "null"]},
    "mineralizer": {"type": ["string", "null"]},
    "mineralizer_conc_value": {"type": ["number", "null"]},
    "mineralizer_conc_min": {"type": ["number", "null"]},
    "mineralizer_conc_max": {"type": ["number", "null"]},
    "mineralizer_conc_is_range": {"type": "boolean"},
    "mineralizer_conc_unit": {"type": ["string", "null"]},
    "temperature_C": {"type": ["number", "null"]},
    "time_h": {"type": ["number", "null"]},
    "pH": {"type": ["number", "null"]},
    "capping_agent": {"type": ["string", "null"]},
    "capping_ratio": {"type": ["string", "null"]},
    "solvent": {"type": ["string", "null"]},
    # 결과
    "morphology": {"type": ["string", "null"]},
    "facets": {"type": "array", "items": {"type": "string"}},
    "size_nm_value": {"type": ["number", "null"]},
    "size_nm_min": {"type": ["number", "null"]},
    "size_nm_max": {"type": ["number", "null"]},
    "size_is_range": {"type": "boolean"},
    "aspect_ratio": {"type": ["number", "null"]},
    # 메타/검증
    "conditions_evidence": {"type": "string"},
    "results_evidence": {"type": "string"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "notes": {"type": "string"},
}

EXTRACT_TOOL = {
    "name": "emit_samples",
    "description": "Return per-sample ceria synthesis records.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paper_has_synthesis": {"type": "boolean"},
            "samples": {"type": "array", "items": {
                "type": "object", "properties": SAMPLE_PROPERTIES,
                "required": ["sample_id", "discriminator", "facets",
                             "mineralizer_conc_is_range", "size_is_range",
                             "conditions_evidence", "results_evidence",
                             "confidence", "notes"]}},
        },
        "required": ["paper_has_synthesis", "samples"],
    },
}
```

### 4.3 추출 호출 (tool-use 강제 → 구조화 출력)

```python
import anthropic
client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"   # 정확도 우선이면 "claude-opus-4-8"

def extract_paper(text, title, doi):
    user = (f"Paper title: {title}\nDOI: {doi}\n\nText:\n{text}\n\n"
            "Extract per-sample ceria synthesis records and call emit_samples.")
    resp = client.messages.create(
        model=MODEL, max_tokens=8000, system=SYSTEM_PROMPT,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "emit_samples"},   # ← 강제
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_samples":
            return dict(block.input)            # {paper_has_synthesis, samples[]}
    return {"paper_has_synthesis": False, "samples": []}
```

### 4.4 입력 분기 (OA 전문 / 비-OA 초록)

```python
FETCH_FULLTEXT = False   # OA PDF 자동 파싱 켜기: True + `pip install pymupdf`

def get_text_for_record(rec):
    """전문 우선, 없으면 초록. is_oa/pdf_url 로 분기."""
    if rec.get("fulltext"):
        return rec["fulltext"], "fulltext"
    if FETCH_FULLTEXT and rec.get("pdf_url"):
        text = try_fetch_pdf_text(rec["pdf_url"])   # requests + pymupdf, 실패 시 None
        if text:
            return text, "fetched_pdf"
    return rec.get("abstract", ""), "abstract"
# 유료 저널 전문은 try_fetch_pdf_text 자리에 기관 TDM 엔드포인트를 끼워 넣는다.
```

### 4.5 출력 (jsonl 논문 단위 + csv 시편 단위 1:1)

```python
import csv, json
CSV_COLUMNS = ["paper_doi", "paper_title", "year"] + list(SAMPLE_PROPERTIES.keys())

def write_outputs(doi, title, year, result, jsonl_f, csv_writer):
    samples = result.get("samples", []) or []
    # 논문 단위 JSONL (시편 배열 + 출처)
    jsonl_f.write(json.dumps({
        "paper_doi": doi, "paper_title": title, "year": year,
        "paper_has_synthesis": result.get("paper_has_synthesis", False),
        "samples": samples}, ensure_ascii=False) + "\n")
    # 시편 단위 CSV (1행 = 1시편)
    for s in samples:
        row = {"paper_doi": doi, "paper_title": title, "year": year}
        row.update({k: ("|".join(map(str, v)) if isinstance(v, list) else v)
                    for k, v in s.items()})
        csv_writer.writerow({k: row.get(k) for k in CSV_COLUMNS})
```

---

## 5. 추출 스키마 확장 (1단계 §5 인자 + CMP 출력 반영)

1단계 §5에서 정리한 형상·크기 조절 인자를 **시편 객체의 조건 필드**로, CMP 관련 특성을 **결과 필드**로 추가한다. 그래야 3단계 모델이 학습할 피처·타깃이 풍부해진다.

### 추가 조건(conditions) 필드

```python
EXTRA_CONDITIONS = {
    "precursor_anion": {"type": ["string", "null"]},      # nitrate/chloride/sulfate/acetate
    "base_type": {"type": ["string", "null"]},            # NaOH/KOH/NH3/urea/HMTA/TMAH
    "pH": {"type": ["number", "null"]},                   # (이미 있음 — 조절제는 notes로)
    "ph_adjuster": {"type": ["string", "null"]},          # HNO3/H2SO4/AcOH/NH3
    "additive": {"type": ["string", "null"]},             # CTAB/SDS/PVP/PEG/citrate/oleic acid
    "additive_conc": {"type": ["string", "null"]},
    "oxidant": {"type": ["string", "null"]},              # H2O2 등 + 농도
    "calcination_temp_C": {"type": ["number", "null"]},
    "calcination_time_h": {"type": ["number", "null"]},
    "calcination_atmosphere": {"type": ["string", "null"]},  # air/H2/O2 분압
    "energy_assist": {"type": ["string", "null"]},        # sonication/microwave/stirring
    "dopant": {"type": ["string", "null"]},               # La/Nd/Pr/Sm/Y/Gd/Eu/Co
    "dopant_fraction": {"type": ["number", "null"]},
}
```

### 추가 결과(results) 필드

```python
EXTRA_RESULTS = {
    "ce3_fraction": {"type": ["number", "null"]},         # Ce3+/(Ce3++Ce4+) (XPS)
    "oxygen_vacancy": {"type": ["string", "null"]},       # 정성/정량
    "ssa_m2g": {"type": ["number", "null"]},              # 비표면적(BET)
    "polydispersity": {"type": ["number", "null"]},
    "zeta_potential_mV": {"type": ["number", "null"]},    # 분산 안정성
    # (CMP 연계 — 보고된 경우만)
    "removal_rate": {"type": ["string", "null"]},         # MRR (단위 함께)
    "selectivity_ox_nitride": {"type": ["number", "null"]},
    "scratch_defect": {"type": ["string", "null"]},
    "surface_roughness_nm": {"type": ["number", "null"]}, # Ra/Sa
}
# SAMPLE_PROPERTIES.update(EXTRA_CONDITIONS); SAMPLE_PROPERTIES.update(EXTRA_RESULTS)
# required 목록과 시스템 프롬프트의 필드 설명도 함께 갱신할 것.
```

> 새 필드도 동일 원칙을 따른다: **시편 단위로 묶고, 없으면 null, 범위는 분리.** CMP 성능 지표는 슬러리·공정에도 의존하므로(3단계 §5 참고), 보고된 경우에만 채우고 공정 조건이 함께 적혀 있으면 `notes`에 남긴다.

---

## 6. 입력 분기 · 출처 · 비용 전략

- **정확도는 입력 텍스트에 달려 있다.** 합성 조건은 대개 "실험 방법" 섹션에 있어, **전문(OA PDF)** 입력일 때 시편 단위 1:1 매칭이 훨씬 정확하다. 초록만으로는 시편별 조건이 잘 안 잡힌다.
- **유료 전문**은 오픈액세스가 아니면 **기관 TDM 라이선스** 경로로만 받는다(약관 준수).
- **비용 전략**: 기본은 `claude-sonnet-4-6`로 대량 처리하고, `confidence=low`로 나온 논문만 `claude-opus-4-8`로 **재추출(2패스)**. 수백 편 규모면 **Batch API**가 저렴하다.

---

## 7. 한계와 검증

- **텍스트 외 수치 누락**: 크기 등이 표·TEM 이미지·그래프에만 있으면 텍스트 추출로는 빠진다 → 표/그림 파싱 보완 또는 결측 플래그.
- **범위·결측·단위 불일치**: 범위는 분리 저장, 결측은 null, 단위는 정규화. `confidence`로 학습 가중치/필터에 활용.
- **골든셋 검증**: 손으로 라벨링한 소수 논문과 대조해 추출 정확도(특히 조건↔결과 짝짓기)를 주기적으로 점검.

---

### 부록 — 핸드오프

- **1단계 ←** : `jsonl`의 `is_oa`·`pdf_url`로 입력을 분기. 1단계 §5의 형상·크기 인자가 본 단계 추출 필드의 근거(§5).
- **3단계 →** : `ceria_samples.csv`(1행=1시편)가 예측·역설계 모델의 입력. 조건 필드 = 모델 피처, 결과 필드 = 타깃.
