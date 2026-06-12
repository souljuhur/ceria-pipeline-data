"""임시 — 12_model.py 실행 + 결과 로그 저장"""
import subprocess, sys, os

BASE = r"d:\머신러닝 교육\ceria_pipeline_data"
LOG  = r"d:\머신러닝 교육\ceria_pipeline_data\output\ml_run_log.txt"
env  = {**os.environ, "PYTHONIOENCODING": "utf-8"}

result = subprocess.run(
    [sys.executable, "12_model.py"],
    cwd=BASE, env=env,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)

with open(LOG, "w", encoding="utf-8") as f:
    f.write(result.stdout)
    if result.stderr:
        f.write("\n--- STDERR ---\n")
        f.write(result.stderr)

print(f"exit code: {result.returncode}")
print(f"log: {LOG}")
# Print last 50 lines of stdout
lines = result.stdout.splitlines()
print("\n".join(lines[-80:]))
sys.exit(result.returncode)
