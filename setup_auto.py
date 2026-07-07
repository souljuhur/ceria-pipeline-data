"""
setup_auto.py — Windows Task Scheduler에 월간 자동화 등록

실행:
    conda activate test
    python setup_auto.py            # 등록
    python setup_auto.py --remove   # 제거
    python setup_auto.py --status   # 상태 확인

일정: 매월 1일 09:00 (2026-08-01부터 시작)
"""
import subprocess
import sys
import os
import argparse

TASK_NAME   = "CeriaPipelineMonthly"
BASE_DIR    = r"d:\머신러닝 교육\ceria_pipeline_data"
PYTHON_EXE  = sys.executable
if r"envs\test" not in PYTHON_EXE and "envs/test" not in PYTHON_EXE:
    raise SystemExit(
        f"잘못된 Python 환경: {PYTHON_EXE}\n"
        "'conda activate test' 후 다시 실행하세요."
    )
SCRIPT      = os.path.join(BASE_DIR, "run_weekly.py")
LOG_DIR     = os.path.join(BASE_DIR, "output", "logs")

# 매월 1일 09:00, 2026-08-01부터 시작
SCHEDULE    = "MONTHLY"
DAY         = "1"        # 매월 1일
START_TIME  = "09:00"
START_DATE  = "2026/08/01"   # yyyy/mm/dd (한국어 Windows schtasks 형식)


def run(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="cp949", errors="replace")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if check and result.returncode != 0:
        sys.exit(1)
    return result


def register():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, "monthly_scheduler.log")

    action_cmd = f'"{PYTHON_EXE}" "{SCRIPT}" >> "{log_file}" 2>&1'

    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", action_cmd,
        "/SC", SCHEDULE,
        "/D",  DAY,
        "/ST", START_TIME,
        "/SD", START_DATE,
        "/F",   # 기존 있으면 덮어쓰기
    ]

    print(f"[등록] Task: {TASK_NAME}")
    print(f"  스크립트: {SCRIPT}")
    print(f"  일정: 매월 {DAY}일 {START_TIME}  (시작일: {START_DATE})")
    run(cmd)
    print("등록 완료.")


def remove():
    # 구 이름(CeriaPipelineWeekly)도 함께 제거
    for name in [TASK_NAME, "CeriaPipelineWeekly"]:
        r = run(["schtasks", "/Delete", "/TN", name, "/F"], check=False)
        if r.returncode == 0:
            print(f"  제거됨: {name}")


def status():
    for name in [TASK_NAME, "CeriaPipelineWeekly"]:
        cmd = ["schtasks", "/Query", "/TN", name, "/FO", "LIST"]
        result = run(cmd, check=False)
        if result.returncode != 0:
            print(f"  등록 안 됨: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task Scheduler 월간 등록/제거/상태 확인")
    parser.add_argument("--remove", action="store_true", help="작업 제거")
    parser.add_argument("--status", action="store_true", help="상태 확인")
    args = parser.parse_args()

    if args.remove:
        remove()
    elif args.status:
        status()
    else:
        register()
