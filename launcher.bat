@echo off
title CeO2 Pipeline Launcher
cd /d "d:\머신러닝 교육\ceria_pipeline_data"
call conda activate test

echo.
echo ============================================================
echo   CeO2 합성 파이프라인 실행기
echo ============================================================
echo.
echo  [1] 전체 파이프라인 실행 (main.py)
echo  [2] 대시보드 열기 (Streamlit)
echo  [3] ML 모델 학습 (HistGBM + LightGBM + CatBoost)
echo  [4] DKL-GP 학습 (12c_gpr_model.py)
echo  [5] 상태 확인 (main.py --status)
echo  [6] 종료
echo.
set /p choice="선택 (1-6): "

if "%choice%"=="1" (
    echo 전체 파이프라인 실행 중...
    python main.py
) else if "%choice%"=="2" (
    echo 대시보드 시작: http://localhost:8501
    streamlit run 13_dashboard.py
) else if "%choice%"=="3" (
    echo ML 모델 학습 중...
    python 12_model.py
    python 12b_lgbm_baseline.py
    python 12d_catboost_model.py
) else if "%choice%"=="4" (
    echo DKL-GP 학습 중 (약 10분 소요)...
    python 12c_gpr_model.py --target particle_size_primary_nm --inducing 512 --epochs 300
) else if "%choice%"=="5" (
    python main.py --status
) else if "%choice%"=="6" (
    exit
) else (
    echo 잘못된 선택입니다.
)

pause
