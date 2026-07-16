"""
normalize_rules.py — ce_precursor/anion/dopant 매칭 규칙 (8_normalize_data.py,
6_fill_keywords.py 공용)

34차 세션 파이프라인 리뷰에서 발견된 버그들을 고치면서, 스크립트 본문에 인라인으로
박혀 있던 순수 매칭 로직(부작용 없음 — Excel 읽기/쓰기 없음)을 분리했다.
이유:
  1. 8_normalize_data.py/6_fill_keywords.py는 import 시점에 즉시 Excel을 읽고
     쓰는 스크립트라 pytest로 직접 테스트할 수 없었음 — 순수 함수만 분리해야 테스트 가능.
  2. 같은 "화학명↔화학식 동의어" 문제가 여러 파일에 반복 등장했으므로, 최소한 이
     두 스크립트가 공유하는 부분만이라도 한 곳에 모아 향후 드리프트를 줄인다.
"""
import re
import pandas as pd

# ── 유니코드 아래첨자 정규화 ──────────────────────────────────────────────────
UNICODE_SUBSCRIPT_MAP = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


# ── ce_precursor 유효성 검증 (8_normalize_data.py Section 1d) ────────────────
def is_ce_compound(val) -> bool:
    """Ce 원소를 실제로 포함하는 화합물이면 True.

    34차 버그: 예전 코드는 `re.match(r"ce", p, re.IGNORECASE)`로 "ce"로 *시작만*
    해도 통과시켜서 "cesium chloride"(세슘, Cs)·"cetyltrimethylammonium bromide"
    (CTAB)·"cellulose acetate" 같은 무관 물질까지 세륨 화합물로 오인했다.
    화학식 표기에서 원소기호는 항상 대문자로 시작하므로("CeO2", "CeCl3", "CeIII",
    "Ce(NO3)3") "Ce" 바로 다음 글자가 소문자가 아닐 때만 화학식으로 인정한다
    (원본 문자열의 대소문자를 보존한 채로 검사 — 전부 소문자로 낮추면 이 구분이
    불가능해짐).
    """
    if pd.isna(val):
        return False
    s_orig = str(val).strip()
    if not s_orig or s_orig.lower() in ("nan", "none", "null", "n/a", ""):
        return False
    for p_orig in re.split(r"[;,]", s_orig):
        p_orig = p_orig.strip()
        if not p_orig:
            continue
        p = p_orig.lower()
        # Ce로 시작하는 화학식 표기 (CeO2, Ce(NO3)3, CeCl3, CeIII ...) —
        # 대소문자 보존 검사로 cesium/cellulose/cetyl... 등과 구분
        if re.match(r"[Cc][Ee](?![a-z])", p_orig):
            return True
        # cerium / cerous / ceric 단어 포함
        if re.search(r"\b(cerium|cerous|ceric)\b", p):
            return True
        # (NH4)2Ce... 또는 (NH4)2[Ce... 형태
        if re.search(r"\(nh4\)[\d\s]*\[?ce", p):
            return True
        # Ce를 원소로 포함하는 복합식: 앞뒤가 비문자인 Ce (예: La0.5Ce0.5O2)
        if re.search(r"(?<![a-z])ce(?![a-z])", p):
            return True
    return False


# ── ce_precursor → anion_type 파생 (8_normalize_data.py Section 6) ──────────
ANION_PATTERNS = [
    # ammonium_nitrate 먼저 — nitrate보다 우선
    ("ammonium_nitrate", r"nh4.*no3|ammonium.*nitrate|\bcan\b|ceric ammonium|\(nh4\)2ce"),
    ("nitrate",          r"no3|nitrate"),
    ("chloride",         r"cecl|\bcl\d|chloride"),
    ("acetate",          r"ch3coo|ch3co2|\boac\b|acetate"),
    ("sulfate",          r"so4|sulfate"),
    ("carbonate",        r"co3|carbonate"),
    ("acetylacetonate",  r"acac|acetylacetonate"),
    ("alkoxide",         r"oipr|oisop|\boet\b|omeo|isopropoxide|ethoxide|methoxide|butoxide|alkoxide"),
    ("oxalate",          r"c2o4|oxalate"),
    ("hydroxide",        r"ce\(oh\)|hydroxide"),
    ("carboxylate",      r"octanoate|hexanoate|2-ethylhex|stearate|oleate|laurate|propanoate|formate"),
    ("mof",              r"\bmof\b|btc\b|bdc\b|uio-|mil-|zif-"),
    # oxide: CeO2 / CeO / CeZrO2 등 — 산화물계 출발 물질
    ("oxide",            r"^ceo2$|^ceo$|cezro|\bcerium oxide\b|\bceria\b"),
    # metal_ion: Ce 금속/이온 표기 (Ce, Ce3+, Ce(III), Ce(IV) 등)
    ("metal_ion",        r"^ce$|^ce metal$|^ce\d?\+$|ce\(iii\)|ce\(iv\)|^ce3\+$|^ce4\+$"),
]


def derive_anion(val):
    """ce_precursor 값 → 음이온 유형. 반환: 매칭된 anion 문자열 / 매칭 실패시 "other" / 빈값이면 None.

    34차 버그: 예전 코드는 세미콜론으로 구분된 다중값 필드("NH4Cl; KNO3; Ce(SO4)2")를
    통째로 정규식에 넣어 `nh4.*no3`류 패턴이 서로 무관한 두 성분(첫 토큰의 NH4, 두 번째
    토큰의 NO3)에 걸쳐 매칭되는 오분류를 냈다. `is_ce_compound()`처럼 토큰 단위로
    쪼개서 각 토큰 내부에서만 매칭하도록 수정 — 토큰을 넘어가는 매칭은 발생하지 않는다.
    """
    if pd.isna(val) or not str(val).strip():
        return None
    v_full = str(val).strip().translate(UNICODE_SUBSCRIPT_MAP).lower()
    tokens = [t.strip() for t in re.split(r"[;,]", v_full) if t.strip()] or [v_full]
    for token in tokens:
        for anion, pat in ANION_PATTERNS:
            if re.search(pat, token, re.I):
                return anion
    return "other"


# ── 도핑 원소 심볼 매칭 (6_fill_keywords.py Section 4) ───────────────────────
DOPANT_SYMBOLS = [
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


def dopant_symbol_pattern(symbol: str) -> str:
    """원소기호 `symbol`의 도핑 표기 매칭 정규식.

    34차 버그: 예전 코드는 haystack을 전부 소문자로 낮춘 뒤 `case=False`로 매칭해서
    "Co"(코발트)가 "co-doped"(=여러 원소로 "공동 도핑됨"이라는 일반 접두사)와,
    "In"(인듐)이 전치사 "in"("... results **in doped** ceria ...")과 구분 없이
    매칭됐다. 화학식에서 원소기호는 항상 대문자+소문자 1글자(Co, In)로 쓰고 일반
    접두사/전치사는 소문자로 쓰는 관례를 활용해, 원소기호 부분(`symbol`)만
    대소문자를 구분하고 나머지("doped"/"CeO2" 등)는 대소문자 무관하게 매칭한다.
    호출 시 대소문자를 보존한 haystack에 `case=True`로 매칭해야 이 구분이 살아남는다.
    """
    return rf'\b{symbol}(?i:-doped|doped|/CeO2|[- ]doped\s+ceri|[- ]doped\s+ceo)'


# ── ce_precursor 전문 텍스트 키워드 (6_fill_keywords.py Section 실험섹션 보완) ─
# 34차 버그: "(NH4)2Ce(NO3)6" 항목에 있던 `" can "`이 영어 조동사 "can"과 충돌해
# ("this method **can** produce...") 무관한 논문에 ammonium ceric nitrate를
# 잘못 채울 수 있었음 — 제거. 나머지 5개 구절만으로도 충분히 식별 가능.
CE_PRECURSOR_FULLTEXT_KW = [
    ("Ce(NO3)3·6H2O",  ["ce(no3)3", "cerium(iii) nitrate", "cerium nitrate hexahydrate",
                         "cerium nitrate", "cerous nitrate", "ceric nitrate"]),
    ("Ce(NO3)4",       ["ce(no3)4", "cerium(iv) nitrate"]),
    ("(NH4)2Ce(NO3)6", ["(nh4)2ce(no3)6", "ceric ammonium nitrate",
                         "ammonium cerium(iv) nitrate", "ammonium cerium nitrate",
                         "ammonium ceric nitrate"]),
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
