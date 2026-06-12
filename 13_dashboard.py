"""
CeO2 파이프라인 대시보드 (개선판)

CMD:
  streamlit run dashboard.py
"""
import os, json, glob
from datetime import datetime
from collections import Counter

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="CeO2 파이프라인",
    page_icon="⚗️",
    layout="wide",
)

BASE_DIR      = r"d:\머신러닝 교육\ceria_pipeline_data"
OUTPUT_DIR    = os.path.join(BASE_DIR, "output")
PDF_DIR       = os.path.join(BASE_DIR, "pdf")
TEXT_DIR      = os.path.join(BASE_DIR, "text")
XLSX_PATH     = os.path.join(OUTPUT_DIR, "ceria_synthesis_database.xlsx")
FULL_JSONL    = os.path.join(OUTPUT_DIR, "ceria_dataset_full.jsonl")
SAMPLES_JSONL = os.path.join(OUTPUT_DIR, "ceria_samples.jsonl")
SAMPLE_CACHE  = os.path.join(OUTPUT_DIR, "sample_extraction_cache.json")
MODEL_DIR     = os.path.join(OUTPUT_DIR, "model")
MERGED_CSV    = os.path.join(OUTPUT_DIR, "ceria_samples_merged.csv")
DISPLAY_XLSX  = os.path.join(OUTPUT_DIR, "ceria_synthesis_database_display.xlsx")
NOA_CACHE     = os.path.join(OUTPUT_DIR, "noa_download_cache.json")
WEEKLY_STATE  = os.path.join(OUTPUT_DIR, "weekly_state.json")

# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚗️ CeO₂ 파이프라인")
    st.divider()
    page = st.radio(
        "페이지 선택",
        ["📊 개요", "🔍 DB 탐색", "🧪 샘플 결과", "📈 ML 결과", "🔬 탐색 분석", "⚙️ 운영 현황"],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("🔄 새로고침", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    # 서식 Excel 다운로드 버튼
    if os.path.exists(DISPLAY_XLSX):
        with open(DISPLAY_XLSX, "rb") as _f:
            st.download_button(
                "📥 서식 Excel 다운로드",
                _f.read(),
                file_name="ceria_synthesis_database_display.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
    # 파일 수정 시각 표시
    def _mtime(path):
        try:
            return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%m-%d %H:%M")
        except Exception:
            return "—"

    st.caption(
        f"DB: {_mtime(XLSX_PATH)}  |  "
        f"샘플: {_mtime(MERGED_CSV)}  |  "
        f"페이지: {datetime.now().strftime('%H:%M:%S')}"
    )

# ── 데이터 로더 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_excel() -> pd.DataFrame:
    if not os.path.exists(XLSX_PATH):
        return pd.DataFrame()
    return pd.read_excel(XLSX_PATH, sheet_name=0)

def _load_xlsx_safe(path) -> pd.DataFrame:
    """'doi' 컬럼 위치를 자동 감지하여 읽기 (요약 행 유무 무관)."""
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=15)
    for idx, row in raw.iterrows():
        if any(str(v).strip().lower() == "doi" for v in row):
            return pd.read_excel(path, sheet_name=0, header=idx)
    return pd.read_excel(path, sheet_name=0)

@st.cache_data(ttl=300)
def load_col_counts() -> pd.DataFrame:
    """열별 데이터 보유 수 계산"""
    if not os.path.exists(XLSX_PATH):
        return pd.DataFrame()
    df = _load_xlsx_safe(XLSX_PATH)
    total = max(len(df), 1)
    counts = df.notna().sum().reset_index()
    counts.columns = ["컬럼명", "보유 수"]
    counts["전체 대비(%)"] = (counts["보유 수"] / total * 100).round(1)
    counts["미보유 수"] = total - counts["보유 수"]
    return counts.sort_values("보유 수", ascending=False).reset_index(drop=True)

@st.cache_data(ttl=60)
def load_noa_status() -> dict:
    """PMC/Sci-Hub 다운로드 캐시 현황"""
    if not os.path.exists(NOA_CACHE):
        return {}
    try:
        with open(NOA_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

@st.cache_data(ttl=60)
def load_weekly_state() -> dict:
    """주간 자동화 실행 이력"""
    if not os.path.exists(WEEKLY_STATE):
        return {}
    try:
        with open(WEEKLY_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

@st.cache_data(ttl=300)
def load_full_jsonl() -> list:
    if not os.path.exists(FULL_JSONL):
        return []
    rows = []
    with open(FULL_JSONL, encoding="utf-8") as f:
        for line in f:
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

@st.cache_data(ttl=300)
def load_samples() -> list:
    if not os.path.exists(SAMPLES_JSONL):
        return []
    rows = []
    with open(SAMPLES_JSONL, encoding="utf-8") as f:
        for line in f:
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

@st.cache_data(ttl=300)
def sample_progress() -> tuple:
    if not os.path.exists(SAMPLE_CACHE):
        return 0, 0
    with open(SAMPLE_CACHE, encoding="utf-8") as f:
        c = json.load(f)
    return len(c.get("done_dois", [])), c.get("total_samples", 0)

def _file_count(directory, ext):
    return len(glob.glob(os.path.join(directory, f"*.{ext}")))

_MORPH_NORM = {
    "spherical": "sphere", "spheres": "sphere", "nanoparticle": "sphere",
    "nanoparticles": "sphere", "nanosphere": "sphere", "quasi-spherical": "sphere",
    "nanorods": "rod", "nanorod": "rod", "rod-like": "rod", "rod-shaped": "rod",
    "nanowires": "wire", "nanowire": "wire", "wire-like": "wire",
    "nanocube": "cube", "nanocubes": "cube", "cubic": "cube",
    "nanoflower": "flower", "nanoflowers": "flower", "flower-like": "flower",
    "nanoplate": "plate", "nanoplates": "plate", "plate-like": "plate", "platelet": "plate",
    "octahedral": "octahedron",
    "hollow sphere": "hollow", "hollow nanoparticle": "hollow",
    "mesoporous": "porous", "nanoporous": "porous",
}
_MORPH_KW = {
    "rod":        ["nanorod", "nano-rod", "rod-shaped", "rod-like", "nanorods"],
    "wire":       ["nanowire", "nano-wire", "wire-like"],
    "cube":       ["nanocube", "cube-shaped"],
    "flower":     ["nanoflower", "flower-like"],
    "plate":      ["nanoplate", "plate-like", "platelet"],
    "octahedron": ["octahedral", "octahedron"],
    "hollow":     ["hollow sphere", "core-shell"],
    "porous":     ["mesoporous", "nanoporous"],
    "sphere":     ["nanosphere", "spherical"],
}

def _norm_morph(val: str, context: str = "") -> str:
    """형태 값 정규화: MORPH_NORM 직접 매핑 → 'other'면 context 키워드로 재분류"""
    if not val:
        return val
    v = val.strip().lower()
    if v in _MORPH_NORM:
        return _MORPH_NORM[v]
    if v == "other" and context:
        ctx = context.lower()
        for morph, kws in _MORPH_KW.items():
            if any(kw in ctx for kw in kws):
                return morph
    return val

def _parse_tags(series: pd.Series) -> Counter:
    counter = Counter()
    for val in series.dropna():
        for tag in str(val).split("|"):
            tag = tag.strip()
            if tag:
                counter[tag] += 1
    return counter

# ══════════════════════════════════════════════════════════════════════════════
# 📊 개요 페이지
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 개요":
    st.title("📊 개요")

    # ── 파이프라인 진행 현황 ───────────────────────────────────────────────
    _s_pdf   = _file_count(PDF_DIR, "pdf") > 0
    _s_gpt   = os.path.exists(SAMPLES_JSONL)
    _s_merge = os.path.exists(MERGED_CSV)
    _s_norm  = False
    if os.path.exists(XLSX_PATH):
        try:
            _xh = pd.read_excel(XLSX_PATH, nrows=1)
            _s_norm = "anion_type" in _xh.columns or "solvent_type" in _xh.columns
        except Exception:
            pass
    _s_excel  = os.path.exists(DISPLAY_XLSX)
    _mdl_ok   = os.path.exists(MODEL_DIR)
    _s_ml     = bool(glob.glob(os.path.join(MODEL_DIR, "*.pkl"))) if _mdl_ok else False
    _s_design = bool(glob.glob(os.path.join(MODEL_DIR, "targeted_design_*nm.csv"))) if _mdl_ok else False
    _pipeline_stages = [
        (_s_pdf,    "PDF 수집",   f"{_file_count(PDF_DIR,'pdf'):,}편"),
        (_s_gpt,    "GPT 추출",   "ceria_samples.jsonl"),
        (_s_merge,  "병합·보완",  "merged.csv"),
        (_s_norm,   "정규화",     "anion/solvent_type"),
        (_s_excel,  "서식 Excel", "_display.xlsx"),
        (_s_ml,     "ML 학습",    f"{len(glob.glob(os.path.join(MODEL_DIR,'*.pkl'))) if _mdl_ok else 0}개 모델"),
        (_s_design, "목표 설계",  "targeted_design*.csv"),
    ]
    _n_done = sum(1 for s, *_ in _pipeline_stages if s)
    st.subheader("파이프라인 진행 현황")
    st.progress(_n_done / len(_pipeline_stages), text=f"{_n_done} / {len(_pipeline_stages)} 단계 완료")
    _pcols = st.columns(7)
    for (ok, label, detail), col in zip(_pipeline_stages, _pcols):
        with col:
            st.markdown(f"{'✅' if ok else '⏳'} **{label}**")
            st.caption(detail)
    st.divider()

    df    = load_excel()
    rows  = load_full_jsonl()
    pdfs  = _file_count(PDF_DIR, "pdf")
    texts = _file_count(TEXT_DIR, "txt")
    done_p, total_s = sample_progress()

    total   = len(df)
    scores  = [r.get("completeness_score") or 0 for r in rows]
    quality = sum(1 for s in scores if s >= 40)

    # ── 상단 메트릭 ────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("전체 논문",      f"{total:,}편")
    c2.metric("PDF 확보",       f"{pdfs:,}편",
              f"{pdfs/total*100:.1f}%" if total else "")
    c3.metric("전문 텍스트",    f"{texts:,}편",
              f"{texts/total*100:.1f}%" if total else "")
    c4.metric("완성도 ≥40%",   f"{quality:,}편",
              f"{quality/len(scores)*100:.1f}%" if scores else "")
    c5.metric("샘플 추출 완료", f"{done_p:,}편",
              f"{done_p/texts*100:.1f}%" if texts else "")
    c6.metric("추출된 샘플",    f"{total_s:,}개")

    st.divider()

    # ── 완성도 분포 + is_oa ────────────────────────────────────────────────
    left, right = st.columns(2)

    with left:
        st.subheader("완성도 점수 분포")
        if scores:
            buckets = list(range(0, 101, 10))
            labels, counts = [], []
            for lo, hi in zip(buckets[:-1], buckets[1:]):
                labels.append(f"{lo}–{hi}%")
                counts.append(sum(1 for s in scores if lo <= s < hi))
            fig = go.Figure(go.Bar(
                x=labels, y=counts,
                text=counts, textposition="outside",
                marker_color="#4C9BE8",
            ))
            fig.update_layout(margin=dict(t=30,b=10,l=0,r=0), height=300,
                              xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, width="stretch")
            st.caption(f"전체 {len(scores):,}편 | 중앙값 {sorted(scores)[len(scores)//2]:.1f}%")
        else:
            st.info("ceria_dataset_full.jsonl 없음 — build_dataset.py 실행 후 표시")

    with right:
        st.subheader("OA 여부 (is_oa)")
        if not df.empty and "is_oa" in df.columns:
            try:
                import altair as alt
                _altair_ok = True
            except ImportError:
                _altair_ok = False

            oa_counts = df["is_oa"].value_counts()
            oa_n   = int(oa_counts.get(True, 0))
            noa_n  = int(oa_counts.get(False, 0))

            if _altair_ok:
                oa_df  = pd.DataFrame({
                    "구분":   ["OA (전문)", "비-OA (초록만)"],
                    "논문 수": [oa_n, noa_n],
                })
                chart = (
                    alt.Chart(oa_df)
                    .mark_arc(innerRadius=60, outerRadius=110)
                    .encode(
                        theta=alt.Theta("논문 수:Q"),
                        color=alt.Color(
                            "구분:N",
                            scale=alt.Scale(
                                domain=["OA (전문)", "비-OA (초록만)"],
                                range=["#54C89B", "#4C9BE8"],
                            ),
                            legend=alt.Legend(orient="bottom"),
                        ),
                        tooltip=["구분", "논문 수"],
                    )
                    .properties(height=320, padding={"top": 30, "bottom": 10})
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                fig = go.Figure(go.Bar(
                    x=["OA (전문)", "비-OA (초록만)"],
                    y=[oa_n, noa_n],
                    text=[oa_n, noa_n], textposition="outside",
                    marker_color=["#54C89B", "#4C9BE8"],
                ))
                fig.update_layout(margin=dict(t=30,b=10,l=0,r=0), height=300,
                                  xaxis_title="", yaxis_title="")
                st.plotly_chart(fig, width="stretch")
            st.caption(f"OA {oa_n:,}편 ({oa_n/total*100:.1f}%)  |  비-OA {noa_n:,}편 ({noa_n/total*100:.1f}%)")
        else:
            st.info("is_oa 컬럼 없음 — add_triage_tags.py 실행 후 표시")

    st.divider()

    # ── 연도별 논문 수 (전체 / CMP) ───────────────────────────────────────
    st.subheader("연도별 출판 논문 수")
    if not df.empty and "year" in df.columns:
        _CMP_KEYWORDS = [
            # 직접 표현
            "cmp",
            "chemical mechanical polishing",
            "chemical mechanical planarization",
            # slurry / 연마재
            "polishing slurry", "abrasive slurry",
            "ceria slurry", "cerium oxide slurry",
            "polishing agent", "polishing pad",
            "abrasive particle", "abrasive material",
            # 공정 용어
            "planarization",
            "wafer polishing", "semiconductor polishing",
            "material removal rate", "mrr",
            "surface planarization",
            # polishing 복합어 (단독은 false positive 다수)
            "polishing performance", "polishing efficiency",
            "polishing rate", "polishing process",
            "for polishing", "as polishing",
            "high-polishing", "optical polishing",
        ]
        # title + abstract + notes 를 모두 탐색
        haystack_cmp = (
            df.get("title",    pd.Series([""] * len(df))).fillna("") + " " +
            df.get("abstract", pd.Series([""] * len(df))).fillna("") + " " +
            df.get("notes",    pd.Series([""] * len(df))).fillna("")
        ).str.lower()
        cmp_mask = haystack_cmp.apply(
            lambda t: any(kw in t for kw in _CMP_KEYWORDS)
        )

        year_all = (
            df["year"].dropna().astype(int)
            .value_counts().sort_index()
        )
        _all_years = list(range(int(year_all.index.min()), int(year_all.index.max()) + 1))
        year_all = year_all.reindex(_all_years, fill_value=0)

        year_cmp = (
            df.loc[cmp_mask, "year"].dropna().astype(int)
            .value_counts().sort_index()
        )
        if not year_cmp.empty:
            _cmp_years = list(range(int(year_cmp.index.min()), int(year_cmp.index.max()) + 1))
            year_cmp = year_cmp.reindex(_cmp_years, fill_value=0)

        col_all, col_cmp = st.columns(2)

        with col_all:
            st.markdown("**전체 논문**")
            fig_y = go.Figure(go.Bar(
                x=year_all.index.tolist(), y=year_all.values.tolist(),
                text=year_all.values.tolist(), textposition="outside",
                marker_color="#4C9BE8",
            ))
            _years_all = year_all.index.tolist()
            fig_y.update_layout(
                margin=dict(t=30, b=60, l=0, r=0), height=320,
                xaxis=dict(
                    tickmode="array",
                    tickvals=_years_all,
                    ticktext=[str(y) for y in _years_all],
                    tickangle=-60,
                    title="",
                ),
                yaxis_title="",
            )
            st.plotly_chart(fig_y, width="stretch")
            peak = int(year_all.idxmax())
            st.caption(
                f"{int(year_all.index.min())}–{int(year_all.index.max())}년 | "
                f"피크: {peak}년 ({year_all.max():,}편) | 총 {year_all.sum():,}편"
            )

        with col_cmp:
            st.markdown("**CMP 관련 논문**")
            if year_cmp.empty:
                st.info("CMP 관련 논문 없음")
            else:
                fig_c = go.Figure(go.Bar(
                    x=year_cmp.index.tolist(), y=year_cmp.values.tolist(),
                    text=year_cmp.values.tolist(), textposition="outside",
                    marker_color="#E87C4C",
                ))
                _years_cmp = year_cmp.index.tolist()
                fig_c.update_layout(
                    margin=dict(t=30, b=60, l=0, r=0), height=320,
                    xaxis=dict(
                        tickmode="array",
                        tickvals=_years_cmp,
                        ticktext=[str(y) for y in _years_cmp],
                        tickangle=-60,
                        title="",
                    ),
                    yaxis_title="",
                )
                st.plotly_chart(fig_c, width="stretch")
                peak_c = int(year_cmp.idxmax())
                st.caption(
                    f"{int(year_cmp.index.min())}–{int(year_cmp.index.max())}년 | "
                    f"피크: {peak_c}년 ({year_cmp.max():,}편) | 총 {year_cmp.sum():,}편"
                )
    else:
        st.info("year 컬럼 없음")

    st.divider()

    # ── triage 태그 분포 ───────────────────────────────────────────────────
    t1, t2 = st.columns(2)

    with t1:
        st.subheader("합성방법 태그 분포")
        if not df.empty and "tagged_methods" in df.columns:
            cnt = _parse_tags(df["tagged_methods"])
            if cnt:
                tag_df = pd.DataFrame(
                    {"tag": list(cnt.keys()), "논문 수": list(cnt.values())}
                ).sort_values("논문 수", ascending=False)
                fig_m = go.Figure(go.Bar(
                    x=tag_df["tag"], y=tag_df["논문 수"],
                    text=tag_df["논문 수"], textposition="outside",
                    marker_color="#E87C4C"
                ))
                fig_m.update_layout(
                    margin=dict(t=30, b=10, l=0, r=0),
                    yaxis=dict(title=""),
                    xaxis=dict(title=""),
                    height=320,
                )
                st.plotly_chart(fig_m, width="stretch")
                st.caption(f"태그 있는 논문: {(df['tagged_methods'].fillna('') != '').sum():,}편")
            else:
                st.info("태그 데이터 없음")
        else:
            st.info("tagged_methods 컬럼 없음 — add_triage_tags.py 실행 후 표시")

    with t2:
        st.subheader("형상 태그 분포")
        if not df.empty and "tagged_morphologies" in df.columns:
            cnt = _parse_tags(df["tagged_morphologies"])
            if cnt:
                tag_df = pd.DataFrame(
                    {"tag": list(cnt.keys()), "논문 수": list(cnt.values())}
                ).sort_values("논문 수", ascending=False)
                fig_mo = go.Figure(go.Bar(
                    x=tag_df["tag"], y=tag_df["논문 수"],
                    text=tag_df["논문 수"], textposition="outside",
                    marker_color="#A04CE8"
                ))
                fig_mo.update_layout(
                    margin=dict(t=30, b=10, l=0, r=0),
                    yaxis=dict(title=""),
                    xaxis=dict(title=""),
                    height=320,
                )
                st.plotly_chart(fig_mo, width="stretch")
                st.caption(f"태그 있는 논문: {(df['tagged_morphologies'].fillna('') != '').sum():,}편")
            else:
                st.info("태그 데이터 없음")
        else:
            st.info("tagged_morphologies 컬럼 없음 — add_triage_tags.py 실행 후 표시")

    st.divider()

    # ── 필드 채움률 (3개 그룹) ──────────────────────────────────────────
    st.subheader("필드별 채움률 (%)")
    if rows:
        counter, total_r = Counter(), len(rows)
        for r in rows:
            for k, v in (r.get("synthesis_conditions") or {}).items():
                if v is not None:
                    counter[k] += 1
        fills = {k: v / total_r * 100 for k, v in counter.items()}

        GROUPS = {
            "🧪 실험공정": [
                "synthesis_method", "synthesis_temperature_c", "synthesis_time_h",
                "ph_synthesis", "atmosphere", "calcination_temperature_c",
                "calcination_time_h", "drying_temperature_c",
                "ce_concentration_M", "mineralizer_concentration_M", "synthesis_volume_mL",
            ],
            "⚗️ 케미컬": [
                "ce_precursor", "anion_type", "solvent", "solvent_type",
                "mineralizer", "capping_agent", "chelating_agent",
                "oxidant", "dopant", "additive",
            ],
            "📏 실험결과": [
                "particle_size_primary_nm", "particle_size_tem_nm", "particle_size_sem_nm",
                "crystallite_size_xrd_nm", "bet_surface_area_m2g",
                "morphology", "crystal_phase", "dopant_concentration",
            ],
        }
        COLORS = {
            "🧪 실험공정": "#4C8BF5",
            "⚗️ 케미컬":   "#F0A500",
            "📏 실험결과": "#34A853",
        }

        cols = st.columns(3)
        for col, (group_name, fields) in zip(cols, GROUPS.items()):
            group_df = pd.DataFrame(
                [(f, fills.get(f, 0.0)) for f in fields],
                columns=["필드", "채움률(%)"]
            ).sort_values("채움률(%)", ascending=True)

            with col:
                st.markdown(f"**{group_name}**")
                fig_g = go.Figure(go.Bar(
                    x=group_df["채움률(%)"].tolist(),
                    y=group_df["필드"].tolist(),
                    orientation="h",
                    text=[f"{v:.1f}%" for v in group_df["채움률(%)"]],
                    textposition="outside",
                    marker_color=COLORS[group_name],
                    cliponaxis=False,
                ))
                fig_g.update_layout(
                    margin=dict(t=10, b=10, l=10, r=55),
                    height=max(220, len(group_df) * 34),
                    xaxis=dict(range=[0, 120], showticklabels=False),
                    yaxis_title="",
                    showlegend=False,
                )
                st.plotly_chart(fig_g, use_container_width=True)
    else:
        st.info("데이터 없음")

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 DB 탐색 페이지
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 DB 탐색":
    st.title("🔍 DB 탐색")

    df = load_excel()
    if df.empty:
        st.error("ceria_synthesis_database.xlsx 파일을 찾을 수 없습니다.")
        st.stop()

    # ── 사이드바 필터 ──────────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("필터")

        # 텍스트 검색
        search = st.text_input("제목 / DOI 검색", placeholder="예: hydrothermal, 10.1016/...")

        # 연도 범위
        if "year" in df.columns:
            years = df["year"].dropna().astype(int)
            y_min, y_max = int(years.min()), int(years.max())
            year_range = st.slider("출판 연도", y_min, y_max, (y_min, y_max))
        else:
            year_range = None

        # 합성방법
        method_filter = []
        method_col = next((c for c in df.columns if "method" in c.lower() or "합성방법" in c), None)
        if method_col:
            methods = sorted(df[method_col].dropna().unique().tolist())
            method_filter = st.multiselect("합성방법", methods)

        # is_oa
        oa_filter = "전체"
        if "is_oa" in df.columns:
            oa_filter = st.radio("OA 여부", ["전체", "OA만", "비-OA만"])

        # 완성도 점수
        score_col = next((c for c in df.columns if "completeness" in c.lower() or "완성도" in c.lower()), None)
        score_min = 0
        if score_col:
            score_min = st.slider("완성도 점수 최소 (%)", 0, 100, 0)

    # ── 필터 적용 ──────────────────────────────────────────────────────────
    filtered = df.copy()

    if search:
        mask = pd.Series([False] * len(filtered), index=filtered.index)
        for col in ["title", "doi", "제목"]:
            if col in filtered.columns:
                mask |= filtered[col].fillna("").str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    if year_range and "year" in filtered.columns:
        filtered = filtered[
            filtered["year"].between(year_range[0], year_range[1], inclusive="both")
        ]

    if method_filter and method_col:
        filtered = filtered[filtered[method_col].isin(method_filter)]

    if oa_filter != "전체" and "is_oa" in filtered.columns:
        filtered = filtered[filtered["is_oa"] == (oa_filter == "OA만")]

    if score_min > 0 and score_col:
        filtered = filtered[filtered[score_col].fillna(0) >= score_min]

    # ── 결과 표시 ──────────────────────────────────────────────────────────
    st.caption(f"검색 결과: **{len(filtered):,}편** / 전체 {len(df):,}편")

    # 표시할 컬럼 선택
    priority_cols = ["title", "제목", "year", "doi", "journal", "저널",
                     method_col, score_col, "is_oa",
                     "tagged_methods", "tagged_morphologies",
                     "citation_count", "인용수"]
    show_cols = [c for c in priority_cols if c and c in filtered.columns]
    # 위에서 선택 안 된 컬럼도 뒤에 추가 (중복 제거)
    remaining = [c for c in filtered.columns if c not in show_cols]
    show_cols = show_cols + remaining

    st.dataframe(
        filtered[show_cols].reset_index(drop=True),
        width="stretch",
        height=600,
    )

# ══════════════════════════════════════════════════════════════════════════════
# 🧪 샘플 결과 페이지
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🧪 샘플 결과":
    st.title("🧪 샘플 결과")

    texts   = _file_count(TEXT_DIR, "txt")
    done_p, total_s = sample_progress()
    samples = load_samples()

    # ── 진행률 ────────────────────────────────────────────────────────────
    st.subheader("샘플 추출 진행률")
    if texts > 0:
        progress = done_p / texts
        st.progress(progress, text=f"{done_p:,} / {texts:,}편 완료 ({progress*100:.1f}%)")
    c1, c2, c3 = st.columns(3)
    c1.metric("전문 보유 논문", f"{texts:,}편")
    c2.metric("추출 완료",      f"{done_p:,}편")
    c3.metric("추출된 샘플 수", f"{total_s:,}개")

    if done_p == 0:
        st.info("아직 샘플 추출이 실행되지 않았습니다.\n\n```\npython 2_extract.py\n```")
        st.stop()

    st.divider()

    # ── 합성방법 분포 ──────────────────────────────────────────────────────
    st.subheader("합성방법 분포 (샘플 기준)")
    method_cnt = Counter()
    for s in samples:
        m = (s.get("synthesis_conditions") or {}).get("synthesis_method")
        if m:
            method_cnt[m] += 1

    if method_cnt:
        top = dict(method_cnt.most_common(15))
        fig_m2 = go.Figure(go.Bar(
            x=list(top.keys()), y=list(top.values()),
            text=list(top.values()), textposition="outside",
            marker_color="#54C89B",
        ))
        fig_m2.update_layout(margin=dict(t=30,b=10,l=0,r=0), height=320,
                             xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_m2, width="stretch")

    st.divider()

    # ── 샘플 테이블 ────────────────────────────────────────────────────────
    st.subheader(f"샘플 목록 (전체 {len(samples):,}개)")

    # 사이드바 필터
    with st.sidebar:
        st.subheader("필터")
        method_sel = st.multiselect("합성방법", list(method_cnt.keys()))
        has_tem    = st.checkbox("1차입자크기 있는 것만 (TEM 또는 SEM)")
        has_bet    = st.checkbox("BET 표면적 있는 것만")

    rows = []
    for s in samples:
        sc  = s.get("synthesis_conditions") or {}
        ch  = s.get("characterization") or {}
        m   = sc.get("synthesis_method", "")
        tem = ch.get("particle_size_tem_nm")
        sem = ch.get("particle_size_sem_nm")
        bet = ch.get("bet_surface_area_m2g")
        # 1차 입자: TEM 우선, 없으면 SEM
        primary = tem if tem else sem

        if method_sel and m not in method_sel:
            continue
        if has_tem and not primary:
            continue
        if has_bet and not bet:
            continue

        raw_morph = ch.get("morphology", "") or ""
        context   = s.get("title", "") or s.get("sample_label", "") or ""
        _src = "TEM" if tem else ("SEM" if sem else "")
        # 설명: sample_label 우선, 없으면 합성조건으로 자동 생성
        _label = (s.get("sample_label", "") or "").strip()
        if not _label:
            _parts = [m] if m else []
            _t = sc.get("synthesis_temperature_c", "")
            _ph = sc.get("ph_synthesis", "")
            if _t:
                _parts.append(f"{_t}°C")
            if _ph:
                _parts.append(f"pH {_ph}")
            _label = " · ".join(_parts)
        rows.append({
            "DOI":         s.get("doi", "")[-30:] if s.get("doi") else "",
            "Sample":      s.get("sample_id", ""),
            "설명":        _label[:60],
            "합성법":      m,
            "합성°C":      sc.get("synthesis_temperature_c", "") or "",
            "합성시간(h)": sc.get("synthesis_time_h", "") or "",
            "하소°C":      sc.get("calcination_temperature_c", "") or "",
            "도핑":        sc.get("dopant", ""),
            "1차입자(nm)": primary or "",
            "측정법":      _src,
            "XRD결정자(nm)": ch.get("crystallite_size_xrd_nm", "") or "",
            "BET(m²/g)":   bet or "",
            "형태":        _norm_morph(raw_morph, context),
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", height=600)
        st.caption(f"필터 적용 결과: {len(rows):,}개")
    else:
        st.info("조건에 맞는 샘플이 없습니다.")

# ══════════════════════════════════════════════════════════════════════════════
# 📈 ML 결과 페이지
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 ML 결과":
    st.title("📈 ML 결과")

    _pkl_files = glob.glob(os.path.join(MODEL_DIR, "*.pkl")) if os.path.exists(MODEL_DIR) else []
    _pt_files  = glob.glob(os.path.join(MODEL_DIR, "*.pt"))  if os.path.exists(MODEL_DIR) else []
    all_model_files = sorted(_pkl_files + _pt_files)

    if not all_model_files:
        st.info("ML 모델 결과가 없습니다.")
        st.code("python 12_model.py\npython 12b_lgbm_baseline.py\npython 12c_gpr_model.py",
                language="bash")
        st.stop()

    @st.cache_data(ttl=300)
    def load_coverage():
        def _calc(df, src):
            total = len(df)
            if total == 0:
                return {}
            has_doi = "doi" in df.columns
            def _papers(mask):
                return int(df.loc[mask, "doi"].nunique()) if has_doi else 0
            n_papers = int(df["doi"].nunique()) if has_doi else 0

            tem = pd.to_numeric(df.get("particle_size_tem_nm",    pd.Series(dtype=float)), errors="coerce")
            xrd = pd.to_numeric(df.get("crystallite_size_xrd_nm", pd.Series(dtype=float)), errors="coerce")
            sem = pd.to_numeric(df.get("particle_size_sem_nm",    pd.Series(dtype=float)), errors="coerce")
            primary_col = df.get("particle_size_primary_nm", pd.Series(dtype=float))
            tem_v = tem.where(tem.between(0.3, 500))
            xrd_v = xrd.where(xrd.between(0.3, 200))
            sem_v = sem.where(sem.between(0.3, 500))
            if primary_col.notna().any():
                primary_v = pd.to_numeric(primary_col, errors="coerce").where(
                    pd.to_numeric(primary_col, errors="coerce").between(0.3, 500))
            else:
                primary_v = tem_v.combine_first(sem_v)
            n_comp = int(primary_v.notna().sum())
            return {
                "source":          src,
                "total":           total,
                "n_papers":        n_papers,
                "composite_n":     n_comp,
                "composite_pct":   n_comp / total * 100,
                "composite_papers": _papers(primary_v.notna()),
                "tem_n":           int(tem_v.notna().sum()),
                "tem_pct":         tem_v.notna().sum() / total * 100,
                "tem_papers":      _papers(tem_v.notna()),
                "xrd_n":           int(xrd_v.notna().sum()),
                "xrd_pct":         xrd_v.notna().sum() / total * 100,
                "xrd_papers":      _papers(xrd_v.notna()),
                "sem_n":           int(sem_v.notna().sum()),
                "sem_pct":         sem_v.notna().sum() / total * 100,
                "sem_papers":      _papers(sem_v.notna()),
            }
        if os.path.exists(MERGED_CSV):
            try:
                return _calc(pd.read_csv(MERGED_CSV, low_memory=False), "merged_csv")
            except Exception:
                pass
        if not os.path.exists(XLSX_PATH):
            return {}
        try:
            return _calc(_load_xlsx_safe(XLSX_PATH), "excel")
        except Exception:
            return {}

    cov = load_coverage()

    ml_tabs = st.tabs(["📊 모델 성능", "🔍 피처 중요도", "🎯 역설계 & 목표 설계", "🧬 능동학습"])

    # ── 탭 0: 모델 성능 ───────────────────────────────────────────────────
    with ml_tabs[0]:
        if cov:
            st.subheader("1차 입자크기 커버리지")
            st.caption(
                f"**샘플 기준** (ceria_samples_merged.csv) · "
                f"전체 **{cov['total']:,}샘플** / **{cov['n_papers']:,}논문** | 목표: 80% 이상"
            )
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric(
                "1차입자 커버리지 (TEM+SEM)",
                f"{cov['composite_pct']:.1f}%",
                f"{cov['composite_n']:,}샘플 · {cov['composite_papers']:,}논문",
                delta_color="off",
            )
            cc2.metric(
                "TEM 보유",
                f"{cov['tem_n']:,} 샘플",
                f"{cov['tem_pct']:.1f}% · {cov['tem_papers']:,}논문",
                delta_color="off",
            )
            cc3.metric(
                "SEM 보유",
                f"{cov['sem_n']:,} 샘플",
                f"{cov['sem_pct']:.1f}% · {cov['sem_papers']:,}논문",
                delta_color="off",
            )
            cc4.metric(
                "XRD 결정자 보유",
                f"{cov['xrd_n']:,} 샘플",
                f"{cov['xrd_pct']:.1f}% · {cov['xrd_papers']:,}논문",
                delta_color="off",
            )
            st.divider()

        # ── 현재 모델 성능 비교 ───────────────────────────────────────────────
        st.subheader("현재 모델 성능 비교 (particle_size_primary_nm)")
        _ph_path = os.path.join(BASE_DIR, "output", "model", "performance_history.json")
        _latest_histgbm = _latest_dkl = _latest_cb = {}
        if os.path.exists(_ph_path):
            try:
                with open(_ph_path, "r", encoding="utf-8") as _f:
                    _ph_all = json.load(_f)
                for _e in reversed(_ph_all):
                    if not _latest_histgbm and _e.get("histgbm"):
                        _latest_histgbm = (_e["histgbm"].get("particle_size_primary_nm") or {})
                    if not _latest_dkl and _e.get("dkl_gp"):
                        _latest_dkl = (_e["dkl_gp"].get("particle_size_primary_nm") or {})
                    if not _latest_cb and _e.get("catboost"):
                        _latest_cb = (_e["catboost"].get("particle_size_primary_nm") or {})
            except Exception:
                pass

        _mc1, _mc2, _mc3 = st.columns(3)
        _mc1.metric(
            "HistGBM log-R²",
            f"{_latest_histgbm.get('log_r2', 'N/A'):+.3f}" if _latest_histgbm.get("log_r2") is not None else "N/A",
            f"MAE {_latest_histgbm.get('mae_nm', '?'):.1f} nm  |  n={_latest_histgbm.get('n', '?'):,}" if _latest_histgbm.get("mae_nm") else "",
            delta_color="off",
        )
        _mc2.metric(
            "CatBoost log-R² ★",
            f"{_latest_cb.get('log_r2', 'N/A'):+.3f}" if _latest_cb.get("log_r2") is not None else "N/A",
            f"MAE {_latest_cb.get('mae_nm', '?'):.1f} nm  |  n={_latest_cb.get('n', '?'):,}" if _latest_cb.get("mae_nm") else "",
            delta_color="off",
        )
        _mc3.metric(
            "DKL-GP log-R² (최고)",
            f"{_latest_dkl.get('log_r2', 'N/A'):+.3f}" if _latest_dkl.get("log_r2") is not None else "N/A",
            f"MAE {_latest_dkl.get('mae_nm', '?'):.1f} nm  |  PICP={_latest_dkl.get('picp_90', '?'):.3f}" if _latest_dkl.get("mae_nm") else "",
            delta_color="off",
        )
        st.caption("★ CatBoost = best tabular  |  DKL-GP = best overall (불확실성 정량화 포함)  |  log-R²>0 → mean predictor 초과")
        st.divider()

        st.subheader("학습된 모델 파일")
        model_info = []
        for f in all_model_files:
            name = os.path.basename(f)
            if "lgbm" in name:
                mtype = "LightGBM"
            elif "dkl" in name:
                mtype = "DKL-GP"
            elif "catboost" in name:
                mtype = "CatBoost"
            else:
                mtype = "HistGBM"
            size_kb = os.path.getsize(f) / 1024
            mtime   = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
            model_info.append({
                "파일명": name, "모델 타입": mtype,
                "크기(KB)": f"{size_kb:.1f}", "수정시각": mtime,
            })
        st.dataframe(pd.DataFrame(model_info), width="stretch", hide_index=True)

        # ── 성능 개선 이력 ────────────────────────────────────────────────────
        st.divider()
        st.subheader("📈 세션별 성능 개선 이력")

        _hist_path = os.path.join(BASE_DIR, "output", "model", "performance_history.json")
        _ph = []
        if os.path.exists(_hist_path):
            try:
                with open(_hist_path, "r", encoding="utf-8") as _hf:
                    _ph = json.load(_hf)
            except Exception:
                _ph = []

        if _ph:
            # ── 데이터 정규화 ──
            _rows = []
            for _e in _ph:
                _lbl  = _e.get("session_label", "?")
                _ns   = _e.get("n_samples")
                _cov  = _e.get("coverage_pct")
                _hgbm = (_e.get("histgbm") or {}).get("particle_size_primary_nm") or {}
                _dkl  = (_e.get("dkl_gp") or {}).get("particle_size_primary_nm") or {}
                _cb   = (_e.get("catboost") or {}).get("particle_size_primary_nm") or {}
                _rows.append({
                    "세션": _lbl,
                    "샘플 수": _ns,
                    "커버리지(%)": _cov,
                    "HistGBM log-R²": _hgbm.get("log_r2"),
                    "HistGBM MAE(nm)": _hgbm.get("mae_nm"),
                    "HistGBM RMSE(nm)": _hgbm.get("rmse_nm"),
                    "HistGBM MdAE(nm)": _hgbm.get("mdae_nm"),
                    "DKL-GP log-R²": _dkl.get("log_r2"),
                    "DKL-GP MAE(nm)": _dkl.get("mae_nm"),
                    "CatBoost log-R²": _cb.get("log_r2"),
                    "CatBoost MAE(nm)": _cb.get("mae_nm"),
                    "note": _e.get("note", ""),
                })
            _df_ph = pd.DataFrame(_rows)
            _xs = _df_ph["세션"].tolist()

            _c1, _c2 = st.columns(2)

            with _c1:
                # log-R² 추이
                _fig1 = go.Figure()
                _y_hgbm = _df_ph["HistGBM log-R²"].tolist()
                _y_dkl  = _df_ph["DKL-GP log-R²"].tolist()
                _y_cb   = _df_ph["CatBoost log-R²"].tolist()
                _fig1.add_trace(go.Scatter(
                    x=_xs, y=_y_hgbm, mode="lines+markers", name="HistGBM",
                    line=dict(color="#E87C4C", width=2),
                    marker=dict(size=8),
                    connectgaps=True,
                ))
                _fig1.add_trace(go.Scatter(
                    x=_xs, y=_y_dkl, mode="lines+markers", name="DKL-GP",
                    line=dict(color="#4C9BE8", width=2, dash="dash"),
                    marker=dict(size=8, symbol="diamond"),
                    connectgaps=True,
                ))
                _fig1.add_trace(go.Scatter(
                    x=_xs, y=_y_cb, mode="lines+markers", name="CatBoost",
                    line=dict(color="#44BB44", width=2, dash="dot"),
                    marker=dict(size=8, symbol="square"),
                    connectgaps=True,
                ))
                _fig1.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
                _fig1.update_layout(
                    title="log-R² 추이 (클수록 좋음)", height=300,
                    xaxis_title="세션", yaxis_title="log-R²",
                    legend=dict(orientation="h", y=1.12),
                    margin=dict(t=60, b=40, l=40, r=20),
                )
                st.plotly_chart(_fig1, use_container_width=True)

            with _c2:
                # MAE(nm) 추이
                _fig2 = go.Figure()
                _y_mae_h = _df_ph["HistGBM MAE(nm)"].tolist()
                _y_mae_d = _df_ph["DKL-GP MAE(nm)"].tolist()
                _y_mae_c = _df_ph["CatBoost MAE(nm)"].tolist()
                _fig2.add_trace(go.Scatter(
                    x=_xs, y=_y_mae_h, mode="lines+markers", name="HistGBM MAE",
                    line=dict(color="#E87C4C", width=2),
                    marker=dict(size=8),
                    connectgaps=True,
                ))
                _fig2.add_trace(go.Scatter(
                    x=_xs, y=_y_mae_d, mode="lines+markers", name="DKL-GP MAE",
                    line=dict(color="#4C9BE8", width=2, dash="dash"),
                    marker=dict(size=8, symbol="diamond"),
                    connectgaps=True,
                ))
                _fig2.add_trace(go.Scatter(
                    x=_xs, y=_y_mae_c, mode="lines+markers", name="CatBoost MAE",
                    line=dict(color="#44BB44", width=2, dash="dot"),
                    marker=dict(size=8, symbol="square"),
                    connectgaps=True,
                ))
                _fig2.update_layout(
                    title="nm-MAE 추이 (작을수록 좋음)", height=300,
                    xaxis_title="세션", yaxis_title="MAE (nm)",
                    legend=dict(orientation="h", y=1.12),
                    margin=dict(t=60, b=40, l=40, r=20),
                )
                st.plotly_chart(_fig2, use_container_width=True)

            _c3, _c4 = st.columns(2)

            with _c3:
                # 샘플 수 + 커버리지 이중 축
                _fig3 = go.Figure()
                _fig3.add_trace(go.Bar(
                    x=_xs, y=_df_ph["샘플 수"].tolist(), name="샘플 수",
                    marker_color="#6DBF67", opacity=0.75,
                    yaxis="y",
                ))
                _fig3.add_trace(go.Scatter(
                    x=_xs, y=_df_ph["커버리지(%)"].tolist(), name="커버리지(%)",
                    mode="lines+markers", line=dict(color="#F5A623", width=2),
                    yaxis="y2", connectgaps=True,
                ))
                _fig3.update_layout(
                    title="데이터 성장 (샘플 수 · 커버리지)", height=300,
                    xaxis_title="세션",
                    yaxis=dict(title="샘플 수", side="left"),
                    yaxis2=dict(title="커버리지(%)", side="right", overlaying="y", ticksuffix="%"),
                    legend=dict(orientation="h", y=1.12),
                    margin=dict(t=60, b=40, l=40, r=40),
                )
                st.plotly_chart(_fig3, use_container_width=True)

            with _c4:
                # RMSE / MdAE 비교 (17차 이후부터 데이터 있음)
                _rmse_vals = _df_ph["HistGBM RMSE(nm)"].tolist()
                _mdae_vals = _df_ph["HistGBM MdAE(nm)"].tolist()
                _has_detail = any(v is not None for v in _rmse_vals + _mdae_vals)
                if _has_detail:
                    _fig4 = go.Figure()
                    _fig4.add_trace(go.Scatter(
                        x=_xs, y=_rmse_vals, mode="lines+markers", name="RMSE(nm)",
                        line=dict(color="#B044B0", width=2),
                        marker=dict(size=8), connectgaps=True,
                    ))
                    _fig4.add_trace(go.Scatter(
                        x=_xs, y=_mdae_vals, mode="lines+markers", name="MdAE(nm)",
                        line=dict(color="#44B0B0", width=2, dash="dot"),
                        marker=dict(size=8, symbol="square"), connectgaps=True,
                    ))
                    _fig4.update_layout(
                        title="RMSE vs MdAE (nm, 작을수록 좋음)", height=300,
                        xaxis_title="세션", yaxis_title="nm",
                        legend=dict(orientation="h", y=1.12),
                        margin=dict(t=60, b=40, l=40, r=20),
                    )
                    st.plotly_chart(_fig4, use_container_width=True)
                else:
                    st.info("RMSE/MdAE 이력은 17차 이후 자동 기록됩니다.")

            # 전체 이력 테이블
            with st.expander("📋 전체 이력 테이블"):
                _display_cols = ["세션", "샘플 수", "커버리지(%)",
                                 "HistGBM log-R²", "HistGBM MAE(nm)",
                                 "DKL-GP log-R²", "DKL-GP MAE(nm)",
                                 "CatBoost log-R²", "CatBoost MAE(nm)", "note"]
                _df_show = _df_ph[_display_cols].copy()
                for _col in ["HistGBM log-R²", "DKL-GP log-R²", "CatBoost log-R²"]:
                    _df_show[_col] = _df_show[_col].apply(
                        lambda v: f"{v:+.3f}" if pd.notna(v) else "-"
                    )
                for _col in ["HistGBM MAE(nm)", "DKL-GP MAE(nm)", "CatBoost MAE(nm)"]:
                    _df_show[_col] = _df_show[_col].apply(
                        lambda v: f"{v:.1f}" if pd.notna(v) else "-"
                    )
                st.dataframe(_df_show, hide_index=True, use_container_width=True)
        else:
            st.info("성능 이력 파일이 없습니다. 12_model.py 실행 후 자동 생성됩니다.")

    # ── 탭 1: 피처 중요도 ──────────────────────────────────────────────────
    with ml_tabs[1]:
        def _sort_importance(paths):
            """particle_size_primary_nm 먼저, composite 다음, 나머지 알파벳순."""
            ORDER = ["particle_size_primary_nm", "particle_size_composite",
                     "particle_size_tem_nm", "particle_size_sem_nm",
                     "crystallite_size_xrd_nm", "morphology"]
            def _key(p):
                stem = os.path.basename(p).replace("importance_", "").replace("shap_", "").replace(".png", "")
                return (ORDER.index(stem) if stem in ORDER else len(ORDER), stem)
            return sorted(paths, key=_key)

        importance_pngs    = _sort_importance(glob.glob(os.path.join(MODEL_DIR, "importance_*.png")))
        shap_pngs          = _sort_importance(glob.glob(os.path.join(MODEL_DIR, "shap_*.png")))
        cb_importance_pngs = _sort_importance(glob.glob(os.path.join(MODEL_DIR, "catboost_importance_*.png")))
        cb_shap_pngs       = _sort_importance(glob.glob(os.path.join(MODEL_DIR, "catboost_shap_*.png")))
        dkl_result_pngs    = sorted(glob.glob(os.path.join(MODEL_DIR, "dkl_results_*.png")))

        if not (importance_pngs or shap_pngs or cb_importance_pngs or cb_shap_pngs or dkl_result_pngs):
            st.info("시각화 결과 없음 — 모델 실행 후 생성됩니다.")
        else:
            cols_per_row = 2
            if importance_pngs:
                st.markdown("**HistGBM 피처 중요도**")
                with st.expander("📖 피처 중요도 해석 가이드", expanded=False):
                    st.markdown("""
**Permutation Importance (순열 중요도)** 란?

각 피처를 무작위로 섞었을 때 예측 오차(MAE)가 얼마나 증가하는지 측정합니다.
값이 클수록 해당 피처가 예측에 핵심적임을 의미합니다.

| 피처 | 의미 | 중요도(참고) |
|------|------|------|
| synthesis_method | 합성법 (sol-gel, hydrothermal 등) | 21.6% |
| solvent | 사용 용매 종류 | 11.9% |
| ce_precursor | 세리아 전구체 종류 | 10.8% |
| capping_agent | 캡핑제 (입자 성장 억제) | 7.2% |
| synthesis_temperature_c | 합성 반응 온도 | 6.7% |

> ⚠️ **R² 음수 원인**: 같은 합성법 내에서도 입자크기의 분산이 매우 커서 현재 피처만으로는 예측력이 낮습니다.
> Ce 농도, 반응 부피 등 **미추출 변수**가 결정적 영향을 미치는 것으로 추정됩니다.
""")
                for i in range(0, len(importance_pngs), cols_per_row):
                    _ic = st.columns(cols_per_row)
                    for j, png in enumerate(importance_pngs[i:i + cols_per_row]):
                        with _ic[j]:
                            cap = os.path.basename(png).replace("importance_", "").replace(".png", "")
                            st.image(png, caption=cap, width="stretch")
            if shap_pngs:
                st.divider()
                st.markdown("**HistGBM SHAP 분석**")
                with st.expander("📖 SHAP 분석 해석 가이드", expanded=False):
                    st.markdown("""
**SHAP (SHapley Additive exPlanations)** — 각 샘플에 대해 피처가 예측값에 얼마나 기여했는지 보여줍니다.

**Beeswarm 차트 읽는 법**
- **X축 (SHAP 값)**: 오른쪽(+) = 입자크기 ↑ 방향 기여, 왼쪽(-) = 입자크기 ↓ 방향 기여
- **점 색깔**: 빨강 = 해당 피처 값이 높음, 파랑 = 낮음
- **점 퍼짐 정도**: 넓을수록 샘플 간 영향이 다양함 (비선형 관계 존재)

Permutation Importance와 달리 **방향성**을 알 수 있습니다.
예: 높은 합성온도(빨간 점)가 SHAP+ → 온도가 높을수록 입자가 커지는 경향.
""")
                for i in range(0, len(shap_pngs), cols_per_row):
                    _ic = st.columns(cols_per_row)
                    for j, png in enumerate(shap_pngs[i:i + cols_per_row]):
                        with _ic[j]:
                            cap = os.path.basename(png).replace("shap_", "").replace(".png", "")
                            st.image(png, caption=f"SHAP — {cap}", width="stretch")
            if cb_importance_pngs or cb_shap_pngs:
                st.divider()
                st.markdown("**CatBoost 피처 중요도 & SHAP**")
                with st.expander("📖 CatBoost SHAP 해석 가이드", expanded=False):
                    st.markdown("""
**CatBoost SHAP (SHapley Additive exPlanations)**

CatBoost는 범주형 피처를 native 처리하므로 TargetEncoder 없이도 피처 상호작용을 정확히 포착합니다.

- **X축 (SHAP 값)**: 오른쪽(+) = 입자크기 ↑ 기여, 왼쪽(-) = 입자크기 ↓ 기여
- **점 색깔**: 빨강 = 해당 피처 값이 높음, 파랑 = 낮음
- **HistGBM SHAP와 차이**: CatBoost는 Ordered Boosting으로 target leakage를 방지 → 더 신뢰성 높은 피처 중요도

| 타깃 | log-R² | n |
|------|--------|---|
| particle_size_primary_nm | +0.077 | 3,311 |
| particle_size_tem_nm | +0.080 | 3,141 |
| crystallite_size_xrd_nm | +0.151 | 1,743 |
""")
                if cb_importance_pngs:
                    st.caption("CatBoost 피처 중요도")
                    for i in range(0, len(cb_importance_pngs), cols_per_row):
                        _ic = st.columns(cols_per_row)
                        for j, png in enumerate(cb_importance_pngs[i:i + cols_per_row]):
                            with _ic[j]:
                                cap = os.path.basename(png).replace("catboost_importance_", "").replace(".png", "")
                                st.image(png, caption=f"CatBoost 중요도 — {cap}", use_container_width=True)
                if cb_shap_pngs:
                    st.caption("CatBoost SHAP Beeswarm")
                    for i in range(0, len(cb_shap_pngs), cols_per_row):
                        _ic = st.columns(cols_per_row)
                        for j, png in enumerate(cb_shap_pngs[i:i + cols_per_row]):
                            with _ic[j]:
                                cap = os.path.basename(png).replace("catboost_shap_", "").replace(".png", "")
                                st.image(png, caption=f"CatBoost SHAP — {cap}", use_container_width=True)

            if dkl_result_pngs:
                st.markdown("**DKL-GP 예측 + 불확실성**")
                with st.expander("📖 DKL-GP 차트 해석 가이드", expanded=False):
                    st.markdown("""
**DKL-GP (Deep Kernel Learning + Sparse Gaussian Process)**

신경망(특성 추출) + 가우시안 프로세스(GP) 결합 모델. 일반 ML과 달리 **예측 불확실성 σ** 를 함께 출력합니다.

**① 예측 vs 실제값 산점도**
- 대각선(점선) 위 = 과소예측(실제가 더 큼), 아래 = 과대예측
- 점 색깔: 빨강(σ 높음) = 불확실한 예측, 파랑(σ 낮음) = 확실한 예측
- 📌 해석: 큰 입자일수록 과소예측되는 경향 + σ도 크게 표시됨
  → 모델이 불확실한 예측은 스스로 높은 σ로 신호를 보냄 (잘 교정된 불확실성)

**② 불확실성 분포 (히스토그램)**
- σ 중앙값 ≈ 23 nm — 대부분 예측의 1σ 신뢰 범위가 ±23 nm
- σ가 큰 샘플(오른쪽 꼬리) = **능동학습 우선 실험 대상**
  → 이 조건의 논문을 추가 수집하면 모델 정확도를 효율적으로 개선 가능

**③ 학습 곡선 (Training Curve)**
- Epoch ~20에서 수렴 → 과적합 없이 안정적으로 학습됨
- Sparse GP의 inducing points가 정규화 역할 → val_loss가 train_loss와 근접 유지
""")
                for i in range(0, len(dkl_result_pngs), cols_per_row):
                    _ic = st.columns(cols_per_row)
                    for j, png in enumerate(dkl_result_pngs[i:i + cols_per_row]):
                        with _ic[j]:
                            cap = os.path.basename(png).replace("dkl_results_", "").replace(".png", "")
                            st.image(png, caption=f"DKL — {cap}", width="stretch")

    # ── 탭 2: 역설계 & 목표 설계 ─────────────────────────────────────────
    with ml_tabs[2]:

        # ── 실시간 합성 조건 예측 인터페이스 ─────────────────────────────────
        st.subheader("🔬 합성 조건 예측 (실시간)")
        st.caption("희망 입자 크기와 형태를 입력하면 최적 합성 조건을 예측합니다.")

        @st.cache_resource(show_spinner=False)
        def _load_pred_module():
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "ceria_model_pred", os.path.join(BASE_DIR, "12_model.py"))
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            return _mod

        @st.cache_data(ttl=600, show_spinner=False)
        def _load_df_pred():
            if os.path.exists(MERGED_CSV):
                return pd.read_csv(MERGED_CSV, low_memory=False)
            return pd.DataFrame()

        _reg_ok = os.path.exists(os.path.join(MODEL_DIR, "model_particle_size_primary_nm_reg.pkl"))
        _clf_ok = os.path.exists(os.path.join(MODEL_DIR, "model_morphology_clf.pkl"))

        if not (_reg_ok or _clf_ok):
            st.warning("모델 파일이 없습니다. 먼저 `python 12_model.py`를 실행하세요.")
        else:
            # ── 입력 패널 ──
            _pi1, _pi2, _pi3 = st.columns([2, 2, 1])
            with _pi1:
                _desired_size = st.number_input(
                    "🎯 희망 입자 크기 (nm)",
                    min_value=1.0, max_value=500.0, value=10.0, step=1.0,
                    help="TEM/SEM 기준 1차 입자 크기 목표값 (nm)"
                )
            with _pi2:
                _MORPH_OPTS = [
                    "(선택 안함)", "sphere", "cube", "rod",
                    "porous", "tube", "hollow", "flower", "octahedron", "plate",
                ]
                _morph_sel = st.selectbox(
                    "🔷 희망 입자 형태",
                    _MORPH_OPTS,
                    help="형태를 선택하지 않으면 크기 목표만 최적화합니다",
                )
                _desired_morph = None if _morph_sel == "(선택 안함)" else _morph_sel
            with _pi3:
                st.markdown("<br>", unsafe_allow_html=True)
                _run_btn = st.button("🔍 예측 실행", type="primary", use_container_width=True)

            if _run_btn:
                _df_for_pred = _load_df_pred()
                if _df_for_pred.empty:
                    st.error("데이터 파일을 불러올 수 없습니다.")
                else:
                    with st.spinner("합성 조건 탐색 중 (5,000개 후보 평가)..."):
                        try:
                            _pmod = _load_pred_module()
                            _pred = _pmod.predict_synthesis_conditions(
                                df=_df_for_pred,
                                target_size_nm=float(_desired_size),
                                target_morph=_desired_morph,
                                model_dir=MODEL_DIR,
                                top_k=10,
                            )
                            st.session_state["_inv_pred"] = _pred
                            st.session_state["_inv_inp"] = {
                                "size": _desired_size,
                                "morph": _morph_sel,
                            }
                        except Exception as _ex:
                            st.error(f"예측 실패: {_ex}")

            # ── 예측 결과 표시 ──
            if "_inv_pred" in st.session_state:
                _pred = st.session_state["_inv_pred"]
                _inp  = st.session_state["_inv_inp"]
                _meta = _pred.get("metadata", {})

                st.success(
                    f"✅ 예측 완료 — 목표 크기: **{_inp['size']:.0f} nm** "
                    f"| 목표 형태: **{_inp['morph']}**"
                )

                # 한국어 컬럼명 매핑 + 표시 순서
                _SHOW_COLS = [
                    "synthesis_method", "synthesis_temperature_c", "synthesis_time_h",
                    "ph_synthesis", "atmosphere",
                    "ce_precursor", "solvent",
                    "mineralizer", "capping_agent", "chelating_agent", "dopant",
                    "pred_size_nm", "pred_morph_prob",
                ]
                _COL_KR = {
                    "synthesis_method":      "합성법",
                    "synthesis_temperature_c": "반응온도(°C)",
                    "synthesis_time_h":       "반응시간(h)",
                    "ph_synthesis":           "반응 pH",
                    "atmosphere":             "가스 퍼징",
                    "ce_precursor":           "Ce 전구체",
                    "solvent":                "용매",
                    "mineralizer":            "미네랄라이저",
                    "capping_agent":          "캡핑에이전트",
                    "chelating_agent":        "킬레이터",
                    "dopant":                 "도핑제",
                    "pred_size_nm":           "예측 크기(nm)",
                    "pred_morph_prob":        "형태 확률",
                }

                def _fmt_pred_df(df_r, label):
                    if df_r is None or len(df_r) == 0:
                        return None
                    _cols = [c for c in _SHOW_COLS if c in df_r.columns]
                    _df   = df_r[_cols].rename(columns=_COL_KR).reset_index(drop=True)
                    _df.index = _df.index + 1
                    return _df

                _pt1, _pt2, _pt3 = st.tabs(
                    ["📏 크기 목표", "🔷 형태 목표", "🎯 크기+형태 조합"]
                )

                with _pt1:
                    st.markdown(
                        f"**목표 크기 {_inp['size']:.0f} nm** 달성에 최적화된 합성 조건 Top 10"
                    )
                    st.caption("형태 제약 없이 목표 크기에 가장 가까운 예측값을 내는 조건")
                    _r1 = _fmt_pred_df(_pred.get("size_only"), "size")
                    if _r1 is not None:
                        _num_c1 = [c for c in _r1.columns if _r1[c].dtype.kind == 'f']
                        _fmt1   = {c: "{:.1f}" for c in _num_c1}
                        if "형태 확률" in _fmt1:
                            _fmt1["형태 확률"] = "{:.3f}"
                        st.dataframe(
                            _r1.style.format(_fmt1, na_rep="—"),
                            use_container_width=True,
                        )
                    else:
                        st.info("크기 회귀 모델이 없거나 크기를 입력하지 않았습니다.")

                with _pt2:
                    st.markdown(
                        f"**목표 형태 {_inp['morph']}** 달성에 최적화된 합성 조건 Top 10"
                    )
                    st.caption("크기 제약 없이 목표 형태 확률이 높은 조건")
                    _r2 = _fmt_pred_df(_pred.get("morph_only"), "morph")
                    if _r2 is not None:
                        _num_c2 = [c for c in _r2.columns if _r2[c].dtype.kind == 'f']
                        _fmt2   = {c: "{:.1f}" for c in _num_c2}
                        if "형태 확률" in _fmt2:
                            _fmt2["형태 확률"] = "{:.3f}"
                        st.dataframe(
                            _r2.style.format(_fmt2, na_rep="—"),
                            use_container_width=True,
                        )
                    else:
                        st.info("형태 분류 모델이 없거나 형태를 선택하지 않았습니다.")

                with _pt3:
                    st.markdown(
                        f"**크기 {_inp['size']:.0f} nm + 형태 {_inp['morph']}** 동시 달성 조건 Top 10"
                    )
                    st.caption(
                        "크기 점수 × 형태 확률 종합 스코어 기준 — **실제 실험 설계에 가장 적합**"
                    )
                    _r3 = _fmt_pred_df(_pred.get("combined"), "combined")
                    if _r3 is not None:
                        _num_c3 = [c for c in _r3.columns if _r3[c].dtype.kind == 'f']
                        _fmt3   = {c: "{:.1f}" for c in _num_c3}
                        if "형태 확률" in _fmt3:
                            _fmt3["형태 확률"] = "{:.3f}"
                        st.dataframe(
                            _r3.style.format(_fmt3, na_rep="—"),
                            use_container_width=True,
                        )
                        with st.expander("📖 결과 해석 방법"):
                            st.markdown("""
**예측 크기(nm)**: 해당 조건으로 합성 시 예측되는 1차 입자 크기 (TEM/SEM 기준)

**형태 확률**: 목표 형태가 달성될 확률 (0~1). 0.3 이상이면 실험 가치 있음

**조합 스코어** = 크기 달성 점수 × 형태 달성 확률
- 크기 달성 점수: 목표 크기에서 멀수록 감소 (log-normal 분포 기준 ±35% 허용)
- 조합 점수가 높은 순으로 정렬됨

**주의사항**:
- 모델 학습 데이터(8,185개 샘플) 기반 통계적 패턴 — 확정 처방이 아님
- 동일 조건이라도 실험 편차(±20~50%) 존재
- 상위 3~5개 조건을 동시에 실험하여 비교하는 것을 권장
""")
                    else:
                        st.info("조합 예측에 실패했습니다.")

            st.divider()

        targeted_csvs = sorted(glob.glob(os.path.join(MODEL_DIR, "targeted_design_*nm.csv")))
        targeted_png  = os.path.join(MODEL_DIR, "targeted_design_ci_plot.png")
        targeted_xlsx = os.path.join(MODEL_DIR, "targeted_design_summary.xlsx")

        if targeted_csvs:
            st.subheader("🎯 목표 크기별 합성 조건 (75% 예측 구간)")
            st.caption("12_model.py 출력 | HistGBM Q10/Q90 분위 회귀 (입자크기 10~50nm 범위)")
            if os.path.exists(targeted_png):
                st.image(targeted_png, caption="목표 크기별 75% 예측 구간", width="stretch")
            tabs_t = st.tabs([
                os.path.basename(p).replace("targeted_design_","").replace(".csv","")
                for p in targeted_csvs
            ])
            for tab, csv_path in zip(tabs_t, targeted_csvs):
                with tab:
                    try:
                        tdf = pd.read_csv(csv_path)
                        num_c = tdf.select_dtypes("number").columns
                        fmt   = {c: "{:.2f}" for c in num_c}
                        st.dataframe(tdf.style.format(fmt, na_rep="—"),
                                     width="stretch", hide_index=True)
                        tgt = os.path.basename(csv_path).replace(
                            "targeted_design_","").replace("nm.csv","")
                        st.caption(
                            f"목표 {tgt} nm | 상위 {len(tdf)}개 조건 | "
                            "CI하한~CI상한 = 75% 예측 구간 (nm)"
                        )
                    except Exception as e:
                        st.error(f"읽기 실패: {e}")
            if os.path.exists(targeted_xlsx):
                with open(targeted_xlsx, "rb") as _fx:
                    st.download_button(
                        "📥 목표 크기별 조건 Excel 다운로드",
                        _fx.read(),
                        file_name="targeted_design_summary.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            st.divider()

        inv_hist = sorted(glob.glob(os.path.join(MODEL_DIR, "inverse_design_*.csv")))
        inv_dkl  = sorted(glob.glob(os.path.join(MODEL_DIR, "dkl_inverse_design_*.csv")))

        if inv_hist or inv_dkl:
            st.subheader("역설계 결과 (Inverse Design)")
            if inv_hist:
                st.markdown("**HistGBM 역설계**")
                for csv_path in inv_hist:
                    label = os.path.basename(csv_path).replace("inverse_design_", "").replace(".csv", "")
                    with st.expander(f"🎯 HistGBM — {label}", expanded=True):
                        try:
                            idf = pd.read_csv(csv_path)
                            st.dataframe(idf, width="stretch", hide_index=True)
                            st.caption(f"{len(idf):,}개 후보 조건")
                        except Exception as e:
                            st.error(f"읽기 실패: {e}")
            if inv_dkl:
                st.markdown("**DKL-GP 역설계 (불확실성 포함)**")
                for csv_path in inv_dkl:
                    label = os.path.basename(csv_path).replace("dkl_inverse_design_", "").replace(".csv", "")
                    with st.expander(f"🎯 DKL — {label}", expanded=True):
                        try:
                            idf = pd.read_csv(csv_path)
                            num_c = idf.select_dtypes("number").columns
                            fmt = {c: "{:.2f}" for c in num_c}
                            st.dataframe(idf.style.format(fmt, na_rep="—"),
                                         width="stretch", hide_index=True)
                            st.caption(f"{len(idf):,}개 후보 조건 | uncertainty_sigma 기준 정렬")
                        except Exception as e:
                            st.error(f"읽기 실패: {e}")
        else:
            st.info("역설계 결과 없음 — 12_model.py 실행 후 생성됩니다.")

    # ── 탭 3: 능동학습 ────────────────────────────────────────────────────
    with ml_tabs[3]:
        with st.expander("📖 능동학습이란?", expanded=False):
            st.markdown("""
**능동학습 (Active Learning)** — "어떤 실험을 다음에 해야 모델이 가장 빨리 좋아지는가?"를 알려줍니다.

모델이 가장 **불확실한 조건** = 해당 조건 데이터가 부족하거나 입력 공간에서 멀리 있는 경우.
이 조건으로 실험(또는 논문 수집)하면 같은 비용으로 모델 개선 효과가 최대화됩니다.

| 섹션 | 모델 | 불확실성 측정 방식 | 목표 |
|------|------|-------------------|------|
| 📏 입자크기 — HistGBM | 분위수 회귀 (Q10/Q90) | 예측 구간 폭 (nm) = Q90 − Q10 | **입자크기** 회귀 모델 개선 |
| 📏 입자크기 — DKL-GP | 가우시안 프로세스 | GP 표준편차 σ (nm) | **입자크기** 회귀 모델 개선 |
| 🔷 형태 — HistGBM | 형태 분류기 | 섀넌 엔트로피 (확률분포의 불균등도) | **형태(sphere/rod/cube)** 분류 모델 개선 |

> **두 입자크기 모델의 차이**: HistGBM Q10~Q90 구간폭은 데이터 희소성 기반, DKL-GP σ는 학습된 특성 공간의 거리 기반.
> 두 모델이 동시에 불확실하다고 지목한 조건이 가장 우선 실험 대상입니다.
""")

        # ── 섹션 1: 입자크기 능동학습 비교 ──────────────────────────────────
        st.subheader("📏 입자크기 예측 개선을 위한 실험 제안")
        st.caption("Q10~Q90 구간폭(HistGBM) 또는 σ(DKL-GP)가 가장 큰 조건 — 이 조건을 실험하면 입자크기 모델 개선 효과 최대")

        al_size_hist = os.path.join(MODEL_DIR, "active_learning_size_histgbm.csv")
        al_dkl_files = sorted(glob.glob(os.path.join(MODEL_DIR, "dkl_active_learning_*.csv")))

        col_h, col_d = st.columns(2)
        with col_h:
            st.markdown("**HistGBM — 분위수 구간폭 (Q10~Q90 nm)**")
            if os.path.exists(al_size_hist):
                try:
                    df_sh    = pd.read_csv(al_size_hist)
                    num_cols = df_sh.select_dtypes("number").columns
                    fmt      = {c: "{:.1f}" for c in num_cols}
                    st.dataframe(df_sh.style.format(fmt, na_rep="—"),
                                 width="stretch", hide_index=True)
                    st.caption(f"{len(df_sh)}개 제안 | uncertainty_interval_nm = Q90 − Q10 (nm)")
                except Exception as e:
                    st.error(f"읽기 실패: {e}")
            else:
                st.info("없음 — 12_model.py 재실행 후 생성됩니다")
        with col_d:
            st.markdown("**DKL-GP — GP 표준편차 σ (log-nm 공간)**")
            if al_dkl_files:
                try:
                    df_dkl = pd.read_csv(al_dkl_files[0])
                    # nm 변환 컬럼이 있으면 앞으로 재정렬
                    nm_cols  = [c for c in ["predicted_mean_nm", "sigma_lower_nm",
                                             "sigma_upper_nm", "uncertainty_interval_nm",
                                             "uncertainty_sigma"] if c in df_dkl.columns]
                    other_cols = [c for c in df_dkl.columns if c not in nm_cols]
                    df_dkl = df_dkl[nm_cols + other_cols]
                    num_cols = df_dkl.select_dtypes("number").columns
                    fmt = {c: "{:.1f}" for c in num_cols}
                    st.dataframe(df_dkl.style.format(fmt, na_rep="—"),
                                 width="stretch", hide_index=True)
                    lbl = os.path.basename(al_dkl_files[0]).replace("dkl_active_learning_","").replace(".csv","")
                    has_nm = "uncertainty_interval_nm" in df_dkl.columns
                    cap = (f"{len(df_dkl)}개 제안 ({lbl}) | "
                           + ("predicted_mean_nm: 예측 중앙값, sigma_lower/upper_nm: 1σ 범위 (exp(μ±σ))"
                              if has_nm else "uncertainty_sigma = log-nm 공간 σ"))
                    st.caption(cap)
                except Exception as e:
                    st.error(f"읽기 실패: {e}")
            else:
                st.info("없음 — 12c_gpr_model.py 실행 후 생성됩니다")

        st.divider()

        # ── 섹션 2: 형태 능동학습 ────────────────────────────────────────────
        st.subheader("🔷 형태 예측 개선을 위한 실험 제안")
        st.caption("형태 분류 엔트로피가 가장 높은 조건 — sphere/rod/cube 등 결과 형태 예측 모델 개선")

        al_morph = os.path.join(MODEL_DIR, "active_learning_morph_histgbm.csv")
        if not os.path.exists(al_morph):
            al_morph = os.path.join(MODEL_DIR, "active_learning_suggestions.csv")

        if os.path.exists(al_morph):
            try:
                df_morph = pd.read_csv(al_morph)
                num_cols = df_morph.select_dtypes("number").columns
                fmt      = {c: "{:.2f}" for c in num_cols}
                st.dataframe(df_morph.style.format(fmt, na_rep="—"),
                             width="stretch", hide_index=True)
                st.caption(f"{len(df_morph)}개 제안 | uncertainty = 섀넌 엔트로피 (값이 클수록 형태 예측 불확실)")
            except Exception as e:
                st.error(f"읽기 실패: {e}")
        else:
            st.info("없음 — 12_model.py 실행 후 생성됩니다")

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ 운영 현황 페이지
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ 운영 현황":
    st.title("⚙️ 운영 현황")

    # ── 1. 열별 데이터 수 ─────────────────────────────────────────────────────
    st.subheader("열별 데이터 보유 현황")
    col_df = load_col_counts()
    if not col_df.empty:
        total_rows = int(col_df["보유 수"].max())  # 가장 많이 채워진 컬럼 = 전체 행수 근사

        # 상단 요약 메트릭
        m1, m2, m3, m4 = st.columns(4)
        filled_cols = int((col_df["전체 대비(%)"] >= 50).sum())
        sparse_cols = int((col_df["전체 대비(%)"] < 10).sum())
        m1.metric("전체 컬럼 수", f"{len(col_df)}개")
        m2.metric("전체 논문 수", f"{total_rows:,}편")
        m3.metric("50% 이상 채워진 컬럼", f"{filled_cols}개")
        m4.metric("10% 미만 희소 컬럼", f"{sparse_cols}개")

        # 테이블
        st.dataframe(
            col_df.style
                .background_gradient(subset=["전체 대비(%)"], cmap="Blues", vmin=0, vmax=100)
                .format({"보유 수": "{:,}", "미보유 수": "{:,}", "전체 대비(%)": "{:.1f}%"}),
            width="stretch",
            height=500,
            hide_index=True,
        )
        st.caption(f"데이터 소스: {XLSX_PATH}")
    else:
        st.info("Excel 파일이 없습니다.")

    st.divider()

    # ── 2. PMC / Sci-Hub 다운로드 현황 ───────────────────────────────────────
    st.subheader("전문(Full Text) 수집 현황")
    noa = load_noa_status()

    pdf_count  = len(glob.glob(os.path.join(PDF_DIR,  "*.pdf")))
    text_count = len(glob.glob(os.path.join(TEXT_DIR, "*.txt")))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("PDF 보유",     f"{pdf_count:,}편")
    c2.metric("전문 텍스트",  f"{text_count:,}편")
    c3.metric("PMC 성공",     f"{noa.get('pmc_ok', 0):,}편"    if noa else "—")
    c4.metric("Sci-Hub 성공", f"{noa.get('scihub_ok', 0):,}편" if noa else "—")
    c5.metric("처리 완료 DOI",f"{len(noa.get('done_dois', [])):,}편" if noa else "—")

    if noa:
        failed = noa.get("failed", [])
        if failed:
            with st.expander(f"전문 수집 실패 DOI ({len(failed):,}개)"):
                st.dataframe(
                    pd.DataFrame({"DOI": failed}),
                    width="stretch", hide_index=True, height=300,
                )
    else:
        st.info("1_download.py 실행 전입니다.")

    st.divider()

    # ── 3. 주간 자동화 실행 이력 ──────────────────────────────────────────────
    st.subheader("주간 자동화 실행 이력")
    weekly = load_weekly_state()

    if weekly:
        w1, w2, w3 = st.columns(3)
        last_run = weekly.get("last_run", "없음")
        def _fmt_dt(s):
            if not s or s == "없음":
                return "없음"
            return str(s).replace("T", " ")[:16]   # YYYY-MM-DD HH:MM
        w1.metric("마지막 실행", _fmt_dt(last_run))
        w2.metric("누적 추가 논문", f"{weekly.get('total_added', 0):,}편")
        w3.metric("총 실행 횟수",   f"{len(weekly.get('runs', [])):,}회")

        runs = weekly.get("runs", [])
        if runs:
            run_rows = []
            for r in reversed(runs[-20:]):          # 최근 20회
                results = r.get("results", {})
                ok  = sum(1 for v in results.values() if v == "성공")
                tot = len(results)
                run_rows.append({
                    "실행 날짜":   _fmt_dt(r.get("date", "")),
                    "신규 논문":   f"{r.get('new_papers', 0):,}편",
                    "성공 단계":   f"{ok}/{tot}",
                    "로그 파일":   r.get("log", ""),
                })
            st.dataframe(
                pd.DataFrame(run_rows),
                width="stretch", hide_index=True,
            )
    else:
        st.info("run_weekly.py를 아직 실행하지 않았습니다.")
        st.code("python run_weekly.py", language="bash")

# ══════════════════════════════════════════════════════════════════════════════
# 🔬 탐색 분석 페이지
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔬 탐색 분석":
    st.title("🔬 탐색 분석")

    # quick_analysis.py 와 동일한 데이터 소스 — ceria_synthesis_database.xlsx (논문 단위)
    @st.cache_data(ttl=300)
    def _load_analysis_data():
        if not os.path.exists(XLSX_PATH):
            return None
        df = _load_xlsx_safe(XLSX_PATH)
        num_cols = [
            "particle_size_tem_nm", "crystallite_size_xrd_nm", "particle_size_sem_nm",
            "synthesis_temperature_c", "synthesis_time_h", "ph_synthesis",
            "calcination_temperature_c", "calcination_time_h",
            "bet_surface_area", "bet_surface_area_m2g",
        ]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        # TEM/SEM 이상값 제거 (0.3~500 nm)
        for _sc in ("particle_size_tem_nm", "particle_size_sem_nm"):
            if _sc in df.columns:
                df.loc[~df[_sc].between(0.3, 500), _sc] = None
        # 1차 입자크기 파생: TEM → SEM (Excel 논문단위 기반)
        _tem_v = df["particle_size_tem_nm"] if "particle_size_tem_nm" in df.columns \
                 else pd.Series(dtype=float)
        _sem_v = df["particle_size_sem_nm"] if "particle_size_sem_nm" in df.columns \
                 else pd.Series(dtype=float)
        df["particle_size_primary_nm"] = _tem_v.combine_first(_sem_v)
        # 카테고리 정규화
        for c in ("synthesis_method", "morphology"):
            if c in df.columns:
                df[c] = (df[c].fillna("unknown").astype(str)
                         .str.split(";").str[0].str.strip().str.lower())
        return df

    def _log_pearson(x, y):
        """log(y) vs x 의 Pearson r 반환."""
        mask = x.notna() & y.notna() & (y > 0)
        if mask.sum() < 3:
            return float("nan"), 0
        xi, yi = x[mask].values, y[mask].values
        r = float(np.corrcoef(xi, np.log(yi))[0, 1])
        return r, int(mask.sum())

    def _loglinear_trend(x, y):
        """log(y) = a*x + b 추세선 (x_line, y_line) 반환."""
        mask = x.notna() & y.notna() & (y > 0)
        xi, yi = x[mask].values, np.log(y[mask].values)
        z = np.polyfit(xi, yi, 1)
        x_line = np.linspace(xi.min(), xi.max(), 120)
        return x_line, np.exp(np.poly1d(z)(x_line))

    df_a = _load_analysis_data()

    if df_a is None:
        st.warning("ceria_synthesis_database.xlsx 없음.")
    else:
        TARGET  = "particle_size_primary_nm"   # 1차 입자: TEM → SEM
        n_total = len(df_a)
        n_tem   = int(df_a["particle_size_tem_nm"].notna().sum()) \
                  if "particle_size_tem_nm" in df_a.columns else 0
        n_sem   = int(df_a["particle_size_sem_nm"].notna().sum()) \
                  if "particle_size_sem_nm" in df_a.columns else 0
        n_primary = int(df_a[TARGET].notna().sum()) if TARGET in df_a.columns else 0
        st.caption(
            f"데이터 소스: `ceria_synthesis_database.xlsx` (논문 단위) · "
            f"총 **{n_total:,}** 편 · "
            f"1차 입자크기 보유: **{n_primary:,}** 편 (TEM {n_tem:,} + SEM {n_sem:,}편, 중복 제외)"
        )

        # 1차 입자크기 유효 행만 분리
        df_tem = (df_a[df_a[TARGET].notna()].copy()
                  if TARGET in df_a.columns else pd.DataFrame())

        _PALETTE = [
            "#E87C4C","#4C9BE8","#6EC46E","#B07DD6",
            "#F2C94C","#EB5757","#56CCF2","#27AE60",
            "#F2994A","#9B51E0","#2F80ED","#219653",
        ]

        with st.expander("📖 탐색 분석 차트 해석 가이드", expanded=False):
            st.markdown("""
**① 합성법별 크기** — 박스플롯 (Y축 로그스케일)
- 박스: IQR (25~75%), 중앙선: 중앙값, 삼각형: 평균값, 수염: ±1.5 IQR
- 방법별 데이터 수(n)가 다르므로 신뢰도도 다름 (n≥20만 표시)

**② ③ 온도 vs 입자크기** — 산점도 (Y축 로그스케일)
- 빨간 점선 = log-linear 추세선 (log 입자크기 ∝ 온도)
- **Pearson r**: log(크기) vs 온도의 선형 상관계수. |r| > 0.3이면 의미 있는 상관
- 수직 방향 넓은 분산: 같은 온도에서도 입자크기가 크게 다름
  → 합성법·용매·전구체 등 다른 변수의 영향이 더 큼을 시사

**④ 상관관계 히트맵** — 수치형 피처들 간 Pearson r
- 입자크기(particle_size_primary_nm)와 온도 간 약한 양의 상관이 일반적
- |r| < 0.2: 실질적 상관 거의 없음, 0.2–0.5: 약한 상관, > 0.5: 중간 이상 상관

**⑤ 형태별 크기** — 나노입자 형태(rod/sphere/cube 등)에 따른 크기 분포
**⑥ 합성 조건 분포** — 온도, 시간, pH 등 조건 변수의 전체 분포 히스토그램
""")

        tabs = st.tabs([
            "① 합성법별 크기",
            "② 합성온도 vs 크기",
            "③ 하소온도 vs 크기",
            "④ 상관관계 히트맵",
            "⑤ 형태별 크기",
            "⑥ 합성 조건 분포",
        ])

        # ── ① 합성법별 1차 입자크기 ──────────────────────────────────────────
        with tabs[0]:
            st.subheader("합성법별 1차 입자크기 분포 (TEM+SEM)")
            st.caption("Y축 log scale · 중앙값 오름차순 정렬 · n≥20 방법만 표시")
            if df_tem.empty or "synthesis_method" not in df_tem.columns:
                st.info("데이터 없음")
            else:
                sub = df_tem[["synthesis_method", TARGET]].dropna()
                counts = sub["synthesis_method"].value_counts()
                valid  = counts[counts >= 20].index.tolist()
                sub    = sub[sub["synthesis_method"].isin(valid)]
                order  = (sub.groupby("synthesis_method")[TARGET]
                           .median().sort_values().index.tolist())

                fig = go.Figure()
                for i, m in enumerate(order):
                    d = sub[sub["synthesis_method"] == m][TARGET]
                    fig.add_trace(go.Box(
                        y=d, name=f"{m}<br>(n={len(d)})",
                        marker_color=_PALETTE[i % len(_PALETTE)],
                        line_color=_PALETTE[i % len(_PALETTE)],
                        fillcolor=_PALETTE[i % len(_PALETTE)],
                        opacity=0.75,
                        boxmean=True,
                    ))
                fig.update_layout(
                    yaxis_title="1차 입자크기 (nm)",
                    xaxis_title="합성법",
                    showlegend=False, height=500,
                    margin=dict(t=30, b=10),
                )
                fig.update_yaxes(type="log")
                st.plotly_chart(fig, width="stretch")

        # ── ② 합성온도 vs 1차 입자크기 ───────────────────────────────────────
        with tabs[1]:
            st.subheader("합성온도 vs 1차 입자크기 (TEM+SEM)")
            X_COL = "synthesis_temperature_c"
            if df_tem.empty or X_COL not in df_tem.columns:
                st.info("데이터 없음")
            else:
                sub = df_tem[[X_COL, TARGET]].dropna()
                sub = sub[sub[X_COL].between(0, 1000)]
                r, n = _log_pearson(sub[X_COL], sub[TARGET])

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=sub[X_COL], y=sub[TARGET],
                    mode="markers",
                    marker=dict(
                        color=sub[TARGET], colorscale="Viridis",
                        colorbar=dict(
                            title=dict(text="입자크기 (nm)", side="right"),
                            thickness=12, len=0.65,
                            tickvals=[1, 10, 100], ticktext=["1", "10", "100"],
                        ),
                        size=7, opacity=0.72,
                        line=dict(width=0.4, color="rgba(0,0,0,0.2)"),
                    ),
                    showlegend=False,
                ))
                if n >= 5:
                    xl, yl = _loglinear_trend(sub[X_COL], sub[TARGET])
                    mid = len(xl) // 2
                    fig.add_trace(go.Scatter(
                        x=xl, y=yl, mode="lines",
                        line=dict(color="crimson", width=2, dash="dash"),
                        showlegend=False,
                    ))
                    fig.add_annotation(
                        x=xl[mid], y=yl[mid],
                        text="log-linear 추세",
                        font=dict(color="crimson", size=11),
                        bgcolor="rgba(255,255,255,0.7)",
                        borderpad=3, showarrow=False,
                        yshift=14,
                    )
                fig.update_layout(
                    template="simple_white",
                    xaxis_title="합성온도 (°C)",
                    yaxis_title="1차 입자크기 (nm)",
                    height=500, margin=dict(t=50, b=50, l=60, r=110),
                    annotations=[dict(
                        text=f"Pearson r = {r:.3f}  (n={n})",
                        xref="paper", yref="paper",
                        x=0.01, y=0.98, xanchor="left", yanchor="top",
                        font=dict(size=12, color="#555"), showarrow=False,
                    )],
                )
                fig.update_yaxes(
                    type="log",
                    tickvals=[1, 2, 5, 10, 20, 50, 100, 200, 500],
                    ticktext=["1", "2", "5", "10", "20", "50", "100", "200", "500"],
                    gridcolor="rgba(0,0,0,0.07)",
                )
                fig.update_xaxes(gridcolor="rgba(0,0,0,0.07)")
                st.plotly_chart(fig, use_container_width=True)

        # ── ③ 하소온도 vs 1차 입자크기 ───────────────────────────────────────
        with tabs[2]:
            st.subheader("하소온도 vs 1차 입자크기 (TEM+SEM)")
            X_COL = "calcination_temperature_c"
            if df_tem.empty or X_COL not in df_tem.columns:
                st.info("데이터 없음")
            else:
                sub = df_tem[[X_COL, TARGET]].dropna()
                sub = sub[sub[X_COL].between(50, 1600)]
                r, n = _log_pearson(sub[X_COL], sub[TARGET])

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=sub[X_COL], y=sub[TARGET],
                    mode="markers",
                    marker=dict(
                        color=sub[TARGET], colorscale="Plasma",
                        colorbar=dict(
                            title=dict(text="입자크기 (nm)", side="right"),
                            thickness=12, len=0.65,
                            tickvals=[1, 10, 100], ticktext=["1", "10", "100"],
                        ),
                        size=7, opacity=0.72,
                        line=dict(width=0.4, color="rgba(0,0,0,0.2)"),
                    ),
                    showlegend=False,
                ))
                if n >= 5:
                    xl, yl = _loglinear_trend(sub[X_COL], sub[TARGET])
                    mid = len(xl) // 2
                    fig.add_trace(go.Scatter(
                        x=xl, y=yl, mode="lines",
                        line=dict(color="crimson", width=2, dash="dash"),
                        showlegend=False,
                    ))
                    fig.add_annotation(
                        x=xl[mid], y=yl[mid],
                        text="log-linear 추세",
                        font=dict(color="crimson", size=11),
                        bgcolor="rgba(255,255,255,0.7)",
                        borderpad=3, showarrow=False,
                        yshift=14,
                    )
                fig.update_layout(
                    template="simple_white",
                    xaxis_title="하소온도 (°C)",
                    yaxis_title="1차 입자크기 (nm)",
                    height=500, margin=dict(t=50, b=50, l=60, r=110),
                    annotations=[dict(
                        text=f"Pearson r = {r:.3f}  (n={n})",
                        xref="paper", yref="paper",
                        x=0.01, y=0.98, xanchor="left", yanchor="top",
                        font=dict(size=12, color="#555"), showarrow=False,
                    )],
                )
                fig.update_yaxes(
                    type="log",
                    tickvals=[1, 2, 5, 10, 20, 50, 100, 200, 500],
                    ticktext=["1", "2", "5", "10", "20", "50", "100", "200", "500"],
                    gridcolor="rgba(0,0,0,0.07)",
                )
                fig.update_xaxes(gridcolor="rgba(0,0,0,0.07)")
                st.plotly_chart(fig, use_container_width=True)

        # ── ④ 수치 인자 상관관계 히트맵 ──────────────────────────────────────
        with tabs[3]:
            st.subheader("수치 합성 인자 간 상관관계")
            st.caption("Pearson 상관계수 (pairwise) · quick_analysis.py 동일 컬럼")
            # BET: Excel에는 bet_surface_area 컬럼 사용 (quick_analysis.py 와 동일)
            bet_col = "bet_surface_area" if "bet_surface_area" in df_a.columns else "bet_surface_area_m2g"
            HEAT_MAP = {
                "particle_size_primary_nm":  "1차입자(nm)",
                "crystallite_size_xrd_nm":   "XRD결정자(nm)",
                "synthesis_temperature_c":   "합성온도(°C)",
                "synthesis_time_h":          "합성시간(h)",
                "calcination_temperature_c": "하소온도(°C)",
                "calcination_time_h":        "하소시간(h)",
                "ph_synthesis":              "pH",
                bet_col:                     "BET(m²/g)",
            }
            avail = {label: pd.to_numeric(df_a[col], errors="coerce")
                     for col, label in HEAT_MAP.items() if col in df_a.columns}
            if len(avail) < 3:
                st.info("수치 컬럼 부족")
            else:
                num_df   = pd.DataFrame(avail).dropna(thresh=3)
                corr_mat = num_df.corr()
                fig = go.Figure(go.Heatmap(
                    z=corr_mat.values.round(2),
                    x=list(corr_mat.columns),
                    y=list(corr_mat.columns),
                    colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
                    text=corr_mat.values.round(2),
                    texttemplate="%{text}",
                    hoverongaps=False,
                ))
                fig.update_layout(
                    title="수치 합성 인자 간 상관관계",
                    height=520, margin=dict(t=50, b=10),
                )
                st.plotly_chart(fig, width="stretch")

        # ── ⑤ 형태별 1차 입자크기 ────────────────────────────────────────────
        with tabs[4]:
            st.subheader("입자 형태별 1차 입자크기 분포 (TEM+SEM)")
            st.caption("Y축 log scale · 중앙값 오름차순 정렬 · n≥10 형태만 표시")
            if df_tem.empty or "morphology" not in df_tem.columns:
                st.info("데이터 없음")
            else:
                sub = df_tem[["morphology", TARGET]].dropna()
                sub = sub[sub["morphology"] != "unknown"]
                counts = sub["morphology"].value_counts()
                valid  = counts[counts >= 10].index.tolist()
                sub    = sub[sub["morphology"].isin(valid)]
                order  = (sub.groupby("morphology")[TARGET]
                           .median().sort_values().index.tolist())

                fig = go.Figure()
                for i, m in enumerate(order):
                    d = sub[sub["morphology"] == m][TARGET]
                    fig.add_trace(go.Box(
                        y=d, name=f"{m}<br>(n={len(d)})",
                        marker_color=_PALETTE[i % len(_PALETTE)],
                        line_color=_PALETTE[i % len(_PALETTE)],
                        fillcolor=_PALETTE[i % len(_PALETTE)],
                        opacity=0.75,
                        boxmean=True,
                    ))
                fig.update_layout(
                    yaxis_title="1차 입자크기 (nm)",
                    xaxis_title="형태 (morphology)",
                    showlegend=False, height=500,
                    margin=dict(t=30, b=10),
                )
                fig.update_yaxes(type="log")
                st.plotly_chart(fig, width="stretch")

        # ── ⑥ 합성 조건 분포 (merged CSV 기반) ──────────────────────────────
        with tabs[5]:
            st.subheader("합성 조건 분포")
            st.caption("데이터 소스: ceria_samples_merged.csv (샘플 단위)")

            @st.cache_data(ttl=300)
            def _load_merged_conds():
                if not os.path.exists(MERGED_CSV):
                    return None
                df_m = pd.read_csv(MERGED_CSV, low_memory=False)
                for c in ["synthesis_temperature_c", "synthesis_time_h", "ph_synthesis",
                          "ce_concentration_M", "mineralizer_concentration_M"]:
                    if c in df_m.columns:
                        df_m[c] = pd.to_numeric(df_m[c], errors="coerce")
                return df_m

            df_m = _load_merged_conds()
            if df_m is None:
                st.info("ceria_samples_merged.csv 없음 — 3_merge.py 실행 후 표시됩니다.")
            else:
                _c1, _c2 = st.columns(2)

                # anion_type 분포
                with _c1:
                    if "anion_type" in df_m.columns:
                        st.markdown("**Ce 전구체 음이온 유형 (anion_type)**")
                        _at = df_m["anion_type"].dropna()
                        _at = _at[_at.str.strip() != ""]
                        if not _at.empty:
                            _at_cnt = _at.value_counts()
                            fig_at = go.Figure(go.Bar(
                                x=_at_cnt.index.tolist(), y=_at_cnt.values.tolist(),
                                text=_at_cnt.values.tolist(), textposition="outside",
                                marker_color="#4C9BE8",
                            ))
                            fig_at.update_layout(margin=dict(t=10,b=10,l=0,r=0), height=300,
                                                 xaxis_title="", yaxis_title="샘플 수")
                            st.plotly_chart(fig_at, width="stretch")
                            st.caption(f"매핑 완료: {len(_at):,}편 / 전체 {len(df_m):,}편")
                        else:
                            st.info("anion_type 데이터 없음 — 8_normalize_data.py 실행 후 표시")
                    else:
                        st.info("anion_type 컬럼 없음 — 8_normalize_data.py 실행 후 표시")

                # solvent_type 분포
                with _c2:
                    if "solvent_type" in df_m.columns:
                        st.markdown("**용매 유형 (solvent_type)**")
                        _st = df_m["solvent_type"].dropna()
                        _st = _st[_st.str.strip() != ""]
                        if not _st.empty:
                            _st_cnt = _st.value_counts()
                            fig_st = go.Figure(go.Bar(
                                x=_st_cnt.index.tolist(), y=_st_cnt.values.tolist(),
                                text=_st_cnt.values.tolist(), textposition="outside",
                                marker_color="#54C89B",
                            ))
                            fig_st.update_layout(margin=dict(t=10,b=10,l=0,r=0), height=300,
                                                 xaxis_title="", yaxis_title="샘플 수")
                            st.plotly_chart(fig_st, width="stretch")
                            st.caption(f"매핑 완료: {len(_st):,}편 / 전체 {len(df_m):,}편")
                        else:
                            st.info("solvent_type 데이터 없음 — 8_normalize_data.py 실행 후 표시")
                    else:
                        st.info("solvent_type 컬럼 없음 — 8_normalize_data.py 실행 후 표시")

                st.divider()
                _c3, _c4 = st.columns(2)

                # synthesis_method 분포
                with _c3:
                    if "synthesis_method" in df_m.columns:
                        st.markdown("**합성방법 분포 (synthesis_method)**")
                        _sm = df_m["synthesis_method"].dropna()
                        _sm = _sm[_sm.str.strip() != ""]
                        if not _sm.empty:
                            _sm_cnt = _sm.value_counts().head(15)
                            fig_sm = go.Figure(go.Bar(
                                x=_sm_cnt.index.tolist(), y=_sm_cnt.values.tolist(),
                                text=_sm_cnt.values.tolist(), textposition="outside",
                                marker_color="#E87C4C",
                            ))
                            fig_sm.update_layout(margin=dict(t=10,b=60,l=0,r=0), height=340,
                                                 xaxis_title="", yaxis_title="샘플 수",
                                                 xaxis_tickangle=-40)
                            st.plotly_chart(fig_sm, width="stretch")
                            st.caption(f"상위 15개 표시 · 전체 {_sm.nunique()}종")

                # synthesis_temperature_c 히스토그램
                with _c4:
                    if "synthesis_temperature_c" in df_m.columns:
                        st.markdown("**합성온도 분포 (°C)**")
                        _tc = df_m["synthesis_temperature_c"].dropna()
                        _tc = _tc[_tc.between(0, 1000)]
                        if not _tc.empty:
                            fig_tc = go.Figure(go.Histogram(
                                x=_tc, nbinsx=40,
                                marker_color="#B07DD6", opacity=0.85,
                            ))
                            fig_tc.update_layout(margin=dict(t=10,b=10,l=0,r=0), height=340,
                                                 xaxis_title="합성온도 (°C)", yaxis_title="샘플 수")
                            st.plotly_chart(fig_tc, width="stretch")
                            st.caption(f"n={len(_tc):,} · 중앙값 {_tc.median():.0f}°C · 평균 {_tc.mean():.0f}°C")
