"""
기존 ceria_synthesis_database.xlsx에
is_oa / tagged_methods / tagged_morphologies 컬럼을 사후 추가.

실행:
  conda activate test
  python add_triage_tags.py
"""
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "output", "ceria_synthesis_database.xlsx")

METHOD_KEYWORDS = {
    "hydrothermal":    ["hydrothermal"],
    "solvothermal":    ["solvothermal"],
    "precipitation":   ["precipitation", "co-precipitation", "coprecipitation"],
    "sol-gel":         ["sol-gel", "sol gel"],
    "thermal_decomp":  ["thermal decomposition", "thermolysis"],
    "microemulsion":   ["microemulsion", "reverse micelle"],
    "combustion":      ["combustion synthesis", "solution combustion"],
    "polyol":          ["polyol process", "ethylene glycol", "butanediol"],
    "sonochemical":    ["sonochem", "ultrasonic", "ultrasound", "sonication"],
    "microwave":       ["microwave"],
    "spray_pyrolysis": ["spray pyrolysis"],
    "template":        ["template", "hard template", "soft template"],
    "green":           ["green synthesis", "plant extract", "biogenic"],
}

MORPHOLOGY_KEYWORDS = {
    "nanoparticle": ["nanoparticle", "nanocrystal", "quantum dot"],
    "nanorod":      ["nanorod", "nanowire", "nanotube"],
    "nanocube":     ["nanocube", "cube", "cubic"],
    "nanosphere":   ["nanosphere", "spherical"],
    "nanoflower":   ["nanoflower", "hierarchical", "flower-like"],
    "octahedra":    ["octahedr", "polyhedr"],
    "porous":       ["porous", "mesoporous", "hollow"],
    "nanosheet":    ["nanosheet", "nanoplate", "2d"],
}


def tag_keywords(text: str, keyword_map: dict) -> str:
    low = (text or "").lower()
    matched = [label for label, variants in keyword_map.items()
               if any(v in low for v in variants)]
    return "|".join(matched)


def main():
    print(f"읽는 중: {EXCEL_PATH}")
    df = pd.read_excel(EXCEL_PATH)
    print(f"  총 {len(df)}편 로드됨")
    print(f"  기존 컬럼: {list(df.columns)}")

    haystack = (
        df.get("title", pd.Series([""] * len(df))).fillna("") + " " +
        df.get("abstract", pd.Series([""] * len(df))).fillna("")
    )

    # is_oa: open_access_url이 있으면 True로 근사
    if "is_oa" not in df.columns:
        url_col = df.get("open_access_url", pd.Series([""] * len(df))).fillna("")
        df["is_oa"] = url_col.str.strip() != ""
        print(f"  is_oa 추가: True={df['is_oa'].sum()}편")
    else:
        print("  is_oa 이미 존재 — 건너뜀")

    if "tagged_methods" not in df.columns:
        df["tagged_methods"] = haystack.apply(
            lambda t: tag_keywords(t, METHOD_KEYWORDS)
        )
        tagged_count = (df["tagged_methods"] != "").sum()
        print(f"  tagged_methods 추가: 태그 있음 {tagged_count}편")
    else:
        print("  tagged_methods 이미 존재 — 건너뜀")

    if "tagged_morphologies" not in df.columns:
        df["tagged_morphologies"] = haystack.apply(
            lambda t: tag_keywords(t, MORPHOLOGY_KEYWORDS)
        )
        tagged_count = (df["tagged_morphologies"] != "").sum()
        print(f"  tagged_morphologies 추가: 태그 있음 {tagged_count}편")
    else:
        print("  tagged_morphologies 이미 존재 — 건너뜀")

    # 기존 시트 보존 (합성조건 시트만 교체)
    xl_existing = pd.ExcelFile(EXCEL_PATH)
    other_sheets = {s: xl_existing.parse(s)
                    for s in xl_existing.sheet_names
                    if s not in ("합성조건", "Sheet1")}
    xl_existing.close()

    _tmp_path = EXCEL_PATH + "_tmp.xlsx"
    with pd.ExcelWriter(_tmp_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="합성조건", index=False)
        for sname, sdf in other_sheets.items():
            sdf.to_excel(writer, sheet_name=sname, index=False)
    os.replace(_tmp_path, EXCEL_PATH)
    print(f"\n저장 완료: {EXCEL_PATH}")

    print("\n[태그 분포 — tagged_methods]")
    all_methods = "|".join(df["tagged_methods"].fillna("")).split("|")
    from collections import Counter
    for tag, cnt in Counter(t for t in all_methods if t).most_common():
        print(f"  {tag}: {cnt}편")

    print("\n[태그 분포 — tagged_morphologies]")
    all_morph = "|".join(df["tagged_morphologies"].fillna("")).split("|")
    for tag, cnt in Counter(t for t in all_morph if t).most_common():
        print(f"  {tag}: {cnt}편")


if __name__ == "__main__":
    main()
