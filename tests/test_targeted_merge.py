"""
test_targeted_merge.py — 35차: 4_extract_targeted.py의 재추출 결과가 이미 값이
있는 필드엔 반영되지 않던 버그의 회귀 테스트.

발견 경위: targeted_extraction_cache.json에는 정확한 값(예: "Ce(acac)3")이
있는데 실제 ceria_samples_merged.csv에는 다른(부정확한) 값이 남아있는 행이
1,725개 발견됨 — `--reset`으로 재추출해도 캐시만 새로워지고 CSV의 기존 값은
필드가 "비어있지 않으면" 절대 덮어써지지 않는 구조였다.
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "m4", os.path.join(os.path.dirname(__file__), "..", "4_extract_targeted.py"))
m4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m4)


def _df(rows):
    return pd.DataFrame(rows)


class TestApplyTargetedResults:
    def test_overwrites_existing_incorrect_value(self):
        df = _df([{"doi": "d1", "ce_precursor": "Ce(CH3CO)3", "solvent": "water"}])
        all_results = {"d1": {"ce_precursor": "Ce(acac)3", "solvent": "water"}}
        updated = m4.apply_targeted_results(df, all_results, ["ce_precursor", "solvent"])
        assert df.loc[0, "ce_precursor"] == "Ce(acac)3"
        assert updated["ce_precursor"] == 1
        assert updated["solvent"] == 0  # 값이 같으면 변경 카운트 0

    def test_fills_empty_field(self):
        df = _df([{"doi": "d1", "ce_precursor": None}])
        all_results = {"d1": {"ce_precursor": "Ce(NO3)3·6H2O"}}
        m4.apply_targeted_results(df, all_results, ["ce_precursor"])
        assert df.loc[0, "ce_precursor"] == "Ce(NO3)3·6H2O"

    def test_none_result_value_does_not_erase_existing(self):
        df = _df([{"doi": "d1", "ce_precursor": "Ce(NO3)3·6H2O"}])
        all_results = {"d1": {"ce_precursor": None}}
        m4.apply_targeted_results(df, all_results, ["ce_precursor"])
        assert df.loc[0, "ce_precursor"] == "Ce(NO3)3·6H2O"

    def test_only_matching_doi_rows_updated(self):
        df = _df([
            {"doi": "d1", "ce_precursor": "old"},
            {"doi": "d2", "ce_precursor": "old"},
        ])
        all_results = {"d1": {"ce_precursor": "new"}}
        m4.apply_targeted_results(df, all_results, ["ce_precursor"])
        assert df.loc[df["doi"] == "d1", "ce_precursor"].iloc[0] == "new"
        assert df.loc[df["doi"] == "d2", "ce_precursor"].iloc[0] == "old"
