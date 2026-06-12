# 1단계 문헌 수집 (OpenAlex) — 설계 노트 & 업그레이드 가이드

> 목적: 현재 작업 중인 파이썬 파이프라인의 **수집(crawling) 단계**를 업그레이드할 때 그대로 참고/이식할 수 있도록, 설계 의도와 핵심 코드 조각을 정리한 문서. 기준 구현은 `ceria_litcollect.py`.

---

## 1. 한눈에 보는 동작

1. **OpenAlex 다층 쿼리(코어 · 합성법별 · 형상별)**를 실행해 결과의 **합집합**을 만든다.
2. **DOI / OpenAlex ID 둘 중 하나라도 겹치면 중복**으로 보고 제거한다.
3. 각 논문에서 메타데이터 + **초록(역색인 복원)** + **`is_oa` · `pdf_url`**을 기록한다.
4. 제목+초록에서 **합성법(`tagged_methods`) · 형상(`tagged_morphologies`) 키워드를 사전 태깅**(triage)한다.
5. 출력은 두 갈래: `*_papers.jsonl`(2단계 추출 입력, 논문 1건 = 한 줄)과 `*_papers_summary.csv`(사람 검토용).

---

## 2. 꼭 지킬 설계 의도 (왜 이렇게 했나)

이 네 가지가 업그레이드 시에도 유지해야 할 핵심 결정이다.

- **출력 두 갈래 분리.** `jsonl`은 기계(2단계 추출)용, `csv`는 사람 훑어보기용. 용도가 다르므로 포맷도 분리한다.
- **`is_oa` · `pdf_url`을 반드시 보존.** 다음 단계에서 **OA 논문은 PDF 전문을, 비-OA는 초록을 입력으로 분기**하기 위한 스위치다. 합성 조건은 대개 "실험 방법(Experimental)" 섹션에 있어서, **전문이 확보되는 OA 논문에서 시편 단위 1:1 매칭 정확도가 훨씬 높다.**
- **사전 태깅은 정밀 추출이 아니라 triage.** 제목+초록 키워드 매칭일 뿐이며, 목적은 우선순위 정렬이다. 예: **형상 태그가 붙은 논문부터 추출하면 빈 결과를 줄일 수 있다.**
- **중복 제거는 ID와 DOI 둘 다로.** 같은 논문이 서로 다른 쿼리에서 잡히므로, OpenAlex ID 또는 정규화된 DOI 중 하나라도 겹치면 스킵한다.

---

## 3. 업그레이드 체크리스트 (기존 파이프라인에 적용)

각 항목은 독립적으로 이식 가능하다. 이미 있으면 건너뛰면 된다.

- [ ] **다층 쿼리 + 합집합 + (ID·DOI) 중복 제거** 구조로 전환 — 단일 쿼리보다 커버리지가 넓다.
- [ ] **초록을 `abstract_inverted_index`에서 복원**해 텍스트로 저장.
- [ ] **OA 분기용 필드(`is_oa`, `oa_status`, `oa_url`, `pdf_url`) 보존.**
- [ ] **triage 태그 컬럼(`tagged_methods`, `tagged_morphologies`) 추가.**
- [ ] **커서 페이지네이션 + polite pool(`mailto`) + 재시도/지수 백오프.**
- [ ] **출력 이원화: `jsonl`(추출 입력) + `csv`(검토).**
- [ ] **설정값 외부화: `QUERIES` / 연도 범위 / `MAX_PER_QUERY` / `EMAIL`.**

선택(있으면 더 좋은) 업그레이드:

- [ ] 쿼리별 **`meta.count`**(총 검색량)를 로깅해 커버리지/누락을 가늠.
- [ ] **`topics` · `referenced_works`** 같은 필드도 저장해 두면 나중에 개념 기반 필터링·인용망 분석에 쓸 수 있다.
- [ ] **제목 정규화 dedup 보조키**(DOI가 없는 레코드 대비): 소문자화·공백/기호 제거한 제목 해시로 중복 추가 차단.
- [ ] **재개(resume) 기능**: 이미 수집한 ID를 파일로 두고 다음 실행 때 건너뛰기.
- [ ] **원본 응답 보존**(raw JSON 덤프) — 재현성·스키마 변경 대비.
- [ ] **커버리지 리포트**: OA vs 비-OA 비율, 쿼리별 신규 건수, 태그 분포를 한 번에 출력.

---

## 4. 드롭인 코드 조각

> `requests`만 필요. `EMAIL`을 본인 이메일로 바꾸면 polite pool로 더 안정적이다.

### 4.1 초록 역색인 복원

```python
def reconstruct_abstract(inverted_index):
    """OpenAlex의 abstract_inverted_index 를 평문으로 복원."""
    if not inverted_index:
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(word for _, word in positions)
```

### 4.2 재시도/백오프 GET (polite pool 헤더 포함)

```python
import requests, time, sys

BASE_URL = "https://api.openalex.org/works"
EMAIL = "your_email@example.com"
TIMEOUT, MAX_RETRIES = 30, 4

def _request(params):
    headers = {"User-Agent": f"litcollect/1.0 (mailto:{EMAIL})"}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(BASE_URL, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt); continue
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  요청 오류({e}); 재시도...", file=sys.stderr)
            time.sleep(2 ** attempt)
    return None
```

### 4.3 커서 페이지네이션 단일 쿼리

```python
FROM_YEAR, TO_YEAR, MAX_PER_QUERY, PER_PAGE, SLEEP_SEC = 2000, 2026, 400, 200, 0.3

def search_query(query):
    collected, cursor = [], "*"
    while cursor and len(collected) < MAX_PER_QUERY:
        params = {
            "search": query,
            "filter": (f"from_publication_date:{FROM_YEAR}-01-01,"
                       f"to_publication_date:{TO_YEAR}-12-31,type:article"),
            "per-page": PER_PAGE, "cursor": cursor, "mailto": EMAIL,
        }
        data = _request(params)
        if not data: break
        results = data.get("results", [])
        if not results: break
        collected.extend(results)
        cursor = (data.get("meta") or {}).get("next_cursor")
        time.sleep(SLEEP_SEC)
    return collected[:MAX_PER_QUERY]
```

### 4.4 work → 레코드 (OA 필드 + triage 태깅)

```python
def tag_keywords(text, keyword_map):
    low = text.lower()
    return [label for label, variants in keyword_map.items()
            if any(v in low for v in variants)]

def parse_work(w, method_kw, morph_kw):
    abstract = reconstruct_abstract(w.get("abstract_inverted_index"))
    title = w.get("title") or ""
    haystack = f"{title} {abstract}"

    oa = w.get("open_access") or {}
    best_oa = w.get("best_oa_location") or {}
    source = ((w.get("primary_location") or {}).get("source") or {})

    doi = w.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    return {
        "openalex_id": w.get("id"),
        "doi": doi,
        "title": title,
        "year": w.get("publication_year"),
        "journal": source.get("display_name"),
        "abstract": abstract,
        "is_oa": oa.get("is_oa", False),
        "oa_status": oa.get("oa_status"),
        "oa_url": oa.get("oa_url"),
        "pdf_url": best_oa.get("pdf_url"),      # ← OA면 전문, 아니면 None → 2단계 분기 스위치
        "cited_by_count": w.get("cited_by_count"),
        "tagged_methods": tag_keywords(haystack, method_kw),
        "tagged_morphologies": tag_keywords(haystack, morph_kw),
    }
```

### 4.5 합집합 + 중복 제거 (ID 또는 DOI)

```python
def collect(queries, method_kw, morph_kw):
    by_id, seen_dois = {}, set()
    for q in queries:
        for w in search_query(q):
            rec = parse_work(w, method_kw, morph_kw)
            wid, doi = rec["openalex_id"], rec["doi"]
            if wid in by_id:                continue   # ID 중복
            if doi and doi in seen_dois:    continue   # DOI 중복
            by_id[wid] = rec
            if doi: seen_dois.add(doi)
    records = list(by_id.values())
    records.sort(key=lambda r: r.get("cited_by_count") or 0, reverse=True)  # 중요 논문 우선
    return records
```

---

## 5. 입자 형상·크기 조절 팩터 (수집·태깅·추출에 반영)

도핑 외에도 형상·크기를 좌우하는 인자는 많다. 아래는 합성 단계에서 조절 가능한 주요 팩터와 효과를 정리한 것. **수집 단계에서는 쿼리·태깅에**, **2단계에서는 시편별 추출 필드에** 반영한다.

| 인자 | 대표 옵션 | 크기 영향 | 형상 영향 |
|---|---|---|---|
| 합성법 | hydrothermal · solvothermal · (공)침전 · sol-gel · thermal decomposition · microemulsion · combustion · polyol · sono/microwave | 방법별 고유 분포 | 방법별 고유 경향 |
| Ce 전구체·음이온 | Ce(NO₃)₃ · CeCl₃ · Ce 황산염 · ceric ammonium nitrate(CAN) · acetate · carbonate | 전구체 종류가 크기·상 좌우 | 음이온이 면에 선택 흡착 → 형상 변화(황산염→구형 등) |
| 전구체/반응물 농도 | 묽음 ↔ 진함 | 과포화 → 핵생성·성장 균형 | 농도에 따라 형상 달라짐 |
| 광화제·염기 종류/농도 | NaOH · KOH · NH₃ · urea · HMTA · TMAH | OH⁻ 공급량 → 성장 | NaOH 농도 = 고전 형상 레버; urea+NaOH → 나노큐브 |
| pH(및 조절제) | 산: HNO₃·H₂SO₄·AcOH / 염기: NaOH·NH₃ | 고pH일수록 구형 크기↓ | 저pH 입자 ↔ 고pH 로드 길이↑; 제타전위·응집 |
| 반응 온도 | 80–220 ℃ | ↑ → 크기↑ | 입방형 ↔ 육방형 등 전이 |
| 시간·숙성 | 단시간 ↔ 장시간 | Ostwald ripening → 크기↑ | 형상 진화(중간상→CeO₂) |
| 계면활성제·캡핑·구조유도제 | 양이온 CTAB/CTAC · 음이온 SDS · 비이온 PVP/PEG/Triton/Pluronic · oleic acid/oleylamine · citrate | 성장 억제·응집↓ → 크기↓ (PVP가 특히 효과적) | 면 선택 흡착 → cube/rod/sphere (CTAB→cube·rod, SDS→길쭉한 구형) |
| 용매 | 물 · EtOH · MeOH · ethylene glycol · 1,4-butanediol · iPrOH | 폴리올/글리콜 → 작고 단분산 | 극성·점도가 성장 이방성에 영향 |
| 산화제 | H₂O₂ (및 합성 분위기 O₂) | H₂O₂ 농도↑ → 크기↓ | Ce³⁺/Ce⁴⁺ 비 변화 |
| 후처리 소성·어닐링 | 온도 · 시간 · 분위기 | 결정 성장 → 크기↑ | 면·분포·소결 변화 |
| 에너지 보조 | 초음파 · 마이크로웨이브 · 교반 · 주입속도 | 초음파→4–8 nm, MW→빠르고 균일 | 핵생성 버스트 제어로 균일도↑ |
| 도판트 | La · Nd · Pr · Sm · Y · Eu · Gd · Co 등 | 격자·성장 변화 | Ce³⁺·산소공공·형상 변화 |
| 템플릿·시드 | 마이셀 · 하드/소프트 템플릿 · seed | 템플릿 크기 → 입자 크기 | 마이셀 유도·oriented attachment로 형상 결정 |
| 이온 강도·첨가 염 | NaCl · Na₂SO₄ · 인산염 등 | 전하 차폐 → 응집·크기 | 음이온이 형상 유도(인산·황산 등) |

> **메커니즘 3갈래.** 대부분의 인자는 결국 ① **핵생성 vs 성장 속도**(농도·온도·pH·산화제), ② **특정 결정면 선택 흡착·안정화**(음이온·계면활성제·캡핑제), ③ **후성장·숙성·소결**(시간·소성) 중 하나로 작동한다.

### 태깅 사전 확장 (triage 정밀도↑)

```python
MINERALIZER_KEYWORDS = {
    "NaOH": ["naoh", "sodium hydroxide"],
    "KOH": ["koh", "potassium hydroxide"],
    "ammonia": ["ammonia", "ammonium hydroxide", "nh4oh", "nh3"],
    "urea": ["urea"],
    "HMTA": ["hexamethylenetetramine", "hmta", "hexamine"],
    "TMAH": ["tmah", "tetramethylammonium hydroxide"],
}
ADDITIVE_KEYWORDS = {   # 계면활성제 · 캡핑 · 구조유도제
    "CTAB": ["ctab", "cetyltrimethylammonium"],
    "SDS": ["sds", "sodium dodecyl sulfate", "dodecyl sulphate"],
    "PVP": ["pvp", "polyvinylpyrrolidone", "polyvinyl pyrrolidone"],
    "PEG": ["peg", "polyethylene glycol"],
    "triton": ["triton x-100", "triton"],
    "pluronic": ["pluronic", "p123", "f127"],
    "citrate": ["citrate", "citric acid"],
    "oleic_acid": ["oleic acid", "oleate"],
    "oleylamine": ["oleylamine"],
}
SOLVENT_KEYWORDS = {
    "water": ["aqueous", "deionized", "distilled water"],
    "ethylene_glycol": ["ethylene glycol", "polyol"],
    "ethanol": ["ethanol"],
    "methanol": ["methanol"],
    "butanediol": ["butanediol"],
    "isopropanol": ["isopropanol", "2-propanol", " ipa "],
}
OXIDANT_ASSIST_KEYWORDS = {
    "H2O2": ["h2o2", "hydrogen peroxide"],
    "sonochemical": ["sonochem", "ultrasonic", "ultrasound", "sonication"],
    "microwave": ["microwave"],
    "calcination": ["calcin", "anneal"],
}
DOPANT_KEYWORDS = {
    "La": ["la-doped", "lanthanum doped"], "Nd": ["nd-doped", "neodymium doped"],
    "Pr": ["pr-doped", "praseodymium doped"], "Sm": ["sm-doped", "samarium doped"],
    "Y": ["y-doped", "yttrium doped"], "Gd": ["gd-doped", "gadolinium doped"],
    "Eu": ["eu-doped", "europium doped"], "Co": ["co-doped ceria", "cobalt doped"],
}
```

`parse_work` 의 반환 dict에 태그를 추가:

```python
"tagged_mineralizer": tag_keywords(haystack, MINERALIZER_KEYWORDS),
"tagged_additives":   tag_keywords(haystack, ADDITIVE_KEYWORDS),
"tagged_solvent":     tag_keywords(haystack, SOLVENT_KEYWORDS),
"tagged_assist":      tag_keywords(haystack, OXIDANT_ASSIST_KEYWORDS),
"tagged_dopant":      tag_keywords(haystack, DOPANT_KEYWORDS),
```

> **2단계 추출 반영.** 위 인자들은 시편별 추출 스키마의 **조건 필드**가 되어야 한다 — 전구체·음이온 / 염기 종류·농도 / pH(+조절제) / 온도 / 시간 / 첨가제 종류·농도 / 용매 / 산화제 / 소성 T·시간 / 에너지 보조 / 도판트. 그래야 3단계 모델이 "어떤 인자가 형상·크기를 좌우하는가"를 학습할 수 있다.

---

## 6. 튜닝 포인트

조정 빈도가 높은 세 가지: **`QUERIES` · 연도 범위 · `MAX_PER_QUERY`.**

### 쿼리 확장 예시

```python
# 코어
"ceria nanoparticle synthesis", "CeO2 nanoparticle synthesis",
"cerium oxide nanoparticle synthesis", "nanoceria synthesis",

# 합성법별
"ceria hydrothermal synthesis", "CeO2 solvothermal synthesis",
"cerium oxide precipitation synthesis", "ceria thermal decomposition nanocrystal",
"CeO2 sol-gel nanoparticle",

# 형상별
"ceria nanocube facet", "CeO2 nanorod synthesis", "ceria nanopolyhedra",
"CeO2 octahedra nanocrystal", "ceria nanosphere synthesis", "CeO2 nanoflower hierarchical",

# (선택) 도핑 세리아 — 범위를 도판트로 확장
"La doped ceria nanoparticle", "Eu doped ceria nanoparticle",
"Gd doped CeO2 abrasive", "Nd doped cerium oxide",

# (선택) 응용별 — 목표 분야로 좁히거나 넓히기
"ceria CMP abrasive slurry", "CeO2 STI chemical mechanical planarization",
"ceria catalyst three-way", "CeO2 gas sensor nanoparticle",

# (선택) 전구체·음이온별
"cerium sulfate ceria nanoparticle morphology", "cerium chloride ceria nanorod",
"ceric ammonium nitrate ceria nanocube",

# (선택) 염기·pH·첨가제별
"urea ceria nanocube hydrothermal", "ammonia ceria nanorod precipitation",
"CTAB ceria morphology", "PVP ceria nanoparticle size", "SDS ceria nanostructure",
"citrate capped ceria nanoparticle", "ceria pH effect particle size",

# (선택) 용매·산화제·후처리별
"polyol ceria nanoparticle ethylene glycol", "H2O2 oxidation nanoceria size",
"sonochemical ceria nanoparticle", "microwave ceria nanoparticle synthesis",
"calcination temperature ceria crystallite size",
```

태그 사전(`METHOD_KEYWORDS`, `MORPHOLOGY_KEYWORDS`)도 같은 식으로 항목을 추가하면 triage 컬럼이 함께 풍부해진다. CMP로 좁힐 경우 결과측 태그에 `cube/rod`뿐 아니라 도판트·소성 조건 키워드를 더해두면 다음 단계 우선순위에 유용하다.

---

## 7. 다음 단계로의 핸드오프 (2단계 연결)

- `jsonl`의 각 줄(논문 1건)이 **2단계 추출기의 입력**이 된다.
- 2단계는 `is_oa` / `pdf_url`을 보고 **OA → PDF 전문, 비-OA → 초록**으로 입력을 분기한다.
- 합성 조건이 실험 방법 섹션에 있으므로, **전문이 있는 OA 논문일수록 시편 단위 1:1 매칭 정확도가 높다.**
- 유료 저널 전문이 필요하면, `pdf_url` 자리에 **기관 TDM 라이선스 엔드포인트**를 끼워 넣는 방식으로 확장한다(약관 준수 경로).

---

### 부록 — 합법성 메모

- OpenAlex 메타데이터·초록 수집은 무료·공개 API로 허용된다.
- **유료 전문의 대량 스크래핑은 출판사 약관 위반**이다. 전문은 오픈액세스이거나 기관 TDM 라이선스가 있을 때만 받는다.
- 이 스크립트는 약관상 안전한 기본 경로(메타데이터·초록·OA PDF 위치)만 구현한다.
