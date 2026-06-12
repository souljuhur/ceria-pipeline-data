"""
샘플별 합성조건 → 결과 매칭 추출기

논문 내 여러 샘플(시편)을 식별하고, 각 샘플의 합성조건과 측정결과를 1:1 매칭.
OpenAI gpt-4o-mini 사용. 재시작 가능 (캐시 기반).

출력:
  output/ceria_samples.jsonl              — 샘플 1개 = 1행
  output/sample_extraction_cache.json    — 진행 상황 (재시작용)

CMD:
  python run_sample_extraction.py
  python run_sample_extraction.py --limit 20    # 20편만 테스트
  python run_sample_extraction.py --dry-run     # API 호출 없이 대상만 확인
"""

import os, json, re, time, argparse, csv
import pandas as pd
from tqdm import tqdm
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
args = ap.parse_args()

# ── OpenAI 초기화 ─────────────────────────────────────────────────────────────
if not args.dry_run:
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
2. Read "Experimental" AND "Results/Discussion" sections TOGETHER → link conditions & results in the SAME object (cross-section linking). Never output conditions-only or results-only.
3. Samples sharing base conditions but differing in ONE variable → list each separately, COPY all shared conditions.
4. discriminator: what makes THIS sample unique vs. siblings (e.g. "[NaOH]=6M", "calcined 500°C", "x=0.1 Sm"). Use paper labels if present ("CeO2-NC", "S1"), otherwise describe the varying variable.
5. confidence: "high" if link is explicit in text, "medium" if inferred across sections, "low" if uncertain.
6. conditions_evidence / results_evidence: ≤15-word location hint (e.g. "Exp. sec. para 2, reaction temp", "Table 1 row 3").
7. null for any field not stated. Do NOT guess, interpolate, or copy from other samples.
8. Numeric: plain number, no units. For ranges use midpoint ("5–20 nm" → 12.5).
9. If no extractable synthesis data: paper_has_synthesis=false, empty samples list.
10. MAX 8 samples per paper. For combinatorial studies with many conditions, keep samples that have at least one measured particle size (TEM/SEM/XRD). If too many, prefer samples with both conditions AND results filled.

━━━ FIELD DEFINITIONS ━━━
- ce_precursor    : Cerium source used to synthesize CeO2. Return standardized formula or name.
  · Nitrate: "Ce(NO3)3·6H2O"  (= cerium nitrate, cerous nitrate, cerium(III) nitrate hexahydrate)
  · CAN:     "(NH4)2Ce(NO3)6" (= ceric ammonium nitrate, ammonium cerium(IV) nitrate, abbreviation "CAN")
  · Chloride: "CeCl3·7H2O"   (= cerium(III) chloride, cerous chloride, cerium chloride heptahydrate)
  · Acetate: "Ce(CH3COO)3"   (= Ce(OAc)3, cerium(III) acetate, cerous acetate)
  · Sulfate: "Ce2(SO4)3", "Ce(SO4)2"   Carbonate: "Ce2(CO3)3"   Oxalate: "Ce2(C2O4)3"
  · Sol-gel precursors: "Ce(acac)3", "Ce(OiPr)4" (cerium isopropoxide), "Ce(OEt)4" (cerium ethoxide)
  · Other: "CeO2" (used as starting material), "Ce(OH)3", "CeF3", "Ce(TFSI)3"
  Output: canonical formula or abbreviation. null if not stated.

- solvent         : Main liquid medium for CeO2 synthesis. Mixed → semicolon-separated ("water;ethanol").
  · Aqueous: "water"  (deionized water, distilled water, H2O, aqueous solution → always "water")
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
  ⚠ Urea or glycine as COMBUSTION FUEL (auto-ignition step) → NOT mineralizer
  ⚠ Triethanolamine/diethanolamine as SURFACTANT → put in capping_agent instead

  Canonical labels and their equivalences:
  "NaOH"        = sodium hydroxide, caustic soda, lye
  "KOH"         = potassium hydroxide, caustic potash
  "LiOH"        = lithium hydroxide
  "NH3"         = ammonia, NH3·H2O, NH4OH, ammonium hydroxide, aqueous ammonia, ammonia solution, ammonia water
  "Urea"        = CO(NH2)2, carbamide, CH4N2O [homogeneous precipitation only, NOT combustion fuel]
  "HMTA"        = hexamethylenetetramine, (CH2)6N4, hexamine, urotropine, methenamine, HMT
  "TMAH"        = tetramethylammonium hydroxide, N(CH3)4OH, (CH3)4NOH
  "Na2CO3"      = sodium carbonate, soda ash, washing soda
  "NaHCO3"      = sodium bicarbonate, sodium hydrogen carbonate, sodium acid carbonate
  "NH4HCO3"     = ammonium bicarbonate, ammonium hydrogen carbonate
  "(NH4)2CO3"   = ammonium carbonate
  "Na2C2O4"     = sodium oxalate
  "(NH4)2C2O4"  = ammonium oxalate
  "TEA"         = triethanolamine, 2,2',2''-nitrilotriethanol, N(C2H4OH)3 [as pH agent]
  "DEA"         = diethanolamine, 2,2'-iminodiethanol, HN(C2H4OH)2 [as pH agent]
  "MEA"         = monoethanolamine, ethanolamine, H2N-CH2CH2OH [as pH agent]
  "NaOAc"       = sodium acetate, CH3COONa [mild base in acetate-based synthesis]

- capping_agent : stabilizer/surfactant/polymer controlling particle size and shape.
  Return CANONICAL LABEL. If multiple → semicolon-separated.
  ⚠ PEG is a capping agent, NOT a solvent
  ⚠ Triethanolamine/oleylamine: if "surfactant/ligand/capping" → here; if "pH agent" → mineralizer

  Canonical labels and equivalences:
  "PVP"         = polyvinylpyrrolidone, poly(N-vinylpyrrolidone), PVP-K30, PVP-K40, PVP K30
  "PEG"         = polyethylene glycol, poly(ethylene glycol), PEG-200/400/600/1000/4000/6000/8000
  "PVA"         = polyvinyl alcohol, poly(vinyl alcohol), PVOH
  "CTAB"        = cetyltrimethylammonium bromide, hexadecyltrimethylammonium bromide, cetrimonium bromide
  "CTAC"        = cetyltrimethylammonium chloride
  "SDS"         = sodium dodecyl sulfate, sodium lauryl sulfate, SLS
  "SDBS"        = sodium dodecylbenzenesulfonate, sodium dodecylbenzene sulfonate
  "Tween-80"    = polysorbate 80, polyoxyethylene sorbitan monooleate
  "Tween-20"    = polysorbate 20
  "Span-80"     = sorbitan monooleate, sorbitan (Z)-mono-9-octadecenoate
  "Triton X-100"= octylphenol ethoxylate, p-tert-octylphenol polyethoxylate, TX-100
  "Pluronic P123"= Pluronic P-123, EO20PO70EO20, poloxamer 403
  "Pluronic F127"= Pluronic F-127, EO106PO70EO106, poloxamer 407
  "Pluronic F108"= Pluronic F-108
  "Gelatin"     = gelatin, gelatine
  "Oleic acid"  = cis-9-octadecenoic acid, C18H34O2, OA [surface ligand in organic-phase synthesis]
  "Oleylamine"  = (Z)-octadec-9-en-1-amine, C18H37N, OAm, octadecenylamine
  "Citrate"     = citric acid/citrate as surfactant/stabilizer (not as complexing fuel)
  "DEA"         = diethanolamine, 2,2'-iminodiethanol [as surfactant/template]
  "TEA"         = triethanolamine [as surfactant/template]

- chelating_agent : complexing agent for controlled nucleation/gelation.
  Return CANONICAL LABEL. If multiple → semicolon-separated.
  ⚠ "Citric acid" as chelating agent even in combustion synthesis (forms Ce complex before ignition)
  ⚠ "Glycine" as chelating agent even in combustion (unless trivial aqueous mixing without gelation)
  ⚠ Do NOT put acetic acid here — it is a solvent/acid, not a chelator

  Canonical labels and equivalences:
  "EDTA"         = ethylenediaminetetraacetic acid, C10H16N2O8, disodium EDTA, Na2-EDTA, EDTA-2Na, tetrasodium EDTA
  "Citric acid"  = 2-hydroxypropane-1,2,3-tricarboxylic acid, C6H8O7, H3C6H5O7
  "Acetylacetone"= pentane-2,4-dione, 2,4-pentanedione, Hacac, acac, C5H8O2
  "Glycine"      = aminoacetic acid, 2-aminoacetic acid, H2NCH2COOH, C2H5NO2 [also combustion fuel]
  "PVA"          = polyvinyl alcohol [Pechini/polymeric precursor method]
  "Oxalic acid"  = ethanedioic acid, H2C2O4, C2H2O4
  "Tartaric acid"= 2,3-dihydroxybutanedioic acid, C4H6O6, Rochelle salt (sodium tartrate form)
  "Malic acid"   = 2-hydroxybutanedioic acid, hydroxysuccinic acid, C4H6O5
  "Lactic acid"  = 2-hydroxypropanoic acid, C3H6O3
  "NTA"          = nitrilotriacetic acid, N(CH2COOH)3, C6H9NO6
  "DTPA"         = diethylenetriaminepentaacetic acid, C14H23N3O10
  "Glucose"      = D-glucose, dextrose, C6H12O6 [Pechini-like methods]
  "Sucrose"      = saccharose, C12H22O11
  "Starch"       = soluble starch
  "EDA"          = ethylenediamine, 1,2-diaminoethane, H2N(CH2)2NH2, en [Ce3+ complexation]

- oxidant : explicitly added oxidizing agent to promote CeO2 formation or particle formation.
  Return CANONICAL LABEL. If multiple → semicolon-separated.
  ⚠ Do NOT list Ce(NO3)3 or (NH4)2Ce(NO3)6 as oxidant — those are ce_precursor
  ⚠ Do NOT list HNO3 if used only as counter-ion to dissolve Ce metal/oxide (use context)

  Canonical labels and equivalences:
  "H2O2"         = hydrogen peroxide, aqueous hydrogen peroxide, H₂O₂ [Ce3+→Ce4+ oxidation]
  "HNO3"         = nitric acid, dilute nitric acid [dissolution/oxidation aid]
  "H2SO4"        = sulfuric acid, sulphuric acid [acid dissolution]
  "KMnO4"        = potassium permanganate
  "(NH4)2S2O8"   = ammonium persulfate, ammonium peroxydisulfate, APS
  "O3"           = ozone
  "NaClO"        = sodium hypochlorite, bleach

- synthesis_method: Choose EXACTLY ONE from this closed list:
  hydrothermal       = water + sealed autoclave, 80–250°C (>100°C typical)
  solvothermal       = organic solvent + sealed autoclave, 80–300°C
  sol-gel            = alkoxide/acetate hydrolysis, gel network formation, Pechini/polymeric precursor
  precipitation      = aqueous mixing of ONE Ce salt + precipitant (NaOH/NH3 etc.), no autoclave
  co-precipitation   = TWO or more metal salts precipitated together (Ce + dopant precursor)
  combustion         = fuel (glycine, urea, citric acid, PVA) + nitrate oxidizer → self-ignition/rapid heating
  spray_pyrolysis    = aerosol/spray of precursor solution into hot furnace
  microwave          = microwave radiation as PRIMARY energy source (incl. microwave-hydrothermal)
  template           = hard template (SBA-15, AAO, PS sphere) or soft template (micelle, vesicle)
  thermal_decomposition = solid/liquid precursor thermally decomposed (no solvent synthesis step, just calcination)
  mechanochemical    = ball milling, high-energy milling as primary synthesis step
  sonochemical       = ultrasound as primary energy source
  wet_chemical       = aqueous/solution mixing without autoclave, not strictly precipitation
  other              = anything that does not fit above

  DISAMBIGUATION RULES:
  · microwave-assisted hydrothermal → "microwave"
  · microwave-assisted precipitation → "microwave"
  · urea/glycine + nitrate + ignition → "combustion" (even if aqueous solution is used first)
  · co-precipitation of Ce + dopant (Gd, La, Sm, Y, Zr, etc.) → "co-precipitation"
  · Pechini method / polymer complexation route → "sol-gel"
  · homogeneous precipitation (urea decomposition, no ignition) → "precipitation"
  · reflux synthesis without autoclave → "wet_chemical"

━━━ NUMERIC FIELDS — CRITICAL RULES ━━━
- particle_size_tem_nm : PRIMARY particle size measured by TEM/HRTEM/STEM images (nm).
  ✓ Accept: "TEM image shows 15 nm particles", "average diameter from TEM", "d(TEM) = 12 nm"
  ✗ EXCLUDE: DLS, dynamic light scattering, hydrodynamic diameter, z-average, z-size, PDI,
             laser diffraction, pore size, film thickness, coating thickness, wavelength,
             precursor size, probe size. Use null if method is unspecified.
  For a range "5–20 nm" → midpoint 12.5. Take the AVERAGE/MEAN value if explicitly stated.
  Range: 0.5–500 nm.

- particle_size_sem_nm : PRIMARY particle size from SEM/FE-SEM/FESEM images (nm). Same exclusions as TEM.
  Range: 0.5–500 nm.

- crystallite_size_xrd_nm : Crystallite size from XRD Scherrer equation or Rietveld refinement (nm).
  ✓ Accept: "Scherrer equation", "XRD peak broadening", "DXRD", "D(XRD)"
  ✗ EXCLUDE: grain/particle size from SEM/TEM, BET equivalent diameter.
  Range: 0.5–200 nm.

- synthesis_temperature_c : Temperature DURING the synthesis reaction (°C).
  ✓ Accept: hydrothermal temperature, reaction temperature, synthesis temperature
  ✗ EXCLUDE: calcination/annealing temperature, drying temperature, room temperature
    (do NOT record 25°C unless the paper explicitly says synthesis was done at room temperature).
  Range: 20–500°C.

- calcination_temperature_c : Post-synthesis annealing/calcination/sintering temperature (°C).
  ✓ Key words: "calcined at", "annealed at", "sintered at", "heated to", "fired at"
  ✗ EXCLUDE: drying temperature (<200°C in oven before calcination), synthesis temperature.
  RULE: If two temperatures appear — lower one is usually synthesis, higher one is calcination.
  Range: 150–1600°C.

- drying_temperature_c : Pre-calcination drying temperature in oven (°C).
  ✓ Key words: "dried at", "dried in oven at", "dried overnight at"
  Typically 60–150°C. Range: 40–250°C.

- atmosphere : Gas environment during synthesis or calcination.
  Return ONE of: "air" | "N2" | "Ar" | "O2" | "H2" | "H2/N2" | "NH3" | "vacuum" | "inert" | null
  ✓ "calcined in air at 500°C" → "air"; "annealed under Ar flow" → "Ar"
  Prefer the calcination atmosphere if synthesis atmosphere is not mentioned.

- crystal_phase : Crystallographic phase identified by XRD or other techniques.
  ✓ Common values: "fluorite cubic", "Ce2O3", "amorphous", "pyrochlore", "mixed Ce3+/Ce4+"
  Use short standard names. null if not mentioned.

- morphology : Particle shape from TEM/SEM images.
  sphere = round/equiaxed particles
  cube = cubic/box-shaped particles
  rod = elongated 1D particles (aspect ratio >3:1)
  wire = very long/thin 1D (nanowires, nanofibers)
  flower = flower-like hierarchical aggregates
  octahedron = 8-faced polyhedral particles
  plate = thin 2D flat particles (nanoplates, nanosheets)
  porous = particles with internal pores/channels (mesoporous, macroporous)
  hollow = shell particles with empty interior (hollow spheres, nanocages)
  other = any other morphology
  null if shape not characterized.

━━━ OUTPUT FORMAT (strict JSON) ━━━
{
  "paper_has_synthesis": true,
  "samples": [
    {
      "sample_id": "string",
      "discriminator": "string",
      "confidence": "high|medium|low",
      "conditions_evidence": "≤15-word hint",
      "results_evidence": "≤15-word hint",
      "materials": {
        "ce_precursor": "string or null",
        "solvent": "string or null",
        "mineralizer": "string or null",
        "capping_agent": "string or null",
        "chelating_agent": "string or null",
        "oxidant": "string or null",
        "dopant": "element symbol or null",
        "dopant_concentration_mol_pct": number or null
      },
      "procedure": {
        "synthesis_method": "string or null",
        "synthesis_temperature_c": number or null,
        "synthesis_time_h": number or null,
        "ph_synthesis": number or null,
        "atmosphere": "string or null",
        "calcination_temperature_c": number or null,
        "calcination_time_h": number or null,
        "drying_temperature_c": number or null
      },
      "characterization": {
        "particle_size_tem_nm": number or null,
        "particle_size_sem_nm": number or null,
        "crystallite_size_xrd_nm": number or null,
        "bet_surface_area_m2g": number or null,
        "morphology": "sphere|cube|rod|wire|flower|octahedron|plate|porous|hollow|other or null",
        "crystal_phase": "string or null"
      }
    }
  ]
}"""

USER_TEMPLATE = "Title: {title}\n\nText:\n{text}"

# ── 후처리 검증 ───────────────────────────────────────────────────────────────
_VALID_METHODS = {
    "hydrothermal", "solvothermal", "sol-gel", "precipitation", "co-precipitation",
    "combustion", "spray_pyrolysis", "microwave", "template", "thermal_decomposition",
    "mechanochemical", "sonochemical", "wet_chemical", "other",
}
_VALID_MORPHS = {
    "sphere", "cube", "rod", "wire", "flower", "octahedron",
    "plate", "porous", "hollow", "other",
}
_VALID_ATMO = {
    "air", "n2", "ar", "o2", "h2", "h2/n2", "nh3", "vacuum", "inert",
}
# GPT가 반환하는 null 표현 문자열
_NULL_STRINGS = {
    "", "null", "none", "n/a", "na", "nan", "unknown",
    "not stated", "not reported", "not mentioned", "not specified",
    "not found", "not available", "not applicable", "not given",
}

def _clean_str(v):
    """문자열이 null 표현이면 None 반환, 아니면 strip된 문자열."""
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    stripped = v.strip()
    return None if stripped.lower() in _NULL_STRINGS else stripped

def _clamp_num(v, lo, hi):
    """숫자 범위 검사. 범위 밖이거나 변환 실패면 None."""
    if v is None:
        return None
    try:
        fv = float(v)
        return fv if lo <= fv <= hi else None
    except (TypeError, ValueError):
        return None

def _validate_sample(s: dict) -> dict:
    """수치 범위 + 허용값 집합 + null 문자열 정규화. 무효값은 None으로."""
    if not isinstance(s, dict):
        return s

    mat  = s.get("materials")  or {}
    proc = s.get("procedure")  or {}
    char = s.get("characterization") or {}

    # ── materials: 문자열 필드 정규화 ──────────────────────────────────────
    for field in ("ce_precursor", "solvent", "mineralizer",
                  "capping_agent", "chelating_agent", "oxidant", "dopant"):
        mat[field] = _clean_str(mat.get(field))

    mat["dopant_concentration_mol_pct"] = _clamp_num(
        mat.get("dopant_concentration_mol_pct"), 0.0, 100.0
    )

    # ── procedure: 수치 범위 검사 + 문자열 정규화 ──────────────────────────
    proc["synthesis_temperature_c"]   = _clamp_num(proc.get("synthesis_temperature_c"),   20,   500)
    proc["calcination_temperature_c"] = _clamp_num(proc.get("calcination_temperature_c"), 150, 1600)
    proc["drying_temperature_c"]      = _clamp_num(proc.get("drying_temperature_c"),       40,  250)
    proc["synthesis_time_h"]          = _clamp_num(proc.get("synthesis_time_h"),          0.01, 2400)
    proc["calcination_time_h"]        = _clamp_num(proc.get("calcination_time_h"),        0.01,  240)
    proc["ph_synthesis"]              = _clamp_num(proc.get("ph_synthesis"),              0.0,  14.0)

    # synthesis_method 허용값
    sm = _clean_str(proc.get("synthesis_method"))
    if sm:
        proc["synthesis_method"] = sm if sm.lower() in _VALID_METHODS else "other"
    else:
        proc["synthesis_method"] = None

    # atmosphere 정규화
    atm = _clean_str(proc.get("atmosphere"))
    if atm:
        proc["atmosphere"] = atm if atm.lower() in _VALID_ATMO else atm  # 비표준도 보존
    else:
        proc["atmosphere"] = None

    # ── characterization: 수치 범위 + 문자열 정규화 ────────────────────────
    char["particle_size_tem_nm"]    = _clamp_num(char.get("particle_size_tem_nm"),    0.3, 500)
    char["particle_size_sem_nm"]    = _clamp_num(char.get("particle_size_sem_nm"),    0.3, 500)
    char["crystallite_size_xrd_nm"] = _clamp_num(char.get("crystallite_size_xrd_nm"), 0.3, 200)
    char["bet_surface_area_m2g"]    = _clamp_num(char.get("bet_surface_area_m2g"),    0.1, 1500)

    # morphology 허용값
    mo = _clean_str(char.get("morphology"))
    if mo:
        char["morphology"] = mo if mo.lower() in _VALID_MORPHS else "other"
    else:
        char["morphology"] = None

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

def extract_relevant_sections(text: str, max_chars: int = 12000) -> str:
    """실험 섹션 + 결과 섹션을 합쳐서 반환 (4:6 비율 배분).
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
        # 실험 섹션만 찾은 경우: 실험(60%) + 논문 후반부(40%, 결과 포함 가능)
        exp_text = text[exp_m.end(): end_pos].strip()
        exp_alloc = int(max_chars * 0.6)
        tail_start = max(exp_m.end(), int(len(text) * 0.5))
        tail_text  = text[tail_start: end_pos].strip()
        return (
            "[EXPERIMENTAL]\n" + exp_text[:exp_alloc]
            + "\n\n[LATER_SECTIONS]\n" + tail_text[:max_chars - exp_alloc]
        )

    if res_m:
        # 결과 섹션만 찾은 경우: 논문 앞부분(40%) + 결과(60%)
        res_text = text[res_m.end(): end_pos].strip()
        head_text = text[:int(max_chars * 0.4)].strip()
        return (
            "[EARLIER_TEXT]\n" + head_text
            + "\n\n[RESULTS]\n" + res_text[:int(max_chars * 0.6)]
        )

    # 섹션 감지 실패: 앞 75% + 뒤 25% (결론·참고문헌 제외)
    front = text[:int(max_chars * 0.75)]
    back  = text[max(0, end_pos - int(max_chars * 0.25)): end_pos]
    return front + ("\n\n" + back if back.strip() else "")

# ── DOI → 파일명 stem ─────────────────────────────────────────────────────────
def doi_to_stem(doi) -> str:
    if not doi or pd.isna(doi):
        return ""
    return str(doi).strip().replace("/", "_").replace(":", "_").lower()

def _load_xlsx_safe(path):
    """요약행 자동 감지 후 헤더 행 결정 (format_excel.py 출력 대비)."""
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)

# ── 캐시 로드 ─────────────────────────────────────────────────────────────────
if os.path.exists(CACHE_PATH):
    with open(CACHE_PATH, encoding="utf-8") as f:
        _cache = json.load(f)
    done_dois    = set(_cache.get("done_dois", []))
    total_samples = _cache.get("total_samples", 0)
    print(f"캐시 로드: {len(done_dois):,}편 완료, 누적 {total_samples:,}개 샘플")
else:
    done_dois    = set()
    total_samples = 0
    print("캐시 없음 — 처음부터 시작")

# 캐시 소실 대비: 기존 CSV에서 이미 처리된 DOI 추가 수집
if os.path.exists(OUT_CSV):
    try:
        _csv_prev = pd.read_csv(OUT_CSV, usecols=["doi"], dtype=str)
        _csv_dois = set(_csv_prev["doi"].dropna().str.strip().tolist())
        added = _csv_dois - done_dois
        if added:
            done_dois.update(added)
            print(f"  CSV 기존 DOI {len(added):,}개 → done_dois 추가 (중복 방지)")
    except Exception:
        pass

# ── Excel 로드 + 대상 선별 ────────────────────────────────────────────────────
df = _load_xlsx_safe(XLSX_PATH)
df.columns = [str(c).strip() for c in df.columns]
print(f"Excel 로드: {len(df):,}편\n")

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
est_cost = len(targets) * 0.0008
print(f"예상 비용: 약 ${est_cost:.2f} (gpt-4o-mini 기준)\n")

if args.dry_run:
    print("--dry-run 모드 종료 (API 호출 없음)")
    raise SystemExit(0)

# ── 추출 루프 ─────────────────────────────────────────────────────────────────
new_samples = 0
errors      = 0

os.makedirs(OUTPUT_DIR, exist_ok=True)
csv_is_new = not os.path.exists(OUT_CSV)

with open(OUT_JSONL, "a", encoding="utf-8") as out_f, \
     open(OUT_CSV, "a", encoding="utf-8", newline="") as csv_f:
    csv_writer = csv.DictWriter(csv_f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    if csv_is_new:
        csv_writer.writeheader()
    for i, paper in enumerate(tqdm(targets, desc="샘플 추출")):
        doi   = paper["doi"]
        stem  = paper["stem"]
        title = paper["title"]

        # 텍스트 로드
        try:
            with open(os.path.join(TEXT_DIR, stem + ".txt"),
                      encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except Exception:
            errors += 1
            done_dois.add(doi)
            continue

        snippet = extract_relevant_sections(raw, max_chars=12000)
        if len(snippet) < 200:
            done_dois.add(doi)
            continue

        # OpenAI 호출 (최대 3회 재시도, 지수 백오프)
        samples = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": USER_TEMPLATE.format(
                            title=title, text=snippet)},
                    ],
                    max_tokens=2500,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                raw_resp = resp.choices[0].message.content.strip()
                parsed = json.loads(raw_resp)
                if parsed.get("paper_has_synthesis", True):
                    samples = parsed.get("samples", [])
                else:
                    samples = []
                break
            except json.JSONDecodeError:
                # response_format 보장 실패 시 정규식 폴백
                try:
                    m = re.search(r"\{.*\}", raw_resp, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group())
                        samples = parsed.get("samples", []) if parsed.get("paper_has_synthesis", True) else []
                        break
                except Exception:
                    pass
                if attempt < 2:
                    time.sleep(2 ** attempt * 2)
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt * 3)
                else:
                    tqdm.write(f"  오류 ({doi[:35]}): {e}")
                    errors += 1

        done_dois.add(doi)

        if not isinstance(samples, list):
            continue

        # 샘플 수 상한 (8개): 입자크기 있는 샘플 우선, 없으면 앞에서 자름
        if len(samples) > 8:
            has_ps = [s for s in samples if isinstance(s, dict) and (
                (s.get("characterization") or {}).get("particle_size_tem_nm") or
                (s.get("characterization") or {}).get("crystallite_size_xrd_nm") or
                (s.get("characterization") or {}).get("particle_size_sem_nm")
            )]
            no_ps  = [s for s in samples if s not in has_ps]
            samples = (has_ps + no_ps)[:8]

        # 샘플별 레코드 저장
        for s in samples:
            if not isinstance(s, dict):
                continue
            s = _validate_sample(s)
            mat   = s.get("materials") or {}
            proc  = s.get("procedure") or {}
            char  = s.get("characterization") or {}
            record = {
                "doi":          doi,
                "title":        title,
                "sample_id":    s.get("sample_id", "S1"),
                "discriminator":    s.get("discriminator", ""),
                "confidence":       s.get("confidence", "medium"),
                "conditions_evidence": s.get("conditions_evidence", ""),
                "results_evidence":    s.get("results_evidence", ""),
                "materials":    mat,
                "procedure":    proc,
                "characterization": char,
                # 하위 호환 키
                "synthesis_conditions": {**mat, **proc},
            }
            # CSV 행 (평탄화)
            csv_row = {
                "doi": doi, "title": title,
                "sample_id":    record["sample_id"],
                "discriminator": record["discriminator"],
                "confidence":   record["confidence"],
                "conditions_evidence": record["conditions_evidence"],
                "results_evidence":    record["results_evidence"],
                **mat, **proc, **char,
            }
            csv_writer.writerow(csv_row)
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            new_samples += 1
        total_samples += len(samples)

        # 주기적 캐시 저장
        if (i + 1) % SAVE_INTERVAL == 0:
            with open(CACHE_PATH, "w", encoding="utf-8") as cf:
                json.dump({"done_dois": list(done_dois),
                           "total_samples": total_samples}, cf)
            tqdm.write(f"  [{i+1:,}편] 누적 샘플 {total_samples:,}개 저장")

        time.sleep(0.05)

# 최종 캐시 저장
with open(CACHE_PATH, "w", encoding="utf-8") as cf:
    json.dump({"done_dois": list(done_dois), "total_samples": total_samples}, cf)

print(f"\n완료!")
print(f"  처리: {len(targets):,}편")
print(f"  신규 샘플: {new_samples:,}개")
print(f"  누적 샘플: {total_samples:,}개")
print(f"  오류: {errors}건")
print(f"  출력: {OUT_JSONL}")
