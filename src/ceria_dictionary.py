# Ceria synthesis chemical dictionary
# Used by quantity_extractor.py to link measured quantities to chemical entities.

CHEMICAL_ENTRIES = [
    # ─── Ce Precursors ────────────────────────────────────────────────────────
    {
        "name": "cerium nitrate hexahydrate",
        "canonical_name": "Ce(NO3)3·6H2O",
        "category": "ce_precursor",
        "patterns": [
            # "cerium nitrate", "cerium(III) nitrate", "cerium III nitrate" 모두 커버
            r"cerium\s*(?:\(?\s*III\s*\)?\s*)?nitrate\s*(?:hexahydrate|anhydrous)?",
            r"Ce\s*\(NO[_\s]?3\)[_\s]?3\s*[·\.]?\s*6\s*H[_\s]?2\s*O",
            r"Ce\s*\(NO[_\s]?3\)[_\s]?3(?!\s*\))",
            r"cerous\s+nitrate",
            r"ceric\s+nitrate",          # Ce4+ 질산염도 커버
        ],
    },
    {
        "name": "ammonium cerium(IV) nitrate",
        "canonical_name": "(NH4)2Ce(NO3)6",
        "category": "ce_precursor",
        "patterns": [
            r"ammonium\s+cerium(?:\s*\(?\s*IV\s*\)?\s*)?\s+nitrate",
            r"ceric\s+ammonium\s+nitrate",       # 흔한 별칭
            r"\(NH[_\s]?4\)[_\s]?2\s*Ce\s*\(NO[_\s]?3\)[_\s]?6",
            # CAN: 화학 문맥에서만 매칭 (modal verb "can" 제외)
            r"\bCAN\b(?=\s*(?:solution|powder|precursor|salt|\(|was\b|were\b|is\b|are\b|as\b|of\b|in\b|from\b|dissolved\b|obtained\b|purchased\b|used\b))",
        ],
    },
    {
        "name": "cerium chloride heptahydrate",
        "canonical_name": "CeCl3·7H2O",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*(?:\(?\s*III\s*\)?\s*)?chloride\s*(?:heptahydrate|anhydrous)?",
            r"CeCl[_\s]?3\s*[·\.]?\s*7\s*H[_\s]?2\s*O",
            r"CeCl[_\s]?3(?!\s*\))",
            r"cerous\s+chloride",
        ],
    },
    {
        "name": "cerium(III) acetate hydrate",
        "canonical_name": "Ce(CH3COO)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*(?:\(?\s*III\s*\)?\s*)?acetate",
            r"Ce\s*\(CH[_\s]?3\s*COO\)[_\s]?3",
            r"Ce\s*\(OOCCH[_\s]?3\)[_\s]?3",
            r"Ce\s*\(OAc\)[_\s]?3",             # Ce(OAc)3 표기
            r"cerous\s+acetate",
        ],
    },
    {
        "name": "cerium(III) acetylacetonate",
        "canonical_name": "Ce(acac)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*(?:\(?\s*III\s*\)?\s*)?acetylacetonate",
            r"cerium\s+tris\s*[\(\[]?\s*acetylacetonate",
            r"Ce\s*\(acac\)[_\s]?3",
            r"Ce\s*\(C[_\s]?5H[_\s]?7O[_\s]?2\)[_\s]?3",
        ],
    },
    {
        "name": "cerium(IV) sulfate",
        "canonical_name": "Ce(SO4)2",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*\(?\s*IV\s*\)?\s*sulfate",
            r"Ce\s*\(SO[_\s]?4\)[_\s]?2",
            r"ceric\s+sulfate",
        ],
    },
    {
        "name": "cerium(III) sulfate",
        "canonical_name": "Ce2(SO4)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*\(?\s*III\s*\)?\s*sulfate",
            r"cerous\s+sulfate",
            r"Ce[_\s]?2\s*\(SO[_\s]?4\)[_\s]?3",
        ],
    },
    {
        "name": "cerium(III) carbonate",
        "canonical_name": "Ce2(CO3)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*(?:\(?\s*III\s*\)?\s*)?carbonate",
            r"Ce[_\s]?2\s*\(CO[_\s]?3\)[_\s]?3",
            r"CeCO[_\s]?3",
            r"cerous\s+carbonate",
        ],
    },
    {
        "name": "cerium isopropoxide",
        "canonical_name": "Ce(OiPr)4",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s+(?:tetra)?isopropoxide",
            r"cerium\s+(?:IV\s+)?alkoxide",
            r"Ce\s*\(OiPr\)[_\s]?4",
            r"Ce\s*\(OC[_\s]?3H[_\s]?7\)[_\s]?4",
        ],
    },
    {
        "name": "cerium ethoxide",
        "canonical_name": "Ce(OEt)4",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s+(?:tetra)?ethoxide",
            r"Ce\s*\(OEt\)[_\s]?4",
            r"Ce\s*\(OC[_\s]?2H[_\s]?5\)[_\s]?4",
        ],
    },
    {
        "name": "cerium 2-ethylhexanoate",
        "canonical_name": "Ce(2-EHA)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s+(?:2-)?ethylhexanoate",
            r"cerium\s+(?:2-)?ethylhexan(?:oate|oic)",
            r"Ce\s*\(2-EHA\)",
        ],
    },

    # ─── Solvents ─────────────────────────────────────────────────────────────
    {
        "name": "water",
        "canonical_name": "H2O",
        "category": "solvent",
        "patterns": [
            r"\bwater\b",
            r"deionized\s+water",
            r"distilled\s+water",
            r"D\.?I\.?\s*water",
            r"\bH[_\s]?2\s*O\b",
            r"aqueous\s+solution",
        ],
    },
    {
        "name": "ethanol",
        "canonical_name": "EtOH",
        "category": "solvent",
        "patterns": [
            r"\bethanol\b",
            r"\bEtOH\b",
            r"\bC[_\s]?2H[_\s]?5OH\b",
            r"absolute\s+alcohol",
        ],
    },
    {
        "name": "methanol",
        "canonical_name": "MeOH",
        "category": "solvent",
        "patterns": [
            r"\bmethanol\b",
            r"\bMeOH\b",
            r"\bCH[_\s]?3OH\b",
        ],
    },
    {
        "name": "isopropanol",
        "canonical_name": "IPA",
        "category": "solvent",
        "patterns": [
            r"\bisopropanol\b",
            r"\bisopropyl\s+alcohol\b",
            r"\b2-propanol\b",
            r"\bIPA\b",
        ],
    },
    {
        "name": "ethylene glycol",
        "canonical_name": "EG",
        "category": "solvent",
        "patterns": [
            r"ethylene\s+glycol",
            r"\bEG\b(?!\s*(?:XRD|TEM|SEM))",
        ],
    },
    {
        "name": "diethylene glycol",
        "canonical_name": "DEG",
        "category": "solvent",
        "patterns": [
            r"diethylene\s+glycol",
            r"\bDEG\b",
        ],
    },
    {
        "name": "polyethylene glycol",
        "canonical_name": "PEG",
        "category": "solvent",
        "patterns": [
            r"polyethylene\s+glycol",
            r"\bPEG[-_\s]?\d*\b",
        ],
    },
    {
        "name": "oleylamine",
        "canonical_name": "OLA",
        "category": "solvent",
        "patterns": [
            r"\boleylamine\b",
            r"\bOLA\b",
        ],
    },
    {
        "name": "oleic acid",
        "canonical_name": "OA",
        "category": "solvent",
        "patterns": [
            r"\boleic\s+acid\b",
        ],
    },
    {
        "name": "1-octadecene",
        "canonical_name": "ODE",
        "category": "solvent",
        "patterns": [
            r"1-octadecene",
            r"\bODE\b",
            r"octadecene",
        ],
    },
    {
        "name": "dimethylformamide",
        "canonical_name": "DMF",
        "category": "solvent",
        "patterns": [
            r"dimethylformamide",
            r"N,N-dimethylformamide",
            r"\bDMF\b",
        ],
    },
    {
        "name": "dimethyl sulfoxide",
        "canonical_name": "DMSO",
        "category": "solvent",
        "patterns": [
            r"dimethyl\s+sulfoxide",
            r"\bDMSO\b",
        ],
    },
    {
        "name": "acetone",
        "canonical_name": "acetone",
        "category": "solvent",
        "patterns": [
            r"\bacetone\b",
            r"\b\(CH[_\s]?3\)[_\s]?2CO\b",
        ],
    },
    {
        "name": "benzyl alcohol",
        "canonical_name": "BnOH",
        "category": "solvent",
        "patterns": [
            r"\bbenzyl\s+alcohol\b",
            r"\bBnOH\b",
        ],
    },
    {
        "name": "toluene",
        "canonical_name": "toluene",
        "category": "solvent",
        "patterns": [r"\btoluene\b"],
    },
    {
        "name": "hexane",
        "canonical_name": "hexane",
        "category": "solvent",
        "patterns": [r"\bhexane\b", r"\bn-hexane\b"],
    },
    {
        "name": "N-methyl-2-pyrrolidone",
        "canonical_name": "NMP",
        "category": "solvent",
        "patterns": [
            r"N-methyl-2-pyrrolidinone",
            r"N-methylpyrrolidone",
            r"\bNMP\b",
        ],
    },
    {
        "name": "n-propanol",
        "canonical_name": "n-PrOH",
        "category": "solvent",
        "patterns": [
            r"\bn-propanol\b",
            r"\b1-propanol\b",
            r"\bpropan-1-ol\b",
            r"\bn-PrOH\b",
        ],
    },
    {
        "name": "glycerol",
        "canonical_name": "glycerol",
        "category": "solvent",
        "patterns": [
            r"\bglycerol\b",
            r"\bglycerine?\b",
            r"\bpropane-1,2,3-triol\b",
        ],
    },
    {
        "name": "formic acid",
        "canonical_name": "HCOOH",
        "category": "solvent",
        "patterns": [
            r"\bformic\s+acid\b",
            r"\bHCOOH\b",
            r"\bmethanoic\s+acid\b",
        ],
    },
    {
        "name": "acetonitrile",
        "canonical_name": "MeCN",
        "category": "solvent",
        "patterns": [
            r"\bacetonitrile\b",
            r"\bMeCN\b",
            r"\bCH[_\s]?3CN\b",
        ],
    },
    {
        "name": "diethyl ether",
        "canonical_name": "Et2O",
        "category": "solvent",
        "patterns": [
            r"\bdiethyl\s+ether\b",
            r"\bEt[_\s]?2O\b",
        ],
    },

    # ─── Additives / Mineralizers / pH agents ─────────────────────────────────
    {
        "name": "sodium hydroxide",
        "canonical_name": "NaOH",
        "category": "additive",
        "patterns": [
            r"sodium\s+hydroxide",
            r"\bNaOH\b",
        ],
    },
    {
        "name": "potassium hydroxide",
        "canonical_name": "KOH",
        "category": "additive",
        "patterns": [
            r"potassium\s+hydroxide",
            r"\bKOH\b",
        ],
    },
    {
        "name": "ammonia / ammonium hydroxide",
        "canonical_name": "NH3·H2O",
        "category": "additive",
        "patterns": [
            r"ammonium\s+hydroxide",
            r"ammonia\s+(?:water|solution|aqueous)",
            r"aqueous\s+ammonia",
            r"\bNH[_\s]?3\b",
            r"NH[_\s]?4OH",
        ],
    },
    {
        "name": "urea",
        "canonical_name": "urea",
        "category": "additive",
        "patterns": [
            r"\burea\b",
            r"\bCO\s*\(NH[_\s]?2\)[_\s]?2\b",
        ],
    },
    {
        "name": "hexamethylenetetramine",
        "canonical_name": "HMTA",
        "category": "additive",
        "patterns": [
            r"hexamethylenetetramine",
            r"hexamethylene\s+tetramine",
            r"\bHMTA\b",
            r"\bHMT\b",
        ],
    },
    {
        "name": "citric acid",
        "canonical_name": "citric acid",
        "category": "additive",
        "patterns": [
            r"citric\s+acid",
        ],
    },
    {
        "name": "acetic acid",
        "canonical_name": "CH3COOH",
        "category": "additive",
        "patterns": [
            r"acetic\s+acid",
            r"glacial\s+acetic",
            r"\bCH[_\s]?3COOH\b",
            r"\bHOAc\b",
        ],
    },
    {
        "name": "nitric acid",
        "canonical_name": "HNO3",
        "category": "additive",
        "patterns": [
            r"nitric\s+acid",
            r"\bHNO[_\s]?3\b",
        ],
    },
    {
        "name": "hydrochloric acid",
        "canonical_name": "HCl",
        "category": "additive",
        "patterns": [
            r"hydrochloric\s+acid",
            r"\bHCl\b",
        ],
    },
    {
        "name": "hydrogen peroxide",
        "canonical_name": "H2O2",
        "category": "additive",
        "patterns": [
            r"hydrogen\s+peroxide",
            r"\bH[_\s]?2O[_\s]?2\b",
        ],
    },
    {
        "name": "sodium carbonate",
        "canonical_name": "Na2CO3",
        "category": "additive",
        "patterns": [
            r"sodium\s+carbonate",
            r"\bNa[_\s]?2CO[_\s]?3\b",
        ],
    },
    {
        "name": "sodium bicarbonate",
        "canonical_name": "NaHCO3",
        "category": "additive",
        "patterns": [
            r"sodium\s+bicarbonate",
            r"sodium\s+hydrogen\s+carbonate",
            r"\bNaHCO[_\s]?3\b",
        ],
    },
    {
        "name": "EDTA",
        "canonical_name": "EDTA",
        "category": "additive",
        "patterns": [
            r"ethylenediaminetetraacetic\s+acid",
            r"\bEDTA\b",
        ],
    },
    {
        "name": "triethylamine",
        "canonical_name": "TEA",
        "category": "additive",
        "patterns": [
            r"triethylamine",
            r"\bTEA\b(?!\s*(?:TEM|SEM))",
        ],
    },
    {
        "name": "triethanolamine",
        "canonical_name": "TEOA",
        "category": "additive",
        "patterns": [
            r"triethanolamine",
            r"\bTEOA\b",
        ],
    },
    {
        "name": "ethylenediamine",
        "canonical_name": "EDA",
        "category": "additive",
        "patterns": [
            r"ethylenediamine",
            r"ethylene\s+diamine",
            r"\bEDA\b",
            r"\bEN\b(?=\s+(?:as|was|were|is))",
        ],
    },
    {
        "name": "glycine",
        "canonical_name": "glycine",
        "category": "additive",
        "patterns": [
            r"\bglycine\b",
            r"\baminoacetic\s+acid\b",
        ],
    },
    {
        "name": "monoethanolamine",
        "canonical_name": "MEA",
        "category": "additive",
        "patterns": [
            r"\bmonoethanolamine\b",
            r"\bethanolamine\b",
            r"\bMEA\b(?=\s+(?:as|was|were|is|solution))",
        ],
    },
    {
        "name": "oxalic acid",
        "canonical_name": "H2C2O4",
        "category": "additive",
        "patterns": [
            r"\boxalic\s+acid\b",
            r"\bH[_\s]?2C[_\s]?2O[_\s]?4\b",
        ],
    },
    {
        "name": "succinic acid",
        "canonical_name": "succinic acid",
        "category": "additive",
        "patterns": [
            r"\bsuccinic\s+acid\b",
        ],
    },
    {
        "name": "tartaric acid",
        "canonical_name": "tartaric acid",
        "category": "additive",
        "patterns": [
            r"\btartaric\s+acid\b",
        ],
    },
    {
        "name": "hydrogen peroxide",
        "canonical_name": "H2O2",
        "category": "oxidizer",
        "patterns": [
            r"hydrogen\s+peroxide",
            r"\bH[_\s]?2O[_\s]?2\b",
        ],
    },

    # ─── Template / Surfactant agents ─────────────────────────────────────────
    {
        "name": "CTAB",
        "canonical_name": "CTAB",
        "category": "template_agent",
        "patterns": [
            r"cetyltrimethylammonium\s+bromide",
            r"hexadecyltrimethylammonium\s+bromide",
            r"\bCTAB\b",
        ],
    },
    {
        "name": "polyvinylpyrrolidone",
        "canonical_name": "PVP",
        "category": "template_agent",
        "patterns": [
            r"polyvinylpyrrolidone",
            r"polyvinyl\s+pyrrolidone",
            r"\bPVP\b",
        ],
    },
    {
        "name": "polyvinyl alcohol",
        "canonical_name": "PVA",
        "category": "template_agent",
        "patterns": [
            r"poly(?:vinyl\s+alcohol|vinylalcohol)",
            r"\bPVA\b",
        ],
    },
    {
        "name": "SDS",
        "canonical_name": "SDS",
        "category": "template_agent",
        "patterns": [
            r"sodium\s+dodecyl\s+sulfate",
            r"sodium\s+lauryl\s+sulfate",
            r"\bSDS\b",
            r"\bSLS\b",
        ],
    },
    {
        "name": "Pluronic P123",
        "canonical_name": "P123",
        "category": "template_agent",
        "patterns": [
            r"Pluronic\s+P[-\s]?123",
            r"\bP[-\s]?123\b",
        ],
    },
    {
        "name": "Pluronic F127",
        "canonical_name": "F127",
        "category": "template_agent",
        "patterns": [
            r"Pluronic\s+F[-\s]?127",
            r"\bF[-\s]?127\b",
        ],
    },
    {
        "name": "SDBS",
        "canonical_name": "SDBS",
        "category": "template_agent",
        "patterns": [
            r"sodium\s+dodecylbenzenesulfonate",
            r"\bSDBS\b",
        ],
    },
    {
        "name": "Tween-20",
        "canonical_name": "Tween-20",
        "category": "template_agent",
        "patterns": [
            r"\bTween[-\s]?20\b",
            r"\bpolysorbate\s+20\b",
        ],
    },
    {
        "name": "Tween-80",
        "canonical_name": "Tween-80",
        "category": "template_agent",
        "patterns": [
            r"\bTween[-\s]?80\b",
            r"\bpolysorbate\s+80\b",
        ],
    },
    {
        "name": "Triton X-100",
        "canonical_name": "Triton X-100",
        "category": "template_agent",
        "patterns": [
            r"\bTriton\s+X[-\s]?100\b",
            r"\boctylphenol\s+ethoxylate\b",
        ],
    },
    {
        "name": "cerium oxalate",
        "canonical_name": "Ce2(C2O4)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*(?:III\s*)?oxalate",
            r"Ce[_\s]?2\s*\(C[_\s]?2O[_\s]?4\)[_\s]?3",
        ],
    },
    {
        "name": "cerium(III) hydroxide",
        "canonical_name": "Ce(OH)3",
        "category": "ce_precursor",
        "patterns": [
            r"cerium\s*(?:III\s*)?hydroxide",
            r"Ce\s*\(OH\)[_\s]?3",
            r"cerous\s+hydroxide",
        ],
    },
]
