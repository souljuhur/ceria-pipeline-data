import re
from typing import Optional

# ─── Text normalization ────────────────────────────────────────────────────────

_UNICODE_MAP = str.maketrans({
    "°": "°", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "·": ".", "µ": "u",
    "μ": "u", "−": "-",
})

def normalize_text_basic(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.translate(_UNICODE_MAP)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─── Synthesis method ─────────────────────────────────────────────────────────

SYNTHESIS_METHOD_PATTERNS = [
    ("Hydrothermal",          r"\bhydrothermal\b"),
    ("Solvothermal",          r"\bsolvothermal\b"),
    ("Sol-gel",               r"\bsol[-\s]gel\b"),
    ("Pechini",               r"\bpechini\b|\bmodified\s+pechini\b|\bpolymeric\s+precursor\s+method\b"
                              r"|\bpolymerizable\s+complex\b"),
    ("Co-precipitation",      r"\bco[-\s]?precipitation\b"),
    ("Precipitation",         r"\bprecipitation\b"),
    ("Combustion",            r"\b(?:solution\s+|auto[-\s]?)?combustion\b"),
    ("Spray pyrolysis",       r"\bspray\s+pyrolysis\b|\baerosol\s+pyrolysis\b"),
    ("Flame synthesis",       r"\bflame\s+(?:spray\s+)?(?:synthesis|pyrolysis)\b"),
    ("Microwave",             r"\bmicrowave[-\s]?(?:assisted|synthesis|irradiation|hydrothermal|method|treatment)?\b"),
    ("Sonochemical",          r"\b(?:sono|ultrasound[-\s]?assisted)\b"),
    ("Mechanochemical",       r"\b(?:mechanochemical|ball[-\s]?milling|planetary\s+mill)\b"),
    ("Template-assisted",     r"\btemplate[-\s]assisted\b|\bhard[-\s]?template\b|\bnanocasting\b"),
    ("Thermal decomposition", r"\bthermal\s+decomposition\b|\bthermolysis\b"),
    ("Electrochemical",       r"\belectrochemical\s+(?:synthesis|deposition|method)\b"
                              r"|\banodic\s+oxidation\b|\banodization\b"),
    ("Chemical vapor deposition", r"\b(?:chemical\s+vapor\s+deposition|CVD|ALD|"
                                  r"atomic\s+layer\s+deposition)\b"),
    ("Reverse micelle",       r"\b(?:reverse\s+micelle|reverse[-\s]?microemulsion|"
                              r"water[-\s]in[-\s]oil\s+microemulsion)\b"),
    ("Polyol",                r"\bpolyol\s+(?:synthesis|method|process|route)\b"
                              r"|\bforced\s+hydrolysis\s+in\s+polyol\b"),
    ("Freeze drying",         r"\b(?:freeze[-\s]?drying|lyophiliz(?:ation|ed))\b"),
    ("Supercritical",         r"\bsupercritical\b"),
    ("Ionothermal",           r"\bionot(?:hermal)\b"),
    ("Wet chemical",          r"\bwet[\s-]chemical\b"),
    ("Homogeneous precipitation", r"\bhomogeneous\s+precipitation\b"
                                  r"|\burea\s+hydrolysis\b|\bhmta\s+hydrolysis\b"),
    ("Reflux",                r"\breflux\s+(?:synthesis|method|condensation)\b"),
]


def extract_synthesis_method(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in SYNTHESIS_METHOD_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Particle morphology ──────────────────────────────────────────────────────

MORPHOLOGY_PATTERNS = [
    ("Sphere",                r"\bspher(?:ical|e|es)\b"),
    ("Cube",                  r"\bcub(?:ic|e|es|oid)\b"),
    ("Rod",                   r"\b(?:rod[-\s]?like|nanorod|nanorods|rod[-\s]shaped)\b"),
    ("Wire",                  r"\b(?:wire[-\s]?like|nanowire|nanowires)\b"),
    ("Tube",                  r"\b(?:tube[-\s]?like|nanotube|nanotubes)\b"),
    ("Flower",                r"\b(?:flower[-\s]?like|floral|nanoflower)\b"),
    ("Octahedron",            r"\b(?:octahedr(?:al|on|a)|octahedral)\b"),
    ("Truncated octahedron",  r"\btruncated\s+octahedr(?:al|on)\b"),
    ("Plate",                 r"\b(?:plate[-\s]?like|nanoplate|nanoplates|platelet)\b"),
    ("Sheet",                 r"\b(?:sheet[-\s]?like|nanosheet|nanosheets)\b"),
    ("Disk",                  r"\b(?:disk[-\s]?like|nanotisk)\b"),
    ("Polyhedron",            r"\b(?:polyhedr(?:al|on)|polyhedral)\b"),
    ("Hollow sphere",         r"\bhollow\s+spher(?:e|es|ical)\b"),
    ("Porous sphere",         r"\bporous\s+spher(?:e|es|ical)\b"),
    ("Core-shell",            r"\bcore[-\s]?shell\b"),
    ("Dendrite",              r"\bdendrit(?:ic|e|es)\b"),
    ("Cluster",               r"\bcluster(?:ed|s)?\b"),
    ("Irregular",             r"\birregular\b"),
    ("Agglomerate",           r"\bagglomer(?:ate|ated|ation)\b"),
    ("Nanoparticle",          r"\bnanoparticle(?:s)?\b"),
    ("Quantum dot",           r"\bquantum\s+dots?\b"),
    ("Mesoporous",            r"\bmesoporous\b"),
    ("Porous",                r"\bporous\b"),
    ("Hollow",                r"\bhollow\b"),
    ("Hierarchical",          r"\bhierarchical\b"),
    ("Hexagonal",             r"\bhexagonal\b"),
    ("Rhombic",               r"\brhombic\b"),
]


def extract_morphology(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in MORPHOLOGY_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    # Remove generic "Nanoparticle" if more specific shapes found
    if len(found) > 1 and "Nanoparticle" in found:
        found.remove("Nanoparticle")
    return "; ".join(found[:4]) if found else None


# ─── Crystal phase ────────────────────────────────────────────────────────────

CRYSTAL_PHASE_PATTERNS = [
    ("Fluorite cubic (CeO2)",   r"\bfluorite\b|\bcubic\s+fluorite\b|\bfluorite\s+structure\b"
                                r"|\bfluorite[-\s]type\b|\bFm[-\s]?3[-\s]?m\b|\bcerianite\b"),
    ("Cubic (CeO2)",            r"\bcubic\s+(?:phase|structure|CeO2)\b"),
    ("Ce2O3",                   r"\bCe[_\s]?2O[_\s]?3\b|\bcerium\s+(?:III\s+)?sesquioxide\b"),
    ("Mixed Ce3+/Ce4+",         r"\bCe[_\s]?3\+.*Ce[_\s]?4\+|Ce[_\s]?4\+.*Ce[_\s]?3\+"
                                r"|\bmixed\s+valence\b|\bCe3\+/Ce4\+\b"),
    ("Amorphous",               r"\bamorphous\b|\bnon[-\s]?crystalline\b"),
    ("Pyrochlore",              r"\bpyrochlore\b"),
    ("Defect fluorite",         r"\bdefect\s+fluorite\b|\bdefective\s+fluorite\b"
                                r"|\boxygen[-\s]deficient\s+fluorite\b"),
    ("Fluorite-derived",        r"\bfluorite[-\s]derived\b|\bfluorite[-\s]related\b"),
]


def extract_crystal_phase(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in CRYSTAL_PHASE_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Atmosphere ───────────────────────────────────────────────────────────────

ATMOSPHERE_PATTERNS = [
    ("Air",          r"\bin\s+air\b|\bair\s+atmosphere\b|\batmosphere\s+of\s+air\b|\bunder\s+air\b|\bopen\s+air\b"),
    ("N2",           r"\bN[_\s]?2\s+(?:atmosphere|flow|gas)\b|\bunder\s+N[_\s]?2\b|\bnitrogen\s+atmosphere\b"),
    ("Ar",           r"\bAr\s+(?:atmosphere|flow|gas)\b|\bunder\s+Ar\b|\bargon\s+atmosphere\b"),
    ("O2",           r"\bO[_\s]?2\s+(?:atmosphere|flow|gas)\b|\bunder\s+O[_\s]?2\b|\boxygen\s+atmosphere\b"),
    ("H2",           r"\bH[_\s]?2\s+(?:atmosphere|flow|gas)\b|\bunder\s+H[_\s]?2\b|\bhydrogen\s+atmosphere\b"),
    ("H2/Ar",        r"\bH[_\s]?2/Ar\b|\b5\s*%\s*H[_\s]?2\b|\bH[_\s]?2[-/\s]Ar\s+mix\b"
                     r"|\breducing\s+gas\s+mixture\b|\b5%\s*hydrogen\b"),
    ("CO2",          r"\bCO[_\s]?2\s+(?:atmosphere|flow|gas)\b|\bunder\s+CO[_\s]?2\b"
                     r"|\bcarbon\s+dioxide\s+atmosphere\b"),
    ("Steam",        r"\bsteam\s+atmosphere\b|\bwater\s+vapor\s+atmosphere\b|\bin\s+steam\b"),
    ("Vacuum",       r"\bvacuum\b"),
    ("Inert",        r"\binert\s+atmosphere\b|\binert\s+gas\b"),
    ("Reducing",     r"\breducing\s+atmosphere\b|\breduction\s+atmosphere\b"),
    ("Oxidizing",    r"\boxidizing\s+atmosphere\b|\boxidative\s+atmosphere\b"),
    ("Autoclave",    r"\bautoclave\b|\bsealed\s+(?:vessel|container|bomb)\b"),
]


def extract_atmosphere(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in ATMOSPHERE_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Particle size (regex) ────────────────────────────────────────────────────

# Matches: "15 nm", "5.3 nm", "15 ± 3 nm", "5-20 nm", "~15 nm", "15–30 μm"
_SIZE_VAL_RE = re.compile(
    r"(?:[~≈≤≥<>]?\s*)?"
    r"(\d+(?:\.\d+)?)"                            # main value
    r"(?:\s*[-–]\s*(\d+(?:\.\d+)?))?"            # optional range end: "5-20"
    r"(?:\s*[±\+]\s*\d+(?:\.\d+)?)?"             # optional uncertainty: "± 3"
    r"\s*(nm|[μuµ]m)\b",
    re.I,
)

_TEM_CONTEXT = re.compile(
    r"\bTEM\b|\bHRTEM\b|\bSTEM\b|\bHAADF\b"
    r"|\btransmission\s+electron\s+microscop",
    re.I,
)
_SEM_CONTEXT = re.compile(
    r"\bSEM\b|\bFE[-\s]?SEM\b|\bFESEM\b|\bFIB[-\s]?SEM\b"
    r"|\bscanning\s+electron\s+microscop",
    re.I,
)
_XRD_CONTEXT = re.compile(
    r"\bXRD\b|\bx[-\s]ray\s+diffraction\b|\bScherrer\b"
    r"|\bcrystallite\s+size\b|\bDXRD\b|\bd[_-]XRD\b|\bpowder\s+diffraction\b",
    re.I,
)

# These contexts mean the nm value is NOT a primary particle size
_EXCLUDE_CONTEXT = re.compile(
    r"\bDLS\b|\bdynamic\s+light\s+scattering\b|\bhydrodynamic\b|\bz[-\s]?average\b"
    r"|\bfilm\s+thickness\b|\blayer\s+thickness\b|\bcoating\s+thickness\b"
    r"|\bpore\s+(?:size|diameter|width|radius)\b|\bmesopore\b|\bmacropore\b"
    r"|\bwavelength\b|\bemission\s+(?:at|peak)\b|\babsorption\s+(?:at|peak|edge)\b"
    r"|\bexcitation\s+(?:at|wavelength)\b|\bband\s+gap\b"
    r"|\bparticle\s+size\s+(?:of\s+)?(?:the\s+)?(?:precursor|solvent|template)\b",
    re.I,
)

# Particle-related keywords confirming this is indeed a particle size measurement
_PARTICLE_KW_RE = re.compile(
    r"\b(?:particle|nanoparticle|nano[-\s]?particle|nanocrystal|nanosphere"
    r"|nanocube|nanorod|nano[-\s]?structure|grain)\b"
    r"|\b(?:average|mean|median|primary)\s+(?:particle|grain|crystal)?\s*(?:size|diameter|radius)\b"
    r"|\bparticle\s+(?:size|diameter|radius)\b"
    r"|\bprimary\s+particle\b"
    r"|\bnano[-\s]?(?:particle|crystal)s?\s+(?:of|with|having)\b",
    re.I,
)


def _parse_size_nm(m) -> Optional[float]:
    """Convert a _SIZE_VAL_RE match to nm. Returns midpoint for ranges."""
    val = float(m.group(1))
    unit = m.group(3).lower()
    if any(u in unit for u in ("μ", "µ", "u")):
        val *= 1000.0
    # range "5-20 nm" → midpoint
    if m.group(2):
        hi = float(m.group(2))
        if any(u in unit for u in ("μ", "µ", "u")):
            hi *= 1000.0
        val = round((val + hi) / 2, 2)
    # Valid range for CeO2 primary particles
    if val < 0.3 or val > 2000:
        return None
    return val


def extract_particle_size(text: str) -> dict:
    """
    Extract primary particle sizes (TEM/SEM) and XRD crystallite sizes.
    - Uses up to 2-sentence look-back so cross-sentence TEM/size patterns work.
    - Excludes DLS, hydrodynamic, pore size, film thickness, etc.
    - Handles ranges "5-20 nm" (→ midpoint) and uncertainty "15 ± 3 nm".
    - Requires particle-related keyword in context for TEM/SEM matches.
    """
    text = normalize_text_basic(text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = {
        "particle_size_tem_nm": None,
        "particle_size_sem_nm": None,
        "crystallite_size_xrd_nm": None,
        "particle_size_other_nm": None,
    }

    for i, sent in enumerate(sentences):
        # Skip sentences that are purely exclusion contexts
        if _EXCLUDE_CONTEXT.search(sent):
            continue

        m = _SIZE_VAL_RE.search(sent)
        if not m:
            continue

        val = _parse_size_nm(m)
        if val is None:
            continue

        # Extended context: current sentence + up to 2 prior sentences
        ctx = " ".join(sentences[max(0, i - 2):i + 1])

        # If the broader context is an exclusion context, skip
        if _EXCLUDE_CONTEXT.search(ctx):
            continue

        has_tem     = bool(_TEM_CONTEXT.search(ctx))
        has_sem     = bool(_SEM_CONTEXT.search(ctx))
        has_xrd     = bool(_XRD_CONTEXT.search(ctx))
        has_particle = bool(_PARTICLE_KW_RE.search(ctx))

        # XRD crystallite size (no TEM/SEM overlap needed)
        if has_xrd and not has_tem and not has_sem:
            if result["crystallite_size_xrd_nm"] is None:
                result["crystallite_size_xrd_nm"] = val

        # TEM primary particle (require particle keyword to reduce false positives)
        elif has_tem and not has_xrd and has_particle:
            if result["particle_size_tem_nm"] is None:
                result["particle_size_tem_nm"] = val

        # SEM primary particle (require particle keyword)
        elif has_sem and not has_xrd and has_particle:
            if result["particle_size_sem_nm"] is None:
                result["particle_size_sem_nm"] = val

        # Both TEM and SEM in context — assign based on sentence-level instrument
        elif has_tem and has_sem and has_particle:
            if _TEM_CONTEXT.search(sent) and result["particle_size_tem_nm"] is None:
                result["particle_size_tem_nm"] = val
            elif _SEM_CONTEXT.search(sent) and result["particle_size_sem_nm"] is None:
                result["particle_size_sem_nm"] = val

        # No instrument keyword — general fallback (particle keyword required)
        elif has_particle and not has_xrd:
            if result["particle_size_other_nm"] is None:
                result["particle_size_other_nm"] = val

    return result


# ─── Temperature ──────────────────────────────────────────────────────────────

_TEMP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*°?\s*[CcKk]\b",
)

_CALC_CTX  = re.compile(r"\b(?:calcin|anneal|sinter|fired|heat\s+treat)", re.I)
_DRY_CTX   = re.compile(r"\b(?:dri(?:ed|ing)|oven)\b", re.I)
_SYNTH_CTX = re.compile(r"\b(?:hydrothermal|solvothermal|reaction|autoclave|synthesized|prepared|heated|maintained)\b", re.I)


def extract_temperatures(text: str) -> dict:
    text = normalize_text_basic(text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = {
        "synthesis_temperature_c": None,
        "calcination_temperature_c": None,
        "drying_temperature_c": None,
    }

    for sent in sentences:
        temps = [float(m.group(1)) for m in _TEMP_RE.finditer(sent)]
        if not temps:
            continue
        t = temps[0]

        if _CALC_CTX.search(sent) and result["calcination_temperature_c"] is None:
            result["calcination_temperature_c"] = t
        elif _DRY_CTX.search(sent) and result["drying_temperature_c"] is None:
            result["drying_temperature_c"] = t
        elif _SYNTH_CTX.search(sent) and result["synthesis_temperature_c"] is None:
            result["synthesis_temperature_c"] = t

    return result


# ─── Time ─────────────────────────────────────────────────────────────────────

_TIME_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|min|mins|minute|minutes|day|days|week|weeks)\b",
    re.I,
)

_OVERNIGHT_RE = re.compile(r"\bovernight\b", re.I)
_ONE_DAY_RE   = re.compile(r"\bfor\s+one\s+(?:day|night)\b", re.I)


def _to_hours(value: float, unit: str) -> float:
    unit = unit.lower()
    if "min" in unit:
        return round(value / 60.0, 4)
    if "week" in unit:
        return round(value * 168.0, 4)
    if "day" in unit:
        return round(value * 24.0, 4)
    return value


def extract_times(text: str) -> dict:
    text = normalize_text_basic(text)
    # 서술적 시간 표현 → 수치로 변환
    text = _OVERNIGHT_RE.sub("12 hours", text)
    text = _ONE_DAY_RE.sub("for 24 hours", text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = {
        "synthesis_time_h": None,
        "calcination_time_h": None,
        "drying_time_h": None,
    }

    for sent in sentences:
        matches = [(float(m.group(1)), m.group(2)) for m in _TIME_RE.finditer(sent)]
        if not matches:
            continue
        t = _to_hours(*matches[0])

        if _CALC_CTX.search(sent) and result["calcination_time_h"] is None:
            result["calcination_time_h"] = t
        elif _DRY_CTX.search(sent) and result["drying_time_h"] is None:
            result["drying_time_h"] = t
        elif _SYNTH_CTX.search(sent) and result["synthesis_time_h"] is None:
            result["synthesis_time_h"] = t

    return result


# ─── BET surface area ─────────────────────────────────────────────────────────

_BET_PATTERNS = [
    # "surface area of X m2/g" 또는 "BET surface area X m2/g"
    re.compile(r"(?:BET\s+)?(?:specific\s+)?surface\s+area[^.]{0,80}?(\d+(?:\.\d+)?)\s*m[_\s]?[2²]\s*[/·]\s*g", re.I),
    # "SBET = X m2/g"
    re.compile(r"S[_\s]?BET[^.]{0,40}?[=:≈~\s]+(\d+(?:\.\d+)?)\s*m[_\s]?[2²]\s*[/·]\s*g", re.I),
    # "X m2 g-1"
    re.compile(r"(\d+(?:\.\d+)?)\s*m[_\s]?[2²]\s*g[-\s]?1\b", re.I),
    # "BET ... X m2/g" (넓은 범위)
    re.compile(r"\bBET\b[^.]{0,80}?(\d+(?:\.\d+)?)\s*m[_\s]?[2²]\s*[/·]\s*g", re.I),
]


def extract_bet_surface_area(text: str) -> Optional[float]:
    text = normalize_text_basic(text)
    for pat in _BET_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                val = float(m.group(1))
                if 1.0 <= val <= 1500.0:
                    return val
            except (ValueError, IndexError):
                pass
    return None


# ─── Main extraction function ─────────────────────────────────────────────────

# ─── pH ──────────────────────────────────────────────────────────────────────

_PH_PATTERNS = [
    re.compile(r'pH\s+(?:was\s+)?(?:adjusted\s+to\s+|set\s+to\s+|of\s+|=\s*|≈\s*)?(\d+(?:\.\d+)?)', re.I),
    re.compile(r'pH\s*[=:≈]\s*(\d+(?:\.\d+)?)', re.I),
    re.compile(r'(?:to\s+|at\s+)pH\s+(\d+(?:\.\d+)?)', re.I),
]


def extract_ph(text: str) -> Optional[float]:
    text = normalize_text_basic(text)
    for pat in _PH_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                val = float(m.group(1))
                if 0.0 <= val <= 14.0:
                    return val
            except (ValueError, IndexError):
                pass
    return None


# ─── Dopant concentration ─────────────────────────────────────────────────────

_DOPANT_CONC_PATTERNS = [
    # "5 mol%", "10 at%", "5 mole%"
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:mol|at|mole|atomic)\s*%', re.I),
    # "x = 0.1 in Ce1-xSmxO2"
    re.compile(r'\bx\s*=\s*(\d*\.?\d+)(?=\s*(?:in\s+Ce|for\s+Ce|\b))', re.I),
    # Ce0.9Sm0.1O2 → extract 0.1
    re.compile(r'Ce[_\s]?\d*\.?\d+\s*[A-Z][a-z]?[_\s]?(\d*\.?\d+)\s*O', re.I),
]

_DOPANT_FORMULA_RE = re.compile(
    r'Ce[_\s]?(\d*\.?\d+)\s*([A-Z][a-z]?)[_\s]?(\d*\.?\d+)\s*O[_\s]?\d*(?:[_\s]?[-δδ])?',
    re.I,
)


def extract_dopant_info(text: str) -> dict:
    text = normalize_text_basic(text)
    result = {"dopant_concentration": None, "dopant_formula": None}

    # formula (e.g. Ce0.9Sm0.1O2-δ)
    m = _DOPANT_FORMULA_RE.search(text)
    if m:
        result["dopant_formula"] = m.group(0).strip()
        try:
            frac = float(m.group(3))
            if 0 < frac < 1:
                result["dopant_concentration"] = f"{frac*100:.1f} mol%"
        except (ValueError, IndexError):
            pass

    # explicit concentration if not yet found
    if not result["dopant_concentration"]:
        for pat in _DOPANT_CONC_PATTERNS[:2]:  # mol% and x= patterns
            mc = pat.search(text)
            if mc:
                try:
                    val = float(mc.group(1))
                    if pat.pattern.startswith(r'(\d'):  # mol%
                        if 0 < val <= 100:
                            result["dopant_concentration"] = f"{val} mol%"
                            break
                    else:  # x=
                        if 0 < val < 1:
                            result["dopant_concentration"] = f"x={val}"
                            break
                except (ValueError, IndexError):
                    pass

    return result


# ─── Mineralizer (OH- source / precipitant) ──────────────────────────────────

MINERALIZER_PATTERNS = [
    ("NaOH",         r"\bNaOH\b|\bsodium\s+hydroxide\b|\bcaustic\s+soda\b|\blye\b"),
    ("KOH",          r"\bKOH\b|\bpotassium\s+hydroxide\b|\bcaustic\s+potash\b"),
    ("LiOH",         r"\bLiOH\b|\blithium\s+hydroxide\b"),
    ("NH3",          r"\bNH[_\s]?3\b|\bammonia(?:\s+(?:solution|water|gas|aqueous))?\b"
                     r"|\bNH[_\s]?4OH\b|\bammonium\s+hydroxide\b|\baqueous\s+ammonia\b"
                     r"|\bNH[_\s]?3\s*[·\.]\s*H[_\s]?2O\b|\bammonia\s+hydrate\b"),
    ("Urea",         r"\burea\b|\bcarbamide\b|\bCO\s*\(NH[_\s]?2\)[_\s]?2\b|\bCH[_\s]?4N[_\s]?2O\b"),
    ("HMTA",         r"\bHMTA\b|\bHMT\b|\bhexamethylenetetramine\b|\bhexamine\b"
                     r"|\burotropine\b|\bmethenamine\b|\bCH[_\s]?2\s*\)[_\s]?6N[_\s]?4\b"),
    ("TMAH",         r"\bTMAH\b|\btetramethylammonium\s+hydroxide\b"
                     r"|\btetramethyl\s+ammonium\s+hydroxide\b|\bN\(CH[_\s]?3\)[_\s]?4OH\b"
                     r"|\(CH[_\s]?3\)[_\s]?4NOH\b"),
    ("Na2CO3",       r"\bNa[_\s]?2CO[_\s]?3\b|\bsodium\s+carbonate\b|\bsoda\s+ash\b"),
    ("NaHCO3",       r"\bNaHCO[_\s]?3\b|\bsodium\s+bicarbonate\b|\bsodium\s+hydrogen\s+carbonate\b"),
    ("(NH4)2CO3",    r"\bammonium\s+carbonate\b|\(NH[_\s]?4\)[_\s]?2CO[_\s]?3\b"),
    ("NH4HCO3",      r"\bNH[_\s]?4HCO[_\s]?3\b|\bammonium\s+bicarbonate\b"
                     r"|\bammonium\s+hydrogen\s+carbonate\b"),
    ("Na2C2O4",      r"\bsodium\s+oxalate\b|\bNa[_\s]?2C[_\s]?2O[_\s]?4\b"),
    ("(NH4)2C2O4",   r"\bammonium\s+oxalate\b|\(NH[_\s]?4\)[_\s]?2C[_\s]?2O[_\s]?4\b"),
    ("K2CO3",        r"\bK[_\s]?2CO[_\s]?3\b|\bpotassium\s+carbonate\b"),
    ("TEA",          r"\btriethanolamine\b|\b2,2',2''-nitrilotriethanol\b|\btrolamine\b"
                     r"|\bN\(C[_\s]?2H[_\s]?4OH\)[_\s]?3\b"),
    ("DEA",          r"\bdiethanolamine\b|\b2,2'-iminodiethanol\b"
                     r"|\bHN\(C[_\s]?2H[_\s]?4OH\)[_\s]?2\b"),
    ("MEA",          r"\bmonoethanolamine\b|\bethanolamine\b|\bMEA\b"
                     r"|\bH[_\s]?2NCH[_\s]?2CH[_\s]?2OH\b"),
    ("NaOAc",        r"\bsodium\s+acetate\b|\bNaOAc\b|\bCH[_\s]?3COONa\b"),
    ("TEAOH",        r"\btetraethylammonium\s+hydroxide\b|\bTEAOH\b"),
]


def extract_mineralizer(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in MINERALIZER_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Capping agent / surfactant ───────────────────────────────────────────────

CAPPING_AGENT_PATTERNS = [
    ("PVP",          r"\bPVP\b|\bpolyvinylpyrrolidone\b|\bpolyvinyl\s+pyrrolidone\b"
                     r"|\bpoly\(N-vinylpyrrolidone\)\b|\bPVP[-\s]?K\d+\b"),
    ("PEG",          r"\bPEG[-\s]?\d*\b|\bpolyethylene\s+glycol\b|\bpolyethyleneglycol\b"
                     r"|\bpoly\(ethylene\s+glycol\)\b"),
    ("PVA",          r"\bPVA\b|\bpoly(?:vinyl\s+alcohol|vinylalcohol)\b|\bPVOH\b"),
    ("CTAB",         r"\bCTAB\b|\bcetyltrimethylammonium\s+bromide\b"
                     r"|\bhexadecyltrimethylammonium\s+bromide\b"),
    ("CTAC",         r"\bCTAC\b|\bcetyltrimethylammonium\s+chloride\b"),
    ("SDS",          r"\bSDS\b|\bsodium\s+dodecyl\s+sulph?ate\b|\bdodecyl\s+sulph?ate\b"
                     r"|\bsodium\s+lauryl\s+sulph?ate\b|\bSLS\b"),
    ("SDBS",         r"\bSDBS\b|\bsodium\s+dodecylbenzene\s*sulph?onate\b"),
    ("Tween-80",     r"\bTween[-\s]?80\b|\bpolysorbate\s+80\b"),
    ("Tween-20",     r"\bTween[-\s]?20\b|\bpolysorbate\s+20\b"),
    ("Span-80",      r"\bSpan[-\s]?80\b|\bsorbitan\s+monooleate\b"),
    ("Triton X-100", r"\bTriton\s*X[-\s]?100\b|\bTX[-\s]?100\b|\boctylphenol\s+ethoxylate\b"),
    ("Pluronic P123",r"\bPluronic\s*P[-\s]?123\b|\bP[-\s]?123\b|\bpoloxamer\s+403\b"),
    ("Pluronic F127",r"\bPluronic\s*F[-\s]?127\b|\bF[-\s]?127\b|\bpoloxamer\s+407\b"),
    ("Citrate",      r"\bcitrate\b(?!\s+gel)"),
    ("Oleic acid",   r"\boleic\s+acid\b|\boleate\b|\bC18H34O2\b"),
    ("Oleylamine",   r"\boleylamine\b|\bOAm\b|\boctadecenylamine\b"),
    ("DEA",          r"\bDEA\b|\bdiethanolamine\b|\b2,2'-iminodiethanol\b"),
    ("TEA",          r"\bTEA\b|\btriethanolamine\b|\b2,2',2''-nitrilotriethanol\b"),
    ("Gelatin",      r"\bgelatin\b|\bgelatine\b"),
    ("Brij",         r"\bBrij[-\s]?\d+\b|\bpolyoxyethylene\s+\d+\s+(?:cetyl|stearyl|lauryl)\s+ether\b"),
    ("Igepal",       r"\bIgepal\b|\bNP[-\s]?\d\b|\bnonylphenol\s+ethoxylate\b|\bNonidet\b"),
    ("PAA",          r"\bPAA\b|\bpoly(?:acrylic\s+acid|acrylate)\b|\bpoly\(acrylic\s+acid\)\b"
                     r"|\bpolyacrylate\s+stabiliz\b"),
    ("Stearic acid", r"\bstearic\s+acid\b|\boctadecanoic\s+acid\b|\bC[_\s]?18H[_\s]?36O[_\s]?2\b"),
    ("Lauric acid",  r"\blauric\s+acid\b|\bdodecanoic\s+acid\b|\bC[_\s]?12H[_\s]?24O[_\s]?2\b"),
    ("Caprylic acid",r"\bcaprylic\s+acid\b|\boctanoic\s+acid\b"),
]


def extract_capping_agent(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in CAPPING_AGENT_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Chelating agent ──────────────────────────────────────────────────────────

CHELATING_AGENT_PATTERNS = [
    ("EDTA",          r"\bEDTA\b|\bethylenediaminetetraacetic\s+acid\b"
                      r"|\bNa[_\s]?2[-\s]?EDTA\b|\bEDTA[-\s]?2Na\b"),
    ("Citric acid",   r"\bcitric\s+acid\b|\bC[_\s]?6H[_\s]?8O[_\s]?7\b"
                      r"|\b2-hydroxypropane-1,2,3-tricarboxylic\b"),
    ("Acetylacetone", r"\bacetylacetone\b|\bHacac\b|\bacac\b"
                      r"|\b2,4-pentanedione\b|\bpentane-2,4-dione\b|\bC[_\s]?5H[_\s]?8O[_\s]?2\b"),
    ("Glycine",       r"\bglycine\b|\baminoacetic\s+acid\b|\bC[_\s]?2H[_\s]?5NO[_\s]?2\b"
                      r"|\bH[_\s]?2NCH[_\s]?2COOH\b"),
    ("PVA",           r"\bPVA\b|\bpolyvinyl\s+alcohol\b|\bPVOH\b"),
    ("Oxalic acid",   r"\boxalic\s+acid\b|\boxalate\b|\bethanedioic\s+acid\b"
                      r"|\bH[_\s]?2C[_\s]?2O[_\s]?4\b"),
    ("Tartaric acid", r"\btartaric\s+acid\b|\btartrate\b"
                      r"|\b2,3-dihydroxybutanedioic\s+acid\b|\bC[_\s]?4H[_\s]?6O[_\s]?6\b"),
    ("Malic acid",    r"\bmalic\s+acid\b|\bmalate\b|\b2-hydroxybutanedioic\s+acid\b"
                      r"|\bhydroxysuccinic\s+acid\b|\bC[_\s]?4H[_\s]?6O[_\s]?5\b"),
    ("Lactic acid",   r"\blactic\s+acid\b|\blactate\b|\b2-hydroxypropanoic\s+acid\b"
                      r"|\bC[_\s]?3H[_\s]?6O[_\s]?3\b"),
    ("NTA",           r"\bNTA\b|\bnitrilotriacetic\s+acid\b|\bnitrilotriacetate\b"
                      r"|\bN\(CH[_\s]?2COOH\)[_\s]?3\b|\bC[_\s]?6H[_\s]?9NO[_\s]?6\b"),
    ("DTPA",          r"\bDTPA\b|\bdiethylenetriaminepentaacetic\b"
                      r"|\bC[_\s]?14H[_\s]?23N[_\s]?3O[_\s]?10\b"),
    ("Glucose",       r"\bglucose\b|\bdextrose\b|\bD-glucose\b|\bC[_\s]?6H[_\s]?12O[_\s]?6\b"),
    ("Sucrose",       r"\bsucrose\b|\bsaccharose\b|\bC[_\s]?12H[_\s]?22O[_\s]?11\b"),
    ("Starch",        r"\b(?:soluble\s+)?starch\b"),
    ("EDA",           r"\bethylenediamine\b|\bethylene\s+diamine\b"
                      r"|\b1,2-diaminoethane\b|\bC[_\s]?2H[_\s]?8N[_\s]?2\b"),
    ("Maleic acid",   r"\bmaleic\s+acid\b|\bcis-butenedioic\s+acid\b"
                      r"|\bC[_\s]?4H[_\s]?4O[_\s]?4\b|\bmaleate\b"),
    ("Fumaric acid",  r"\bfumaric\s+acid\b|\btrans-butenedioic\s+acid\b|\bfumarate\b"),
    ("Succinic acid", r"\bsuccinic\s+acid\b|\bbutanedioic\s+acid\b"
                      r"|\bC[_\s]?4H[_\s]?6O[_\s]?4\b|\bsuccinate\b"),
    ("Acrylic acid",  r"\bacrylic\s+acid\b|\bpropenoic\s+acid\b"),
    ("EGTA",          r"\bEGTA\b|\bethylene\s+glycol\s+(?:bis)?tetraacetic\s+acid\b"),
    ("IDA",           r"\biminodiacetic\s+acid\b|\bIDA\b|\biminodiacetate\b"),
]


def extract_chelating_agent(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in CHELATING_AGENT_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Oxidant ──────────────────────────────────────────────────────────────────

OXIDANT_PATTERNS = [
    ("H2O2",        r"\bH[_\s]?2O[_\s]?2\b|\bhydrogen\s+peroxide\b"),
    ("HNO3",        r"\bHNO[_\s]?3\b|\bnitric\s+acid\b"),
    ("H2SO4",       r"\bH[_\s]?2SO[_\s]?4\b|\bsulf[uh]ric\s+acid\b"),
    ("HCl",         r"\bHCl\b|\bhydrochloric\s+acid\b"),
    ("KMnO4",       r"\bKMnO[_\s]?4\b|\bpotassium\s+permanganate\b"
                    r"|\bpotassium\s+manganate\(vii\)\b"),
    ("(NH4)2S2O8",  r"\bammonium\s+per(?:sulfate|sulphate|oxydisulfate)\b"
                    r"|\(NH[_\s]?4\)[_\s]?2S[_\s]?2O[_\s]?8\b|\bAPS\b"),
    ("K2S2O8",      r"\bK[_\s]?2S[_\s]?2O[_\s]?8\b|\bpotassium\s+per(?:sulfate|sulphate)\b"
                    r"|\bpotassium\s+peroxydisulfate\b"),
    ("NaClO",       r"\bNaClO\b|\bsodium\s+hypochlorite\b|\bbleach\b"),
    ("O3",          r"\bozone\b|\bO[_\s]?3\s+(?:treatment|atmosphere|gas)\b"),
    ("Ce4+",        r"\bCe[_\s]?4\+\s+as\s+oxidant\b|\bceric\s+ion\s+oxidat\b"),
]


def extract_oxidant(text: str) -> Optional[str]:
    text = normalize_text_basic(text)
    found = []
    for label, pattern in OXIDANT_PATTERNS:
        if re.search(pattern, text, re.I):
            if label not in found:
                found.append(label)
    return "; ".join(found) if found else None


# ─── Main extraction function ─────────────────────────────────────────────────

def extract_ceria_fields_from_text(text: str) -> dict:
    text = normalize_text_basic(text)
    result = {
        "synthesis_method":    extract_synthesis_method(text),
        "morphology":          extract_morphology(text),
        "crystal_phase":       extract_crystal_phase(text),
        "atmosphere":          extract_atmosphere(text),
        "bet_surface_area":    extract_bet_surface_area(text),
        "ph_synthesis":        extract_ph(text),
        # 재료 세분화 (역설계용)
        "mineralizer":         extract_mineralizer(text),
        "capping_agent":       extract_capping_agent(text),
        "chelating_agent":     extract_chelating_agent(text),
        "oxidant":             extract_oxidant(text),
    }
    result.update(extract_particle_size(text))
    result.update(extract_temperatures(text))
    result.update(extract_times(text))
    result.update(extract_dopant_info(text))
    return result
