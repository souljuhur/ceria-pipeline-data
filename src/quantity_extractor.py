import re
from typing import List, Dict, Any, Tuple

from src.ceria_dictionary import CHEMICAL_ENTRIES


# =========================================================
# 기본 설정
# =========================================================

MAX_LINK_DISTANCE = 160

SAFE_ABBREVIATIONS_FOR_LINKING = {
    "EG", "DMF", "DMSO", "THF", "NMP", "CTAB", "SDS", "SDBS",
    "PVP", "PVA", "PEG", "HMTA", "EDTA"
}

SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[\.\?\!;])\s+')

# slash(/)는 split 대상에서 제외
CONNECTOR_FINDER_PATTERN = re.compile(
    r'\s*(,|and|with|plus|along with|or)\s*',
    re.I
)

PROCESS_VERB_STARTERS = [
    "stirred", "heated", "dried", "calcined", "washed", "transferred",
    "added", "maintained", "reacted", "prepared", "synthesized",
    "aged", "filtered", "centrifuged", "collected", "cooled", "annealed",
    "evaporated", "refluxed", "sonicated", "dispersed", "mixed"
]

PROCESS_NOUNS_AFTER_WITH = [
    "stirring", "heating", "reflux", "sonication", "agitation",
    "cooling", "washing", "drying", "calcination", "annealing",
    "filtration", "centrifugation", "evaporation", "mixing"
]


# =========================================================
# 기본 수치 패턴
# =========================================================

MASS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|g|kg)\b", re.I)
VOLUME_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(uL|µL|mL|L)\b", re.I)
AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(mmol|mol)\b", re.I)
CONC_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(mM|M)\b", re.I)
WT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(wt%|wt\. ?%|%)\b", re.I)

RATIO_PATTERN = re.compile(
    r"\b([A-Za-z]{1,10})\s*:\s*([A-Za-z]{1,10})\s*=\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\b"
)

CHEMICAL_NAME_CHARS = r"[A-Za-z0-9\-\(\)\[\],./\s]+"


# =========================================================
# 공통 유틸
# =========================================================

def normalize_text_for_quantity(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("·", ".")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def unique_dicts_by_key(records: List[Dict[str, Any]], keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for r in records:
        k = tuple(r.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def get_local_text(text: str, start: int, end: int, window: int = 60) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right]


def clip_text(text: str, max_len: int = 180) -> str:
    return text.strip()[:max_len]


def split_sentences(text: str) -> List[str]:
    text = normalize_text_for_quantity(text)
    if not text:
        return []
    return [x.strip() for x in SENTENCE_SPLIT_PATTERN.split(text) if x.strip()]


def starts_with_process_verb(text: str) -> bool:
    text = text.strip(" ,.")
    return any(re.match(rf"^{re.escape(v)}\b", text, flags=re.I) for v in PROCESS_VERB_STARTERS)


def starts_with_process_noun(text: str) -> bool:
    text = text.strip(" ,.")
    return any(re.match(rf"^{re.escape(v)}\b", text, flags=re.I) for v in PROCESS_NOUNS_AFTER_WITH)


# =========================================================
# 화학물질 span 추출
# =========================================================

def build_abbreviation_definition_cache(text: str) -> Dict[str, Dict[str, Any]]:
    """
    문서 전체를 스캔하여 'chemical name (ABBR)' 또는 'ABBR (chemical name)' 패턴을 찾아 캐싱.
    이후 등장하는 strict 약어를 정확하게 인식하기 위해 사용.
    예: "ethylene glycol (EG)" → cache["EG"] = {canonical_name, category, ...}
    """
    cache: Dict[str, Dict[str, Any]] = {}
    text_norm = normalize_text_for_quantity(text)

    for entry in CHEMICAL_ENTRIES:
        canonical_name = entry["canonical_name"]
        category = entry["category"]
        patterns = entry.get("full_patterns", entry.get("patterns", []))

        for abbr_rule in entry.get("abbreviations", []):
            abbr = abbr_rule["abbr"]
            if abbr in cache:
                continue
            for fp in patterns:
                p1 = re.compile(rf"(?:{fp})\s*[\(\[]\s*{re.escape(abbr)}\s*[\)\]]", re.I)
                p2 = re.compile(rf"\b{re.escape(abbr)}\b\s*[\(\[]\s*(?:{fp})\s*[\)\]]", re.I)
                for pat in (p1, p2):
                    m = pat.search(text_norm)
                    if m:
                        cache[abbr] = {
                            "canonical_name": canonical_name,
                            "category": category,
                            "evidence": m.group(0)[:80],
                        }
                        break
                if abbr in cache:
                    break

    # 딕셔너리에 abbreviations 필드가 없어도 일반 대문자 약어 패턴 스캔
    # "ethylene glycol (EG)" 형태를 직접 스캔 (2-5자 대문자 약어)
    gen_abbr_pat = re.compile(
        r"([A-Za-z][A-Za-z0-9\-\s]{3,60}?)\s*[\(\[]\s*([A-Z]{2,6})\s*[\)\]]"
    )
    for m in gen_abbr_pat.finditer(text_norm):
        abbr = m.group(2)
        chem_fragment = m.group(1).strip()
        if abbr in cache:
            continue
        # 해당 약어가 이미 사전 패턴으로 인식되는지 확인
        for entry in CHEMICAL_ENTRIES:
            found = False
            for fp in entry.get("full_patterns", entry.get("patterns", [])):
                if re.search(fp, chem_fragment, flags=re.I):
                    cache[abbr] = {
                        "canonical_name": entry["canonical_name"],
                        "category": entry["category"],
                        "evidence": m.group(0)[:80],
                    }
                    found = True
                    break
            if found:
                break

    return cache


def extract_chemical_spans(text: str, abbr_cache: Dict = None) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    results = []

    for entry in CHEMICAL_ENTRIES:
        canonical_name = entry["canonical_name"]
        category = entry["category"]

        # full_patterns 우선, 없으면 patterns 폴백 (하위 호환성)
        for fp in entry.get("full_patterns", entry.get("patterns", [])):
            for m in re.finditer(fp, text, flags=re.I):
                results.append({
                    "canonical_name": canonical_name,
                    "category": category,
                    "matched_text": m.group(0),
                    "span_start": m.start(),
                    "span_end": m.end(),
                    "match_type": "full_name",
                    "local_snippet": get_local_text(text, m.start(), m.end())
                })

        for abbr_rule in entry.get("abbreviations", []):
            abbr = abbr_rule.get("abbr")
            if abbr not in SAFE_ABBREVIATIONS_FOR_LINKING:
                continue
            pattern = abbr_rule.get("pattern", rf"\b{re.escape(abbr)}\b")
            flags = 0 if abbr_rule.get("case_sensitive", False) else re.I
            for m in re.finditer(pattern, text, flags=flags):
                results.append({
                    "canonical_name": canonical_name,
                    "category": category,
                    "matched_text": m.group(0),
                    "span_start": m.start(),
                    "span_end": m.end(),
                    "match_type": "safe_abbr",
                    "local_snippet": get_local_text(text, m.start(), m.end())
                })

    # 문서 약어 캐시에서 추가 인식
    if abbr_cache:
        for abbr, info in abbr_cache.items():
            for m in re.finditer(rf"\b{re.escape(abbr)}\b", text):
                results.append({
                    "canonical_name": info["canonical_name"],
                    "category": info["category"],
                    "matched_text": m.group(0),
                    "span_start": m.start(),
                    "span_end": m.end(),
                    "match_type": "cached_abbr",
                    "local_snippet": get_local_text(text, m.start(), m.end())
                })

    results = sorted(results, key=lambda x: (x["span_start"], x["span_end"], x["canonical_name"]))
    results = unique_dicts_by_key(results, ("canonical_name", "category", "span_start", "span_end"))
    return results


def find_best_chemical_by_text(fragment: str, chemical_spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    fragment_low = fragment.lower().strip()
    if not fragment_low:
        return None

    candidates = []
    for c in chemical_spans:
        ctext = c["matched_text"].lower().strip()
        if ctext and ctext in fragment_low:
            candidates.append((len(ctext), c))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]["span_start"]))
    return candidates[0][1]


# =========================================================
# 수치 span 추출
# =========================================================

def extract_quantity_spans(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    spans = []

    patterns = [
        ("mass", MASS_PATTERN),
        ("volume", VOLUME_PATTERN),
        ("amount", AMOUNT_PATTERN),
        ("concentration", CONC_PATTERN),
        ("wt_percent", WT_PATTERN),
    ]

    for qtype, pattern in patterns:
        for m in pattern.finditer(text):
            spans.append({
                "quantity_type": qtype,
                "value": float(m.group(1)),
                "unit": m.group(2),
                "raw": m.group(0),
                "span_start": m.start(),
                "span_end": m.end(),
                "local_snippet": get_local_text(text, m.start(), m.end())
            })

    spans = sorted(spans, key=lambda x: (x["span_start"], x["span_end"]))
    spans = unique_dicts_by_key(spans, ("quantity_type", "value", "unit", "span_start", "span_end"))
    return spans


def parse_quantity_string(q_str: str):
    q_str = q_str.strip()
    patterns = [
        ("mass", MASS_PATTERN),
        ("volume", VOLUME_PATTERN),
        ("amount", AMOUNT_PATTERN),
        ("concentration", CONC_PATTERN),
        ("wt_percent", WT_PATTERN),
    ]
    for qtype, pat in patterns:
        m = pat.search(q_str)
        if m:
            return qtype, float(m.group(1)), m.group(2), m.group(0)
    return None, None, None, None


# =========================================================
# connector strict split 규칙
# =========================================================

def is_quantity_led_chunk(chunk: str) -> bool:
    chunk = normalize_text_for_quantity(chunk)
    return bool(re.match(
        r'^\s*\d+(?:\.\d+)?\s*(mg|g|kg|uL|µL|mL|L|mmol|mol|mM|M|wt%|wt\. ?%|%)\b',
        chunk,
        flags=re.I
    ))


def is_chemical_parenthesis_chunk(chunk: str) -> bool:
    chunk = normalize_text_for_quantity(chunk)
    return bool(re.search(
        r'\(\s*\d+(?:\.\d+)?\s*(mg|g|kg|uL|µL|mL|L|mmol|mol|mM|M|wt%|wt\. ?%|%)\s*\)',
        chunk,
        flags=re.I
    ))


def looks_like_quantity_chemical_chunk(text: str) -> bool:
    text = normalize_text_for_quantity(text)
    if not text:
        return False

    has_quantity = bool(re.search(
        r'\b\d+(?:\.\d+)?\s*(mg|g|kg|uL|µL|mL|L|mmol|mol|mM|M|wt%|wt\. ?%|%)\b',
        text,
        flags=re.I
    ))
    has_paren_quantity = is_chemical_parenthesis_chunk(text)
    has_chemical = len(extract_chemical_spans(text)) > 0

    return (has_quantity or has_paren_quantity) and has_chemical


def should_split_on_connector(left: str, connector: str, right: str) -> bool:
    left = normalize_text_for_quantity(left).strip(" ,.")
    right = normalize_text_for_quantity(right).strip(" ,.")
    connector = connector.lower().strip()

    if not left or not right:
        return False

    left_q = is_quantity_led_chunk(left)
    right_q = is_quantity_led_chunk(right)
    left_p = is_chemical_parenthesis_chunk(left)
    right_p = is_chemical_parenthesis_chunk(right)

    if connector == "with":
        if not (left_q and right_q):
            return False
        if starts_with_process_verb(right):
            return False
        if starts_with_process_noun(right):
            return False
        return True

    if connector == "and":
        if starts_with_process_verb(right):
            return False
        if right.lower().startswith("then "):
            return False
        return (left_q and right_q) or (left_p and right_p)

    if connector == "plus":
        if starts_with_process_verb(right):
            return False
        return (left_q and right_q) or (left_p and right_p)

    if connector == "along with":
        if not (left_q and right_q):
            return False
        if starts_with_process_verb(right):
            return False
        if starts_with_process_noun(right):
            return False
        return True

    if connector == ",":
        if starts_with_process_verb(right):
            return False
        return (left_q and right_q) or (left_p and right_p)

    if connector == "or":
        return False

    return False


def split_sentence_chunks_for_parallel_mapping(sentence: str) -> List[str]:
    sentence = normalize_text_for_quantity(sentence)
    if not sentence:
        return []

    matches = list(CONNECTOR_FINDER_PATTERN.finditer(sentence))
    if not matches:
        return [sentence]

    chunks = []
    current_start = 0

    for m in matches:
        connector = m.group(1)
        left = sentence[current_start:m.start()]
        right = sentence[m.end():]

        if should_split_on_connector(left, connector, right):
            chunk = sentence[current_start:m.start()].strip(" ,.")
            if chunk:
                chunks.append(chunk)
            current_start = m.end()

    last_chunk = sentence[current_start:].strip(" ,.")
    if last_chunk:
        chunks.append(last_chunk)

    valid_chunks = [c for c in chunks if looks_like_quantity_chemical_chunk(c) or is_chemical_parenthesis_chunk(c)]
    if len(valid_chunks) >= 2:
        return chunks

    return [sentence]


# =========================================================
# chemical-quantity 링크 생성
# =========================================================

def build_link_record(
    text: str,
    chem: Dict[str, Any],
    quantity_type: str,
    value: float,
    unit: str,
    quantity_raw: str,
    q_start: int,
    q_end: int,
    pattern_type: str,
    score: float
) -> Dict[str, Any]:
    return {
        "canonical_name": chem["canonical_name"],
        "category": chem["category"],
        "chemical_raw": chem["matched_text"],
        "quantity_type": quantity_type,
        "value": value,
        "unit": unit,
        "quantity_raw": quantity_raw,
        "pair_direction": pattern_type,
        "distance": abs(chem["span_start"] - q_end),
        "score": score,
        "pair_text": clip_text(text[min(q_start, chem["span_start"]):max(q_end, chem["span_end"])]),
        "local_snippet": get_local_text(
            text,
            min(q_start, chem["span_start"]),
            max(q_end, chem["span_end"]),
            window=50
        )
    }


def extract_direct_links_from_chunk(chunk: str, chemical_spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    chunk = normalize_text_for_quantity(chunk)
    links = []

    quantity_union = r"(\d+(?:\.\d+)?)\s*(mg|g|kg|uL|µL|mL|L|mmol|mol|mM|M|wt%|wt\. ?%|%)\b"

    direct_patterns = [
        {
            "name": "quantity_of_chemical",
            "pattern": re.compile(
                rf"{quantity_union}\s+of\s+({CHEMICAL_NAME_CHARS}{{2,120}}?)(?=$|\bwas\b|\bwere\b|\bis\b|\bare\b)",
                re.I
            ),
        },
        {
            "name": "quantity_then_chemical",
            "pattern": re.compile(
                rf"{quantity_union}\s+({CHEMICAL_NAME_CHARS}{{2,120}}?)(?=$|\bwas\b|\bwere\b|\bis\b|\bare\b)",
                re.I
            ),
        },
        {
            "name": "chemical_parenthesis_quantity",
            "pattern": re.compile(
                rf"({CHEMICAL_NAME_CHARS}{{2,120}}?)\s*\(\s*{quantity_union}\s*\)$",
                re.I
            ),
        },
        {
            "name": "concentration_chemical_solution",
            "pattern": re.compile(
                rf"(\d+(?:\.\d+)?)\s*(mM|M)\s+({CHEMICAL_NAME_CHARS}{{2,100}}?)\s+solution\b",
                re.I
            ),
        },
        {
            "name": "solution_of_concentration_chemical",
            "pattern": re.compile(
                rf"\bsolution\s+of\s+(\d+(?:\.\d+)?)\s*(mM|M)\s+({CHEMICAL_NAME_CHARS}{{2,100}}?)$",
                re.I
            ),
        },
        {
            "name": "chemical_solution_of_concentration",
            "pattern": re.compile(
                rf"({CHEMICAL_NAME_CHARS}{{2,100}}?)\s+solution\s+of\s+(\d+(?:\.\d+)?)\s*(mM|M)\b",
                re.I
            ),
        },
    ]

    for cfg in direct_patterns:
        pat = cfg["pattern"]
        name = cfg["name"]

        for m in pat.finditer(chunk):
            if name in ["quantity_of_chemical", "quantity_then_chemical"]:
                value = float(m.group(1))
                unit = m.group(2)
                chem_fragment = m.group(3)
                quantity_raw = f"{m.group(1)} {m.group(2)}"
                q_start, q_end = m.start(1), m.end(2)
            elif name == "chemical_parenthesis_quantity":
                chem_fragment = m.group(1)
                value = float(m.group(2))
                unit = m.group(3)
                quantity_raw = f"{m.group(2)} {m.group(3)}"
                q_start, q_end = m.start(2), m.end(3)
            elif name == "concentration_chemical_solution":
                value = float(m.group(1))
                unit = m.group(2)
                chem_fragment = m.group(3)
                quantity_raw = f"{m.group(1)} {m.group(2)}"
                q_start, q_end = m.start(1), m.end(2)
            elif name == "solution_of_concentration_chemical":
                value = float(m.group(1))
                unit = m.group(2)
                chem_fragment = m.group(3)
                quantity_raw = f"{m.group(1)} {m.group(2)}"
                q_start, q_end = m.start(1), m.end(2)
            elif name == "chemical_solution_of_concentration":
                chem_fragment = m.group(1)
                value = float(m.group(2))
                unit = m.group(3)
                quantity_raw = f"{m.group(2)} {m.group(3)}"
                q_start, q_end = m.start(2), m.end(3)
            else:
                continue

            chem_fragment = chem_fragment.strip(" ,.;()")
            best_chem = find_best_chemical_by_text(chem_fragment, chemical_spans)
            if not best_chem:
                continue

            quantity_type, _, _, _ = parse_quantity_string(quantity_raw)
            if not quantity_type:
                continue

            score = 0.95 if "solution" in name or "parenthesis" in name or "_of_" in name else 0.90

            links.append(
                build_link_record(
                    text=chunk,
                    chem=best_chem,
                    quantity_type=quantity_type,
                    value=value,
                    unit=unit,
                    quantity_raw=quantity_raw,
                    q_start=q_start,
                    q_end=q_end,
                    pattern_type=name,
                    score=score
                )
            )

    return links


def extract_parallel_quantity_chemical_links(text: str, chemical_spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    all_links = []

    for sentence in split_sentences(text):
        chunks = split_sentence_chunks_for_parallel_mapping(sentence)
        candidate_units = []

        if len(chunks) >= 2:
            candidate_units.extend(chunks)

        candidate_units.append(sentence)

        for unit in candidate_units:
            if is_quantity_led_chunk(unit) or is_chemical_parenthesis_chunk(unit) or "solution of" in unit.lower():
                all_links.extend(extract_direct_links_from_chunk(unit, chemical_spans))

    return unique_dicts_by_key(
        all_links,
        ("canonical_name", "category", "quantity_type", "value", "unit", "pair_direction")
    )


def classify_pair_distance(q_span: Dict[str, Any], c_span: Dict[str, Any]) -> Tuple[int, str]:
    qs, qe = q_span["span_start"], q_span["span_end"]
    cs, ce = c_span["span_start"], c_span["span_end"]

    if qe <= cs:
        return cs - qe, "quantity_before_chemical"
    elif ce <= qs:
        return qs - ce, "chemical_before_quantity"
    else:
        return 0, "overlap"


def pair_score(q_span: Dict[str, Any], c_span: Dict[str, Any], text: str) -> float:
    distance, direction = classify_pair_distance(q_span, c_span)
    if distance > MAX_LINK_DISTANCE:
        return -1.0

    score = 1.0
    score -= min(distance / MAX_LINK_DISTANCE, 1.0) * 0.45

    if direction == "quantity_before_chemical":
        score += 0.18
    elif direction == "chemical_before_quantity":
        score += 0.10

    between_start = min(q_span["span_end"], c_span["span_end"])
    between_end = max(q_span["span_start"], c_span["span_start"])
    between_text = text[between_start:between_end].lower()

    if re.search(r"[.;]", between_text):
        score -= 0.35

    if re.search(r"\b(and|or|then|after|before|while|which|that|with)\b", between_text):
        score -= 0.12

    if re.search(r"\bof\b", between_text):
        score += 0.08

    local = text[min(q_span["span_start"], c_span["span_start"]):max(q_span["span_end"], c_span["span_end"])]
    if "(" in local and ")" in local:
        score += 0.12

    if q_span["quantity_type"] == "concentration":
        if c_span["category"] in ["additive", "solvent", "ce_precursor"]:
            score += 0.06
        if re.search(r"\bsolution\b", local, flags=re.I):
            score += 0.08

    return round(score, 4)


def extract_distance_based_links(text: str, chemical_spans: List[Dict[str, Any]], quantity_spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    links = []

    for q in quantity_spans:
        candidates = []
        for c in chemical_spans:
            score = pair_score(q, c, text)
            if score < 0:
                continue
            candidates.append((score, c))

        if not candidates:
            continue

        candidates = sorted(candidates, key=lambda x: (-x[0], abs(x[1]["span_start"] - q["span_end"])))
        best_score, best_chem = candidates[0]

        if best_score < 0.45:
            continue

        distance, direction = classify_pair_distance(q, best_chem)

        links.append({
            "canonical_name": best_chem["canonical_name"],
            "category": best_chem["category"],
            "chemical_raw": best_chem["matched_text"],
            "quantity_type": q["quantity_type"],
            "value": q["value"],
            "unit": q["unit"],
            "quantity_raw": q["raw"],
            "pair_direction": direction,
            "distance": distance,
            "score": best_score,
            "pair_text": clip_text(text[min(q["span_start"], best_chem["span_start"]):max(q["span_end"], best_chem["span_end"])]),
            "local_snippet": get_local_text(
                text,
                min(q["span_start"], best_chem["span_start"]),
                max(q["span_end"], best_chem["span_end"]),
                window=50
            )
        })

    return unique_dicts_by_key(
        links,
        ("canonical_name", "category", "quantity_type", "value", "unit", "pair_direction")
    )


def link_quantities_to_chemicals(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    abbr_cache = build_abbreviation_definition_cache(text)
    chemical_spans = extract_chemical_spans(text, abbr_cache=abbr_cache)
    quantity_spans = extract_quantity_spans(text)

    direct_links = extract_parallel_quantity_chemical_links(text, chemical_spans)
    distance_links = extract_distance_based_links(text, chemical_spans, quantity_spans)

    all_links = direct_links + distance_links
    all_links = sorted(all_links, key=lambda x: (-x["score"], x["canonical_name"], x["value"]))

    dedup = []
    seen = set()
    for x in all_links:
        key = (
            x["canonical_name"],
            x["category"],
            x["quantity_type"],
            x["value"],
            x["unit"]
        )
        if key in seen:
            continue
        seen.add(key)
        dedup.append(x)

    return dedup


# =========================================================
# slash(/) 전용 해석기
# =========================================================

UNIT_LIKE_SLASH_PATTERNS = [
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:c|°c)\s*/\s*(?:min|h|hr|s)\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:m2/g|m²/g)\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:g/l|mg/ml|mol/l|mmol/l|m/l)\b", re.I),
    re.compile(r"\b(?:c|°c)\s*/\s*(?:min|h|hr|s)\b", re.I),
    re.compile(r"\b(?:m2/g|m²/g|g/l|mg/ml|mol/l|mmol/l)\b", re.I),
]

SLASH_RATIO_PATTERN = re.compile(
    r"\b([A-Za-z]{1,20})\s*/\s*([A-Za-z]{1,20})\s*=\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\b"
)

SLASH_PAIR_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9\-\(\)]{0,40})\s*/\s*([A-Za-z][A-Za-z0-9\-\(\)]{0,40})\b"
)


def is_unit_like_slash(text: str) -> bool:
    return any(p.search(text) for p in UNIT_LIKE_SLASH_PATTERNS)


def extract_slash_unit_like_patterns(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    found = []

    for pat in UNIT_LIKE_SLASH_PATTERNS:
        for m in pat.finditer(text):
            found.append({
                "type": "unit_like",
                "raw": m.group(0),
                "span_start": m.start(),
                "span_end": m.end()
            })

    return unique_dicts_by_key(found, ("raw", "span_start", "span_end"))


def extract_slash_ratios(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    found = []

    for m in SLASH_RATIO_PATTERN.finditer(text):
        found.append({
            "type": "slash_ratio",
            "lhs": m.group(1),
            "rhs": m.group(2),
            "lhs_value": float(m.group(3)),
            "rhs_value": float(m.group(4)),
            "raw": m.group(0),
            "span_start": m.start(),
            "span_end": m.end()
        })

    return unique_dicts_by_key(found, ("raw", "span_start", "span_end"))


def extract_slash_solvent_mixtures(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    chemical_spans = extract_chemical_spans(text)
    found = []

    for m in SLASH_PAIR_PATTERN.finditer(text):
        raw = m.group(0)
        left = m.group(1)
        right = m.group(2)

        if is_unit_like_slash(raw):
            continue

        left_chem = find_best_chemical_by_text(left, chemical_spans)
        right_chem = find_best_chemical_by_text(right, chemical_spans)

        if not left_chem or not right_chem:
            continue

        if left_chem["category"] == "solvent" and right_chem["category"] == "solvent":
            found.append({
                "type": "slash_solvent_mixture",
                "raw": raw,
                "solvent_1": left_chem["canonical_name"],
                "solvent_2": right_chem["canonical_name"],
                "span_start": m.start(),
                "span_end": m.end()
            })

    return unique_dicts_by_key(found, ("raw", "solvent_1", "solvent_2", "span_start", "span_end"))


def extract_slash_method_or_material_pairs(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    found = []

    for m in SLASH_PAIR_PATTERN.finditer(text):
        raw = m.group(0)

        if is_unit_like_slash(raw):
            continue
        if SLASH_RATIO_PATTERN.search(raw):
            continue

        found.append({
            "type": "slash_other_pair",
            "raw": raw,
            "left": m.group(1),
            "right": m.group(2),
            "span_start": m.start(),
            "span_end": m.end()
        })

    return unique_dicts_by_key(found, ("raw", "span_start", "span_end"))


def extract_slash_patterns(text: str) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "slash_solvent_mixtures": extract_slash_solvent_mixtures(text),
        "slash_ratio_patterns": extract_slash_ratios(text),
        "slash_unit_patterns": extract_slash_unit_like_patterns(text),
        "slash_other_pairs": extract_slash_method_or_material_pairs(text)
    }


# =========================================================
# 비율 추출
# =========================================================

def extract_ratios(text: str) -> List[Dict[str, Any]]:
    text = normalize_text_for_quantity(text)
    ratios = []

    for m in RATIO_PATTERN.finditer(text):
        ratios.append({
            "lhs": m.group(1),
            "rhs": m.group(2),
            "lhs_value": float(m.group(3)),
            "rhs_value": float(m.group(4)),
            "raw": m.group(0),
            "span_start": m.start(),
            "span_end": m.end()
        })

    for x in extract_slash_ratios(text):
        ratios.append({
            "lhs": x["lhs"],
            "rhs": x["rhs"],
            "lhs_value": x["lhs_value"],
            "rhs_value": x["rhs_value"],
            "raw": x["raw"],
            "span_start": x["span_start"],
            "span_end": x["span_end"]
        })

    return unique_dicts_by_key(ratios, ("raw", "span_start", "span_end"))


# =========================================================
# 단순 quantity 추출
# =========================================================

def extract_quantities(text: str) -> Dict[str, List[Dict[str, Any]]]:
    text = normalize_text_for_quantity(text)

    results = {
        "masses": [],
        "volumes": [],
        "amounts": [],
        "concentrations": [],
        "wt_percents": [],
        "ratios": []
    }

    for m in MASS_PATTERN.finditer(text):
        results["masses"].append({"value": float(m.group(1)), "unit": m.group(2), "raw": m.group(0)})

    for m in VOLUME_PATTERN.finditer(text):
        results["volumes"].append({"value": float(m.group(1)), "unit": m.group(2), "raw": m.group(0)})

    for m in AMOUNT_PATTERN.finditer(text):
        results["amounts"].append({"value": float(m.group(1)), "unit": m.group(2), "raw": m.group(0)})

    for m in CONC_PATTERN.finditer(text):
        results["concentrations"].append({"value": float(m.group(1)), "unit": m.group(2), "raw": m.group(0)})

    for m in WT_PATTERN.finditer(text):
        results["wt_percents"].append({"value": float(m.group(1)), "unit": m.group(2), "raw": m.group(0)})

    results["ratios"] = extract_ratios(text)
    return results


# =========================================================
# 집계 함수
# =========================================================

def summarize_quantity_links(links: List[Dict[str, Any]], category: str = None) -> str:
    filtered = links if category is None else [x for x in links if x["category"] == category]
    if not filtered:
        return None

    items = []
    for x in filtered:
        items.append(f"{x['canonical_name']} [{x['value']} {x['unit']}]")

    out = []
    seen = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)

    return "; ".join(out)


def summarize_quantity_links_verbose(links: List[Dict[str, Any]]) -> str:
    if not links:
        return None

    out = []
    seen = set()
    for x in links:
        item = (
            f"{x['canonical_name']}|{x['category']}|"
            f"{x['quantity_type']}={x['value']} {x['unit']}|"
            f"score={x['score']}|pattern={x['pair_direction']}"
        )
        if item not in seen:
            seen.add(item)
            out.append(item)

    return "; ".join(out)


def summarize_slash_solvent_mixtures(items: List[Dict[str, Any]]) -> str:
    if not items:
        return None
    out = []
    seen = set()
    for x in items:
        val = f"{x['solvent_1']}/{x['solvent_2']}"
        if val not in seen:
            seen.add(val)
            out.append(val)
    return "; ".join(out)


def summarize_slash_unit_patterns(items: List[Dict[str, Any]]) -> str:
    if not items:
        return None
    out = []
    seen = set()
    for x in items:
        val = x["raw"]
        if val not in seen:
            seen.add(val)
            out.append(val)
    return "; ".join(out)


def summarize_slash_other_pairs(items: List[Dict[str, Any]]) -> str:
    if not items:
        return None
    out = []
    seen = set()
    for x in items:
        val = x["raw"]
        if val not in seen:
            seen.add(val)
            out.append(val)
    return "; ".join(out)


# =========================================================
# 테스트
# =========================================================

if __name__ == "__main__":
    sample = """
    2.17 g of cerium nitrate hexahydrate and 1.00 g citric acid were dissolved in
    50 mL ethanol, 20 mL water, and 5 mL EG.
    The slurry was prepared with 10 mL ethanol with 5 mL water.
    A solution of 0.5 M sodium hydroxide was added.
    sodium hydroxide solution of 1.0 M was also tested.
    Ethanol/water mixed solvent was used.
    EG/water = 1:4.
    The heating rate was 10 C/min and BET area was 50 m2/g.
    SEM/TEM and CeO2/ZrO2 were mentioned.
    Ce:Zr = 8:2.
    """

    print("=== chemical spans ===")
    for x in extract_chemical_spans(sample):
        print(x)

    print("\n=== quantity links ===")
    for x in link_quantities_to_chemicals(sample):
        print(x)

    print("\n=== slash patterns ===")
    slash = extract_slash_patterns(sample)
    for k, v in slash.items():
        print(f"{k}:")
        for item in v:
            print("  ", item)

    print("\n=== ratios ===")
    for x in extract_ratios(sample):
        print(x)



        