"""
main.py — CeO2 합성 파이프라인 마스터 실행기
=============================================

5단계 파이프라인 (번호 순서대로 실행):

  [Stage 0] 문헌 수집 업그레이드 (선택 — 신규 수집 시에만)
    0_collect.py          — OpenAlex 다층 쿼리 수집 (커서 페이지네이션, 초록·태그 포함)

  [Stage 1] 논문 수집
    1_download.py          — 비-OA PDF 다운로드 (PMC + Sci-Hub)

  [Stage 2] 데이터 추출
    2_extract.py           — GPT-4o-mini 합성조건 추출
    3_merge.py             — 샘플 CSV + 논문 Excel 병합
    4_extract_targeted.py  — 핵심 3필드 집중 재추출 (합성법/전구체/용매)
    5_table_extract.py     — 표/그림 기반 입자크기 보완

  [Stage 3] 후처리 + 출력
    6_fill_keywords.py     — 키워드 기반 빈 필드 보완
    7_calc_completeness.py — 완성도 점수 계산
    8_normalize_data.py    — 데이터 정규화 + 파생 피처 생성
    9_add_tags.py          — OA/방법/형태 태그 추가
    10_build_dataset.py    — ML 데이터셋 JSONL 생성
    11_format_excel.py     — 서식 Excel 생성

  [Stage 4] ML 학습 + 역설계
    12_model.py            — 입자크기 예측 모델 + 역설계 + 능동학습

  대시보드: python main.py --dashboard  (13_dashboard.py 실행)

사용법 (CMD에서 실행):
  python main.py                    전체 실행 (완료된 단계 자동 건너뜀)
  python main.py --stage 2          2단계만 실행
  python main.py --from 3           3단계부터 끝까지
  python main.py --reset            체크포인트 초기화 후 전체 재실행
  python main.py --reset --stage 2  2단계만 강제 재실행
  python main.py --status           현재 진행 상황 확인
  python main.py --dashboard        Streamlit 대시보드 실행

체크포인트: output/pipeline_state.json
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
BASE       = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE, "output")
STATE_FILE = os.path.join(OUTPUT_DIR, "pipeline_state.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _env():
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _count_pdfs():
    pdf_dir = os.path.join(BASE, "pdf")
    if not os.path.isdir(pdf_dir):
        return 0
    return sum(1 for f in os.listdir(pdf_dir) if f.endswith(".pdf"))


def _out(*parts):
    return os.path.exists(os.path.join(OUTPUT_DIR, *parts))


# ── 4단계 정의 ─────────────────────────────────────────────────────────────────
STAGES = [
    # ──────────────────────────────────────────────────────────────────────────
    {
        "num" : 1,
        "name": "논문 수집 + PDF 다운로드",
        "desc": "비-OA 전문(PMC/Sci-Hub) 다운로드",
        "steps": [
            {
                "id"    : "download",
                "script": "1_download.py",
                "args"  : ["--scihub"],
                "desc"  : "1_download.py  — 비-OA PDF 다운로드 (PMC + Sci-Hub)",
                "done_check": lambda: _count_pdfs() > 3000,
            },
        ],
        "done_check": lambda: (
            _out("ceria_synthesis_database.xlsx") and _count_pdfs() > 3000
        ),
        "output": "pdf/ (3,000편+), text/",
    },
    # ──────────────────────────────────────────────────────────────────────────
    {
        "num" : 2,
        "name": "데이터 추출",
        "desc": "GPT 추출 → 병합 → 재추출 → 표추출",
        "steps": [
            {
                "id"    : "extract",
                "script": "2_extract.py",
                "args"  : [],
                "desc"  : "2_extract.py  — GPT-4o-mini 합성조건 추출 (~6시간, ~$1.60)",
                "done_check": lambda: _out("ceria_samples.jsonl"),
            },
            {
                "id"    : "merge",
                "script": "3_merge.py",
                "args"  : [],
                "desc"  : "3_merge.py  — 샘플 + 논문 데이터 병합",
                "done_check": lambda: _out("ceria_samples_merged.csv"),
            },
            {
                "id"    : "extract_targeted",
                "script": "4_extract_targeted.py",
                "args"  : [],
                "desc"  : "4_extract_targeted.py  — 핵심 3필드 집중 재추출 (~$0.50)",
                "done_check": lambda: _out("targeted_extraction_cache.json"),
            },
            {
                "id"    : "table_extract",
                "script": "5_table_extract.py",
                "args"  : [],
                "desc"  : "5_table_extract.py  — 표/그림 기반 입자크기 보완",
                "done_check": lambda: _out("table_extraction_cache.json"),
            },
        ],
        "done_check": lambda: (
            _out("ceria_samples_merged.csv")
            and _out("table_extraction_cache.json")
        ),
        "output": "output/ceria_samples_merged.csv (composite 57%+)",
    },
    # ──────────────────────────────────────────────────────────────────────────
    {
        "num" : 3,
        "name": "후처리 + 출력",
        "desc": "키워드보완 → 완성도 → 정규화 → 태그 → JSONL → Excel",
        "steps": [
            {
                "id"    : "fill_keywords",
                "script": "6_fill_keywords.py",
                "args"  : [],
                "desc"  : "6_fill_keywords.py  — 키워드 기반 빈 필드 보완",
            },
            {
                "id"    : "calc_completeness",
                "script": "7_calc_completeness.py",
                "args"  : [],
                "desc"  : "7_calc_completeness.py  — 완성도 점수 계산",
            },
            {
                "id"    : "normalize_data",
                "script": "8_normalize_data.py",
                "args"  : [],
                "desc"  : "8_normalize_data.py  — 데이터 정규화 + 파생 피처",
            },
            {
                "id"    : "add_tags",
                "script": "9_add_tags.py",
                "args"  : [],
                "desc"  : "9_add_tags.py  — OA/방법/형태 태그 추가",
            },
            {
                "id"    : "build_dataset",
                "script": "10_build_dataset.py",
                "args"  : [],
                "desc"  : "10_build_dataset.py  — ML 데이터셋 JSONL 생성",
                "done_check": lambda: _out("ceria_dataset_quality.jsonl"),
            },
            {
                "id"    : "format_excel",
                "script": "11_format_excel.py",
                "args"  : [],
                "desc"  : "11_format_excel.py  — 서식 Excel 생성",
                "done_check": lambda: _out("ceria_synthesis_database_display.xlsx"),
            },
        ],
        "done_check": lambda: (
            _out("ceria_dataset_quality.jsonl")
            and _out("ceria_synthesis_database_display.xlsx")
        ),
        "output": "output/ceria_dataset_quality.jsonl + _display.xlsx",
    },
    # ──────────────────────────────────────────────────────────────────────────
    {
        "num" : 4,
        "name": "ML 학습 + 역설계",
        "desc": "입자크기 예측 모델 훈련 + 역설계 + 능동학습",
        "steps": [
            {
                "id"    : "ml_model",
                "script": "12_model.py",
                "args"  : [],
                "desc"  : "12_model.py  — ML 모델 학습 + 역설계 + 능동학습",
                "done_check": lambda: _out(
                    "model", "model_particle_size_primary_nm_reg.pkl"),
            },
        ],
        "done_check": lambda: _out(
            "model", "model_particle_size_primary_nm_reg.pkl"),
        "output": "output/model/*.pkl + importance_*.png + inverse_design_*.csv",
    },
]


# ── 체크포인트 ─────────────────────────────────────────────────────────────────
def _load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _step_done(state, stage_num, step_id):
    return (state.get(f"stage{stage_num}", {})
                 .get("steps", {})
                 .get(step_id, {})
                 .get("status") == "done")


def _mark_step_done(state, stage_num, step_id):
    key = f"stage{stage_num}"
    if key not in state:
        state[key] = {"status": "partial", "steps": {}}
    state[key].setdefault("steps", {})[step_id] = {
        "status": "done", "completed_at": _now()
    }
    _save_state(state)


def _mark_stage_done(state, stage_num):
    key = f"stage{stage_num}"
    state.setdefault(key, {}).update({"status": "done", "completed_at": _now()})
    _save_state(state)


def _reset_stage(state, stage_num):
    state[f"stage{stage_num}"] = {"status": "pending", "steps": {}}
    _save_state(state)


def _stage_status(stage, state):
    key = f"stage{stage['num']}"
    if state.get(key, {}).get("status") == "done":
        return "done"
    try:
        if stage["done_check"]():
            return "done"
    except Exception:
        pass
    steps = state.get(key, {}).get("steps", {})
    if any(v.get("status") == "done" for v in steps.values()):
        return "partial"
    return "pending"


# ── 상태 출력 ──────────────────────────────────────────────────────────────────
ICON  = {"done": "✓", "partial": "◑", "pending": "○", "failed": "✗"}
LABEL = {"done": "완료", "partial": "진행중", "pending": "대기", "failed": "실패"}


def print_status():
    state = _load_state()
    print("\n" + "=" * 65)
    print("  CeO2 파이프라인 진행 현황")
    print("=" * 65)

    for stage in STAGES:
        st    = _stage_status(stage, state)
        print(f"\n  {ICON[st]} [Stage {stage['num']}] {stage['name']}  ({LABEL[st]})")
        print(f"     {stage['desc']}")

        stage_state = state.get(f"stage{stage['num']}", {})
        step_states = stage_state.get("steps", {})
        for step in stage["steps"]:
            if step_states.get(step["id"], {}).get("status") == "done":
                s_icon = "✓"
            else:
                try:
                    s_icon = "✓" if step.get("done_check", lambda: False)() else "○"
                except Exception:
                    s_icon = "○"
            print(f"       {s_icon} {step['desc']}")

        print(f"     출력: {stage['output']}")

    done_count = sum(1 for s in STAGES if _stage_status(s, state) == "done")
    print(f"\n  진행률: {done_count}/{len(STAGES)} 단계 완료")

    pending = [s for s in STAGES if _stage_status(s, state) != "done"]
    if pending:
        n = pending[0]["num"]
        if n == 4 and _stage_status(STAGES[2], state) == "done":
            print(f"\n  다음: python main.py --stage 4")
        else:
            print(f"\n  다음: python main.py --from {n}")
    else:
        print("\n  모든 단계 완료! python main.py --dashboard 로 결과 확인")

    print("=" * 65 + "\n")


# ── 단계 실행 ──────────────────────────────────────────────────────────────────
def _run_script(script, args=None):
    cmd = [sys.executable, os.path.join(BASE, script)] + (args or [])
    return subprocess.run(cmd, cwd=BASE, env=_env()).returncode


def run_stage(stage, state, force=False):
    num  = stage["num"]
    name = stage["name"]

    print(f"\n{'='*65}")
    print(f"  [Stage {num}] {name}")
    print(f"  {stage['desc']}")
    print(f"{'='*65}")

    all_ok = True
    for step in stage["steps"]:
        sid = step["id"]

        already_done = False
        if not force:
            if _step_done(state, num, sid):
                already_done = True
            else:
                try:
                    already_done = step.get("done_check", lambda: False)()
                except Exception:
                    already_done = False

        if already_done:
            print(f"\n  ✓ (완료됨) {step['desc']}")
            continue

        args_str = " ".join(step.get("args", []))
        print(f"\n  ▶ {step['desc']}" + (f"  [{args_str}]" if args_str else ""))
        print(f"  {'-'*55}")

        t0 = time.time()
        rc = _run_script(step["script"], step.get("args", []))
        elapsed = time.time() - t0

        if rc != 0:
            print(f"\n  ✗ 실패: {step['script']} (종료코드 {rc}, {elapsed:.0f}초)")
            print(f"    재시작: python main.py --from {num}")
            all_ok = False
            break

        print(f"\n  ✓ 완료 ({elapsed:.0f}초)")
        _mark_step_done(state, num, sid)

    if all_ok:
        _mark_stage_done(state, num)
        print(f"\n  [Stage {num}] 완료!\n")

    return all_ok


# ── 메인 ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="CeO2 합성 파이프라인 마스터 실행기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--stage",     type=int,
                        help="특정 단계만 실행 (1-4)")
    parser.add_argument("--from",      type=int, dest="from_stage",
                        help="해당 단계부터 끝까지 실행")
    parser.add_argument("--reset",     action="store_true",
                        help="체크포인트 초기화 (--stage와 함께 쓰면 해당 단계만)")
    parser.add_argument("--status",    action="store_true",
                        help="진행 상황만 출력")
    parser.add_argument("--dashboard", action="store_true",
                        help="Streamlit 대시보드 실행 (13_dashboard.py)")
    args = parser.parse_args()

    if args.dashboard:
        print("Streamlit 대시보드를 시작합니다 (http://localhost:8501)")
        print("종료: Ctrl+C\n")
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run",
             os.path.join(BASE, "13_dashboard.py")],
            cwd=BASE, env=_env(),
        )
        return

    if args.status:
        print_status()
        return

    state = _load_state()

    if args.reset:
        if args.stage:
            print(f"Stage {args.stage} 체크포인트를 초기화합니다.")
            _reset_stage(state, args.stage)
        else:
            print("모든 체크포인트를 초기화합니다.")
            state = {}
            _save_state(state)

    if args.stage:
        target_stages = [s for s in STAGES if s["num"] == args.stage]
    elif args.from_stage:
        target_stages = [s for s in STAGES if s["num"] >= args.from_stage]
    else:
        target_stages = STAGES

    if not target_stages:
        print("유효하지 않은 단계 번호입니다. (1~4)")
        sys.exit(1)

    print(f"\n{'='*65}")
    print(f"  CeO2 합성 파이프라인  —  {_now()}")
    print(f"{'='*65}")

    success = True
    for stage in target_stages:
        st    = _stage_status(stage, state)
        force = args.reset and (args.stage is None or stage["num"] == args.stage)

        if st == "done" and not force:
            print(f"\n  ✓ [Stage {stage['num']}] {stage['name']} — 이미 완료")
            continue

        ok = run_stage(stage, state, force=force)
        if not ok:
            success = False
            print(f"\n파이프라인이 Stage {stage['num']}에서 중단됐습니다.")
            print(f"재시작: python main.py --from {stage['num']}")
            break

    if success:
        print(f"\n{'='*65}")
        print("  파이프라인 완료!")
        print("  대시보드: python main.py --dashboard")
        print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
