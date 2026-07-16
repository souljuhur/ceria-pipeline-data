"""
test_normalize_rules.py — 34차 파이프라인 리뷰에서 발견된 회귀 테스트.

각 테스트는 실제로 재현했던 버그 사례를 고정한다. 여기 있는 케이스가 실패하면
같은 유형의 버그(단어경계 없는 접두사 매칭, 대소문자 무시로 인한 원소기호 충돌,
필드 전체에 걸친 `.*` 매칭, 영단어와 충돌하는 키워드)가 다시 들어온 것이다.

실행: python -m pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import normalize_rules as nr


# ── is_ce_compound ────────────────────────────────────────────────────────
class TestIsCeCompound:
    def test_rejects_cesium_chloride(self):
        assert nr.is_ce_compound("cesium chloride") is False

    def test_rejects_ctab(self):
        assert nr.is_ce_compound("cetyltrimethylammonium bromide") is False

    def test_rejects_cellulose_acetate(self):
        assert nr.is_ce_compound("cellulose acetate") is False

    def test_rejects_ceramic_or_generic_ce_word(self):
        # "ce"로 시작하지만 세륨과 무관한 일반 단어
        assert nr.is_ce_compound("ceramic support") is False

    def test_accepts_ceo2_formula(self):
        assert nr.is_ce_compound("CeO2") is True

    def test_accepts_ce_no3_3_formula(self):
        assert nr.is_ce_compound("Ce(NO3)3·6H2O") is True

    def test_accepts_cecl3_formula(self):
        assert nr.is_ce_compound("CeCl3·7H2O") is True

    def test_accepts_ammonium_ceric_nitrate_formula(self):
        assert nr.is_ce_compound("(NH4)2Ce(NO3)6") is True

    def test_accepts_cerium_word(self):
        assert nr.is_ce_compound("cerium nitrate") is True

    def test_accepts_ceric_ceroust_words(self):
        assert nr.is_ce_compound("cerous chloride") is True
        assert nr.is_ce_compound("ceric ammonium nitrate") is True

    def test_accepts_ce_embedded_in_mixed_oxide(self):
        # La0.5Ce0.5O2 처럼 Ce가 문자열 중간에 있는 경우
        assert nr.is_ce_compound("La0.5Ce0.5O2") is True

    def test_multivalue_field_any_token_matches(self):
        assert nr.is_ce_compound("La(NO3)3; Ce(NO3)3") is True

    def test_empty_and_na_values(self):
        assert nr.is_ce_compound(None) is False
        assert nr.is_ce_compound("") is False
        assert nr.is_ce_compound("nan") is False


# ── derive_anion ──────────────────────────────────────────────────────────
class TestDeriveAnion:
    def test_ammonium_ceric_nitrate_formula(self):
        assert nr.derive_anion("(NH4)2Ce(NO3)6") == "ammonium_nitrate"

    def test_plain_nitrate(self):
        assert nr.derive_anion("Ce(NO3)3·6H2O") == "nitrate"

    def test_chloride(self):
        assert nr.derive_anion("CeCl3·7H2O") == "chloride"

    def test_unrelated_multivalue_does_not_become_ammonium_nitrate(self):
        # 34차 버그: "NH4Cl; KNO3; Ce(SO4)2" — 서로 무관한 성분들이 한 셀에 있을 때
        # 예전 코드는 필드 전체에 .*로 매칭해 ammonium_nitrate로 잘못 분류했다.
        val = "NH4Cl; KNO3; Ce(SO4)2"
        assert nr.derive_anion(val) != "ammonium_nitrate"

    def test_none_and_empty(self):
        assert nr.derive_anion(None) is None
        assert nr.derive_anion("") is None

    def test_unrecognized_returns_other(self):
        assert nr.derive_anion("some unknown compound xyz") == "other"


# ── dopant_symbol_pattern (대소문자 보존 haystack에 case=True로 써야 함) ────
class TestDopantSymbolPattern:
    def _matches(self, symbol, text_cased):
        import re
        pat = nr.dopant_symbol_pattern(symbol)
        return bool(re.search(pat, text_cased))  # case=True와 동일 (IGNORECASE 없음)

    def test_co_element_doped_matches(self):
        assert self._matches("Co", "Co-doped CeO2 nanoparticles were synthesized.") is True

    def test_generic_co_doped_prefix_does_not_match_cobalt(self):
        # 34차 버그: "co-doped"(공동 도핑)가 코발트로 오인됨
        assert self._matches("Co", "co-doped CeO2 with Sm and Gd was prepared.") is False

    def test_in_element_doped_matches(self):
        assert self._matches("In", "In-doped ceria nanostructures were obtained.") is True

    def test_preposition_in_doped_does_not_match_indium(self):
        # 34차 버그: 전치사 "in" + "doped"가 인듐으로 오인됨
        text = "This trend leads in doped ceria nanoparticles synthesis discussions."
        assert self._matches("In", text) is False

    def test_ordinary_dopant_symbol_still_matches_case_insensitively_for_suffix(self):
        # "-doped"/"CeO2" 부분은 대소문자 무관해야 함 (원소기호만 대소문자 구분)
        assert self._matches("Sm", "Sm-Doped CEO2 samples") is True


# ── CE_PRECURSOR_FULLTEXT_KW ──────────────────────────────────────────────
class TestCePrecursorFulltextKeywords:
    def test_no_bare_can_keyword(self):
        # 34차 버그: " can " 키워드가 영어 조동사 "can"과 충돌
        for _label, kws in nr.CE_PRECURSOR_FULLTEXT_KW:
            assert " can " not in kws

    def test_ammonium_ceric_nitrate_still_matchable_without_can(self):
        kw_map = dict(nr.CE_PRECURSOR_FULLTEXT_KW)
        assert "(nh4)2ce(no3)6" in kw_map["(NH4)2Ce(NO3)6"]
        assert "ceric ammonium nitrate" in kw_map["(NH4)2Ce(NO3)6"]

    def test_ordinary_prose_with_can_does_not_trigger_any_precursor(self):
        text = "this method can produce highly uniform ceo2 nanoparticles with good yield"
        for _label, kws in nr.CE_PRECURSOR_FULLTEXT_KW:
            assert not any(kw in text for kw in kws)
