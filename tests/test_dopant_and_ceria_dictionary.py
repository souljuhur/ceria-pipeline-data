"""
test_dopant_and_ceria_dictionary.py — 35차 백로그 항목: dopant_dictionary.py의
canonical_name이 실제 매칭된 음이온과 무관하게 고정돼 있던 문제, ceria_dictionary.py의
"ceric nitrate"(Ce4+)가 "cerium nitrate hexahydrate"(Ce3+)와 같은 canonical로
묶여 있던 문제의 회귀 테스트.

주의: src/experiment_parser.py, src/ceria_dictionary.py는 35차에 확인된 대로
현재 파이프라인 어디서도 호출되지 않는 죽은 코드 — 이 테스트는 향후 재사용/부활
시를 대비한 안전망이지 실 데이터에 영향을 주지 않는다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.experiment_parser import extract_dopants
from src.quantity_extractor import extract_chemical_spans


class TestDopantCanonicalName:
    def test_oxide_reported_as_oxide_not_nitrate(self):
        result = extract_dopants("Gadolinium oxide (Gd2O3, 99.9%) was used as the dopant source.")
        assert result["dopant_precursors"] == "gadolinium oxide"

    def test_chloride_reported_as_chloride(self):
        result = extract_dopants("Samarium chloride was dissolved along with the cerium precursor.")
        assert result["dopant_precursors"] == "samarium chloride"

    def test_formula_match_still_reports_nitrate(self):
        result = extract_dopants("Gd(NO3)3 was added dropwise to the cerium nitrate solution.")
        assert result["dopant_precursors"] == "gadolinium nitrate"


class TestCericNitrateVsCeriumNitrate:
    def test_ceric_nitrate_is_ce4_not_hexahydrate(self):
        spans = extract_chemical_spans("Ceric nitrate was dissolved in dilute nitric acid.")
        names = [s["canonical_name"] for s in spans] if spans else []
        assert "Ce(NO3)4" in names
        assert "Ce(NO3)3·6H2O" not in names

    def test_cerium_nitrate_hexahydrate_unaffected(self):
        spans = extract_chemical_spans("Cerium nitrate hexahydrate was used as the Ce source.")
        names = [s["canonical_name"] for s in spans] if spans else []
        assert "Ce(NO3)3·6H2O" in names
