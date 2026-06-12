"""
fill_keywords.py — [Stage 2] 키워드/정규식 기반 빈 필드 보완

합성방법·형태·결정립크기·도핑원소·결정상 등을 제목+초록 키워드로 자동 채웁니다.
iterrows() 루프 → pandas 벡터 연산으로 구현. 4,388편 기준 수 초 처리.

이전 이름: run_cell17.py
"""
import pandas as pd, os, re, numpy as np

_output_path = os.path.join(r"d:\머신러닝 교육\ceria_pipeline_data", "output", "ceria_synthesis_database.xlsx")


def _load_xlsx_safe(path):
    """요약행 자동 감지 후 헤더 행 결정 (11_format_excel.py 실행 후에도 안전)."""
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)


df = _load_xlsx_safe(_output_path)
total = len(df)
print(f"보완 시작: {total:,}편\n")

# ── 공통 haystack (title + abstract 소문자 결합) ─────────────────────────────
_hay = (df["title"].fillna("") + " " +
        (df["abstract"].fillna("") if "abstract" in df.columns
         else pd.Series("", index=df.index))).str.lower()

def _null_mask(col: str) -> pd.Series:
    """해당 컬럼이 비어있는 행 마스크."""
    if col not in df.columns:
        df[col] = pd.NA
    return df[col].isna() | (df[col].astype(str).str.strip().isin(["", "nan", "none", "NaN"]))


# ── 1. 합성방법 키워드 매칭 (우선순위 순서 유지) ────────────────────────────────
METHOD_KEYWORDS = [
    ("co-precipitation",        ["co-precipitation", "coprecipitation", "co precipitation"]),
    ("solvothermal",            ["solvothermal"]),
    ("hydrothermal",            ["hydrothermal", "autoclave-assisted", "autoclave treatment"]),
    ("sol-gel",                 ["sol-gel", "sol gel", "pechini", "modified pechini",
                                 "polymeric precursor method", "polymerizable complex",
                                 "citrate gel", "citrate-nitrate method"]),
    ("combustion",              ["combustion", "auto-combustion", "autocombustion",
                                 "solution combustion", "self-combustion",
                                 "self-propagating", "glycine-nitrate", "urea-nitrate",
                                 "citrate-nitrate combustion"]),
    ("spray_pyrolysis",         ["spray pyrolysis", "spray-pyrolysis",
                                 "aerosol pyrolysis", "flame spray"]),
    ("microwave",               ["microwave", "microwave-assisted", "microwave-hydrothermal",
                                 "microwave irradiation"]),
    ("thermal_decomposition",   ["thermal decomposition", "thermolysis", "thermally decomposed",
                                 "thermal treatment", "pyrolysis of cerium"]),
    ("mechanochemical",         ["mechanochemical", "ball mill", "ball-mill", "milling",
                                 "high-energy milling", "planetary mill"]),
    ("sonochemical",            ["sonochemical", "sonication-assisted synthesis",
                                 "ultrasound synthesis", "ultrasound-assisted synthesis",
                                 "sonication synthesis", "acoustic cavitation"]),
    ("electrochemical",         ["electrochemical synthesis", "electrodeposition",
                                 "anodic oxidation", "electrochemical method",
                                 "anodization"]),
    ("freeze_drying",           ["freeze-drying", "freeze drying", "lyophilization",
                                 "cryogenic synthesis", "freeze-dried"]),
    ("polyol",                  ["polyol process", "polyol method", "polyol synthesis",
                                 "polyol route", "forced hydrolysis in polyol"]),
    ("reverse_micelle",         ["reverse micelle", "reverse-micelle", "microemulsion",
                                 "water-in-oil", "w/o microemulsion",
                                 "AOT-water-isooctane", "reverse microemulsion"]),
    ("template",                ["hard template", "soft template", "template-assisted",
                                 "nanocasting", "hard-template", "soft-template",
                                 "SBA-15", "MCM-41", "KIT-6", "anodic alumina"]),
    ("homogeneous_precipitation", ["homogeneous precipitation", "urea hydrolysis",
                                   "hmta hydrolysis", "uniform precipitation"]),
    ("wet_chemical",            ["wet-chemical", "wet chemical", "wet chemistry"]),
    ("precipitation",           ["precipitation"]),
]

originally_empty = _null_mask("synthesis_method")
filled_method = 0
for method, keywords in METHOD_KEYWORDS:
    pattern = "|".join(re.escape(kw) for kw in keywords)
    still_empty = _null_mask("synthesis_method") & originally_empty
    matches = _hay.str.contains(pattern, case=False, na=False, regex=True)
    mask = still_empty & matches
    df.loc[mask, "synthesis_method"] = method
    filled_method += mask.sum()
print(f"  합성방법 추가: {filled_method:,}편")


# ── 2. 형태(morphology) 키워드 매칭 ───────────────────────────────────────────
MORPHOLOGY_KEYWORDS = [
    ("rod",          ["nanorod", "nano-rod", "rod-shaped", "rod-like", "nanorods"]),
    ("wire",         ["nanowire", "nano-wire", "wire-like", "nanowires"]),
    ("tube",         ["nanotube", "nano-tube", "tubular", "hollow tube", "tube-like",
                      "nanotubes"]),
    ("cube",         ["nanocube", "nanocubes", "cube-shaped", "cubic nanoparticle"]),
    ("flower",       ["nanoflower", "flower-like", "flowerlike", "nanoflowers"]),
    ("plate",        ["nanoplate", "nanoplates", "plate-like", "platelet", "nanoflake",
                      "flake-like"]),
    ("sheet",        ["nanosheet", "nano-sheet", "2d nanosheet", "ultrathin sheet",
                      "sheet-like", "nanosheets"]),
    ("disk",         ["nanodisk", "nano-disk", "disk-like", "disc-like", "nanotisk",
                      "nanodiscs"]),
    ("octahedron",   ["octahedral", "octahedron"]),
    ("polyhedron",   ["polyhedral", "polyhedron", "multifaceted"]),
    ("hollow",       ["hollow sphere", "hollow nanoparticle", "core-shell",
                      "hollow structure", "hollow ceo2"]),
    ("porous",       ["mesoporous", "nanoporous", "porous ceo2", "porous ceria",
                      "hierarchical porous", "macro-mesoporous"]),
    ("dendrite",     ["dendritic", "dendrite-like", "dendrite structure",
                      "fractal morphology"]),
    ("sphere",       ["nanosphere", "spherical nanoparticle", "quasi-spherical",
                      "quasi-spherical particles"]),
    ("quantum_dot",  ["quantum dot", "ceo2 qd", "ceria quantum dot", "ceo2 quantum dots"]),
]

orig_empty_morph = _null_mask("morphology")
filled_morph = 0
for morph, keywords in MORPHOLOGY_KEYWORDS:
    pattern = "|".join(re.escape(kw) for kw in keywords)
    still_empty = _null_mask("morphology") & orig_empty_morph
    matches = _hay.str.contains(pattern, case=False, na=False, regex=True)
    mask = still_empty & matches
    df.loc[mask, "morphology"] = morph
    filled_morph += mask.sum()
print(f"  형태    추가: {filled_morph:,}편")


# ── 3. 크기/BET 정규식 추출 ───────────────────────────────────────────────────
XRD_PATTERNS = [
    r'(?:crystallite|crystalline)\s*size[^.]{0,80}?(\d+\.?\d*)\s*nm',
    r'scherrer[^.]{0,80}?(\d+\.?\d*)\s*nm',
    r'(?:xrd|x-ray)[^.]{0,80}?(\d+\.?\d*)\s*nm',
    r'(?:mean|average)\s+crystallite[^.]{0,60}?(\d+\.?\d*)\s*nm',
]
TEM_PATTERNS = [
    r'tem[^.]{0,80}?(\d+\.?\d*)\s*nm',
    r'transmission\s+electron\s+microscop[^.]{0,80}?(\d+\.?\d*)\s*nm',
    r'(?:mean|average)\s+(?:particle|grain)\s+size[^.]{0,60}?(\d+\.?\d*)\s*nm',
]
BET_PATTERNS = [
    r'bet[^.]{0,80}?(\d+\.?\d*)\s*m[²2][/\s]?g',
    r'surface\s+area[^.]{0,80}?(\d+\.?\d*)\s*m[²2][/\s]?g',
    r'(\d+\.?\d*)\s*m[²2]\s*/\s*g',
]

_DLS_EXCL = re.compile(
    r'(?:dls|dynamic\s+light\s+scatter|hydrodynamic|z-average|zeta|'
    r'colloidal|zetasizer|nanotrack|nanosight|intensity-weighted)',
    re.I
)

def _strip_dls(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', str(text))
    return " ".join(s for s in sentences if not _DLS_EXCL.search(s))

# DLS-제거 초록 Series (apply는 단일 패스로 빠름)
_abst_raw = df["abstract"].fillna("") if "abstract" in df.columns else pd.Series("", index=df.index)
_abst_clean = _abst_raw.apply(_strip_dls)

def _vec_extract(clean_series: pd.Series, patterns: list, lo: float, hi: float) -> pd.Series:
    """벡터화 정규식 추출: 각 패턴을 순서대로 시도, 유효범위(lo~hi) 내 첫 값 반환."""
    result = pd.Series([np.nan] * len(clean_series), index=clean_series.index)
    for pat in patterns:
        extracted = clean_series.str.extract(pat, flags=re.IGNORECASE, expand=False)
        num = pd.to_numeric(extracted, errors="coerce")
        valid = num.between(lo, hi) & result.isna()
        result = result.where(~valid, num)
    return result

xrd_extracted = _vec_extract(_abst_clean, XRD_PATTERNS, 0.5, 200)
tem_extracted = _vec_extract(_abst_clean, TEM_PATTERNS, 0.5, 500)
bet_extracted = _vec_extract(_abst_clean, BET_PATTERNS, 1.0, 1000)

# 빈 행에만 채우기
def _fill_col(col: str, extracted: pd.Series):
    null = _null_mask(col)
    mask = null & extracted.notna()
    df.loc[mask, col] = extracted[mask]
    return int(mask.sum())

filled_xrd = _fill_col("crystallite_size_xrd_nm", xrd_extracted)
filled_tem = _fill_col("particle_size_tem_nm",     tem_extracted)
filled_bet = _fill_col("bet_surface_area",          bet_extracted)

print(f"  XRD 결정립크기 추가: {filled_xrd:,}편")
print(f"  TEM 입자크기 추가:   {filled_tem:,}편")
print(f"  BET 표면적 추가:     {filled_bet:,}편")


# ── 4. 도핑 원소 ───────────────────────────────────────────────────────────────
DOPANTS = [
    # 희토류
    "Sm", "Gd", "La", "Y", "Pr", "Nd", "Eu", "Tb", "Dy",
    "Ho", "Er", "Yb", "Lu", "Sc", "In",
    # 전이금속
    "Zr", "Ti", "Cu", "Fe", "Co", "Ni", "Mn", "Cr", "V", "Nb", "W", "Mo",
    "Ru", "Ag",
    # 귀금속
    "Pt", "Pd", "Au",
    # 준금속/기타
    "Al", "Si", "Bi", "Sn", "Mg", "Ca", "Sr", "Ba",
]

orig_empty_dopant = _null_mask("dopant")
filled_dopant = 0
for d in DOPANTS:
    pat = rf'\b{d}(?:-doped|doped|/CeO2|[- ]doped\s+ceri|[- ]doped\s+ceo)'
    still_empty = _null_mask("dopant") & orig_empty_dopant
    matches = _hay.str.contains(pat, case=False, na=False, regex=True)
    mask = still_empty & matches
    df.loc[mask, "dopant"] = d
    filled_dopant += mask.sum()
print(f"  도핑원소 추가:       {filled_dopant:,}편")


# ── 5. 결정상 ──────────────────────────────────────────────────────────────────
PHASE_KEYWORDS = [
    ("fluorite cubic", ["fluorite", "cubic fluorite", "face-centered cubic",
                        "fluorite structure", "fluorite-type", "fluorite phase",
                        "fm3m", "fm-3m", "cerianite"]),
    ("Ce2O3",          ["ce2o3", "cerium(iii) oxide", "cerium sesquioxide"]),
    ("mixed",          ["mixed phase", "mixed oxide", "multiphase",
                        "mixed ce3+/ce4+", "ce3+/ce4+"]),
    ("amorphous",      ["amorphous", "non-crystalline", "amorphous ceo2",
                        "amorphous phase"]),
    ("pyrochlore",     ["pyrochlore", "pyrochlore phase", "pyrochlore structure"]),
    ("defect fluorite",["defect fluorite", "defective fluorite",
                        "oxygen vacancy", "sub-stoichiometric"]),
]

orig_empty_phase = _null_mask("crystal_phase")
filled_phase = 0
for phase, keywords in PHASE_KEYWORDS:
    pattern = "|".join(re.escape(kw) for kw in keywords)
    still_empty = _null_mask("crystal_phase") & orig_empty_phase
    matches = _hay.str.contains(pattern, case=False, na=False, regex=True)
    mask = still_empty & matches
    df.loc[mask, "crystal_phase"] = phase
    filled_phase += mask.sum()
print(f"  결정상 추가:         {filled_phase:,}편")


# ── 6–9. 다중 레이블 필드 (mineralizer / capping / chelating / oxidant) ────────
def _fill_multilabel(col: str, keyword_map: list):
    if col not in df.columns:
        df[col] = pd.NA
    null = _null_mask(col)
    if not null.any():
        return 0
    # 각 레이블마다 벡터화 매칭 후 행별로 발견 레이블 수집
    label_masks = {}
    for label, kws in keyword_map:
        pat = "|".join(re.escape(kw) for kw in kws)
        label_masks[label] = _hay.str.contains(pat, case=False, na=False, regex=True)
    filled = 0
    for idx in df.index[null]:
        found = [label for label, mask in label_masks.items() if mask.at[idx]]
        if found:
            df.at[idx, col] = "; ".join(found)
            filled += 1
    return filled

MINERALIZER_KW = [
    ("NaOH",       ["naoh", "sodium hydroxide", "caustic soda", "lye"]),
    ("KOH",        ["koh", "potassium hydroxide", "caustic potash"]),
    ("LiOH",       ["lioh", "lithium hydroxide"]),
    ("NH3",        ["nh3", "ammonia", "nh4oh", "ammonium hydroxide",
                    "aqueous ammonia", "ammonia solution", "ammonia water",
                    "aqua ammonia", "ammonium solution", "concentrated ammonia",
                    "dilute ammonia", "ammonia gas"]),
    ("Urea",       ["urea", "carbamide", "co(nh2)2", "ch4n2o",
                    "homogeneous precipitation"]),   # urea→NH3 분해 context
    ("HMTA",       ["hmta", "hexamethylenetetramine", "hexamine",
                    "urotropine", "methenamine", "(ch2)6n4", " hmt "]),
    ("TMAH",       ["tmah", "tetramethylammonium hydroxide",
                    "tetramethyl ammonium hydroxide", "tetramethylammonium",
                    "(ch3)4noh", "n(ch3)4oh"]),
    ("Na2CO3",     ["na2co3", "sodium carbonate", "soda ash", "washing soda"]),
    ("NaHCO3",     ["nahco3", "sodium bicarbonate", "sodium hydrogen carbonate",
                    "sodium acid carbonate"]),
    ("(NH4)2CO3",  ["ammonium carbonate", "(nh4)2co3", "ammonium sesquicarbonate"]),
    ("NH4HCO3",    ["nh4hco3", "ammonium bicarbonate",
                    "ammonium hydrogen carbonate"]),
    ("Na2C2O4",    ["sodium oxalate", "na2c2o4"]),
    ("(NH4)2C2O4", ["ammonium oxalate", "(nh4)2c2o4"]),
    ("TEA",        ["triethanolamine as precipitant", "tea as ph", "trolamine as base",
                    "ph adjusted with triethanolamine"]),   # pH조절 목적일 때만
    ("MEA",        ["monoethanolamine as precipitant", "ethanolamine as base",
                    "ph adjusted with ethanolamine", "mea as mineralizer"]),
    ("NaOAc",      ["sodium acetate as base", "ch3coona", "sodium acetate buffer"]),
    ("K2CO3",      ["k2co3", "potassium carbonate"]),
    ("TEAOH",      ["tetraethylammonium hydroxide", "tetraethyl ammonium hydroxide"]),
    ("Ba(OH)2",    ["barium hydroxide", "ba(oh)2"]),
]
CAPPING_KW = [
    ("PVP",          ["pvp", "polyvinylpyrrolidone", "polyvinyl pyrrolidone",
                      "poly(vinylpyrrolidone)", "poly(vinyl pyrrolidone)",
                      "pvp-k30", "pvp k30", "pvpk30", "k-30", "k30",
                      "pvp-k40", "pvp k40", "pvp-k90", "poly(n-vinylpyrrolidone)"]),
    ("PEG",          ["peg", "polyethylene glycol", "poly(ethylene glycol)",
                      "polyethyleneglycol", "polyoxyethylene",
                      "peg-200", "peg-400", "peg-600", "peg-1000",
                      "peg-2000", "peg-4000", "peg-6000", "peg-8000",
                      "peg200", "peg400", "peg600", "peg1000",
                      "peg2000", "peg4000", "peg6000", "peg8000"]),
    ("PVA",          ["pva", "polyvinyl alcohol", "poly(vinyl alcohol)",
                      "polyvinylalcohol", "pvoh"]),
    ("CTAB",         ["ctab", "cetyltrimethylammonium bromide",
                      "cetrimonium bromide",
                      "hexadecyltrimethylammonium bromide",
                      "cetyl trimethylammonium bromide"]),
    ("CTAC",         ["ctac", "cetyltrimethylammonium chloride",
                      "hexadecyltrimethylammonium chloride"]),
    ("SDS",          ["sds", "sodium dodecyl sulfate", "sodium dodecyl sulphate",
                      "sodium lauryl sulfate", "sodium lauryl sulphate",
                      "lauryl sulfate", " sls "]),
    ("SDBS",         ["sdbs", "sodium dodecylbenzenesulfonate",
                      "sodium dodecylbenzene sulfonate",
                      "sodium dodecylbenzenesulphonate"]),
    ("Tween-80",     ["tween-80", "tween 80", "tween80", "polysorbate 80",
                      "polyoxyethylene sorbitan monooleate"]),
    ("Tween-20",     ["tween-20", "tween 20", "tween20", "polysorbate 20"]),
    ("Span-80",      ["span-80", "span 80", "span80", "sorbitan monooleate",
                      "sorbitan oleate"]),
    ("Triton X-100", ["triton x-100", "triton x100", "triton x 100",
                      "tx-100", "tx100", "octylphenol ethoxylate",
                      "p-tert-octylphenol"]),
    ("Pluronic P123",["pluronic p123", "pluronic p-123", "p-123", "p123",
                      "poloxamer 403", "eo20po70eo20"]),
    ("Pluronic F127",["pluronic f127", "pluronic f-127", "f-127", "f127",
                      "poloxamer 407", "eo106po70eo106"]),
    ("Pluronic F108",["pluronic f108", "pluronic f-108", "f-108", "f108",
                      "poloxamer 338"]),
    ("Pluronic P85", ["pluronic p85", "pluronic p-85", "p-85", "p85",
                      "poloxamer 335"]),
    ("Citrate",      ["citrate", "sodium citrate", "trisodium citrate",
                      "ammonium citrate"]),   # citric acid는 chelating에 분리
    ("Oleic acid",   ["oleic acid", "oleate", "cis-9-octadecenoic acid",
                      "c18h34o2"]),
    ("Oleylamine",   ["oleylamine", "octadecenylamine",
                      "(z)-octadec-9-en-1-amine", "c18h37n"]),
    ("DEA",          ["diethanolamine", "diethanol amine",
                      "2,2'-iminodiethanol", "hn(c2h4oh)2"]),
    ("TEA",          ["triethanolamine", "triethanol amine",
                      "2,2',2''-nitrilotriethanol", "trolamine",
                      "n(c2h4oh)3"]),
    ("Gelatin",      ["gelatin", "gelatine"]),
    ("Brij-58",      ["brij-58", "brij 58", "polyoxyethylene 20 cetyl ether",
                      "brij58"]),
    ("Brij-76",      ["brij-76", "brij 76", "polyoxyethylene 10 stearyl ether",
                      "brij76"]),
    ("Brij-35",      ["brij-35", "brij 35", "polyoxyethylene lauryl ether",
                      "brij35"]),
    ("Igepal",       ["igepal co-520", "igepal co-630", "igepal", "np-5", "np-9",
                      "nonylphenol ethoxylate", "nonidet p-40"]),
    ("PAA",          ["polyacrylic acid as capping", "poly(acrylic acid) stabilizer",
                      "paa as stabilizer", "paa-stabilized", "paa-capped"]),
    ("Stearic acid", ["stearic acid", "octadecanoic acid", "c18h36o2"]),
    ("Lauric acid",  ["lauric acid", "dodecanoic acid", "c12h24o2"]),
    ("Caprylic acid",["caprylic acid", "octanoic acid", "c8h16o2"]),
]
CHELATING_KW = [
    ("EDTA",          ["edta", "ethylenediaminetetraacetic",
                       "ethylenediaminetetraacetic acid",
                       "ethylene diamine tetraacetic",
                       "disodium edta", "na2-edta", "na2edta",
                       "edta-2na", "tetrasodium edta",
                       "c10h16n2o8"]),
    ("Citric acid",   ["citric acid", "c6h8o7", "h3c6h5o7",
                       "2-hydroxypropane-1,2,3-tricarboxylic acid"]),
    ("Acetylacetone", ["acetylacetone", " acac ", "2,4-pentanedione",
                       "pentane-2,4-dione", "acach", "hacac",
                       "c5h8o2", "acetyl acetone"]),
    ("Glycine",       ["glycine", "aminoacetic acid", "2-aminoacetic acid",
                       " gly ", "nh2ch2cooh", "c2h5no2",
                       "glycocoll"]),
    ("PVA",           ["pva as complexing", "polyvinyl alcohol pechini",
                       "pvoh pechini", "polymeric precursor method"]),
    ("Oxalic acid",   ["oxalic acid", "oxalate", "ethanedioic acid",
                       "h2c2o4", "c2h2o4"]),
    ("Tartaric acid", ["tartaric acid", "tartrate",
                       "2,3-dihydroxybutanedioic acid",
                       "sodium tartrate", "rochelle salt",
                       "c4h6o6"]),
    ("Malic acid",    ["malic acid", "malate",
                       "2-hydroxybutanedioic acid",
                       "hydroxysuccinic acid", "c4h6o5"]),
    ("Lactic acid",   ["lactic acid", "lactate",
                       "2-hydroxypropanoic acid",
                       "c3h6o3"]),
    ("Glucose",       ["glucose", "dextrose", "d-glucose",
                       "c6h12o6"]),
    ("Sucrose",       ["sucrose", "saccharose",
                       "c12h22o11"]),
    ("Starch",        ["starch", "soluble starch"]),
    ("NTA",           ["nta", "nitrilotriacetic acid", "nitrilotriacetate",
                       "n(ch2cooh)3", "c6h9no6"]),
    ("DTPA",          ["dtpa", "diethylenetriaminepentaacetic",
                       "diethylenetriaminepentaacetic acid",
                       "c14h23n3o10"]),
    ("EDA",           ["ethylenediamine", "ethylene diamine",
                       "1,2-diaminoethane", "h2n(ch2)2nh2",
                       "c2h8n2", " en "]),
    ("Succinic acid", ["succinic acid", "butanedioic acid",
                       "c4h6o4"]),
    ("Acrylic acid",  ["acrylic acid", "propenoic acid",
                       "polyacrylic acid", "paa"]),
    ("Urea",          ["urea as complexing", "urea for gelation"]),  # Pechini-type
    ("Maleic acid",   ["maleic acid", "cis-butenedioic acid", "c4h4o4",
                       "maleate"]),
    ("Fumaric acid",  ["fumaric acid", "trans-butenedioic acid", "fumarate"]),
    ("EGTA",          ["egta", "ethylene glycol tetraacetic acid",
                       "ethylene glycol-bis(2-aminoethylether)-n,n,n',n'-tetraacetic acid"]),
    ("IDA",           ["iminodiacetic acid", " ida as chelating", "iminodiacetate"]),
    ("Propionic acid",["propionic acid as complexing", "propanoic acid complexing"]),
]
OXIDANT_KW = [
    ("H2O2",        ["h2o2", "hydrogen peroxide", "aqueous hydrogen peroxide",
                     "30% h2o2", "hydrogen peroxide solution"]),
    ("HNO3",        ["hno3", "nitric acid", "dilute nitric acid",
                     "concentrated nitric acid"]),
    ("H2SO4",       ["h2so4", "sulfuric acid", "sulphuric acid",
                     "concentrated sulfuric", "dilute sulfuric"]),
    ("HCl",         ["hcl as oxidant", "hydrochloric acid dissolved"]),
    ("KMnO4",       ["kmno4", "potassium permanganate",
                     "potassium manganate(vii)"]),
    ("(NH4)2S2O8",  ["ammonium persulfate", "ammonium peroxydisulfate",
                     "(nh4)2s2o8", " aps "]),
    ("K2S2O8",      ["potassium persulfate", "potassium peroxydisulfate",
                     "k2s2o8"]),
    ("NaClO",       ["sodium hypochlorite", "naclo", "bleach"]),
    ("O3",          ["ozone", " o3 "]),
]

filled_min  = _fill_multilabel("mineralizer",    MINERALIZER_KW)
filled_cap  = _fill_multilabel("capping_agent",  CAPPING_KW)
filled_chel = _fill_multilabel("chelating_agent", CHELATING_KW)
filled_ox   = _fill_multilabel("oxidant",        OXIDANT_KW)

print(f"  광화제(mineralizer) 추가: {filled_min:,}편")
print(f"  캡핑제(capping_agent) 추가: {filled_cap:,}편")
print(f"  킬레이트제(chelating_agent) 추가: {filled_chel:,}편")
print(f"  산화제(oxidant) 추가:       {filled_ox:,}편")


# ── 10. Ce 전구체 / 용매 — 2단계 보완 ────────────────────────────────────────
# [단계1] ceria_samples_merged.csv(GPT 추출) → Excel 역전파
#         Excel의 ce_precursor/solvent(18%/38%)는 pipeline.py 초록 기반이므로
#         GPT가 전문에서 뽑은 값(ceria_samples_merged.csv)을 역전파해 커버리지 개선.
# [단계2] 여전히 빈 논문 → text/ 파일 실험 섹션에서 키워드 매칭

_SAMPLES_CSV = os.path.join(r"d:\머신러닝 교육\ceria_pipeline_data", "output", "ceria_samples_merged.csv")
_TEXT_DIR    = os.path.join(r"d:\머신러닝 교육\ceria_pipeline_data", "text")

print("\n  [Ce 전구체 / 용매 보완]")

# ── 단계 1: 샘플 CSV → Excel 역전파 ─────────────────────────────────────────
def _sync_from_samples(col: str) -> int:
    """ceria_samples_merged.csv의 GPT 추출값을 Excel 빈 셀에 역전파."""
    if not os.path.exists(_SAMPLES_CSV):
        print(f"    ! {_SAMPLES_CSV} 없음 — CSV 역전파 건너뜀")
        return 0
    try:
        df_s = pd.read_csv(_SAMPLES_CSV, dtype=str, low_memory=False)
    except Exception as e:
        print(f"    ! CSV 로드 실패: {e}")
        return 0
    if col not in df_s.columns or "doi" not in df_s.columns:
        return 0
    _bad = {"", "nan", "none", "null", "n/a", "na"}
    valid = df_s[df_s["doi"].notna() & df_s[col].notna() &
                 ~df_s[col].str.strip().str.lower().isin(_bad)]
    best = valid.groupby("doi")[col].first()
    filled = 0
    for idx in df.index[_null_mask(col) & df["doi"].notna()]:
        doi = str(df.at[idx, "doi"]).strip()
        if doi in best.index:
            df.at[idx, col] = best[doi]
            filled += 1
    return filled


# ── 단계 2: 전문 텍스트 키워드 매칭 ─────────────────────────────────────────
def _doi_to_stem(doi: str) -> str:
    return str(doi).strip().replace("/", "_").replace(":", "_")

def _load_exp_text(doi: str) -> str:
    """전문 파일에서 실험 섹션 앞 5,000자 반환 (없으면 빈 문자열)."""
    path = os.path.join(_TEXT_DIR, _doi_to_stem(doi) + ".txt")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            full = f.read().lower()
    except Exception:
        return ""
    m = re.search(
        r'(?:experimental(?:\s+(?:section|details?|procedure|part))?'
        r'|materials?\s+and\s+methods?'
        r'|synthesis\s+procedure|preparation\s+of)',
        full
    )
    start = m.start() if m else 0
    return full[start: start + 5000]


CE_PRECURSOR_KW = [
    ("Ce(NO3)3·6H2O",  ["ce(no3)3", "cerium(iii) nitrate", "cerium nitrate hexahydrate",
                         "cerium nitrate", "cerous nitrate", "ceric nitrate"]),
    ("Ce(NO3)4",       ["ce(no3)4", "cerium(iv) nitrate"]),
    ("(NH4)2Ce(NO3)6", ["(nh4)2ce(no3)6", "ceric ammonium nitrate",
                         "ammonium cerium(iv) nitrate", "ammonium cerium nitrate",
                         "ammonium ceric nitrate", " can "]),
    ("CeCl3·7H2O",     ["cecl3", "cerium(iii) chloride", "cerium chloride heptahydrate",
                         "cerium chloride", "cerous chloride"]),
    ("Ce(CH3COO)3",    ["ce(ch3coo)3", "ce(oac)3", "cerium(iii) acetate",
                         "cerium acetate hydrate", "cerium acetate", "cerous acetate"]),
    ("Ce(acac)3",      ["ce(acac)3", "cerium(iii) acetylacetonate",
                         "cerium tris(acetylacetonate)", "cerium acetylacetonate"]),
    ("Ce(acac)4",      ["ce(acac)4", "cerium(iv) acetylacetonate"]),
    ("Ce(SO4)2",       ["ce(so4)2", "ceric sulfate", "cerium(iv) sulfate"]),
    ("Ce2(SO4)3",      ["ce2(so4)3", "cerous sulfate", "cerium(iii) sulfate"]),
    ("Ce2(CO3)3",      ["ce2(co3)3", "cerium(iii) carbonate", "cerium carbonate",
                         "cerous carbonate"]),
    ("Ce(OiPr)4",      ["cerium isopropoxide", "cerium(iv) isopropoxide",
                         "cerium tetraisopropoxide", "cerium propoxide"]),
    ("Ce(OBu)4",       ["cerium n-butoxide", "cerium butoxide", "cerium(iv) butoxide",
                         "cerium tert-butoxide", "ce(obu)4"]),
    ("Ce(OEt)4",       ["cerium ethoxide", "cerium(iv) ethoxide", "ce(oet)4"]),
    ("Ce2(C2O4)3",     ["cerium(iii) oxalate", "cerium oxalate", "cerous oxalate",
                         "ce2(c2o4)3"]),
    ("Ce(OH)3",        ["ce(oh)3", "cerium(iii) hydroxide", "cerous hydroxide",
                         "cerium hydroxide"]),
    ("Ce(TMHD)3",      ["ce(tmhd)3", "cerium 2,2,6,6-tetramethyl",
                         "cerium heptanedionate"]),
    ("CeO2",           ["ceo2 starting material", "cerium oxide as precursor",
                         "starting from ceo2"]),
]

SOLVENT_KW = [
    ("water",            ["deionized water", "distilled water", "d.i. water", "di water",
                          "milli-q water", "ultrapure water", "nanopure water",
                          "aqueous solution", "dissolved in water", "in water",
                          "dissolved in h2o", "in h2o"]),          # H₂O (단독 h2o는 h2o2와 충돌 방지)
    ("ethanol",          ["dissolved in ethanol", "in ethanol", "absolute ethanol",
                          "ethanol as solvent", "ethanol as a solvent",
                          " etoh ", "c2h5oh", "c2h6o"]),           # C₂H₅OH / C₂H₆O
    ("methanol",         ["dissolved in methanol", "in methanol", "methanol as solvent",
                          " meoh ", "ch3oh", "ch4o"]),             # CH₃OH / CH₄O
    ("isopropanol",      ["isopropyl alcohol", "isopropanol", "2-propanol",
                          " ipa ", "c3h7oh", "c3h8o"]),            # C₃H₇OH
    ("ethylene glycol",  ["ethylene glycol", "1,2-ethanediol",
                          " eg ", "c2h6o2"]),                      # C₂H₆O₂
    ("diethylene glycol",["diethylene glycol", " deg ",
                          "c4h10o3"]),                             # C₄H₁₀O₃
    ("propylene glycol", ["propylene glycol", "1,2-propanediol",
                          " pg "]),                                # C₃H₈O₂ (2-methoxyethanol과 동일식 — 생략)
    ("glycerol",         ["glycerol", "glycerine", "glycerin",
                          "c3h8o3"]),                              # C₃H₈O₃
    ("DMF",              ["dimethylformamide", "n,n-dimethylformamide",
                          " dmf ", "c3h7no"]),                     # DMF 약어 추가 / C₃H₇NO
    ("DMSO",             ["dimethyl sulfoxide", " dmso ",
                          "c2h6os"]),                              # DMSO 약어 추가 / C₂H₆OS
    ("oleylamine",       ["oleylamine", "octadecenylamine",
                          "c18h37n"]),                             # C₁₈H₃₇N
    ("oleic acid",       ["oleic acid", "c18h34o2"]),              # C₁₈H₃₄O₂
    ("1-octadecene",     ["1-octadecene", "c18h36"]),              # C₁₈H₃₆
    ("toluene",          ["dissolved in toluene", "in toluene", "toluene as solvent",
                          "methylbenzene", "c7h8"]),               # C₇H₈
    ("benzyl alcohol",   ["benzyl alcohol", "phenylmethanol",
                          "c7h8o", "c6h5ch2oh"]),                  # C₇H₈O
    ("2-methoxyethanol", ["2-methoxyethanol", "ethylene glycol monomethyl ether",
                          "c3h8o2"]),                              # C₃H₈O₂
    ("1-butanol",        ["1-butanol", "n-butanol", "butan-1-ol",
                          "c4h9oh", "c4h10o"]),                    # C₄H₁₀O
    ("NMP",              ["n-methyl-2-pyrrolidone", "n-methylpyrrolidone",
                          " nmp ", "c5h9no"]),                     # NMP 약어 추가 / C₅H₉NO
    ("acetone",          ["dissolved in acetone", "in acetone", "acetone as solvent",
                          "propanone", "(ch3)2co", "c3h6o"]),      # C₃H₆O
    ("acetonitrile",     ["acetonitrile", "ch3cn", " mecn ", " acn ",
                          "c2h3n"]),                               # C₂H₃N
    ("THF",              ["tetrahydrofuran", " thf ", "oxolane",
                          "c4h8o"]),                               # C₄H₈O
    ("n-hexane",         [" hexane as solvent", "dissolved in hexane",
                          "in n-hexane", " n-hexane ", "c6h14"]),  # C₆H₁₄ (context limited)
    ("1-propanol",       ["1-propanol", "n-propanol", "propan-1-ol",
                          " npoh ", "c3h7oh"]),
    ("2-propanol",       ["2-propanol", "isopropyl alcohol", "isopropanol",
                          " ipa ", "c3h8o"]),                      # already in isopropanol entry
    ("t-butanol",        ["tert-butanol", "t-butanol", "2-methyl-2-propanol",
                          "tert-butyl alcohol"]),
    ("triethylene glycol", ["triethylene glycol", " teg ",
                             "2,2'-oxydiethan-1-ol ethoxylate",
                             "c6h14o4"]),                          # C₆H₁₄O₄
    ("cyclohexane",      ["dissolved in cyclohexane", "in cyclohexane",
                          "cyclohexane as solvent"]),
    ("xylene",           ["dissolved in xylene", "in xylene", "xylene as solvent",
                          " p-xylene ", " o-xylene ", "dimethylbenzene"]),
    ("diethyl ether",    ["diethyl ether", "ethoxyethane", "c4h10o"]),
    ("chloroform",       ["chloroform", "trichloromethane", "chcl3"]),
    ("n-octane",         [" octane as solvent", "in n-octane",
                          "octane solvent"]),
    ("isooctane",        ["isooctane", "2,2,4-trimethylpentane",
                          "isooctane solvent"]),                   # common in reverse micelle
]


def _fill_from_fulltext(col: str, keyword_map: list) -> int:
    """전문 파일에서 단일값 필드 보완 (first-match 방식, 빈 행만 대상)."""
    if col not in df.columns:
        df[col] = pd.NA
    null_idx = df.index[_null_mask(col) & df["doi"].notna()]
    filled = 0
    text_found = 0
    for idx in null_idx:
        doi = str(df.at[idx, "doi"]).strip()
        exp_text = _load_exp_text(doi)
        if not exp_text:
            continue
        text_found += 1
        for label, kws in keyword_map:
            if any(kw in exp_text for kw in kws):
                df.at[idx, col] = label
                filled += 1
                break
    print(f"    대상 {len(null_idx)}편 | 텍스트파일 {text_found}편 | 키워드매칭 {filled}편")
    return filled


# ── 실행 ─────────────────────────────────────────────────────────────────────
sync_prec = _sync_from_samples("ce_precursor")
sync_solv = _sync_from_samples("solvent")
print(f"  [단계1 CSV역전파] ce_precursor +{sync_prec}편 | solvent +{sync_solv}편")

print("  [단계2 전문텍스트]")
kw_prec = _fill_from_fulltext("ce_precursor", CE_PRECURSOR_KW)
kw_solv = _fill_from_fulltext("solvent",       SOLVENT_KW)
print(f"  Ce 전구체 합계: +{sync_prec + kw_prec}편")
print(f"  용매     합계: +{sync_solv + kw_solv}편")


# ── 저장 (임시파일 → rename 방식 — 원본 손상 방지) ───────────────────────────
existing_sheets = {}
xl = pd.ExcelFile(_output_path)
for sheet in xl.sheet_names:
    if sheet not in ("합성조건", "Sheet1"):
        existing_sheets[sheet] = xl.parse(sheet)
xl.close()

_tmp_path = _output_path.replace(".xlsx", "_tmp.xlsx")
with pd.ExcelWriter(_tmp_path, engine="openpyxl") as writer:
    df.to_excel(writer, sheet_name="합성조건", index=False)
    for sheet_name, sheet_df in existing_sheets.items():
        sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

# 쓰기 완료 후 원본 교체 (원자적)
if os.path.exists(_output_path):
    os.replace(_tmp_path, _output_path)
else:
    os.rename(_tmp_path, _output_path)

print(f"\n저장 완료: {_output_path}")
print(f"\n── 최종 채움률 ──────────────────────────────────────")
key_cols = ["synthesis_method", "morphology",
            "particle_size_tem_nm", "particle_size_sem_nm", "crystallite_size_xrd_nm",
            "crystal_phase", "ce_precursor", "solvent", "dopant"]
for col in key_cols:
    if col in df.columns:
        n = df[col].replace("", pd.NA).notna().sum()
        print(f"  {col:<32} {n:>5,}  ({n/total*100:.1f}%)")

# TEM + SEM 통합 1차입자 Size 커버리지
tem = df["particle_size_tem_nm"].replace("", pd.NA) if "particle_size_tem_nm" in df.columns else pd.Series(pd.NA, index=df.index)
sem = df["particle_size_sem_nm"].replace("", pd.NA) if "particle_size_sem_nm" in df.columns else pd.Series(pd.NA, index=df.index)
n_primary = (tem.notna() | sem.notna()).sum()
print(f"  {'[1차입자 Size (TEM or SEM)]':<32} {n_primary:>5,}  ({n_primary/total*100:.1f}%)")
