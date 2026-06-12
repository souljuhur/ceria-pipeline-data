"""
quick_analysis.py — 입자크기 예측 인자 탐색 (30분용)

현재 ceria_synthesis_database.xlsx 기반 탐색적 분석.
출력: output/analysis/*.png  (5개 그래프)

실행:
  conda activate test
  python quick_analysis.py
"""
import os, warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

warnings.filterwarnings("ignore")

BASE_DIR  = r"d:\머신러닝 교육\ceria_pipeline_data"
XLSX_PATH = os.path.join(BASE_DIR, "output", "ceria_synthesis_database.xlsx")
OUT_DIR   = os.path.join(BASE_DIR, "output", "analysis")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 한글 폰트 설정 ─────────────────────────────────────────────────────────────
def _set_korean_font():
    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]
    for name in candidates:
        if any(name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False

_set_korean_font()

# ── 데이터 로드 ────────────────────────────────────────────────────────────────
print(f"로드: {XLSX_PATH}")
df = pd.read_excel(XLSX_PATH, sheet_name=0)
print(f"  총 {len(df):,}편\n")

# 핵심 컬럼 채움률 출력
KEY_COLS = {
    "particle_size_tem_nm":      "TEM 입자크기",
    "crystallite_size_xrd_nm":   "XRD 결정크기",
    "particle_size_sem_nm":      "SEM 입자크기",
    "synthesis_method":          "합성방법",
    "synthesis_temperature_c":   "합성온도",
    "synthesis_time_h":          "합성시간",
    "calcination_temperature_c": "하소온도",
    "solvent":                   "용매",
    "ce_precursor":              "Ce전구체",
    "additive":                  "첨가제",
    "morphology":                "형태",
    "ph_synthesis":              "pH",
    "dopant":                    "도핑원소",
    "dopant_concentration":      "도핑농도",
    "bet_surface_area":          "BET표면적",
}

print("=== 핵심 컬럼 채움률 ===")
fill_data = {}
for col, label in KEY_COLS.items():
    if col in df.columns:
        n = df[col].notna().sum()
        pct = n / len(df) * 100
        fill_data[label] = pct
        print(f"  {label:<15} {n:>5}편  ({pct:5.1f}%)")
    else:
        print(f"  {label:<15}  컬럼 없음")

# TEM 기준 분석 데이터
TARGET = "particle_size_tem_nm"
if TARGET not in df.columns:
    print(f"\n{TARGET} 컬럼 없음. 분석 종료.")
    exit()

df_tem = df[df[TARGET].notna() & pd.to_numeric(df[TARGET], errors="coerce").notna()].copy()
df_tem[TARGET] = pd.to_numeric(df_tem[TARGET], errors="coerce")
df_tem = df_tem[df_tem[TARGET].between(0.5, 500)]  # 이상값 제거
print(f"\nTEM 입자크기 유효 데이터: {len(df_tem):,}편")
print(f"  범위: {df_tem[TARGET].min():.1f} ~ {df_tem[TARGET].max():.1f} nm")
print(f"  중앙값: {df_tem[TARGET].median():.1f} nm | 평균: {df_tem[TARGET].mean():.1f} nm")


# ── 그래프 1: 합성방법별 TEM 입자크기 분포 ────────────────────────────────────
print("\n[1/5] 합성방법별 TEM 입자크기 분포...")
if "synthesis_method" in df_tem.columns:
    method_col = "synthesis_method"
    grp = df_tem[[method_col, TARGET]].dropna()

    # 복수 방법(세미콜론 구분)의 경우 첫 번째만 사용
    grp = grp.copy()
    grp[method_col] = grp[method_col].str.split(";").str[0].str.strip()

    # 20편 이상인 방법만
    counts = grp[method_col].value_counts()
    valid_methods = counts[counts >= 20].index.tolist()
    grp = grp[grp[method_col].isin(valid_methods)]

    order = (grp.groupby(method_col)[TARGET].median()
               .sort_values().index.tolist())

    fig, ax = plt.subplots(figsize=(12, 6))
    data_by_method = [grp[grp[method_col] == m][TARGET].values for m in order]
    bp = ax.boxplot(data_by_method, labels=order, patch_artist=True,
                    medianprops=dict(color="red", linewidth=2))
    colors = plt.cm.Set3(np.linspace(0, 1, len(order)))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    ax.set_yscale("log")
    ax.set_ylabel("TEM 입자크기 (nm, log scale)", fontsize=12)
    ax.set_title("합성방법별 TEM 입자크기 분포", fontsize=14, fontweight="bold")
    ax.set_xticklabels(order, rotation=35, ha="right", fontsize=9)

    for i, m in enumerate(order):
        n = len(grp[grp[method_col] == m])
        med = grp[grp[method_col] == m][TARGET].median()
        ax.text(i + 1, med * 1.3, f"n={n}", ha="center", fontsize=7, color="navy")

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "01_method_vs_size.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  저장: {out}")
else:
    print("  synthesis_method 컬럼 없음 — 건너뜀")


# ── 그래프 2: 합성온도 vs TEM 입자크기 ────────────────────────────────────────
print("[2/5] 합성온도 vs TEM 입자크기...")
TEMP_COL = "synthesis_temperature_c"
if TEMP_COL in df_tem.columns:
    scatter = df_tem[[TEMP_COL, TARGET, "synthesis_method"]].dropna(subset=[TEMP_COL, TARGET]).copy()
    scatter[TEMP_COL] = pd.to_numeric(scatter[TEMP_COL], errors="coerce")
    scatter = scatter.dropna().query(f"0 < {TEMP_COL} < 1000")

    if len(scatter) < 5:
        print(f"  데이터 부족({len(scatter)}행) — 건너뜀")
    else:
        fig, ax = plt.subplots(figsize=(9, 6))
        sc = ax.scatter(scatter[TEMP_COL], scatter[TARGET],
                        alpha=0.5, s=20, c=scatter[TARGET], cmap="viridis",
                        norm=matplotlib.colors.LogNorm())
        plt.colorbar(sc, ax=ax, label="입자크기 (nm)")

        log_y = np.log(scatter[TARGET])
        z = np.polyfit(scatter[TEMP_COL], log_y, 1)
        x_line = np.linspace(scatter[TEMP_COL].min(), scatter[TEMP_COL].max(), 100)
        ax.plot(x_line, np.exp(np.poly1d(z)(x_line)), "r-", linewidth=1.5, label="추세선")

        corr = scatter[TEMP_COL].corr(np.log(scatter[TARGET]))
        ax.set_xlabel("합성온도 (°C)", fontsize=12)
        ax.set_ylabel("TEM 입자크기 (nm, log scale)", fontsize=12)
        ax.set_yscale("log")
        ax.set_title(f"합성온도 vs TEM 입자크기  (Pearson r={corr:.3f}, n={len(scatter)})",
                     fontsize=13, fontweight="bold")
        ax.legend()
        plt.tight_layout()
        out = os.path.join(OUT_DIR, "02_temp_vs_size.png")
        plt.savefig(out, dpi=150)
        plt.close()
        print(f"  저장: {out}  |  상관계수(log): r={corr:.3f}")
else:
    print(f"  {TEMP_COL} 컬럼 없음 — 건너뜀")


# ── 그래프 3: 하소온도 vs TEM 입자크기 ────────────────────────────────────────
print("[3/5] 하소온도 vs TEM 입자크기...")
CALC_COL = "calcination_temperature_c"
if CALC_COL in df_tem.columns:
    scatter = df_tem[[CALC_COL, TARGET]].dropna().copy()
    scatter[CALC_COL] = pd.to_numeric(scatter[CALC_COL], errors="coerce")
    scatter = scatter.dropna().query(f"50 < {CALC_COL} < 1600")

    if len(scatter) < 5:
        print(f"  데이터 부족({len(scatter)}행) — 건너뜀")
    else:
        fig, ax = plt.subplots(figsize=(9, 6))
        sc = ax.scatter(scatter[CALC_COL], scatter[TARGET],
                        alpha=0.5, s=20, c=scatter[TARGET], cmap="plasma",
                        norm=matplotlib.colors.LogNorm())
        plt.colorbar(sc, ax=ax, label="입자크기 (nm)")

        log_y = np.log(scatter[TARGET])
        z = np.polyfit(scatter[CALC_COL], log_y, 1)
        x_line = np.linspace(scatter[CALC_COL].min(), scatter[CALC_COL].max(), 100)
        ax.plot(x_line, np.exp(np.poly1d(z)(x_line)), "r-", linewidth=1.5, label="추세선")

        corr = scatter[CALC_COL].corr(np.log(scatter[TARGET]))
        ax.set_xlabel("하소온도 (°C)", fontsize=12)
        ax.set_ylabel("TEM 입자크기 (nm, log scale)", fontsize=12)
        ax.set_yscale("log")
        ax.set_title(f"하소온도 vs TEM 입자크기  (Pearson r={corr:.3f}, n={len(scatter)})",
                     fontsize=13, fontweight="bold")
        ax.legend()
        plt.tight_layout()
        out = os.path.join(OUT_DIR, "03_calcination_vs_size.png")
        plt.savefig(out, dpi=150)
        plt.close()
        print(f"  저장: {out}  |  상관계수(log): r={corr:.3f}")
else:
    print(f"  {CALC_COL} 컬럼 없음 — 건너뜀")


# ── 그래프 4: 수치 인자 상관관계 히트맵 ───────────────────────────────────────
print("[4/5] 수치 인자 상관관계 히트맵...")
NUMERIC_COLS = {
    "particle_size_tem_nm":      "TEM 크기(nm)",
    "crystallite_size_xrd_nm":   "XRD 크기(nm)",
    "synthesis_temperature_c":   "합성온도(°C)",
    "synthesis_time_h":          "합성시간(h)",
    "calcination_temperature_c": "하소온도(°C)",
    "calcination_time_h":        "하소시간(h)",
    "ph_synthesis":              "pH",
    "bet_surface_area":          "BET(m²/g)",
}
available = {v: df[k].apply(pd.to_numeric, errors="coerce")
             for k, v in NUMERIC_COLS.items() if k in df.columns}
if len(available) >= 3:
    num_df = pd.DataFrame(available).dropna(thresh=3)
    corr_mat = num_df.corr()

    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(corr_mat, cmap="RdBu_r", vmin=-1, vmax=1)
    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.set_xticks(range(len(corr_mat)))
    ax.set_yticks(range(len(corr_mat)))
    ax.set_xticklabels(corr_mat.columns, rotation=40, ha="right", fontsize=9)
    ax.set_yticklabels(corr_mat.columns, fontsize=9)
    for i in range(len(corr_mat)):
        for j in range(len(corr_mat)):
            val = corr_mat.iloc[i, j]
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=8, color="white" if abs(val) > 0.5 else "black")
    ax.set_title("수치 합성 인자 간 상관관계", fontsize=13, fontweight="bold")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "04_correlation_heatmap.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  저장: {out}")
else:
    print("  수치 컬럼 부족 — 건너뜀")


# ── 그래프 5: 형태(morphology)별 TEM 입자크기 ─────────────────────────────────
print("[5/5] 형태별 TEM 입자크기...")
MORPH_COL = "morphology"
if MORPH_COL in df_tem.columns:
    grp = df_tem[[MORPH_COL, TARGET]].dropna().copy()
    grp[MORPH_COL] = grp[MORPH_COL].str.split(";").str[0].str.strip()
    counts = grp[MORPH_COL].value_counts()
    valid = counts[counts >= 10].index.tolist()
    grp = grp[grp[MORPH_COL].isin(valid)]
    order = grp.groupby(MORPH_COL)[TARGET].median().sort_values().index.tolist()

    fig, ax = plt.subplots(figsize=(11, 6))
    data_by_morph = [grp[grp[MORPH_COL] == m][TARGET].values for m in order]
    bp = ax.boxplot(data_by_morph, labels=order, patch_artist=True,
                    medianprops=dict(color="red", linewidth=2))
    colors = plt.cm.Pastel1(np.linspace(0, 1, len(order)))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    ax.set_yscale("log")
    ax.set_ylabel("TEM 입자크기 (nm, log scale)", fontsize=12)
    ax.set_title("입자 형태별 TEM 입자크기 분포", fontsize=14, fontweight="bold")
    ax.set_xticklabels(order, rotation=30, ha="right", fontsize=9)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "05_morphology_vs_size.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  저장: {out}")
else:
    print("  morphology 컬럼 없음 — 건너뜀")


# ── 텍스트 요약 ────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("분석 완료. 결과 파일:")
for f in sorted(os.listdir(OUT_DIR)):
    if f.endswith(".png"):
        print(f"  output/analysis/{f}")
print("="*55)
