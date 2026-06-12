# Common dopant elements for CeO2 and their precursor patterns

DOPANT_ENTRIES = [
    # Rare earth dopants
    {
        "element": "Gd",
        "canonical_name": "gadolinium nitrate",
        "patterns": [
            r"gadolinium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Gd\s*\(NO[_\s]?3\)[_\s]?3",
            r"GdCl[_\s]?3",
            r"\bGDC\b",
            r"Gd-doped",
            r"Gd[_\s]?0\.\d+\s*Ce",
        ],
    },
    {
        "element": "Sm",
        "canonical_name": "samarium nitrate",
        "patterns": [
            r"samarium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Sm\s*\(NO[_\s]?3\)[_\s]?3",
            r"SmCl[_\s]?3",
            r"\bSDC\b",
            r"Sm-doped",
            r"Sm[_\s]?0\.\d+\s*Ce",
        ],
    },
    {
        "element": "La",
        "canonical_name": "lanthanum nitrate",
        "patterns": [
            r"lanthanum\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"La\s*\(NO[_\s]?3\)[_\s]?3",
            r"LaCl[_\s]?3",
            r"La-doped",
            r"La[_\s]?0\.\d+\s*Ce",
        ],
    },
    {
        "element": "Nd",
        "canonical_name": "neodymium nitrate",
        "patterns": [
            r"neodymium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Nd\s*\(NO[_\s]?3\)[_\s]?3",
            r"Nd-doped",
        ],
    },
    {
        "element": "Pr",
        "canonical_name": "praseodymium nitrate",
        "patterns": [
            r"praseodymium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Pr\s*\(NO[_\s]?3\)[_\s]?3",
            r"Pr-doped",
        ],
    },
    {
        "element": "Eu",
        "canonical_name": "europium nitrate",
        "patterns": [
            r"europium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Eu\s*\(NO[_\s]?3\)[_\s]?3",
            r"Eu-doped",
        ],
    },
    {
        "element": "Tb",
        "canonical_name": "terbium nitrate",
        "patterns": [
            r"terbium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Tb\s*\(NO[_\s]?3\)[_\s]?3",
            r"Tb-doped",
        ],
    },
    {
        "element": "Y",
        "canonical_name": "yttrium nitrate",
        "patterns": [
            r"yttrium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Y\s*\(NO[_\s]?3\)[_\s]?3",
            r"YCl[_\s]?3",
            r"\bYDC\b",
            r"Y-doped",
        ],
    },
    # Transition metal dopants
    {
        "element": "Zr",
        "canonical_name": "zirconium(IV) oxynitrate",
        "patterns": [
            r"zirconium(?:yl)?\s*(?:oxynitrate|nitrate|chloride|acetate|oxide|oxychloride)",
            r"ZrO\s*\(NO[_\s]?3\)[_\s]?2",
            r"ZrCl[_\s]?4",
            r"ZrOCl[_\s]?2",
            r"Zr-doped",
            r"ceria[-\s]zirconia",
            r"CeZrO",
            r"Ce[_\s]?\d*\.?\d*\s*Zr[_\s]?\d*\.?\d*\s*O",  # Ce0.8Zr0.2O2 형태
            r"Ce[_\s]?1[-\s]?x\s*Zr[_\s]?x",               # Ce1-xZrxO2 형태
        ],
    },
    {
        "element": "Ti",
        "canonical_name": "titanium isopropoxide",
        "patterns": [
            r"titanium\s*(?:IV\s*)?(?:isopropoxide|chloride|nitrate|oxide)",
            r"TiCl[_\s]?4",
            r"Ti\s*\(OiPr\)[_\s]?4",
            r"Ti-doped",
        ],
    },
    {
        "element": "Cu",
        "canonical_name": "copper(II) nitrate",
        "patterns": [
            r"copper\s*(?:II\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Cu\s*\(NO[_\s]?3\)[_\s]?2",
            r"CuCl[_\s]?2",
            r"Cu-doped",
            r"Cu(?:O)?[-/]CeO",
        ],
    },
    {
        "element": "Fe",
        "canonical_name": "iron(III) nitrate",
        "patterns": [
            r"iron\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Fe\s*\(NO[_\s]?3\)[_\s]?3",
            r"FeCl[_\s]?3",
            r"Fe-doped",
            r"Fe(?:2O3)?[-/]CeO",
        ],
    },
    {
        "element": "Mn",
        "canonical_name": "manganese(II) nitrate",
        "patterns": [
            r"manganese\s*(?:II\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Mn\s*\(NO[_\s]?3\)[_\s]?2",
            r"MnCl[_\s]?2",
            r"Mn-doped",
        ],
    },
    {
        "element": "Co",
        "canonical_name": "cobalt(II) nitrate",
        "patterns": [
            r"cobalt\s*(?:II\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Co\s*\(NO[_\s]?3\)[_\s]?2",
            r"CoCl[_\s]?2",
            r"Co-doped",
        ],
    },
    {
        "element": "Ni",
        "canonical_name": "nickel(II) nitrate",
        "patterns": [
            r"nickel\s*(?:II\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Ni\s*\(NO[_\s]?3\)[_\s]?2",
            r"NiCl[_\s]?2",
            r"Ni-doped",
        ],
    },
    {
        "element": "Al",
        "canonical_name": "aluminum nitrate",
        "patterns": [
            r"aluminum\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide|sulfate)",
            r"aluminium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide|sulfate)",
            r"Al\s*\(NO[_\s]?3\)[_\s]?3",
            r"AlCl[_\s]?3",
            r"Al-doped",
            r"Al[_\s]?2O[_\s]?3[-/]CeO",
        ],
    },
    {
        "element": "Si",
        "canonical_name": "tetraethyl orthosilicate",
        "patterns": [
            r"tetraethyl\s+orthosilicate",
            r"\bTEOS\b",
            r"silicon\s*(?:IV\s*)?(?:nitrate|chloride|oxide|alkoxide)",
            r"SiCl[_\s]?4",
            r"Si-doped",
            r"SiO[_\s]?2[-/]CeO",
        ],
    },
    {
        "element": "W",
        "canonical_name": "ammonium tungstate",
        "patterns": [
            r"ammonium\s+(?:meta)?tungstate",
            r"tungsten(?:ic)?\s*(?:acid|oxide|chloride|nitrate)?",
            r"WO[_\s]?3",
            r"W-doped",
        ],
    },
    {
        "element": "Mo",
        "canonical_name": "ammonium molybdate",
        "patterns": [
            r"ammonium\s+(?:hepta)?molybdate",
            r"molybdenum\s*(?:IV\s*)?(?:oxide|chloride|nitrate)?",
            r"MoO[_\s]?3",
            r"Mo-doped",
        ],
    },
    {
        "element": "Cr",
        "canonical_name": "chromium(III) nitrate",
        "patterns": [
            r"chromium\s*(?:III\s*)?(?:nitrate|chloride|acetate|oxide)",
            r"Cr\s*\(NO[_\s]?3\)[_\s]?3",
            r"CrCl[_\s]?3",
            r"Cr-doped",
        ],
    },
    {
        "element": "Ag",
        "canonical_name": "silver nitrate",
        "patterns": [
            r"silver\s+nitrate",
            r"\bAgNO[_\s]?3\b",
            r"Ag-doped",
            r"Ag(?:NPs?)?[-/]CeO",
        ],
    },
    {
        "element": "Ru",
        "canonical_name": "ruthenium(III) chloride",
        "patterns": [
            r"ruthenium\s*(?:III\s*)?(?:chloride|nitrate|oxide)?",
            r"RuCl[_\s]?3",
            r"RuO[_\s]?2",
            r"Ru-doped",
            r"Ru(?:NPs?)?[-/]CeO",
        ],
    },
    # Noble metal dopants
    {
        "element": "Pt",
        "canonical_name": "chloroplatinic acid",
        "patterns": [
            r"chloroplatinic\s+acid",
            r"platinum\s*(?:nitrate|chloride|acetate)?",
            r"H[_\s]?2PtCl[_\s]?6",
            r"Pt\s*(?:nanoparticles?|NPs?|clusters?)?[-/]CeO",
            r"Pt-doped",
            r"Pt-Ce",
        ],
    },
    {
        "element": "Pd",
        "canonical_name": "palladium(II) nitrate",
        "patterns": [
            r"palladium\s*(?:II\s*)?(?:nitrate|chloride|acetate|oxide)?",
            r"Pd\s*\(NO[_\s]?3\)[_\s]?2",
            r"PdCl[_\s]?2",
            r"Pd-doped",
        ],
    },
    {
        "element": "Au",
        "canonical_name": "chloroauric acid",
        "patterns": [
            r"chloroauric\s+acid",
            r"hydrogen\s+tetrachloroaurate",
            r"HAuCl[_\s]?4",
            r"gold\s*(?:III\s*)?(?:nitrate|chloride|acetate)?",
            r"Au-doped",
            r"Au(?:NPs?)?[-/]CeO",
        ],
    },
]
