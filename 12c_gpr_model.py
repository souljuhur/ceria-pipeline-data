"""
12c_gpr_model.py — Stage 3-c: Deep Kernel Learning (DKL) + 불확실성 정량화

아키텍처:
  [범주형 임베딩 + 수치형 정규화] → NN 특징 추출기 → Sparse GP (SVGP) 헤드
  커널: ScaleKernel(RBF-ARD), 변분 추론(ELBO), 유도점 학습

주요 기여:
  1. 예측 불확실성(σ) 정량화 — 실험 신뢰도 평가
  2. 능동학습 — 불확실성 최대 조건 제안
  3. 역설계 — 목표 입자 크기 조건 최적화 (불확실성 패널티 포함)

실행:
  python 12c_gpr_model.py                    # DKL 학습 + 평가
  python 12c_gpr_model.py --target particle_size_tem_nm
  python 12c_gpr_model.py --epochs 200 --inducing 512

필요 패키지:
  pip install torch gpytorch
"""
import os, sys, warnings, pickle, argparse, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

# ── 12_model.py 공통 모듈 동적 임포트 ─────────────────────────────────────────
import importlib.util
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "m12", os.path.join(_SCRIPT_DIR, "12_model.py"))
m12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m12)

BASE_DIR             = m12.BASE_DIR
MODEL_DIR            = os.path.join(BASE_DIR, "output", "model")
os.makedirs(MODEL_DIR, exist_ok=True)

NUMERIC_FEATURES     = m12.NUMERIC_FEATURES
CATEGORICAL_FEATURES = m12.CATEGORICAL_FEATURES
FEATURES             = m12.FEATURES
TARGET_COMPOSITE     = m12.TARGET_COMPOSITE
TARGET_SIZE          = m12.TARGET_SIZE
TARGET_XRD           = m12.TARGET_XRD
_LOG_TARGETS         = m12._LOG_TARGETS

# ── 패키지 임포트 ─────────────────────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader
    import gpytorch
    from gpytorch.models import ApproximateGP
    from gpytorch.variational import (
        CholeskyVariationalDistribution, VariationalStrategy
    )
    from gpytorch.mlls import VariationalELBO
except ImportError:
    sys.exit("torch/gpytorch 미설치: pip install torch gpytorch")

from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
import matplotlib.font_manager as _fm

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_avail_fonts = {f.name for f in _fm.fontManager.ttflist}
for _fn in ["Malgun Gothic", "NanumGothic", "NanumBarunGothic", "AppleGothic", "DejaVu Sans"]:
    if _fn in _avail_fonts:
        plt.rcParams["font.family"] = _fn
        break
plt.rcParams["axes.unicode_minus"] = False


# ── 피처 인코더 ───────────────────────────────────────────────────────────────
class FeatureEncoder:
    """수치형 + 범주형 피처 → DKL 입력 텐서."""

    def __init__(self, embed_dim: int = 8):
        self.embed_dim = embed_dim
        self.label_encoders: dict = {}
        self.scaler = StandardScaler()
        self.cat_cardinalities: dict = {}

    def fit(self, df: pd.DataFrame) -> "FeatureEncoder":
        # 수치형
        num_vals = df[NUMERIC_FEATURES].fillna(0.0).values
        self.scaler.fit(num_vals)
        # 범주형
        for col in CATEGORICAL_FEATURES:
            le = LabelEncoder()
            le.fit(df[col].astype(str))
            self.label_encoders[col] = le
            # +1 for unknown (index 0 reserved for OOV via padding_idx)
            self.cat_cardinalities[col] = len(le.classes_) + 1
        return self

    def transform(self, df: pd.DataFrame):
        num_vals = self.scaler.transform(df[NUMERIC_FEATURES].fillna(0.0).values)
        cat_cols = []
        for col in CATEGORICAL_FEATURES:
            le    = self.label_encoders[col]
            known = set(le.classes_)
            # OOV → 0 (padding_idx), valid → 1-indexed
            enc = df[col].astype(str).apply(
                lambda x: int(le.transform([x])[0]) + 1 if x in known else 0
            ).values
            cat_cols.append(enc)
        cat_vals = np.stack(cat_cols, axis=1)  # (N, n_cat)
        num_t = torch.tensor(num_vals, dtype=torch.float32)
        cat_t = torch.tensor(cat_vals, dtype=torch.long)
        return num_t, cat_t


# ── NN 특징 추출기 ─────────────────────────────────────────────────────────────
class FeatureExtractor(nn.Module):
    def __init__(self, cat_cardinalities: dict, embed_dim: int = 8,
                 num_dim: int = 15, hidden_dim: int = 64, output_dim: int = 16):
        super().__init__()
        # 범주형 임베딩
        self.embeddings = nn.ModuleDict({
            col: nn.Embedding(card, embed_dim, padding_idx=0)
            for col, card in cat_cardinalities.items()
        })
        total_in = num_dim + len(cat_cardinalities) * embed_dim
        self.net = nn.Sequential(
            nn.Linear(total_in, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.SiLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, num_x: torch.Tensor, cat_x: torch.Tensor) -> torch.Tensor:
        embs = [
            self.embeddings[col](cat_x[:, i])
            for i, col in enumerate(CATEGORICAL_FEATURES)
        ]
        x = torch.cat([num_x] + embs, dim=1)
        return self.net(x)


# ── Sparse GP 코어 ────────────────────────────────────────────────────────────
class SVGPCore(ApproximateGP):
    """잠재 피처 공간에서 동작하는 Sparse GP."""

    def __init__(self, inducing_points: torch.Tensor):
        latent_dim = inducing_points.size(1)
        var_dist   = CholeskyVariationalDistribution(inducing_points.size(0))
        var_strat  = VariationalStrategy(
            self, inducing_points, var_dist, learn_inducing_locations=True
        )
        super().__init__(var_strat)
        self.mean_module  = gpytorch.means.ConstantMean()
        self.covar_module = gpytorch.kernels.ScaleKernel(
            gpytorch.kernels.RBFKernel(ard_num_dims=latent_dim)
        )

    def forward(self, z: torch.Tensor):
        return gpytorch.distributions.MultivariateNormal(
            self.mean_module(z), self.covar_module(z)
        )


# ── DKL 모델 (NN + SVGP 통합) ──────────────────────────────────────────────────
class DKLModel(nn.Module):
    def __init__(self, cat_cardinalities: dict,
                 n_inducing: int = 256, embed_dim: int = 8,
                 hidden_dim: int = 64, latent_dim: int = 16,
                 num_dim: int = 15):
        super().__init__()
        self.feature_extractor = FeatureExtractor(
            cat_cardinalities, embed_dim, num_dim, hidden_dim, latent_dim
        )
        # 유도점을 잠재 공간에서 초기화
        inducing_pts = torch.randn(n_inducing, latent_dim) * 0.1
        self.gp = SVGPCore(inducing_pts)

    def forward(self, num_x: torch.Tensor, cat_x: torch.Tensor):
        z = self.feature_extractor(num_x, cat_x)
        return self.gp(z)


# ── 학습 ─────────────────────────────────────────────────────────────────────
def train_dkl(num_tr, cat_tr, y_tr, num_val, cat_val, y_val,
              cat_cardinalities: dict, n_inducing: int = 256,
              n_epochs: int = 150, batch_size: int = 256,
              lr: float = 1e-3) -> tuple:

    n_train  = len(y_tr)
    num_dim  = num_tr.shape[1]  # 실제 수치 피처 수 (NUMERIC_FEATURES 개수)
    model     = DKLModel(cat_cardinalities, n_inducing=n_inducing, num_dim=num_dim).to(DEVICE)
    likelihood = gpytorch.likelihoods.GaussianLikelihood().to(DEVICE)

    model.train(); likelihood.train()

    optimizer = torch.optim.Adam([
        {"params": model.feature_extractor.parameters(), "lr": lr},
        {"params": model.gp.parameters(),               "lr": lr * 0.5},
        {"params": likelihood.parameters(),              "lr": lr * 0.5},
    ])
    # T_max=100: epoch 100에서 eta_min에 도달 → 초기 수렴 가속
    # (n_epochs=300 전체를 T_max로 쓰면 epoch 70 시점에서도 LR이 너무 높음)
    t_max = min(n_epochs, 100)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=t_max, eta_min=lr * 0.05)
    mll = VariationalELBO(likelihood, model.gp, num_data=n_train)

    # DataLoader (미니배치 SVGP)
    ds      = TensorDataset(
        torch.tensor(num_tr, dtype=torch.float32),
        torch.tensor(cat_tr, dtype=torch.long),
        torch.tensor(y_tr,  dtype=torch.float32),
    )
    loader  = DataLoader(ds, batch_size=batch_size, shuffle=True)

    best_val_mae  = float("inf")
    history       = []
    no_improve    = 0          # patience 카운터
    eval_freq     = 5          # 5 epoch마다 검증
    patience      = 10         # 10회 연속 미개선 시 조기 종료 (= 50 epoch)
    best_epoch    = 0

    # top-K 체크포인트 버퍼: val-MAE 상위 3개 보존 → 최신 epoch 선택
    # val-best(ep20)과 test-best(ep25) 불일치 해결용 (근사값이 노이즈 수준이면 최신 사용)
    CKPT_BUFFER_SIZE = 3
    ckpt_buffer = []  # [(val_mae, epoch, state_dict), ...] — val_mae 오름차순 유지

    for epoch in range(1, n_epochs + 1):
        model.train(); likelihood.train()
        epoch_loss = 0.0
        for num_b, cat_b, y_b in loader:
            num_b, cat_b, y_b = num_b.to(DEVICE), cat_b.to(DEVICE), y_b.to(DEVICE)
            optimizer.zero_grad()
            out  = model(num_b, cat_b)
            loss = -mll(out, y_b)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step()

        if epoch % eval_freq == 0 or epoch == 1:
            val_mae = _eval_mae(model, likelihood, num_val, cat_val, y_val)
            history.append({"epoch": epoch, "loss": epoch_loss, "val_mae": val_mae})

            # 체크포인트 버퍼에 추가 (상위 K개 유지)
            state = {
                "model":      {k: v.cpu().clone() for k, v in model.state_dict().items()},
                "likelihood": {k: v.cpu().clone() for k, v in likelihood.state_dict().items()},
            }
            ckpt_buffer.append((val_mae, epoch, state))
            ckpt_buffer.sort(key=lambda x: x[0])   # val_mae 오름차순 (낮을수록 좋음)
            if len(ckpt_buffer) > CKPT_BUFFER_SIZE:
                ckpt_buffer.pop()                   # 가장 나쁜 checkpoint 제거

            if val_mae < best_val_mae:
                best_val_mae = val_mae
                best_epoch   = epoch
                no_improve   = 0
            else:
                no_improve += 1
            print(f"  Epoch {epoch:>3}/{n_epochs} | loss={epoch_loss:.3f} | "
                  f"val-MAE={val_mae:.4f}  (best={best_val_mae:.4f} @ep{best_epoch})")
            if no_improve >= patience:
                print(f"  [Early stop] {patience}회 연속 미개선 → epoch {epoch}에서 종료 "
                      f"(best epoch={best_epoch})")
                break

    # 버퍼에서 val-MAE 상위 K 중 최신 epoch 선택 (val/test 불일치 최소화)
    if ckpt_buffer:
        chosen_mae, chosen_epoch, best_state = max(ckpt_buffer, key=lambda x: x[1])
        print(f"  [체크포인트] top-{CKPT_BUFFER_SIZE} 중 최신 ep{chosen_epoch} 사용 "
              f"(val-MAE={chosen_mae:.4f}, best={best_val_mae:.4f} @ep{best_epoch})")
        model.load_state_dict(best_state["model"])
        likelihood.load_state_dict(best_state["likelihood"])

    return model, likelihood, history


def _eval_mae(model, likelihood, num_x, cat_x, y_true) -> float:
    model.eval(); likelihood.eval()
    with torch.no_grad(), gpytorch.settings.fast_pred_var():
        num_t = torch.tensor(num_x, dtype=torch.float32).to(DEVICE)
        cat_t = torch.tensor(cat_x, dtype=torch.long).to(DEVICE)
        preds = likelihood(model(num_t, cat_t))
        pred_np = preds.mean.cpu().numpy()
    return mean_absolute_error(y_true, pred_np)


# ── 예측 + 불확실성 ────────────────────────────────────────────────────────────
def predict(model, likelihood, num_x, cat_x, chunk_size=512):
    """청크 단위 예측 (GPU OOM 방지). 반환: (mean, std) numpy."""
    model.eval(); likelihood.eval()
    means, stds = [], []
    n = len(num_x)
    with torch.no_grad(), gpytorch.settings.fast_pred_var():
        for i in range(0, n, chunk_size):
            nm = torch.tensor(num_x[i:i+chunk_size], dtype=torch.float32).to(DEVICE)
            ct = torch.tensor(cat_x[i:i+chunk_size], dtype=torch.long).to(DEVICE)
            p  = likelihood(model(nm, ct))
            means.append(p.mean.cpu().numpy())
            stds.append(p.stddev.cpu().numpy())
    return np.concatenate(means), np.concatenate(stds)


# ── 시각화 ────────────────────────────────────────────────────────────────────
def plot_results(y_true_raw, mean_nm, std_nm, history, target):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # 좌: 예측 vs 실제 (색 = 불확실성)
    ax = axes[0]
    sc = ax.scatter(y_true_raw, mean_nm, c=std_nm,
                    cmap="RdYlGn_r", alpha=0.4, s=8)
    mn = min(y_true_raw.min(), mean_nm.min())
    mx = max(y_true_raw.max(), mean_nm.max())
    ax.plot([mn, mx], [mn, mx], "k--", lw=1)
    plt.colorbar(sc, ax=ax, label="σ (nm)")
    ax.set_xlabel("Actual (nm)"); ax.set_ylabel("Predicted (nm)")
    ax.set_title(f"DKL: Pred vs Actual\n{target}")

    # 중: 불확실성 히스토그램
    ax2 = axes[1]
    ax2.hist(std_nm, bins=50, color="#4C9BE8", edgecolor="white", alpha=0.8)
    ax2.axvline(std_nm.median() if hasattr(std_nm, "median") else np.median(std_nm),
                color="red", linestyle="--", label=f"median={np.median(std_nm):.2f}")
    ax2.set_xlabel("Uncertainty σ (nm)")
    ax2.set_ylabel("Count")
    ax2.set_title("Uncertainty Distribution")
    ax2.legend()

    # 우: 학습 곡선
    ax3 = axes[2]
    if history:
        epochs = [h["epoch"] for h in history]
        vals   = [h["val_mae"] for h in history]
        ax3.plot(epochs, vals, "o-", color="#E87C4C")
        ax3.set_xlabel("Epoch"); ax3.set_ylabel("Val MAE (log scale)")
        ax3.set_title("Training Curve")

    plt.tight_layout()
    path = os.path.join(MODEL_DIR, f"dkl_results_{target}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  결과 플롯: {path}")


# ── 능동학습: 불확실성 기반 실험 제안 ─────────────────────────────────────────
def active_learning(model, likelihood, encoder: FeatureEncoder,
                    df: pd.DataFrame, target: str,
                    n_cand: int = 2000, top_k: int = 10,
                    use_log: bool = True):
    rng = np.random.default_rng(0)
    cand = pd.DataFrame(index=range(n_cand))

    # 수치형: 관측된 범위 내 균등 샘플링
    for col in NUMERIC_FEATURES:
        vals = df[col].dropna()
        lo, hi = (vals.quantile(0.05), vals.quantile(0.95)) if len(vals) >= 5 else (0.0, 1.0)
        cand[col] = rng.uniform(lo, hi, n_cand)

    # 범주형: 관측된 범주 중 무작위 선택
    for col in CATEGORICAL_FEATURES:
        vals = df[col].replace("", np.nan).dropna().unique()
        cand[col] = rng.choice(vals, n_cand) if len(vals) > 0 else "unknown"

    # 파생 피처 (8_normalize_data 동일 규칙)
    for src, dst in [("synthesis_temperature_c", "log_synth_temp"),
                     ("synthesis_time_h",         "log_synth_time"),
                     ("calcination_temperature_c","log_calc_temp")]:
        cand[dst] = np.log(cand[src].clip(lower=1))
    cand["thermal_budget"]      = cand["synthesis_temperature_c"] * cand["synthesis_time_h"]
    cand["calc_thermal_budget"] = cand["calcination_temperature_c"] * cand["calcination_time_h"]

    for bin_col, src_col in [("has_mineralizer","mineralizer"),
                               ("has_dopant","dopant"),
                               ("capping_present","capping_agent")]:
        cand[bin_col] = cand[src_col].apply(
            lambda x: 0.0 if pd.isna(x) or str(x).strip().lower() in ("none","unknown","") else 1.0
        )
    if "bet_surface_area_m2g" not in cand.columns:
        cand["bet_surface_area_m2g"] = np.nan

    num_c, cat_c = encoder.transform(cand)
    mean_cand, std_cand = predict(model, likelihood, num_c.numpy(), cat_c.numpy())

    # log-nm → nm 변환: 예측 범위를 사람이 읽을 수 있는 nm 단위로 표시
    if use_log:
        mean_nm        = np.exp(mean_cand)
        sigma_lower_nm = np.exp(mean_cand - std_cand)   # exp(μ - σ)
        sigma_upper_nm = np.exp(mean_cand + std_cand)   # exp(μ + σ)
    else:
        mean_nm        = mean_cand
        sigma_lower_nm = mean_cand - std_cand
        sigma_upper_nm = mean_cand + std_cand

    cand["uncertainty_sigma"]       = std_cand                          # log-space σ (정렬 기준)
    cand["predicted_mean_nm"]       = mean_nm                           # 예측 중앙값 (nm)
    cand["sigma_lower_nm"]          = sigma_lower_nm                    # 1σ 하한 (nm)
    cand["sigma_upper_nm"]          = sigma_upper_nm                    # 1σ 상한 (nm)
    cand["uncertainty_interval_nm"] = sigma_upper_nm - sigma_lower_nm  # 구간 폭 (nm)

    key_cols = ["uncertainty_sigma", "predicted_mean_nm",
                "sigma_lower_nm", "sigma_upper_nm", "uncertainty_interval_nm",
                "synthesis_method", "synthesis_temperature_c",
                "synthesis_time_h", "ph_synthesis", "mineralizer",
                "ce_precursor", "capping_agent"]
    key_cols = [c for c in key_cols if c in cand.columns]
    top = cand.nlargest(top_k, "uncertainty_sigma")[key_cols].reset_index(drop=True)

    print(f"\n[능동학습] 불확실성 상위 {top_k}개 제안:")
    print(top.to_string())

    path = os.path.join(MODEL_DIR, f"dkl_active_learning_{target}.csv")
    top.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  저장: {path}")
    return top


# ── 역설계: 목표 입자 크기 최적화 ─────────────────────────────────────────────
def inverse_design(model, likelihood, encoder: FeatureEncoder,
                   df: pd.DataFrame, target: str,
                   target_size_nm: float = 10.0,
                   n_cand: int = 5000, top_k: int = 5,
                   use_log: bool = True):
    """목표 크기에 가장 가까우면서 불확실성이 낮은 조건 탐색."""
    rng = np.random.default_rng(1)
    cand = pd.DataFrame(index=range(n_cand))

    for col in NUMERIC_FEATURES:
        vals = df[col].dropna()
        lo, hi = (vals.quantile(0.02), vals.quantile(0.98)) if len(vals) >= 5 else (0.0, 1.0)
        cand[col] = rng.uniform(lo, hi, n_cand)
    for col in CATEGORICAL_FEATURES:
        vals = df[col].replace("", np.nan).dropna().unique()
        cand[col] = rng.choice(vals, n_cand) if len(vals) > 0 else "unknown"

    for src, dst in [("synthesis_temperature_c","log_synth_temp"),
                     ("synthesis_time_h",        "log_synth_time"),
                     ("calcination_temperature_c","log_calc_temp")]:
        cand[dst] = np.log(cand[src].clip(lower=1))
    cand["thermal_budget"]      = cand["synthesis_temperature_c"] * cand["synthesis_time_h"]
    cand["calc_thermal_budget"] = cand["calcination_temperature_c"] * cand["calcination_time_h"]
    for bin_col, src_col in [("has_mineralizer","mineralizer"),
                               ("has_dopant","dopant"),
                               ("capping_present","capping_agent")]:
        cand[bin_col] = cand[src_col].apply(
            lambda x: 0.0 if pd.isna(x) or str(x).strip().lower() in ("none","unknown","") else 1.0
        )
    if "bet_surface_area_m2g" not in cand.columns:
        cand["bet_surface_area_m2g"] = np.nan

    num_c, cat_c = encoder.transform(cand)
    mean_log, std_log = predict(model, likelihood, num_c.numpy(), cat_c.numpy())
    mean_nm = np.exp(mean_log) if use_log else mean_log
    std_nm  = (np.exp(mean_log + std_log) - np.exp(mean_log)) if use_log else std_log

    # 점수 = 크기 근접도 * 불확실성 역수
    target_log = np.log(target_size_nm) if use_log else target_size_nm
    log_vals   = mean_log if use_log else mean_nm
    dist       = np.abs(log_vals - target_log)
    score      = 1.0 / (dist + 1e-3) / (std_log + 1e-3)

    cand["predicted_size_nm"]  = mean_nm
    cand["uncertainty_sigma"]  = std_nm
    cand["inv_design_score"]   = score

    top = cand.nlargest(top_k, "inv_design_score")[
        ["inv_design_score", "predicted_size_nm", "uncertainty_sigma",
         "synthesis_method", "synthesis_temperature_c", "synthesis_time_h",
         "mineralizer", "ce_precursor", "solvent", "ph_synthesis"]
    ].reset_index(drop=True)

    print(f"\n[역설계] 목표 {target_size_nm} nm 상위 {top_k}:")
    print(top.to_string())
    path = os.path.join(MODEL_DIR, f"dkl_inverse_design_{target}.csv")
    top.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  저장: {path}")
    return top


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target",   default=TARGET_COMPOSITE)
    parser.add_argument("--epochs",   type=int, default=150)
    parser.add_argument("--inducing", type=int, default=256)
    parser.add_argument("--batch",    type=int, default=256)
    parser.add_argument("--lr",       type=float, default=1e-3)
    parser.add_argument("--target-size", type=float, default=10.0,
                        help="역설계 목표 입자 크기(nm)")
    args = parser.parse_args()

    print("=" * 60)
    print("Deep Kernel Learning (DKL-GP) — Stage 3-c")
    print(f"  Target:  {args.target}")
    print(f"  Device:  {DEVICE}")
    print(f"  Epochs:  {args.epochs}  |  Inducing: {args.inducing}")
    print("=" * 60)

    df_raw = m12.load_data()
    df     = m12.preprocess(df_raw)
    if "confidence" in df.columns:
        df = df[df["confidence"].isin(["high", "medium", "unknown", ""])]

    sub = df.dropna(subset=[args.target]).copy()
    if len(sub) < 30:
        sys.exit(f"표본 부족: {len(sub)}행 — {args.target} 데이터가 충분하지 않습니다")

    print(f"\n학습 데이터: {len(sub):,}행  |  논문: {sub['doi'].nunique():,}편")

    use_log = args.target in _LOG_TARGETS
    y_raw   = sub[args.target].values.astype(float)
    y       = np.log(y_raw) if use_log else y_raw.copy()

    # 피처 인코딩
    encoder = FeatureEncoder(embed_dim=8)
    encoder.fit(sub)
    num_x, cat_x = encoder.transform(sub)
    num_np = num_x.numpy()
    cat_np = cat_x.numpy()

    # 논문 단위 train/val 분할
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    tr_idx, val_idx = next(gss.split(num_np, y, groups=sub["doi"]))
    print(f"  학습: {len(tr_idx):,}행  |  검증: {len(val_idx):,}행\n")

    # 학습
    model, likelihood, history = train_dkl(
        num_np[tr_idx], cat_np[tr_idx], y[tr_idx],
        num_np[val_idx], cat_np[val_idx], y[val_idx],
        cat_cardinalities=encoder.cat_cardinalities,
        n_inducing=args.inducing,
        n_epochs=args.epochs,
        batch_size=args.batch,
        lr=args.lr,
    )

    # 전체 집합 예측 — 시각화·능동학습·σ 통계용 (train 포함)
    mean_pred, std_pred = predict(model, likelihood, num_np, cat_np)

    # val set 예측 — 성능 지표용 (train 데이터 누출 방지)
    val_mean, val_std = predict(model, likelihood, num_np[val_idx], cat_np[val_idx])

    if use_log:
        mean_nm  = np.exp(mean_pred)
        std_nm   = np.exp(mean_pred + std_pred) - np.exp(mean_pred)
        # 지표: val set만
        val_nm   = np.exp(val_mean)
        mae_nm   = mean_absolute_error(y_raw[val_idx], val_nm)
        rmse_nm  = np.sqrt(mean_squared_error(y_raw[val_idx], val_nm))
        mdae_nm  = np.median(np.abs(y_raw[val_idx] - val_nm))
        r2_nm    = r2_score(y_raw[val_idx], val_nm)
        r2_log   = r2_score(y[val_idx], val_mean)
        # PICP: 90% 예측구간 포함률 (z=1.645 → 명목 90%), val set 기준
        lo_nm    = np.exp(val_mean - 1.645 * val_std)
        hi_nm    = np.exp(val_mean + 1.645 * val_std)
        picp_90  = np.mean((y_raw[val_idx] >= lo_nm) & (y_raw[val_idx] <= hi_nm))
        print(f"\n[val 평가 (n={len(val_idx)})]  log-R²={r2_log:.3f} | "
              f"nm-MAE={mae_nm:.2f}  RMSE={rmse_nm:.2f}  MdAE={mdae_nm:.2f}nm"
              f"  nm-R²={r2_nm:.3f}")
        print(f"  불확실성 캘리브레이션: PICP(90%)={picp_90:.3f}"
              f"  (이상적=0.900, >{0.900:.3f} → 과소추정, <{0.900:.3f} → 과대추정)")
    else:
        mean_nm  = mean_pred
        std_nm   = std_pred
        mae      = mean_absolute_error(y[val_idx], val_mean)
        rmse     = np.sqrt(mean_squared_error(y[val_idx], val_mean))
        mdae     = np.median(np.abs(y[val_idx] - val_mean))
        r2       = r2_score(y[val_idx], val_mean)
        lo       = val_mean - 1.645 * val_std
        hi       = val_mean + 1.645 * val_std
        picp_90  = np.mean((y[val_idx] >= lo) & (y[val_idx] <= hi))
        print(f"\n[val 평가 (n={len(val_idx)})]  MAE={mae:.4f}  RMSE={rmse:.4f}  MdAE={mdae:.4f}  R²={r2:.3f}")
        print(f"  불확실성 캘리브레이션: PICP(90%)={picp_90:.3f}")

    print(f"  불확실성 σ — median={np.median(std_nm):.2f}nm  "
          f"mean={np.mean(std_nm):.2f}nm  std={np.std(std_nm):.2f}nm")

    # 시각화
    plot_results(y_raw, mean_nm, std_nm, history, args.target)

    # 능동학습
    active_learning(model, likelihood, encoder, df, args.target, use_log=use_log)

    # 역설계
    inverse_design(model, likelihood, encoder, df, args.target,
                   target_size_nm=args.target_size, use_log=use_log)

    # 모델 저장
    model_path = os.path.join(MODEL_DIR, f"dkl_{args.target}.pt")
    torch.save({
        "model_state":       model.state_dict(),
        "likelihood_state":  likelihood.state_dict(),
        "cat_cardinalities": encoder.cat_cardinalities,
        "history":           history,
        "r2_log":            r2_log   if use_log else float("nan"),
        "mae_nm":            mae_nm   if use_log else float("nan"),
        "rmse_nm":           rmse_nm  if use_log else float("nan"),
        "mdae_nm":           mdae_nm  if use_log else float("nan"),
        "picp_90":           picp_90,
    }, model_path)
    enc_path = os.path.join(MODEL_DIR, f"dkl_encoder_{args.target}.pkl")
    with open(enc_path, "wb") as f:
        pickle.dump(encoder, f)

    print(f"\n모델 저장: {model_path}")
    print(f"인코더 저장: {enc_path}")

    # 성능 이력 저장 (performance_history.json)
    try:
        from datetime import datetime
        hist_path = os.path.join(MODEL_DIR, "performance_history.json")
        if os.path.exists(hist_path):
            with open(hist_path, "r", encoding="utf-8") as hf:
                ph = json.load(hf)
        else:
            ph = []
        today_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        today_date = today_str[:10]
        dkl_metrics = {
            "log_r2":  float(r2_log)  if use_log else None,
            "mae_nm":  float(mae_nm)  if use_log else None,
            "rmse_nm": float(rmse_nm) if use_log else None,
            "mdae_nm": float(mdae_nm) if use_log else None,
            "picp_90": float(picp_90),
            "n": int(len(df[df[args.target].notna()])) if args.target in df.columns else None,
        }
        # 오늘 날짜(auto) 항목 찾아 dkl_gp 필드 업데이트
        updated = False
        for entry in ph:
            if entry.get("run_date", "")[:10] == today_date and entry.get("session_label") == "auto":
                if entry.get("dkl_gp") is None:
                    entry["dkl_gp"] = {}
                entry["dkl_gp"][args.target] = dkl_metrics
                updated = True
                break
        if not updated:
            # 새 항목 추가
            ph.append({
                "session_label": "auto",
                "run_date": today_str,
                "n_samples": None,
                "n_papers": None,
                "n_features": None,
                "coverage_pct": None,
                "note": "DKL-GP auto-saved",
                "histgbm": None,
                "dkl_gp": {args.target: dkl_metrics},
                "lgbm": None,
                "catboost": None,
            })
        with open(hist_path, "w", encoding="utf-8") as hf:
            json.dump(ph, hf, ensure_ascii=False, indent=2)
        print(f"  성능 이력 저장: {hist_path}")
    except Exception as _he:
        print(f"  성능 이력 저장 실패(무시): {_he}")

    print("\n" + "=" * 60)
    print("완료. 결과 디렉토리:", MODEL_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
