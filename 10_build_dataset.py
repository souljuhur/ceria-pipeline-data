"""
build_dataset.py — [Stage 2] ML 학습용 데이터셋 내보내기

- 완성도 점수 기준으로 고품질 레코드 필터링 (≥40%)
- JSON Lines 형식 출력 (HuggingFace / LLM 파인튜닝 호환)
- Instruction-Input-Output 형식 학습 데이터 생성
- 통계 요약 출력

출력 파일:
  output/ceria_dataset_full.jsonl     전체 레코드
  output/ceria_dataset_quality.jsonl  완성도 40% 이상 필터링
  output/ceria_dataset_stats.txt      데이터셋 통계

이전 이름: run_cell22.py
"""
import pandas as pd, os, json, re, math

_BASE = r"d:\머신러닝 교육\ceria_pipeline_data"
_PATH = os.path.join(_BASE, "output", "ceria_synthesis_database.xlsx")
_OUT  = os.path.join(_BASE, "output")

df = pd.read_excel(_PATH, sheet_name=0)
total = len(df)
print(f"로드: {total:,}편")

def _v(val):
    """None/NaN → None, 나머지는 원시값 반환"""
    if pd.isna(val) or str(val).strip().lower() in ("", "nan", "none"):
        return None
    try:
        f = float(val)
        if not math.isfinite(f):
            return None
        return int(f) if f == int(f) else round(f, 4)
    except (ValueError, TypeError):
        return str(val).strip()

def _bool(val):
    if pd.isna(val):
        return None
    return bool(val)

# ── 필드 정의 ─────────────────────────────────────────────────────────────────
SYNTH_FIELDS = [
    "synthesis_method", "ce_precursor", "ce_precursor_amount",
    "precursor_concentration", "solvent", "solvent_amount",
    "additive", "additive_amount",
    "mineralizer", "capping_agent", "chelating_agent", "oxidant",
    "synthesis_temperature_c", "synthesis_time_h", "ph_synthesis",
    "atmosphere", "calcination_temperature_c", "calcination_time_h",
    "drying_temperature_c",
    "particle_size_tem_nm", "particle_size_sem_nm",
    "crystallite_size_xrd_nm", "morphology", "crystal_phase",
    "dopant", "dopant_concentration", "dopant_formula",
    "bet_surface_area", "bet_surface_area_m2g",
    "notes",
]

META_FIELDS = [
    "paper_id", "title", "authors", "year", "journal",
    "doi", "citation_count", "source_api",
]

# ── 레코드 변환 ───────────────────────────────────────────────────────────────
def _to_record(row):
    meta  = {f: _v(row.get(f)) for f in META_FIELDS}
    synth = {f: _v(row.get(f)) for f in SYNTH_FIELDS if f in row.index}

    bet_val = synth.get("bet_surface_area_m2g") or synth.get("bet_surface_area")
    synth.pop("bet_surface_area_m2g", None)
    synth.pop("bet_surface_area", None)
    if bet_val is not None:
        synth["bet_surface_area_m2g"] = bet_val

    filled = {k: v for k, v in synth.items() if v is not None}

    parts = []
    if synth.get("synthesis_method"):
        parts.append(f"Synthesis method: {synth['synthesis_method']}")
    if synth.get("ce_precursor"):
        amt = synth.get("ce_precursor_amount", "")
        parts.append(f"Ce precursor: {synth['ce_precursor']}" + (f" ({amt})" if amt else ""))
    if synth.get("solvent"):
        vol = synth.get("solvent_amount", "")
        parts.append(f"Solvent: {synth['solvent']}" + (f" ({vol})" if vol else ""))
    if synth.get("additive"):
        amt = synth.get("additive_amount", "")
        parts.append(f"Additive: {synth['additive']}" + (f" ({amt})" if amt else ""))
    if synth.get("mineralizer"):
        parts.append(f"Mineralizer: {synth['mineralizer']}")
    if synth.get("capping_agent"):
        parts.append(f"Capping agent: {synth['capping_agent']}")
    if synth.get("chelating_agent"):
        parts.append(f"Chelating agent: {synth['chelating_agent']}")
    if synth.get("oxidant"):
        parts.append(f"Oxidant: {synth['oxidant']}")
    if synth.get("synthesis_temperature_c") is not None:
        parts.append(f"Synthesis temperature: {synth['synthesis_temperature_c']} °C")
    if synth.get("synthesis_time_h") is not None:
        parts.append(f"Synthesis time: {synth['synthesis_time_h']} h")
    if synth.get("ph_synthesis") is not None:
        parts.append(f"pH: {synth['ph_synthesis']}")
    if synth.get("calcination_temperature_c") is not None:
        t = synth["calcination_temperature_c"]
        h = synth.get("calcination_time_h", "")
        parts.append(f"Calcination: {t} °C" + (f" for {h} h" if h else ""))
    if synth.get("particle_size_tem_nm") is not None:
        parts.append(f"TEM particle size: {synth['particle_size_tem_nm']} nm")
    if synth.get("crystallite_size_xrd_nm") is not None:
        parts.append(f"XRD crystallite size: {synth['crystallite_size_xrd_nm']} nm")
    if synth.get("morphology"):
        parts.append(f"Morphology: {synth['morphology']}")
    if synth.get("crystal_phase"):
        parts.append(f"Crystal phase: {synth['crystal_phase']}")
    if synth.get("dopant"):
        dc = synth.get("dopant_concentration", "")
        df_ = synth.get("dopant_formula", "")
        parts.append(f"Dopant: {synth['dopant']}"
                     + (f" ({dc})" if dc else "")
                     + (f", formula: {df_}" if df_ else ""))
    if synth.get("bet_surface_area_m2g") is not None:
        parts.append(f"BET surface area: {synth['bet_surface_area_m2g']} m²/g")
    if synth.get("notes"):
        parts.append(f"Notes: {synth['notes']}")

    synthesis_summary = "; ".join(parts) if parts else None

    return {
        "id":               str(meta.get("paper_id", "")),
        "title":            meta.get("title"),
        "year":             meta.get("year"),
        "journal":          meta.get("journal"),
        "doi":              meta.get("doi"),
        "citation_count":   meta.get("citation_count"),
        "source":           meta.get("source_api"),
        "synthesis_conditions": filled,
        "synthesis_summary":    synthesis_summary,
        "completeness_score":   _v(row.get("completeness_score")),
        "is_synthesis_paper":   _bool(row.get("is_synthesis_paper")),
        "data_quality_flags":   _v(row.get("data_quality_flags")) or None,
        "instruction": (
            "Extract the key synthesis conditions for the CeO2 nanoparticles "
            f"described in this paper: \"{meta.get('title', '')}\""
        ),
        "output": synthesis_summary,
    }

# ── 전체 레코드 생성 및 저장 ──────────────────────────────────────────────────
records = [_to_record(row) for _, row in df.iterrows()]

_full_path = os.path.join(_OUT, "ceria_dataset_full.jsonl")
with open(_full_path, "w", encoding="utf-8") as f:
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"\n전체 데이터셋: {len(records):,}편 → {_full_path}")

# ── 품질 필터링 ───────────────────────────────────────────────────────────────
quality_records = [
    r for r in records
    if (r.get("completeness_score") or 0) >= 40
    and r.get("synthesis_summary")
    and r.get("is_synthesis_paper") is not False
]
_qual_path = os.path.join(_OUT, "ceria_dataset_quality.jsonl")
with open(_qual_path, "w", encoding="utf-8") as f:
    for rec in quality_records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"고품질 데이터셋: {len(quality_records):,}편 (완성도≥40%) → {_qual_path}")

# ── 통계 요약 ─────────────────────────────────────────────────────────────────
stats_lines = []
stats_lines.append("=== CeO2 Synthesis Dataset Statistics ===\n")
stats_lines.append(f"Total papers:          {total:,}")
stats_lines.append(f"Quality filtered (≥40%): {len(quality_records):,}")

if "completeness_score" not in df.columns:
    df["completeness_score"] = 0.0
q_df = df[df["completeness_score"].fillna(0) >= 40]

if "synthesis_method" in q_df.columns:
    stats_lines.append("\n--- Synthesis Method Distribution (quality set) ---")
    vc = q_df["synthesis_method"].dropna().value_counts()
    for m, c in vc.items():
        stats_lines.append(f"  {m:<30} {c:>5,}  ({c/len(q_df)*100:.1f}%)")

if "morphology" in q_df.columns:
    stats_lines.append("\n--- Morphology Distribution ---")
    vc = q_df["morphology"].dropna().value_counts()
    for m, c in vc.head(10).items():
        stats_lines.append(f"  {m:<25} {c:>5,}")

for col, label in [
    ("particle_size_tem_nm",   "TEM size (nm)"),
    ("crystallite_size_xrd_nm","XRD size (nm)"),
    ("synthesis_temperature_c","Synthesis Temp (°C)"),
    ("calcination_temperature_c","Calcination Temp (°C)"),
    ("bet_surface_area_m2g",   "BET (m²/g)"),
    ("bet_surface_area",       "BET legacy (m²/g)"),
    ("ph_synthesis",           "pH"),
]:
    if col in q_df.columns:
        s = pd.to_numeric(q_df[col], errors="coerce").dropna()
        if len(s):
            stats_lines.append(
                f"\n{label}: n={len(s)}, "
                f"mean={s.mean():.1f}, median={s.median():.1f}, "
                f"min={s.min():.1f}, max={s.max():.1f}"
            )

if "dopant" in q_df.columns:
    stats_lines.append("\n--- Top Dopants ---")
    vc = q_df["dopant"].dropna().value_counts()
    for d, c in vc.head(10).items():
        stats_lines.append(f"  {d:<10} {c:>5,}")

if "year" in q_df.columns:
    stats_lines.append("\n--- Year Distribution ---")
    vc = q_df["year"].dropna().astype(int).value_counts().sort_index()
    for yr, c in vc.items():
        bar = "█" * min(c // 5, 40)
        stats_lines.append(f"  {yr}  {bar} {c}")

_stats_path = os.path.join(_OUT, "ceria_dataset_stats.txt")
with open(_stats_path, "w", encoding="utf-8") as f:
    f.write("\n".join(stats_lines))

print(f"통계 파일:        {_stats_path}")
print()
for line in stats_lines[:30]:
    print(line)
