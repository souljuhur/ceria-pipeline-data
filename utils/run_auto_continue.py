"""
run_auto_continue.py — 다운로드 완료 감지 후 자동 파이프라인 이어달리기

동작:
  1. 1_download.py 완료 감지 (noa_download_cache.json 모니터링)
  2. 2_extract.py          — 새 전문에서 합성조건 추출
  3. 3_merge.py            — 샘플 + 논문 데이터 병합
  4. 6_fill_keywords.py    — 키워드 보완
  5. 7_calc_completeness.py — 완성도 계산
  6. 8_normalize_data.py   — 정규화
  7. 9_add_tags.py         — 태그 추가
  8. 10_build_dataset.py   — JSONL 생성
  9. 12_model.py           — ML 모델 재학습
  10. 11_format_excel.py   — Excel 서식 갱신

실행:  python utils/run_auto_continue.py
       (새 CMD 창에서 1_download.py와 동시에 실행)

권장: 체크포인트/재시작 지원 → python main.py --from 2
"""
import json, subprocess, sys, time, logging
from datetime import datetime
from pathlib import Path

BASE   = Path(r"d:\머신러닝 교육\ceria_pipeline_data")
OUTPUT = BASE / "output"
CACHE  = OUTPUT / "noa_download_cache.json"
LOGS   = OUTPUT / "logs"
# 현재 실행 중인 Python(conda test 환경)을 그대로 사용
PYTHON = sys.executable

# ── 로깅 ─────────────────────────────────────────────────────────────────────
LOGS.mkdir(parents=True, exist_ok=True)
_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_log = LOGS / f"auto_continue_{_ts}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        logging.FileHandler(_log, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── 완료 감지 ─────────────────────────────────────────────────────────────────
STABLE_SECONDS = 90   # N초 동안 done_dois 수가 변하지 않으면 완료로 판단
CHECK_INTERVAL = 15   # 확인 주기 (초)

def wait_for_download():
    log.info("=" * 60)
    log.info("run_download_noa.py 완료 대기 중...")
    log.info(f"  감지 조건: done_dois 수가 {STABLE_SECONDS}초 이상 변화 없으면 완료")
    log.info("=" * 60)

    prev_count = -1
    stable_since = None

    while True:
        if not CACHE.exists():
            log.info("  캐시 파일 없음 — 다운로드 시작 전이거나 이미 완료됨")
            time.sleep(CHECK_INTERVAL)
            continue

        try:
            with open(CACHE, encoding="utf-8") as f:
                data = json.load(f)
            done  = len(data.get("done_dois", []))
            pmc   = data.get("pmc_ok", 0)
            sh    = data.get("scihub_ok", 0)
        except Exception:
            time.sleep(CHECK_INTERVAL)
            continue

        now = datetime.now()

        if done != prev_count:
            prev_count  = done
            stable_since = now
            log.info(f"  진행 중: done={done:,}편  PMC={pmc}  Sci-Hub={sh}")
        else:
            elapsed = (now - stable_since).seconds if stable_since else 0
            remaining = max(0, STABLE_SECONDS - elapsed)
            log.info(f"  변화 없음: {elapsed}초 경과 (완료 판정까지 {remaining}초 남음) "
                     f"| done={done:,}  PMC={pmc}  Sci-Hub={sh}")
            if elapsed >= STABLE_SECONDS:
                log.info(f"\n완료 감지! PMC={pmc}편, Sci-Hub={sh}편 수집됨")
                return done, pmc, sh

        time.sleep(CHECK_INTERVAL)


# ── 스크립트 실행 ─────────────────────────────────────────────────────────────
def run_script(script: str, *args, timeout: int = 3600) -> bool:
    label = f"{script} {' '.join(args)}".strip()
    log.info(f"\n{'─'*50}")
    log.info(f"실행: {label}")
    log.info(f"{'─'*50}")

    cmd = [PYTHON, str(BASE / script)] + list(args)
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    try:
        # 실시간 출력: Popen으로 한 줄씩 읽어서 즉시 표시
        proc = subprocess.Popen(
            cmd, cwd=str(BASE), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        deadline = __import__("time").time() + timeout
        while True:
            line = proc.stdout.readline()
            if line:
                log.info(f"  {line.rstrip()}")
            elif proc.poll() is not None:
                break
            if __import__("time").time() > deadline:
                proc.kill()
                log.warning(f"  ✗ 타임아웃 ({timeout//60}분 초과)")
                return False
        returncode = proc.wait()
        if returncode != 0:
            log.warning(f"  ✗ 실패 (returncode={returncode})")
            return False
        log.info(f"  ✓ 완료")
        return True
    except Exception as e:
        log.warning(f"  ✗ 오류: {e}")
        return False


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info(f"자동 이어달리기 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)

    # 1. 다운로드 완료 대기
    done_count, pmc_ok, sh_ok = wait_for_download()

    if pmc_ok + sh_ok == 0:
        log.info("\n새로 수집된 전문이 없어 파이프라인을 건너뜁니다.")
        log.info("(이미 모든 논문이 처리됐거나 수집에 실패했습니다)")
    else:
        log.info(f"\n새 전문 {pmc_ok + sh_ok}편 수집됨 → 파이프라인 시작")

    # 2. 후속 파이프라인 (새 전문 없어도 실행 — DB 업데이트 반영)
    steps = [
        ("2_extract.py",            [], 21600,
         "새 전문에서 GPT로 합성조건 추출 (~6시간)"),
        ("3_merge.py",              [], 600,
         "샘플 CSV + 논문 Excel 병합"),
        ("6_fill_keywords.py",      [], 600,
         "키워드 기반 빈 필드 보완"),
        ("7_calc_completeness.py",  [], 600,
         "완성도 점수 계산"),
        ("8_normalize_data.py",     [], 300,
         "데이터 정규화 + 파생 피처"),
        ("9_add_tags.py",           [], 300,
         "OA/방법/형태 태그 추가"),
        ("10_build_dataset.py",     [], 600,
         "JSONL 데이터셋 생성"),
        ("12_model.py",             [], 1800,
         "ML 모델 재학습"),
        ("11_format_excel.py",      [], 600,
         "Excel 서식 갱신"),
    ]

    results = {}
    for script, args, timeout, desc in steps:
        log.info(f"\n[{desc}]")
        ok = run_script(script, *args, timeout=timeout)
        results[script] = ok
        if not ok:
            log.warning(f"  → 실패했지만 다음 단계 계속 진행")

    # 3. 최종 요약
    log.info(f"\n{'='*60}")
    log.info("전체 파이프라인 완료 요약")
    log.info(f"{'='*60}")
    for script, ok in results.items():
        status = "✓ 성공" if ok else "✗ 실패"
        log.info(f"  {status}  {script}")
    log.info(f"\n로그: {_log}")
    log.info(f"대시보드 새로고침 버튼을 눌러 결과를 확인하세요.")


if __name__ == "__main__":
    main()
