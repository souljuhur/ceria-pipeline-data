"""ML 결과 빠른 확인 스크립트"""
import os, sys
import pandas as pd
import numpy as np

BASE = r"d:\머신러닝 교육\ceria_pipeline_data"
LOG  = os.path.join(BASE, "output", "ml_check.txt")

lines = []
def log(s=""):
    print(s)
    lines.append(s)

# 1. CSV 현황
csv = os.path.join(BASE, "output", "ceria_samples_merged.csv")
df = pd.read_csv(csv, low_memory=False)
log(f"CSV 행수: {len(df):,}")
log(f"논문수: {df['doi'].nunique():,}")

prim = "particle_size_primary_nm"
if prim in df.columns:
    vals = pd.to_numeric(df[prim], errors="coerce")
    n_valid = vals.notna().sum()
    log(f"\nparticle_size_primary_nm 유효값: {n_valid:,}행 ({n_valid/len(df)*100:.1f}%)")
else:
    log(f"\n{prim} 컬럼 없음!")

# 2. 모델 파일 목록
model_dir = os.path.join(BASE, "output", "model")
files = sorted(os.listdir(model_dir))
log(f"\n모델 파일 ({len(files)}개):")
for f in files:
    fpath = os.path.join(model_dir, f)
    mtime = os.path.getmtime(fpath)
    import datetime
    dt = datetime.datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
    log(f"  {dt}  {f}")

# 3. active_learning_size_histgbm.csv 존재 여부
al_size = os.path.join(model_dir, "active_learning_size_histgbm.csv")
if os.path.exists(al_size):
    log(f"\nactive_learning_size_histgbm.csv 존재!")
    log(pd.read_csv(al_size).to_string())
else:
    log(f"\nactive_learning_size_histgbm.csv 없음")

# 4. 로그 저장
with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
log(f"\n로그 저장: {LOG}")
