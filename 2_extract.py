"""
샘플별 합성조건 → 결과 매칭 추출기 (개선판 — function calling strict=True)

논문 내 여러 샘플(시편)을 식별하고, 각 샘플의 합성조건과 측정결과를 1:1 매칭.
OpenAI function calling strict=True 사용. 병렬 20workers. 재시작 가능 (캐시 기반).

출력:
  output/ceria_samples.jsonl           — 샘플 1개 = 1행
  output/sample_extraction_cache.json  — 진행 상황 (재시작용)

CMD:
  python 2_extract.py                  # 전체 실행 (미완료 논문만)
  python 2_extract.py --limit 20       # 20편만 테스트
  python 2_extract.py --dry-run        # API 호출 없이 대상만 확인
  python 2_extract.py --reset          # 캐시 초기화 + 전체 재추출 (~$6, ~15분)
  python 2_extract.py --model gpt-4o   # 고정밀 모드 (10× 비용 — 중요 논문 재추출용)
  python 2_extract.py --workers 10     # 동시 처리 수 조정
"""

import os, sys, json, re, time, argparse, csv, threading
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

BASE_DIR   = r"d:\머신러닝 교육\ceria_pipeline_data"
TEXT_DIR   = os.path.join(BASE_DIR, "text")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
XLSX_PATH  = os.path.join(OUTPUT_DIR, "ceria_synthesis_database.xlsx")
OUT_JSONL  = os.path.join(OUTPUT_DIR, "ceria_samples.jsonl")
OUT_CSV    = os.path.join(OUTPUT_DIR, "ceria_samples.csv")
CACHE_PATH = os.path.join(OUTPUT_DIR, "sample_extraction_cache.json")

CSV_COLUMNS = [
    "doi", "title", "sample_id", "discriminator", "confidence",
    "conditions_evidence", "results_evidence",
    # materials
    "ce_precursor", "solvent", "mineralizer", "capping_agent",
    "chelating_agent", "oxidant", "dopant", "dopant_concentration_mol_pct",
    # procedure
    "synthesis_method", "synthesis_temperature_c", "synthesis_time_h",
    "ph_synthesis", "atmosphere", "calcination_temperature_c",
    "calcination_time_h", "drying_temperature_c",
    # characterization
    "particle_size_tem_nm", "particle_size_sem_nm", "crystallite_size_xrd_nm",
    "bet_surface_area_m2g", "morphology", "crystal_phase",
]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SAVE_INTERVAL  = 50   # N편마다 캐시 저장

# ── CLI ──────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--limit",   type=int, default=0,
                help="처리할 최대 논문 수 (0=전체)")
ap.add_argument("--dry-run", action="store_true",
                help="API 호출 없이 대상 논문 수·예상 비용만 출력")
ap.add_argument("--reset",   action="store_true",
                help="캐시·출력 초기화 후 전체 재추출")
ap.add_argument("--model",   default="gpt-4o-mini",
                help="OpenAI 모델 (기본: gpt-4o-mini / 고정밀: gpt-4o)")
ap.add_argument("--workers", type=int, default=20,
                help="병렬 처리 worker 수 (기본: 20)")
args = ap.parse_args() if __name__ == "__main__" else ap.parse_args([])

# ── OpenAI 초기화 ─────────────────────────────────────────────────────────────
if __name__ == "__main__" and not args.dry_run:
    if not OPENAI_API_KEY:
        raise SystemExit("OPENAI_API_KEY가 .env에 없습니다.")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        raise SystemExit("openai 패키지 없음. 실행: pip install openai")

# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert materials scientist specializing in CeO2 (ceria) nanoparticle synthesis.

TASK: Extract ALL distinct samples and match each sample's synthesis CONDITIONS to its measured RESULTS.

━━━ KEY PRINCIPLES (READ CAREFULLY) ━━━
1. UNIT = SAMPLE (specimen), not paper. One paper → N sample objects.
2. Read "Experimental" AND "Results/Discussion" sections TOGETHER → link conditions & results in the SAME object. Never output conditions-only or results-only.
3. Samples sharing base conditions but differing in ONE variable → list each separately, COPY all shared conditions.
4. discriminator: what makes THIS sample unique vs. siblings (e.g. "[NaOH]=6M", "calcined 500°C", "x=0.1 Sm"). Use paper labels if present ("CeO2-NC", "S1"), otherwise describe the varying variable.
5. confidence: "high" if link is explicit in text, "medium" if inferred across sections, "low" if uncertain.
6. conditions_evidence / results_evidence: ≤15-word location hint (e.g. "Exp. sec. para 2, reaction temp", "Table 1 row 3").
7. null for any field not stated. Do NOT guess, interpolate, or copy from other samples.
8. Numeric: plain number, no units. For ranges use midpoint ("5–20 nm" → 12.5).
9. If no extractable synthesis data: paper_has_synthesis=false, empty samples list.
10. MAX 8 samples per paper. Prefer samples that have at least one measured particle size (TEM/SEM/XRD). If too many, prefer samples with both conditions AND results filled.

━━━ CRITICAL ACCURACY RULES — AVOID THESE COMMON ERRORS ━━━

A. PARTICLE SIZE — ACCEPT ONLY TEM/SEM DIRECT IMAGING MEASUREMENTS:
   ✓ ACCEPT: "TEM shows 15 nm particles", "HRTEM average diameter = 12 nm", "d(TEM) = 8.3 nm",
             "average particle size from SEM images = 25 nm", "FE-SEM diameter ~30 nm",
             "particle size measured from TEM micrographs"
   ✗ REJECT (use null):
     · DLS / dynamic light scattering / z-average / hydrodynamic diameter / hydrodynamic size
     · PDI / polydispersity index / autocorrelation / Zetasizer / NanoSight / PCS / QELS
     · BET equivalent diameter (calculated from surface area formula d = 6/(ρ·SSA), NOT measured)
     · Grain size from optical microscopy or EBSD
     · Crystallite size by XRD Scherrer equation → use crystallite_size_xrd_nm instead
     · Film thickness / coating thickness / shell thickness / pore diameter / wall thickness
     · Probe size / aperture size / wavelength

B. NUMBER PARSING — RANGES AND UNCERTAINTIES:
   "15 ± 2 nm"             → 15    (take the central value, ignore ±)
   "5–20 nm" / "5 to 20 nm"→ 12.5  (midpoint)
   "~15 nm" / "≈15 nm"     → 15    (drop the approximation symbol)
   "mostly 10–15 nm"       → 12.5  (midpoint of stated range)
   "15 nm (range 10–20)"   → 15    (stated mean wins over range)
   If paper provides BOTH mean and range → always take the stated mean.
   If only a range is given (no mean stated) → take the midpoint.

C. TEMPERATURE DISAMBIGUATION:
   Rule: when two temperatures appear, lower = synthesis, higher = calcination/annealing.
   "hydrothermal at 120°C, calcined at 550°C"  → synth=120, calc=550
   "refluxed 80°C for 2h, then annealed 600°C" → synth=80, calc=600
   "dried at 80°C overnight, calcined at 500°C" → drying=80, calc=500
   "dried 120°C, then 500°C calcination"        → drying=120, calc=500
   Room temperature (25°C) → record ONLY if paper explicitly says "synthesis at RT/room temperature".
   Microwave power (W) is NOT a temperature — leave synthesis_temperature_c null unless °C is stated.

D. SYNTHESIS METHOD — EXACT DISAMBIGUATION:
   combustion:             fuel (glycine/urea/citric acid/PVA) + Ce(NO3)3 → ignition / auto-combustion / self-propagating step
   precipitation:          urea or HMTA decomposed slowly at 80–100°C for homogeneous precipitation (NO ignition)
   green_synthesis:        plant extract / algae / fungus / bacteria is the PRIMARY reducing or capping agent
                           ⚠ NOT green_synthesis if extract is just a minor additive to a hydrothermal step
   impregnation:           Ce solution absorbed into porous support (Al2O3/SiO2/TiO2/activated carbon) → dried → calcined
   deposition_precipitation: precipitant (NaOH/urea) added to a support suspension containing Ce salt
   microemulsion:          synthesis inside W/O or O/W micelle/reverse-micelle system (AOT, CTAB with oil phase)
   microwave:              microwave (MW) is the PRIMARY heating energy — "microwave-assisted hydrothermal" → "microwave"
   sol-gel:                alkoxide/acetate hydrolysis → gel formation; Pechini / polymeric precursor route
   template:               hard template (SBA-15/MCM-41/AAO/PS sphere) OR soft template (vesicle/liquid crystal)

E. PRECURSOR FIELD ACCURACY:
   ce_precursor = ONLY the cerium compound (Ce source). Never include solvent or mineralizer.
   If Ce(NO3)3·6H2O dissolved in ethanol → ce_precursor="Ce(NO3)3·6H2O", solvent="ethanol"
   ⚠ CeO2 is almost always the TARGET PRODUCT being synthesized/characterized, NOT the starting
     reagent — it appears constantly throughout every paper. Do NOT default to "CeO2" just because
     the actual precursor salt wasn't found nearby. Only use ce_precursor="CeO2" if the paper
     EXPLICITLY states that pre-made/commercial CeO2 powder was redissolved, redispersed, or used
     as a raw material feedstock for further processing (rare). If no such explicit statement exists
     and no other Ce salt is mentioned, use null instead of "CeO2".
   Dopant precursors (Gd(NO3)3, La(NO3)3, Sm(NO3)3) → dopant field only, NOT ce_precursor
   Ce(NO3)3 and (NH4)2Ce(NO3)6 are ALWAYS ce_precursor, NEVER oxidant
   H2O2 added separately to oxidize Ce³⁺ → Ce⁴⁺ → oxidant

F. CROSS-SECTION LINKING — MOST IMPORTANT:
   ✓ If a TABLE lists multiple samples with conditions AND sizes → each row = one sample (up to 8)
   ✓ If paper varies ONE parameter (pH/temp/concentration) → each value = one sample
   ✓ Read figure captions: "Fig. 3a: TEM of sample A (10 nm)" → link to sample A's conditions
   ✗ Do NOT create a sample if you cannot find BOTH at least one condition AND one characterization result
   Exception: allowed if paper truly lacks one side; use confidence="low" in that case

━━━ FIELD DEFINITIONS ━━━
- ce_precursor    : Cerium source used to synthesize CeO2. Return standardized formula or name.
  · Nitrate: "Ce(NO3)3·6H2O"  (= cerium nitrate, cerous nitrate, cerium(III) nitrate hexahydrate)
  · CAN:     "(NH4)2Ce(NO3)6" (= ceric ammonium nitrate, ammonium cerium(IV) nitrate, "CAN")
  · Chloride: "CeCl3·7H2O"   (= cerium(III) chloride, cerous chloride)
  · Acetate: "Ce(CH3COO)3"   (= Ce(OAc)3, cerium(III) acetate, cerous acetate)
  · Sulfate: "Ce2(SO4)3", "Ce(SO4)2"   Carbonate: "Ce2(CO3)3"   Oxalate: "Ce2(C2O4)3"
  · Sol-gel precursors: "Ce(acac)3", "Ce(OiPr)4" (cerium isopropoxide), "Ce(OEt)4"
  · Other: "Ce(OH)3", "CeF3"
  · "CeO2" ONLY if explicitly redissolved/redispersed as a raw feedstock (rare) — NEVER as a
    default guess when the actual starting salt is unclear (CeO2 is the product, not a reagent).
  Output: canonical formula or abbreviation. null if not stated.

- solvent         : Main liquid medium for CeO2 synthesis. Mixed → semicolon-separated ("water;ethanol").
  · Aqueous: "water"  (deionized water, distilled water, H2O → always "water")
  · Alcohols: "ethanol", "methanol", "isopropanol", "n-butanol", "2-methoxyethanol"
  · Polyols: "ethylene glycol", "diethylene glycol", "glycerol", "propylene glycol"
    ⚠ PEG is a capping agent, NOT a solvent — put it in capping_agent
  · Polar aprotic: "DMF", "DMSO", "NMP", "acetone", "THF"
  · Nonpolar: "toluene", "xylene", "hexane", "1-octadecene"
  · Other: "oleylamine", "benzyl alcohol", "ionic liquid"
  ⚠ Acetic acid and citric acid are chelating agents, NOT solvents — put them in chelating_agent
  null if not stated.

- mineralizer : OH⁻ source / pH-raising precipitant for solution synthesis.
  Return CANONICAL LABEL. If multiple present → semicolon-separated (e.g. "NaOH; Na2CO3").
  ⚠ Urea or glycine as COMBUSTION FUEL (auto-ignition step) → NOT mineralizer; put in chelating_agent
  ⚠ Triethanolamine/diethanolamine as SURFACTANT → put in capping_agent instead

  Canonical labels:
  "NaOH" | "KOH" | "LiOH" | "NH3" (= NH4OH, ammonium hydroxide, aqueous ammonia)
  "Urea" (homogeneous precipitation only, NOT combustion fuel)
  "HMTA" (= hexamethylenetetramine, hexamine, HMT)
  "TMAH" (= tetramethylammonium hydroxide)
  "Na2CO3" | "NaHCO3" | "NH4HCO3" | "(NH4)2CO3"
  "Na2C2O4" (sodium oxalate) | "(NH4)2C2O4" (ammonium oxalate)
  "TEA" (triethanolamine, as pH agent) | "DEA" (diethanolamine, as pH agent)
  "MEA" (monoethanolamine, as pH agent) | "NaOAc" (sodium acetate, mild base)

- capping_agent : stabilizer/surfactant/polymer controlling particle size and shape.
  Return CANONICAL LABEL. If multiple → semicolon-separated.
  ⚠ PEG is a capping agent, NOT a solvent

  Canonical labels:
  "PVP" (polyvinylpyrrolidone, PVP-K30/K40) | "PEG" (polyethylene glycol, PEG-200/400/1000/4000)
  "PVA" (polyvinyl alcohol) | "CTAB" | "CTAC" | "SDS" (sodium dodecyl sulfate)
  "SDBS" | "Tween-80" | "Tween-20" | "Span-80" | "Triton X-100"
  "Pluronic P123" | "Pluronic F127" | "Gelatin"
  "Oleic acid" | "Oleylamine" | "Citrate" (citric acid/citrate as surfactant/stabilizer)
  "DEA" / "TEA" (when used as surfactant/template, not pH agent)

- chelating_agent : complexing agent for controlled nucleation/gelation.
  Return CANONICAL LABEL. If multiple → semicolon-separated.
  ⚠ Citric acid as chelating agent even in combustion synthesis (forms Ce complex before ignition)
  ⚠ Glycine as chelating agent even in combustion (unless trivial aqueous mixing)

  Canonical labels:
  "EDTA" | "Citric acid" | "Acetylacetone" (= acac, Hacac)
  "Glycine" (also combustion fuel) | "PVA" (Pechini/polymeric precursor method)
  "Oxalic acid" | "Tartaric acid" | "Malic acid" | "Lactic acid"
  "NTA" (nitrilotriacetic acid) | "DTPA" | "EDA" (ethylenediamine)
  "Glucose" | "Sucrose" | "Starch"

- oxidant : explicitly added oxidizing agent to promote CeO2 formation.
  ⚠ Do NOT list Ce(NO3)3 or (NH4)2Ce(NO3)6 as oxidant — those are ce_precursor
  Canonical labels: "H2O2" | "HNO3" | "H2SO4" | "KMnO4" | "(NH4)2S2O8" | "O3" | "NaClO"

- synthesis_method: Choose EXACTLY ONE from this closed list:
  hydrothermal          = water + sealed autoclave, 80–250°C (>100°C typical)
  solvothermal          = organic solvent + sealed autoclave, 80–300°C
  sol-gel               = alkoxide/acetate hydrolysis, gel network formation, Pechini/polymeric precursor
  precipitation         = aqueous mixing of ONE Ce salt + precipitant (NaOH/NH3 etc.), no autoclave
  co-precipitation      = TWO or more metal salts precipitated together (Ce + dopant precursor)
  combustion            = fuel (glycine, urea, citric acid, PVA) + nitrate oxidizer → self-ignition/rapid heating
  spray_pyrolysis       = aerosol/spray of precursor solution into hot furnace
  microwave             = microwave radiation as PRIMARY energy source (incl. microwave-hydrothermal)
  template              = hard template (SBA-15, AAO, PS sphere) or soft template (micelle, vesicle)
  thermal_decomposition = solid/liquid precursor thermally decomposed (no solvent synthesis step, just calcination)
  mechanochemical       = ball milling, high-energy milling as primary synthesis step
  sonochemical          = ultrasound as primary energy source
  wet_chemical          = aqueous/solution mixing without autoclave, not strictly precipitation
  impregnation          = Ce solution impregnated onto support (Al2O3/SiO2/TiO2) → calcined
  electrodeposition     = electrochemical deposition of Ce oxide onto electrode surface
  flame_spray           = flame spray pyrolysis (FSP), aerosol flame synthesis
  deposition_precipitation = precipitant added to support suspension containing Ce precursor
  microemulsion         = water-in-oil or oil-in-water micelle/reverse-micelle synthesis
  green_synthesis       = plant extract / biological route as PRIMARY reducing/capping agent
  other                 = anything that does not fit above

━━━ NUMERIC FIELDS — CRITICAL RULES ━━━
- particle_size_tem_nm : PRIMARY particle size measured by TEM/HRTEM/STEM direct imaging (nm).
  ✓ Accept: "TEM image shows 15 nm", "average diameter from TEM", "d(TEM) = 12 nm", "HRTEM = 8.3 nm"
  ✗ EXCLUDE: DLS, dynamic light scattering, hydrodynamic diameter, z-average, z-size, PDI,
             laser diffraction, BET equivalent diameter, pore size, film thickness,
             crystallite size from XRD (→ crystallite_size_xrd_nm). null if method is unspecified.
  Range/uncertainty: "15 ± 2 nm" → 15. "5–20 nm" → 12.5. "~15 nm" → 15.
  Take the AVERAGE/MEAN value if explicitly stated. Valid range: 0.5–500 nm.

- particle_size_sem_nm : PRIMARY particle size from SEM/FE-SEM/FESEM direct imaging (nm).
  Same exclusion rules as particle_size_tem_nm. Valid range: 0.5–500 nm.

- crystallite_size_xrd_nm : Crystallite size from XRD Scherrer equation or Rietveld refinement (nm).
  ✓ Accept: "Scherrer equation", "XRD peak broadening", "D_XRD", "crystallite size by XRD"
  ✗ EXCLUDE: grain/particle size from SEM/TEM, BET equivalent spherical diameter.
  ⚠ BET equivalent diameter (d = 6/(ρ·SSA)) is NOT a crystallite size — put null here.
  Valid range: 0.5–200 nm.

- synthesis_temperature_c : Temperature DURING the synthesis reaction (°C).
  ✓ Accept: hydrothermal temperature, reaction temperature, reflux temperature
  ✗ EXCLUDE: calcination/annealing temperature, drying temperature
  ✗ EXCLUDE: room temperature (25°C) UNLESS paper explicitly states "RT synthesis" or "at room temperature"
  Valid range: 20–500°C.

- calcination_temperature_c : Post-synthesis annealing/calcination/sintering temperature (°C).
  ✓ Key words: "calcined at", "annealed at", "sintered at", "heated to", "fired at"
  ✗ EXCLUDE: drying temperature (<200°C before calcination), synthesis temperature.
  Rule: two temperatures → lower is synthesis, higher is calcination.
  Valid range: 150–1600°C.

- drying_temperature_c : Pre-calcination drying temperature in oven (°C).
  ✓ Key words: "dried at", "dried in oven at", "dried overnight at"
  Typically 60–150°C. Valid range: 40–250°C.

- atmosphere : Gas environment during synthesis or calcination.
  Return ONE of: "air" | "N2" | "Ar" | "O2" | "H2" | "H2/N2" | "NH3" | "vacuum" | "inert" | null
  Prefer the calcination atmosphere if synthesis atmosphere is not mentioned.

- crystal_phase : Crystallographic phase identified by XRD or other techniques.
  Common values: "fluorite cubic", "Ce2O3", "amorphous", "pyrochlore", "mixed"
  Use short standard names. null if not mentioned.

- morphology : Particle shape from TEM/SEM images.
  sphere=round/equiaxed | cube=cubic | rod=elongated 1D (AR>3) | wire=nanowires/nanofibers
  flower=hierarchical | octahedron=8-faced polyhedral | plate=thin 2D (nanoplates/nanosheets)
  porous=particles with internal pores | hollow=shell particles (hollow spheres/nanocages)
  other=any other morphology | null if shape not characterized"""

USER_TEMPLATE = "Title: {title}\n\nText:\n{text}"

# ── Function calling 스키마 (strict=True) ─────────────────────────────────────
_METHOD_ENUM = [
    "hydrothermal", "solvothermal", "sol-gel", "precipitation", "co-precipitation",
    "combustion", "spray_pyrolysis", "microwave", "template", "thermal_decomposition",
    "mechanochemical", "sonochemical", "wet_chemical",
    "impregnation", "electrodeposition", "flame_spray",
    "deposition_precipitation", "microemulsion", "green_synthesis", "other",
]
_MORPH_ENUM = ["sphere", "cube", "rod", "wire", "flower", "octahedron", "plate", "porous", "hollow", "other"]
_ATMO_ENUM  = ["air", "N2", "Ar", "O2", "H2", "H2/N2", "NH3", "vacuum", "inert"]

def _nullable(t):
    return {"anyOf": [{"type": t}, {"type": "null"}]}

def _nullable_enum(values):
    return {"anyOf": [{"type": "string", "enum": values}, {"type": "null"}]}

EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_synthesis_samples",
        "strict": True,
        "description": "Extract all distinct CeO2 synthesis samples from the paper, linking synthesis conditions to measured results.",
        "parameters": {
            "type": "object",
            "required": ["paper_has_synthesis", "samples"],
            "additionalProperties": False,
            "properties": {
                "paper_has_synthesis": {
                    "type": "boolean",
                    "description": "True if the paper reports CeO2 synthesis experiments."
                },
                "samples": {
                    "type": "array",
                    "description": "One object per distinct sample. Empty list if paper_has_synthesis=false.",
                    "items": {
                        "type": "object",
                        "required": ["sample_id", "discriminator", "confidence",
                                     "conditions_evidence", "results_evidence",
                                     "materials", "procedure", "characterization"],
                        "additionalProperties": False,
                        "properties": {
                            "sample_id":           {"type": "string"},
                            "discriminator":       {"type": "string"},
                            "confidence":          {"type": "string", "enum": ["high", "medium", "low"]},
                            "conditions_evidence": {"type": "string"},
                            "results_evidence":    {"type": "string"},
                            "materials": {
                                "type": "object",
                                "required": ["ce_precursor", "solvent", "mineralizer",
                                             "capping_agent", "chelating_agent", "oxidant",
                                             "dopant", "dopant_concentration_mol_pct"],
                                "additionalProperties": False,
                                "properties": {
                                    "ce_precursor":                 _nullable("string"),
                                    "solvent":                      _nullable("string"),
                                    "mineralizer":                  _nullable("string"),
                                    "capping_agent":                _nullable("string"),
                                    "chelating_agent":              _nullable("string"),
                                    "oxidant":                      _nullable("string"),
                                    "dopant":                       _nullable("string"),
                                    "dopant_concentration_mol_pct": _nullable("number"),
                                },
                            },
                            "procedure": {
                                "type": "object",
                                "required": ["synthesis_method", "synthesis_temperature_c",
                                             "synthesis_time_h", "ph_synthesis", "atmosphere",
                                             "calcination_temperature_c", "calcination_time_h",
                                             "drying_temperature_c"],
                                "additionalProperties": False,
                                "properties": {
                                    "synthesis_method":          _nullable_enum(_METHOD_ENUM),
                                    "synthesis_temperature_c":   _nullable("number"),
                                    "synthesis_time_h":          _nullable("number"),
                                    "ph_synthesis":              _nullable("number"),
                                    "atmosphere":                _nullable_enum(_ATMO_ENUM),
                                    "calcination_temperature_c": _nullable("number"),
                                    "calcination_time_h":        _nullable("number"),
                                    "drying_temperature_c":      _nullable("number"),
                                },
                            },
                            "characterization": {
                                "type": "object",
                                "required": ["particle_size_tem_nm", "particle_size_sem_nm",
                                             "crystallite_size_xrd_nm", "bet_surface_area_m2g",
                                             "morphology", "crystal_phase"],
                                "additionalProperties": False,
                                "properties": {
                                    "particle_size_tem_nm":    _nullable("number"),
                                    "particle_size_sem_nm":    _nullable("number"),
                                    "crystallite_size_xrd_nm": _nullable("number"),
                                    "bet_surface_area_m2g":    _nullable("number"),
                                    "morphology":              _nullable_enum(_MORPH_ENUM),
                                    "crystal_phase":           _nullable("string"),
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

# ── 후처리 검증 ───────────────────────────────────────────────────────────────
_VALID_METHODS = set(_METHOD_ENUM)
_VALID_MORPHS  = set(_MORPH_ENUM)
_VALID_ATMO    = {a.lower() for a in _ATMO_ENUM}
_NULL_STRINGS  = {
    "", "null", "none", "n/a", "na", "nan", "unknown",
    "not stated", "not reported", "not mentioned", "not specified",
    "not found", "not available", "not applicable", "not given",
}

def _clean_str(v):
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    stripped = v.strip()
    return None if stripped.lower() in _NULL_STRINGS else stripped

def _clamp_num(v, lo, hi):
    if v is None:
        return None
    try:
        fv = float(v)
        return fv if lo <= fv <= hi else None
    except (TypeError, ValueError):
        return None

def _validate_sample(s: dict) -> dict:
    if not isinstance(s, dict):
        return s
    mat  = s.get("materials")  or {}
    proc = s.get("procedure")  or {}
    char = s.get("characterization") or {}

    for field in ("ce_precursor", "solvent", "mineralizer",
                  "capping_agent", "chelating_agent", "oxidant", "dopant"):
        mat[field] = _clean_str(mat.get(field))
    mat["dopant_concentration_mol_pct"] = _clamp_num(
        mat.get("dopant_concentration_mol_pct"), 0.0, 100.0)

    proc["synthesis_temperature_c"]   = _clamp_num(proc.get("synthesis_temperature_c"),   20,   500)
    proc["calcination_temperature_c"] = _clamp_num(proc.get("calcination_temperature_c"), 150, 1600)
    proc["drying_temperature_c"]      = _clamp_num(proc.get("drying_temperature_c"),       40,  250)
    proc["synthesis_time_h"]          = _clamp_num(proc.get("synthesis_time_h"),          0.01, 2400)
    proc["calcination_time_h"]        = _clamp_num(proc.get("calcination_time_h"),        0.01,  240)
    proc["ph_synthesis"]              = _clamp_num(proc.get("ph_synthesis"),              0.0,  14.0)

    sm = _clean_str(proc.get("synthesis_method"))
    proc["synthesis_method"] = (sm if sm and sm.lower() in _VALID_METHODS else
                                sm.lower() if sm else None)

    atm = _clean_str(proc.get("atmosphere"))
    proc["atmosphere"] = atm  # 비표준도 보존

    char["particle_size_tem_nm"]    = _clamp_num(char.get("particle_size_tem_nm"),    0.3, 500)
    char["particle_size_sem_nm"]    = _clamp_num(char.get("particle_size_sem_nm"),    0.3, 500)
    char["crystallite_size_xrd_nm"] = _clamp_num(char.get("crystallite_size_xrd_nm"), 0.3, 200)
    char["bet_surface_area_m2g"]    = _clamp_num(char.get("bet_surface_area_m2g"),    0.1, 1500)

    mo = _clean_str(char.get("morphology"))
    char["morphology"] = mo if mo and mo.lower() in _VALID_MORPHS else ("other" if mo else None)
    char["crystal_phase"] = _clean_str(char.get("crystal_phase"))

    s["materials"]        = mat
    s["procedure"]        = proc
    s["characterization"] = char
    return s

# ── 섹션 추출 ─────────────────────────────────────────────────────────────────
_EXP_RE = re.compile(
    r'\n[ \t]*(?:\d+[\.\d]*\s*)?'
    r'(?:experimental(?:\s+(?:section|details?|procedure|part|methods?))?'
    r'|materials?\s+and\s+(?:experimental\s+)?methods?'
    r'|experimental\s+methods?'
    r'|methods?\s+(?:and\s+materials?|section)'
    r'|synthesis(?:\s+(?:and\s+characterization\s+of\s+|of\s+)[\w\s]{0,40})?'
    r'|preparation(?:\s+(?:and\s+characterization\s+of\s+|of\s+)[\w\s]{0,40})?'
    r'|sample\s+preparation|nanoparticle\s+synthesis'
    r'|synthesis\s+procedure|fabrication\s+of'
    r'|hydrothermal\s+synthesis|solvothermal\s+synthesis|sol[-\s]?gel\s+synthesis'
    r'|combustion\s+synthesis|co[-\s]?precipitation\s+synthesis)'
    r'\s*[\n:]', re.I
)
_RES_RE = re.compile(
    r'\n[ \t]*(?:\d+[\.\d]*\s*)?'
    r'(?:results?(?:\s+and\s+discussion)?'
    r'|characterization(?:\s+results?)?'
    r'|discussion(?:\s+and\s+results?)?'
    r'|structural\s+(?:and\s+)?(?:optical\s+)?characterization'
    r'|physicochemical\s+characterization)'
    r'\s*[\n:]', re.I
)
_END_RE = re.compile(
    r'\n[ \t]*(?:\d+[\.\d]*\s*)?'
    r'(?:conclusions?|summary|references?|acknowledgements?|supporting\s+information'
    r'|conflict\s+of\s+interest|author\s+contributions?|data\s+availability)'
    r'\s*\n', re.I
)

def extract_relevant_sections(text: str, max_chars: int = 16000) -> str:
    """실험 섹션 + 결과 섹션을 합쳐서 반환 (45:55 비율).
    섹션 감지 실패 시 초반 + 중반 텍스트로 폴백."""
    exp_m = _EXP_RE.search(text)
    res_m = _RES_RE.search(text)
    end_m = _END_RE.search(text)
    end_pos = end_m.start() if end_m else len(text)

    if exp_m and res_m and res_m.start() > exp_m.end():
        exp_text = text[exp_m.end(): res_m.start()].strip()
        res_text = text[res_m.end(): end_pos].strip()
        exp_alloc = int(max_chars * 0.45)
        res_alloc = max_chars - exp_alloc
        return (
            "[EXPERIMENTAL]\n" + exp_text[:exp_alloc]
            + "\n\n[RESULTS]\n" + res_text[:res_alloc]
        )

    if exp_m:
        exp_text = text[exp_m.end(): end_pos].strip()
        exp_alloc = int(max_chars * 0.6)
        tail_start = max(exp_m.end(), int(len(text) * 0.5))
        tail_text  = text[tail_start: end_pos].strip()
        return (
            "[EXPERIMENTAL]\n" + exp_text[:exp_alloc]
            + "\n\n[LATER_SECTIONS]\n" + tail_text[:max_chars - exp_alloc]
        )

    if res_m:
        res_text = text[res_m.end(): end_pos].strip()
        head_text = text[:int(max_chars * 0.4)].strip()
        return (
            "[EARLIER_TEXT]\n" + head_text
            + "\n\n[RESULTS]\n" + res_text[:int(max_chars * 0.6)]
        )

    front = text[:int(max_chars * 0.75)]
    back  = text[max(0, end_pos - int(max_chars * 0.25)): end_pos]
    return front + ("\n\n" + back if back.strip() else "")

# ── DOI → 파일명 stem ─────────────────────────────────────────────────────────
def doi_to_stem(doi) -> str:
    if not doi or pd.isna(doi):
        return ""
    return str(doi).strip().replace("/", "_").replace(":", "_").lower()

def _load_xlsx_safe(path):
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # ── 캐시 로드 ─────────────────────────────────────────────────────────────
    if args.reset:
        for p in [CACHE_PATH, OUT_JSONL, OUT_CSV]:
            if os.path.exists(p):
                os.remove(p)
        print("캐시 초기화 완료 — 전체 재추출")

    if os.path.exists(CACHE_PATH) and not args.reset:
        with open(CACHE_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
        done_dois     = set(_cache.get("done_dois", []))
        total_samples = _cache.get("total_samples", 0)
        print(f"캐시 로드: {len(done_dois):,}편 완료, 누적 {total_samples:,}개 샘플")
    else:
        done_dois     = set()
        total_samples = 0
        print("캐시 없음 — 처음부터 시작")

    # 캐시 소실 대비: 기존 CSV에서 이미 처리된 DOI 추가
    if os.path.exists(OUT_CSV) and not args.reset:
        try:
            _csv_prev = pd.read_csv(OUT_CSV, usecols=["doi"], dtype=str)
            _csv_dois = set(_csv_prev["doi"].dropna().str.strip().tolist())
            added = _csv_dois - done_dois
            if added:
                done_dois.update(added)
                print(f"  CSV 기존 DOI {len(added):,}개 → done_dois 추가 (중복 방지)")
        except Exception:
            pass

    # ── Excel 로드 + 대상 선별 ──────────────────────────────────────────────
    df = _load_xlsx_safe(XLSX_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"Excel 로드: {len(df):,}편\n")

    if not os.path.exists(TEXT_DIR):
        raise SystemExit(f"text/ 폴더가 없습니다: {TEXT_DIR}")
    txt_stems = {
        os.path.splitext(fn)[0].lower()
        for fn in os.listdir(TEXT_DIR) if fn.endswith(".txt")
    }

    targets = []
    for _, row in df.iterrows():
        doi  = str(row.get("doi", "") or "").strip()
        stem = doi_to_stem(doi)
        if stem and stem in txt_stems and doi not in done_dois:
            targets.append({
                "doi":   doi,
                "stem":  stem,
                "title": str(row.get("title", "") or ""),
            })

    if args.limit:
        targets = targets[: args.limit]

    print(f"처리 대상: {len(targets):,}편 (전문 있고 미완료)")
    cost_per_paper = 0.003 if "gpt-4o" in args.model and "mini" not in args.model else 0.0008
    est_cost = len(targets) * cost_per_paper
    print(f"모델: {args.model}  |  예상 비용: 약 ${est_cost:.2f}  |  workers: {args.workers}\n")

    if args.dry_run:
        print("--dry-run 모드 종료 (API 호출 없음)")
        raise SystemExit(0)

# ── 단일 논문 추출 함수 (병렬 실행 단위) ────────────────────────────────────
def _process_one(paper):
    """(doi, samples, is_error) 반환. samples=None은 오류, []=합성없음."""
    doi, stem, title = paper["doi"], paper["stem"], paper["title"]
    try:
        with open(os.path.join(TEXT_DIR, stem + ".txt"),
                  encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception:
        return doi, None, True

    snippet = extract_relevant_sections(raw, max_chars=16000)
    if len(snippet) < 200:
        return doi, [], False

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": USER_TEMPLATE.format(
                        title=title, text=snippet)},
                ],
                tools=[EXTRACT_TOOL],
                tool_choice={"type": "function",
                             "function": {"name": "extract_synthesis_samples"}},
                max_tokens=4096,
                temperature=0,
            )
            tc = resp.choices[0].message.tool_calls[0]
            parsed = json.loads(tc.function.arguments)
            samples = (parsed.get("samples", [])
                       if parsed.get("paper_has_synthesis", True) else [])
            return doi, samples, False
        except Exception as e:
            err_str = str(e)
            wait = 10 if ("429" in err_str or "rate" in err_str.lower()) else (2 ** attempt * 3)
            if attempt < 2:
                time.sleep(wait)
            else:
                return doi, None, True

    return doi, None, True

if __name__ == "__main__":
    # ── 추출 루프 (병렬) ──────────────────────────────────────────────────────
    _write_lock   = threading.Lock()
    _done_lock    = threading.Lock()
    new_samples   = 0
    errors        = 0
    processed     = 0

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_is_new = not os.path.exists(OUT_CSV)

    with open(OUT_JSONL, "a", encoding="utf-8") as out_f, \
         open(OUT_CSV,   "a", encoding="utf-8", newline="") as csv_f:

        csv_writer = csv.DictWriter(csv_f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if csv_is_new:
            csv_writer.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_process_one, p): p for p in targets}
            pbar    = tqdm(total=len(targets), desc="샘플 추출")

            for future in as_completed(futures):
                paper = futures[future]
                doi   = paper["doi"]
                title = paper["title"]

                try:
                    doi_r, samples, is_error = future.result()
                except Exception as e:
                    tqdm.write(f"  예외 ({doi[:40]}): {e}")
                    is_error = True
                    samples  = None

                with _done_lock:
                    done_dois.add(doi)

                if is_error:
                    with _write_lock:
                        errors += 1
                elif isinstance(samples, list) and samples:
                    # 샘플 수 상한 (8개): 입자크기 있는 샘플 우선
                    if len(samples) > 8:
                        has_ps = [s for s in samples if isinstance(s, dict) and (
                            (s.get("characterization") or {}).get("particle_size_tem_nm") or
                            (s.get("characterization") or {}).get("particle_size_sem_nm") or
                            (s.get("characterization") or {}).get("crystallite_size_xrd_nm")
                        )]
                        no_ps  = [s for s in samples if s not in has_ps]
                        samples = (has_ps + no_ps)[:8]

                    with _write_lock:
                        for s in samples:
                            if not isinstance(s, dict):
                                continue
                            s    = _validate_sample(s)
                            mat  = s.get("materials")        or {}
                            proc = s.get("procedure")        or {}
                            char = s.get("characterization") or {}
                            record = {
                                "doi":   doi,
                                "title": title,
                                "sample_id":             s.get("sample_id", "S1"),
                                "discriminator":         s.get("discriminator", ""),
                                "confidence":            s.get("confidence", "medium"),
                                "conditions_evidence":   s.get("conditions_evidence", ""),
                                "results_evidence":      s.get("results_evidence", ""),
                                "materials":             mat,
                                "procedure":             proc,
                                "characterization":      char,
                                "synthesis_conditions":  {**mat, **proc},
                            }
                            csv_row = {
                                "doi": doi, "title": title,
                                "sample_id":           record["sample_id"],
                                "discriminator":       record["discriminator"],
                                "confidence":          record["confidence"],
                                "conditions_evidence": record["conditions_evidence"],
                                "results_evidence":    record["results_evidence"],
                                **mat, **proc, **char,
                            }
                            csv_writer.writerow(csv_row)
                            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                            new_samples += 1

                        # 주기적 캐시 저장
                        processed += 1
                        if processed % SAVE_INTERVAL == 0:
                            with open(CACHE_PATH, "w", encoding="utf-8") as cf:
                                json.dump({"done_dois": list(done_dois),
                                           "total_samples": new_samples}, cf)
                            out_f.flush()
                            csv_f.flush()
                            tqdm.write(f"  [{processed:,}편] 누적 샘플 {new_samples:,}개")

                pbar.update(1)
            pbar.close()

    # 최종 캐시 저장
    with open(CACHE_PATH, "w", encoding="utf-8") as cf:
        json.dump({"done_dois": list(done_dois),
                   "total_samples": new_samples}, cf)

    print(f"\n완료!")
    print(f"  처리: {len(targets):,}편  |  신규 샘플: {new_samples:,}개  |  오류: {errors}건")
    print(f"  출력: {OUT_JSONL}")
