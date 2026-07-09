"""
4_extract_targeted.py — 15개 핵심 필드 집중 재추출 (합성조건 + 농도 + 부피 + 후처리 + 분석값)

대상: ceria_samples_merged.csv 에서 15개 핵심 피처 중 하나라도 비어있는 논문
     (전문 텍스트 파일 보유 필수)
방법: GPT-4o-mini 포커스 프롬프트 + ThreadPoolExecutor 병렬 처리
비용 예상: 대상 논문당 ~$0.0010  (총 ~$3.00 내외, --reset 기준)

추출 필드 (13→15):
  synthesis_method, ce_precursor, solvent,
  synthesis_temperature_c, ph_synthesis,
  ce_concentration_M, mineralizer_concentration_M,
  synthesis_volume_mL,
  capping_agent, chelating_agent, atmosphere,
  calcination_temperature_c, crystallite_size_xrd_nm,
  synthesis_time_h,    ← NEW (합성 시간 — Ostwald ripening 직결 변수)
  morphology           ← NEW (입자 형태 — 분류 모델 타겟)

실행:
  python 4_extract_targeted.py --dry-run        # 대상 확인만
  python 4_extract_targeted.py                  # 실제 추출 (기본 20 workers)
  python 4_extract_targeted.py --workers 40     # 더 빠르게 (rate limit 주의)
  python 4_extract_targeted.py --reset          # 캐시 초기화 후 전체 재시도
  python 4_extract_targeted.py --limit 50       # 50편만 테스트
"""
import os, sys, json, argparse, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE   = Path(r"d:\머신러닝 교육\ceria_pipeline_data")
OUTPUT = BASE / "output"
TEXT   = BASE / "text"
CSV    = OUTPUT / "ceria_samples_merged.csv"
CACHE  = OUTPUT / "targeted_extraction_cache.json"

TARGET_FIELDS = [
    "synthesis_method",
    "ce_precursor",
    "solvent",
    "synthesis_temperature_c",
    "ph_synthesis",
    "ce_concentration_M",
    "mineralizer_concentration_M",
    "synthesis_volume_mL",
    "capping_agent",              # 입자 형태/크기 제어 유기분자
    "chelating_agent",            # Ce 이온 착화 분자
    "atmosphere",                 # 합성/소성 분위기 가스
    "calcination_temperature_c",  # 후열처리 온도 (℃)
    "crystallite_size_xrd_nm",    # XRD Scherrer 결정자 크기 (nm)
    "synthesis_time_h",           # NEW — 합성 반응 시간 (h)
    "morphology",                 # NEW — 나노입자 형태 (TEM/SEM 기반)
]
_BAD = {"", "nan", "none", "null", "n/a", "na", "unknown",
        "not specified", "not reported", "not mentioned", "not stated"}

# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an expert in CeO2 (ceria) nanoparticle synthesis. \
Extract 13 specific fields from the paper text using the provided tool. \
Use null for any value not found or not reported."""

# ── Function calling 스키마 (strict=True: 타입 강제 + null 안전) ──────────────
_SYNTHESIS_METHOD_ENUM = [
    "hydrothermal", "solvothermal", "sol-gel", "precipitation", "co-precipitation",
    "combustion", "spray_pyrolysis", "flame_spray", "microwave", "template",
    "thermal_decomposition", "mechanochemical", "sonochemical", "wet_chemical",
    "impregnation", "electrodeposition", "deposition_precipitation",
    "microemulsion", "green_synthesis", "other",
]

def _nullable_str(desc: str) -> dict:
    return {"anyOf": [{"type": "string"}, {"type": "null"}], "description": desc}

def _nullable_num(desc: str) -> dict:
    return {"anyOf": [{"type": "number"}, {"type": "null"}], "description": desc}

_EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_synthesis_data",
        "description": "Extract 15 CeO2 synthesis fields. Use null for missing values.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "synthesis_method", "ce_precursor", "solvent",
                "synthesis_temperature_c", "ph_synthesis",
                "ce_concentration_M", "mineralizer_concentration_M", "synthesis_volume_mL",
                "capping_agent", "chelating_agent", "atmosphere",
                "calcination_temperature_c", "crystallite_size_xrd_nm",
                "synthesis_time_h", "morphology",
            ],
            "properties": {
                "synthesis_method": {
                    "anyOf": [
                        {"type": "string", "enum": _SYNTHESIS_METHOD_ENUM},
                        {"type": "null"},
                    ],
                    "description": (
                        "Main synthesis route. "
                        "hydrothermal=autoclave+water 100-250°C; "
                        "solvothermal=autoclave+organic solvent; "
                        "sol-gel=alkoxide/acetate hydrolysis/gelation; "
                        "precipitation/co-precipitation=rapid mixing aqueous; "
                        "combustion=fuel+oxidizer self-ignition; "
                        "flame_spray=FSP/flame spray pyrolysis; "
                        "spray_pyrolysis=aerosol/spray+pyrolysis (non-flame); "
                        "impregnation=wet/incipient wetness impregnation; "
                        "electrodeposition=electrochemical/electrosynthesis; "
                        "deposition_precipitation=DP method on support; "
                        "microemulsion=reverse/w-o microemulsion; "
                        "green_synthesis=plant/bio-mediated synthesis. "
                        "null only if synthesis is truly not described."
                    ),
                },
                "ce_precursor": _nullable_str(
                    "STRICTLY the cerium-containing starting material only. "
                    "VALID examples: Ce(NO3)3·6H2O, CeCl3·7H2O, (NH4)2Ce(NO3)6, "
                    "Ce(CH3COO)3, Ce(acac)3, Ce2(SO4)3, Ce(OiPr)3, CeF3, Ce2(C2O4)3. "
                    "⚠ Do NOT use 'CeO2' as a default guess — it is almost always the TARGET "
                    "PRODUCT being synthesized/characterized (mentioned constantly throughout the "
                    "paper), not the starting reagent. Only output 'CeO2' if the paper EXPLICITLY "
                    "states pre-made/commercial CeO2 powder was redissolved or redispersed as a "
                    "raw feedstock (rare). Otherwise use null. "
                    "CRITICAL — do NOT include ANY of the following: "
                    "(1) Dopant/co-metal salts: La, Sm, Gd, Nd, Pr, Eu, Zr, Fe, Ni, Co, "
                    "Cu, Zn, Mn, Al, Ti, Sn, Si, Y, Ba, Sr compounds — even if in the same solution; "
                    "(2) Noble metal precursors: HAuCl4, H2PtCl6, H2PdCl4, AgNO3, etc.; "
                    "(3) Support/substrate oxides: TiO2, ZrO2, SiO2, SnO2, Al2O3, etc.; "
                    "(4) Organic additives/polymers: PEI, TEMED, cellulose, PVP, etc.; "
                    "(5) Plant/biological extracts: leaf extract, plant extract, biosource, etc.; "
                    "(6) Solvents, acids, bases, or reducing agents. "
                    "null if no Ce compound is explicitly used as a cerium source."
                ),
                "solvent": _nullable_str(
                    "Primary liquid medium. DI/distilled water→'water'. "
                    "Mixed: semicolon-separated ('water;ethanol')."
                ),
                "synthesis_temperature_c": _nullable_num(
                    "Synthesis/reaction temperature in °C. Number only (180, not '180°C')."
                ),
                "ph_synthesis": _nullable_num(
                    "Reaction pH as number. 'pH adjusted to X' or 'pH=X'. "
                    "Range: use final/target value."
                ),
                "ce_concentration_M": _nullable_num(
                    "Ce precursor molar concentration in mol/L. "
                    "Formula: concentration = amount_mmol / final_volume_mL * 1000. "
                    "IMPORTANT — 'final volume' means total reaction solution volume, "
                    "not just the added water/solvent. "
                    "Examples: '5 mmol Ce in 50 mL total' → 0.1; "
                    "'5 mmol Ce dissolved, water added to 50 mL' → 0.1; "
                    "'0.2 g Ce(NO3)3·6H2O (MW=434) in 40 mL' → 0.01149. "
                    "null if only wt%, g without volume, or mole fraction given."
                ),
                "mineralizer_concentration_M": _nullable_num(
                    "Mineralizer (base/precipitant) molar concentration in mol/L. "
                    "Mineralizers: NaOH, KOH, NH4OH, urea, HMTA, Na2CO3, NaHCO3, etc. "
                    "Formula: same as ce_concentration_M — mmol / final_volume_mL * 1000. "
                    "null if only wt%, drops, or excess amount given."
                ),
                "synthesis_volume_mL": _nullable_num(
                    "Total reaction solution volume in mL. "
                    "'50 mL autoclave'→50. Total volume, not single-reagent volume."
                ),
                "capping_agent": _nullable_str(
                    "Particle size/shape control molecule: PVP, PEG, CTAB, SDS, "
                    "oleic acid, oleylamine, citric acid (as capping), sodium citrate, "
                    "Tween 20/80, Triton X-100. As written in paper."
                ),
                "chelating_agent": _nullable_str(
                    "Ce-ion chelating molecule: EDTA, glycine, oxalic acid, DTPA, NTA, "
                    "acetylacetone, citric acid (as chelating). "
                    "Citric acid/EDTA: check described role."
                ),
                "atmosphere": _nullable_str(
                    "Gas atmosphere during synthesis or calcination: "
                    "air, N2, Ar, O2, vacuum, H2/Ar, NH3, CO2. "
                    "Do NOT assume 'air' if not stated."
                ),
                "calcination_temperature_c": _nullable_num(
                    "Post-synthesis heat treatment in °C. "
                    "'calcined/annealed/sintered at X°C'. "
                    "Multiple steps: highest temperature."
                ),
                "crystallite_size_xrd_nm": _nullable_num(
                    "XRD Scherrer crystallite size in nm. "
                    "'crystallite size X nm', 'D=X nm (Scherrer)', 'grain size X nm from XRD'. "
                    "Do NOT use BET equivalent diameter or TEM/SEM particle size here."
                ),
                "synthesis_time_h": _nullable_num(
                    "Synthesis/reaction duration in HOURS. Convert if needed: "
                    "30 min→0.5, 90 min→1.5, 2 days→48. "
                    "Hydrothermal/solvothermal: time inside autoclave. "
                    "Precipitation: stirring/aging time after mixing. "
                    "Do NOT include drying or calcination time. null if not stated."
                ),
                "morphology": {
                    "anyOf": [
                        {
                            "type": "string",
                            "enum": [
                                "sphere", "cube", "rod", "wire", "tube",
                                "flower", "plate", "octahedron",
                                "porous", "hollow", "dendrite", "fiber", "other",
                            ],
                        },
                        {"type": "null"},
                    ],
                    "description": (
                        "Primary nanoparticle shape from TEM/SEM images or paper description. "
                        "sphere=equiaxed nanoparticles; cube=nanocube/cubic; "
                        "rod=elongated aspect ratio>3; wire=nanowire/nanofiber (AR>>10); "
                        "tube=hollow 1D nanotube; flower=hierarchical flower-like assembly; "
                        "plate=nanoplate/nanosheet/2D; octahedron=8-faced polyhedral; "
                        "porous=mesoporous/nanoporous with visible pores; "
                        "hollow=core-shell or nanocage; dendrite=branched tree-like; "
                        "fiber=fiber/strand morphology; other=described but doesn't fit above. "
                        "null if shape is not described anywhere in the paper."
                    ),
                },
            },
        },
    },
}

# ── 유저 프롬프트 ────────────────────────────────────────────────────────────────
USER_PROMPT = """\
From this CeO2 synthesis paper, extract the 15 synthesis fields using the extract_synthesis_data tool.

SEARCH LOCATIONS:
- Experimental section: synthesis_method, ce_precursor, solvent, synthesis_temperature_c,
  ph_synthesis, ce_concentration_M, mineralizer_concentration_M, synthesis_volume_mL,
  capping_agent, chelating_agent, atmosphere, calcination_temperature_c, synthesis_time_h
- Results/Characterization section: crystallite_size_xrd_nm (XRD/Scherrer equation),
  morphology (TEM/SEM image description or caption)

CRITICAL RULES:
1. crystallite_size_xrd_nm — XRD Scherrer only. REJECT BET equivalent diameter or TEM/SEM size.
2. DLS/hydrodynamic size is NOT particle size — reject any value labeled:
   z-average, hydrodynamic diameter, dynamic size, apparent diameter, Zetasizer, NanoSight,
   PDI, z-size, effective diameter. Use null if only DLS values are available.
3. Concentration: use final reaction volume (total solution), not just added solvent volume.
4. synthesis_time_h: reaction/hydrothermal time only — exclude drying and calcination time.
5. ce_precursor: Ce compound only — exclude dopant salts, noble metals, supports, organics.

EXAMPLE (abbreviated — only non-null fields shown):
  synthesis_method: "hydrothermal"
  ce_precursor: "Ce(NO3)3·6H2O"
  solvent: "water"
  synthesis_temperature_c: 180
  synthesis_time_h: 12
  ph_synthesis: 9.0
  ce_concentration_M: 0.1
  mineralizer_concentration_M: 2.0
  synthesis_volume_mL: 50
  capping_agent: "PVP"
  calcination_temperature_c: 500
  crystallite_size_xrd_nm: 8.5
  morphology: "rod"

Paper text:
{text}"""


def _safe_doi(doi: str) -> str:
    return doi.replace("/", "_").replace(":", "_").replace(" ", "_")


def _is_empty(val) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return True
    return str(val).strip().lower() in _BAD


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict, lock: threading.Lock):
    with lock:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_snippet(text: str) -> str:
    """Experimental + Results 섹션 우선 추출 (최대 8000자).

    - Experimental 섹션: synthesis_method, ce_precursor, solvent, temperature, pH, concentration, volume,
      capping_agent, chelating_agent, atmosphere, calcination_temperature_c
    - Results/Characterization 섹션: crystallite_size_xrd_nm (Scherrer), 기타 측정값
    """
    lower = text.lower()

    exp_chunk = ""
    for kw in ["experimental", "materials and methods", "synthesis of",
               "preparation of", "sample preparation", "nanoparticle synthesis"]:
        idx = lower.find(kw)
        if idx != -1:
            start = max(0, idx - 50)
            exp_chunk = text[start:start + 5000]
            break
    if not exp_chunk:
        exp_chunk = text[:4000]

    # Results/Characterization 섹션 — crystallite size, BET 등 측정값 위치
    res_chunk = ""
    for kw in ["results", "characterization", "discussion", "xrd", "x-ray diffraction",
               "scherrer", "crystallite size", "bet surface"]:
        idx = lower.find(kw)
        if idx != -1:
            start = max(0, idx - 50)
            res_chunk = text[start:start + 2000]
            break

    tail = text[-500:] if len(text) > 500 else ""
    return exp_chunk + ("\n\n--- RESULTS ---\n" + res_chunk if res_chunk else "") + "\n\n" + tail


def call_gpt(text: str, client) -> dict:
    snippet = _extract_snippet(text)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": USER_PROMPT.format(text=snippet)},
        ],
        temperature=0,
        max_tokens=700,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "extract_synthesis_data"}},
    )
    tool_calls = resp.choices[0].message.tool_calls
    if not tool_calls:
        return {}
    return json.loads(tool_calls[0].function.arguments)


def process_one(doi: str, cache: dict, cache_lock: threading.Lock, client) -> tuple:
    """단일 DOI 처리. (doi, result_or_None) 반환."""
    with cache_lock:
        if doi in cache:
            return doi, cache[doi]

    txt_path = TEXT / f"{_safe_doi(doi)}.txt"
    try:
        text = txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        with cache_lock:
            cache[doi] = {}
        return doi, {}

    if len(text.strip()) < 200:
        with cache_lock:
            cache[doi] = {}
        return doi, None  # None = 텍스트 짧아 스킵

    # 재시도 (rate limit 대응: 최대 4회, 지수 백오프)
    for attempt in range(4):
        try:
            result = call_gpt(text, client)
            with cache_lock:
                cache[doi] = result
            return doi, result
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str or "limit" in err_str:
                wait = 2 ** attempt   # 1s → 2s → 4s → 8s
                time.sleep(wait)
            else:
                with cache_lock:
                    cache[doi] = {}
                return doi, {}

    with cache_lock:
        cache[doi] = {}
    return doi, {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--reset",    action="store_true")
    parser.add_argument("--limit",    type=int, default=0)
    parser.add_argument("--workers",  type=int, default=20,
                        help="병렬 API 호출 수 (기본 20, 최대 권장 40)")
    args = parser.parse_args()

    # ── CSV 로드 ──────────────────────────────────────────────────────────────
    if not CSV.exists():
        print(f"CSV 없음: {CSV}"); sys.exit(1)
    df = pd.read_csv(CSV, dtype=str, low_memory=False)
    print(f"CSV 로드: {len(df):,}행 / {df['doi'].nunique() if 'doi' in df.columns else '?'}편")

    for field in TARGET_FIELDS:
        if field not in df.columns:
            df[field] = None
            print(f"  신규 컬럼 추가: {field}")

    # ce_precursor="CeO2" 의심값 초기화 (31차+ 진단: 프롬프트 CeO2 화이트리스트 버그로
    # 실제 전구체 대신 최종 생성물명이 대신 들어간 오분류, 원문대조 검증됨) → 재추출 대상 편입
    if "ce_precursor" in df.columns:
        suspect = df["ce_precursor"].astype(str).str.strip() == "CeO2"
        n_suspect = int(suspect.sum())
        if n_suspect:
            df.loc[suspect, "ce_precursor"] = None
            print(f"  ce_precursor='CeO2' 의심값 {n_suspect:,}행 초기화 (재추출 대상 편입)")

    # ── 대상 DOI 선정 ─────────────────────────────────────────────────────────
    missing_per_field = {}
    target_mask = pd.Series(False, index=df.index)
    for field in TARGET_FIELDS:
        m = df[field].apply(_is_empty)
        missing_per_field[field] = int(m.sum())
        target_mask |= m

    print("\n현재 빈 행 수:")
    for f, n in missing_per_field.items():
        print(f"  {f:<30} {n:>5,}행  ({n/len(df)*100:.1f}%)")

    if "doi" not in df.columns:
        print("doi 컬럼 없음"); sys.exit(1)

    missing_dois_set = set(df.loc[target_mask, "doi"].dropna().tolist())
    target_dois = sorted(
        d for d in missing_dois_set if (TEXT / f"{_safe_doi(d)}.txt").exists()
    )

    est_min = len(target_dois) / (min(args.workers, 40) * 4.5)   # ~4.5 req/s per TPM limit
    print(f"\n대상 논문: {len(target_dois):,}편  (전문 보유 + 7개 필드 중 하나 이상 빈값)")
    print(f"예상 비용: ~${len(target_dois) * 0.0007:.2f}")
    print(f"예상 시간: ~{est_min:.0f}분  ({args.workers} workers)")

    if args.dry_run:
        print("\n[샘플 대상 DOI]")
        for d in target_dois[:5]:
            row = df[df["doi"] == d].iloc[0]
            print(f"  {d[:50]}")
            for f in TARGET_FIELDS:
                status = "빈값" if _is_empty(row.get(f)) else str(row.get(f, ""))[:30]
                print(f"    {f}: {status}")
        print("\n--dry-run 모드 종료")
        return

    # ── OpenAI 클라이언트 ─────────────────────────────────────────────────────
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("OPENAI_API_KEY 없음"); sys.exit(1)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except ImportError:
        print("pip install openai 필요"); sys.exit(1)

    cache = {} if args.reset else load_cache()
    if args.reset:
        print("캐시 초기화됨")

    if args.limit:
        target_dois = target_dois[:args.limit]
        print(f"--limit {args.limit} 적용")

    total      = len(target_dois)
    cache_lock = threading.Lock()
    print_lock = threading.Lock()
    counter    = {"done": 0, "errors": 0, "skipped": 0}

    # 결과를 모아 마지막에 DataFrame에 일괄 반영
    all_results: dict = {}   # doi → result_dict

    print(f"\n추출 시작: {total}편  [{args.workers} workers]\n")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_one, doi, cache, cache_lock, client): doi
            for doi in target_dois
        }
        for future in as_completed(futures):
            doi, result = future.result()
            counter["done"] += 1

            if result is None:
                counter["skipped"] += 1
            elif result == {}:
                counter["errors"] += 1
            else:
                all_results[doi] = result

            # 100편마다 캐시 저장 + 진행 출력
            if counter["done"] % 100 == 0 or counter["done"] == total:
                save_cache(cache, cache_lock)
                elapsed = time.time() - t0
                speed   = counter["done"] / elapsed * 60
                remain  = (total - counter["done"]) / (speed / 60) if speed > 0 else 0
                with print_lock:
                    print(
                        f"  [{counter['done']:>5}/{total}] "
                        f"추출 {len(all_results):,}편 | "
                        f"오류 {counter['errors']} | "
                        f"스킵 {counter['skipped']} | "
                        f"{speed:.0f}편/분 | "
                        f"잔여 ~{remain/60:.1f}분"
                    )

    save_cache(cache, cache_lock)

    # ── DataFrame에 결과 반영 ─────────────────────────────────────────────────
    updated_rows = {f: 0 for f in TARGET_FIELDS}
    for doi, result in all_results.items():
        doi_mask = df["doi"] == doi
        for field in TARGET_FIELDS:
            val = result.get(field)
            if val is not None and not _is_empty(str(val)):
                row_mask = doi_mask & df[field].apply(_is_empty)
                if row_mask.any():
                    df.loc[row_mask, field] = str(val).strip()
                    updated_rows[field] += int(row_mask.sum())

    # ── CSV 저장 ──────────────────────────────────────────────────────────────
    tmp = str(CSV).replace(".csv", "_tmp.csv")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, str(CSV))

    # ── 결과 요약 ─────────────────────────────────────────────────────────────
    elapsed_total = time.time() - t0
    print("\n" + "=" * 60)
    print(f"완료: {total}편 처리 | {elapsed_total/60:.1f}분 소요")
    print(f"      오류 {counter['errors']} | 텍스트 짧아 스킵 {counter['skipped']}")
    print("\n필드별 채움 결과:")
    for field in TARGET_FIELDS:
        before = missing_per_field[field]
        after  = int(df[field].apply(_is_empty).sum()) if field in df.columns else before
        gained = before - after
        print(f"  {field:<30} +{gained:>4}행  (잔여 빈값: {after:,})")
    print(f"\n저장: {CSV}")
    print("\n다음 단계:")
    print("  python 5_table_extract.py")
    print("  python 6_fill_keywords.py ~ python 12_model.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
