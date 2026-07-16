@echo off
title CeO2 대시보드
cd /d "d:\머신러닝 교육\ceria_pipeline_data"
call conda activate test
echo 대시보드 시작 중... 브라우저가 자동으로 열립니다 (http://localhost:8501)
streamlit run 13_dashboard.py
pause
