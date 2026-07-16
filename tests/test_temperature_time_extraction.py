"""
test_temperature_time_extraction.py — 34차: 건조/소성이 한 문장에 같이 나올 때
값이 바뀌어 들어가던 버그의 회귀 테스트.

실제 재현 문장: "The precipitate was dried at 80 C for 12 h and then calcined
at 500 C for 3 h." — 예전 코드는 calcination_temperature_c=80(건조값)을 넣고
drying 필드는 비워뒀다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.extract_ceria_rules import extract_temperatures, extract_times, split_into_clauses
from src.experiment_parser import extract_contextual_conditions, parse_experiment_block

DRY_THEN_CALCINE = (
    "The precipitate was dried at 80 C for 12 h and then calcined at 500 C for 3 h."
)


class TestSplitIntoClauses:
    def test_splits_on_and_then(self):
        clauses = split_into_clauses(DRY_THEN_CALCINE)
        assert len(clauses) == 2

    def test_single_clause_sentence_unchanged(self):
        sent = "The powder was calcined at 500 C for 3 h."
        assert split_into_clauses(sent) == [sent]


class TestExtractTemperatures:
    def test_dry_then_calcine_assigns_correct_temperatures(self):
        result = extract_temperatures(DRY_THEN_CALCINE)
        assert result["drying_temperature_c"] == 80.0
        assert result["calcination_temperature_c"] == 500.0

    def test_single_step_sentence_still_works(self):
        result = extract_temperatures("The gel was calcined at 500 C for 3 h.")
        assert result["calcination_temperature_c"] == 500.0
        assert result["drying_temperature_c"] is None


class TestExtractTimes:
    def test_dry_then_calcine_assigns_correct_times(self):
        result = extract_times(DRY_THEN_CALCINE)
        assert result["drying_time_h"] == 12.0
        assert result["calcination_time_h"] == 3.0

    def test_single_step_sentence_still_works(self):
        result = extract_times("The gel was calcined at 500 C for 3 h.")
        assert result["calcination_time_h"] == 3.0
        assert result["drying_time_h"] is None


class TestExtractContextualConditions:
    """experiment_parser.py의 중복 구현 — 같은 버그가 있었음."""

    def test_dry_then_calcine_assigns_correct_values(self):
        result = extract_contextual_conditions(DRY_THEN_CALCINE)
        assert result["drying_temperature_c"] == 80.0
        assert result["drying_time_h"] == 12.0
        assert result["calcination_temperature_c"] == 500.0
        assert result["calcination_time_h"] == 3.0


class TestParseExperimentBlockMergeOrder:
    """34차: result.update(cond)가 cond의 None으로 base의 올바른 값을 지워버리던 버그."""

    def test_base_value_not_erased_by_none_from_cond(self):
        result = parse_experiment_block(DRY_THEN_CALCINE)
        assert result["drying_temperature_c"] == 80.0
        assert result["calcination_temperature_c"] == 500.0
        assert result["drying_time_h"] == 12.0
        assert result["calcination_time_h"] == 3.0
