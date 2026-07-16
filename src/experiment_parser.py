import re

from src.extract_ceria_rules import extract_ceria_fields_from_text, normalize_text_basic, split_into_clauses
from src.quantity_extractor import (
    extract_quantities,
    extract_ratios,
    extract_slash_patterns,
    link_quantities_to_chemicals,
    summarize_quantity_links,
    summarize_quantity_links_verbose,
    summarize_slash_solvent_mixtures,
    summarize_slash_unit_patterns,
    summarize_slash_other_pairs
)
from src.dopant_dictionary import DOPANT_ENTRIES

SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[\.\?\!])\s+(?=[A-Z])')

SYNTHESIS_CONTEXT = [
    r"hydrothermal", r"solvothermal", r"reaction", r"autoclave",
    r"synthesized", r"prepared", r"heated", r"maintained"
]
DRYING_CONTEXT = [
    r"dried", r"drying", r"oven-dried", r"vacuum dried"
]
CALCINATION_CONTEXT = [
    r"calcined", r"calcination", r"annealed", r"annealing", r"fired"
]
TEM_CONTEXT = [r"\btem\b", r"\bhrtem\b", r"\btransmission electron microscopy\b"]
SEM_CONTEXT = [r"\bsem\b", r"\bscanning electron microscopy\b", r"\bfesem\b"]
XRD_CONTEXT = [r"\bxrd\b", r"\bscherrer\b", r"\bcrystallite\b"]

TEMP_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*°?\s*[Cc]\b", re.I)
TIME_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|min|mins|minute|minutes)\b", re.I)
SIZE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(nm|um|µm)\b", re.I)

# DLS/수력학적 크기 관련 키워드 — 이런 문장의 크기는 1차 입자 아님
_DLS_CONTEXT_RE = re.compile(
    r"\b(?:dls|dynamic\s+light\s+scattering|hydrodynamic|z-average|"
    r"zeta|zetasizer|nanotrack|colloidal\s+size)\b",
    re.I
)


def split_sentences(text: str):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return SENTENCE_SPLIT_PATTERN.split(text)


def has_any(patterns, text):
    return any(re.search(p, text, flags=re.I) for p in patterns)


def parse_time_to_hours(value, unit):
    unit = unit.lower()
    value = float(value)
    if "min" in unit:
        return round(value / 60.0, 4)
    return value


def extract_contextual_conditions(sentence: str):
    """34차: 건조/소성이 한 문장에 같이 나오면("dried at 80C ... and then
    calcined at 500C ...") 절(clause) 단위로 나눠서 각각 판정 — 그렇지 않으면
    문장 전체의 첫 숫자가 먼저 매칭된 컨텍스트(소성이 if문에서 먼저 검사됨)에
    잘못 배정된다. extract_ceria_rules.py의 extract_temperatures/extract_times와
    동일한 버그였음(사실상 같은 로직의 중복 구현)."""
    sentence = normalize_text_basic(sentence)

    out = {
        "synthesis_temperature_c": None,
        "synthesis_time_h": None,
        "drying_temperature_c": None,
        "drying_time_h": None,
        "calcination_temperature_c": None,
        "calcination_time_h": None
    }

    for clause in split_into_clauses(sentence):
        temps = [float(m.group(1)) for m in TEMP_PATTERN.finditer(clause)]
        times = [parse_time_to_hours(m.group(1), m.group(2)) for m in TIME_PATTERN.finditer(clause)]

        if has_any(CALCINATION_CONTEXT, clause):
            if temps and out["calcination_temperature_c"] is None:
                out["calcination_temperature_c"] = temps[0]
            if times and out["calcination_time_h"] is None:
                out["calcination_time_h"] = times[0]
        elif has_any(DRYING_CONTEXT, clause):
            if temps and out["drying_temperature_c"] is None:
                out["drying_temperature_c"] = temps[0]
            if times and out["drying_time_h"] is None:
                out["drying_time_h"] = times[0]
        elif has_any(SYNTHESIS_CONTEXT, clause):
            if temps and out["synthesis_temperature_c"] is None:
                out["synthesis_temperature_c"] = temps[0]
            if times and out["synthesis_time_h"] is None:
                out["synthesis_time_h"] = times[0]

    return out


def extract_size_with_method(sentence: str):
    sentence = normalize_text_basic(sentence)

    # DLS/수력학적 크기가 언급된 문장은 무시
    if _DLS_CONTEXT_RE.search(sentence):
        return {
            "particle_size_tem_nm": None,
            "particle_size_sem_nm": None,
            "crystallite_size_xrd_nm": None,
            "particle_size_other_nm": None
        }

    sizes = []

    for m in SIZE_PATTERN.finditer(sentence):
        value = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ["um", "µm"]:
            value *= 1000.0
        sizes.append(value)

    if not sizes:
        return {
            "particle_size_tem_nm": None,
            "particle_size_sem_nm": None,
            "crystallite_size_xrd_nm": None,
            "particle_size_other_nm": None
        }

    first_size = sizes[0]

    if has_any(TEM_CONTEXT, sentence):
        return {
            "particle_size_tem_nm": first_size,
            "particle_size_sem_nm": None,
            "crystallite_size_xrd_nm": None,
            "particle_size_other_nm": None
        }
    elif has_any(SEM_CONTEXT, sentence):
        return {
            "particle_size_tem_nm": None,
            "particle_size_sem_nm": first_size,
            "crystallite_size_xrd_nm": None,
            "particle_size_other_nm": None
        }
    elif has_any(XRD_CONTEXT, sentence):
        return {
            "particle_size_tem_nm": None,
            "particle_size_sem_nm": None,
            "crystallite_size_xrd_nm": first_size,
            "particle_size_other_nm": None
        }
    else:
        return {
            "particle_size_tem_nm": None,
            "particle_size_sem_nm": None,
            "crystallite_size_xrd_nm": None,
            "particle_size_other_nm": first_size
        }


def extract_dopants(text: str):
    found = []
    for entry in DOPANT_ENTRIES:
        for p in entry["patterns"]:
            if re.search(p, text, flags=re.I):
                found.append((entry["element"], entry["canonical_name"]))
                break

    elements = sorted(set(x[0] for x in found))
    precursors = sorted(set(x[1] for x in found))

    return {
        "dopant_present": len(found) > 0,
        "dopant_elements": "; ".join(elements) if elements else None,
        "dopant_precursors": "; ".join(precursors) if precursors else None
    }


def split_experiment_blocks(text: str):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    blocks = []

    for p in paragraphs:
        if len(p) < 80:
            continue
        if re.search(
            r"\b(prepared|synthesized|dissolved|mixed|added|transferred|autoclave|calcined|dried|washed|annealed)\b",
            p,
            flags=re.I
        ):
            blocks.append(p)

    if not blocks and text.strip():
        blocks = [text.strip()]

    return blocks


def parse_experiment_block(block_text: str, experiment_id: str = None):
    base = extract_ceria_fields_from_text(block_text)
    quantities = extract_quantities(block_text)
    ratios = extract_ratios(block_text)
    slash_info = extract_slash_patterns(block_text)
    quantity_links = link_quantities_to_chemicals(block_text)
    dopants = extract_dopants(block_text)

    sentences = split_sentences(block_text)

    cond = {
        "synthesis_temperature_c": None,
        "synthesis_time_h": None,
        "drying_temperature_c": None,
        "drying_time_h": None,
        "calcination_temperature_c": None,
        "calcination_time_h": None,
        "particle_size_tem_nm": None,
        "particle_size_sem_nm": None,
        "crystallite_size_xrd_nm": None,
        "particle_size_other_nm": None
    }

    for sent in sentences:
        c = extract_contextual_conditions(sent)
        for k, v in c.items():
            if v is not None and cond.get(k) is None:
                cond[k] = v

        size_info = extract_size_with_method(sent)
        for k, v in size_info.items():
            if v is not None and cond.get(k) is None:
                cond[k] = v

    result = {}
    result.update(base)
    # 34차: dict.update()는 cond의 None까지 덮어써서 base가 이미 정확히 찾아둔 값을
    # 지워버릴 수 있었음(예: cond가 문장 분리 방식이 달라 base보다 못 찾는 경우) —
    # None이 아닌 값만 덮어써서 base/cond 중 하나라도 찾은 값은 보존한다.
    for k, v in cond.items():
        if v is not None:
            result[k] = v
    result.update(dopants)

    result["experiment_id"] = experiment_id
    result["raw_block_text"] = block_text[:5000]

    # 단순 quantity
    result["mass_values"] = "; ".join(x["raw"] for x in quantities["masses"]) if quantities["masses"] else None
    result["volume_values"] = "; ".join(x["raw"] for x in quantities["volumes"]) if quantities["volumes"] else None
    result["amount_values"] = "; ".join(x["raw"] for x in quantities["amounts"]) if quantities["amounts"] else None
    result["concentration_values"] = "; ".join(x["raw"] for x in quantities["concentrations"]) if quantities["concentrations"] else None
    result["wt_percent_values"] = "; ".join(x["raw"] for x in quantities["wt_percents"]) if quantities["wt_percents"] else None
    result["ratio_values"] = "; ".join(x["raw"] for x in ratios) if ratios else None

    # chemical-quantity pairs
    result["chemical_quantity_pairs"] = summarize_quantity_links_verbose(quantity_links)
    result["ce_precursor_amounts"] = summarize_quantity_links(quantity_links, "ce_precursor")
    result["solvent_amounts"] = summarize_quantity_links(quantity_links, "solvent")
    result["additive_amounts"] = summarize_quantity_links(quantity_links, "additive")
    result["template_agent_amounts"] = summarize_quantity_links(quantity_links, "template_agent")

    result["chemical_quantity_pair_count"] = len(quantity_links)
    result["chemical_quantity_pair_snippets"] = " || ".join(
        sorted(set(x["local_snippet"] for x in quantity_links[:20]))
    ) if quantity_links else None

    # slash(/) 구조 정보
    result["slash_solvent_mixtures"] = summarize_slash_solvent_mixtures(
        slash_info.get("slash_solvent_mixtures", [])
    )
    result["slash_unit_patterns"] = summarize_slash_unit_patterns(
        slash_info.get("slash_unit_patterns", [])
    )
    result["slash_other_pairs"] = summarize_slash_other_pairs(
        slash_info.get("slash_other_pairs", [])
    )
    result["slash_ratio_values"] = "; ".join(
        x["raw"] for x in slash_info.get("slash_ratio_patterns", [])
    ) if slash_info.get("slash_ratio_patterns") else None

    return result


def parse_experiments_from_text(text: str, paper_id: str = None):
    blocks = split_experiment_blocks(text)
    records = []

    for i, block in enumerate(blocks, start=1):
        exp_id = f"{paper_id}_EXP{i:03d}" if paper_id else f"EXP{i:03d}"
        rec = parse_experiment_block(block, experiment_id=exp_id)
        records.append(rec)

    return records