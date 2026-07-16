"""
test_filter_offtopic_papers.py — 34차: CERIA_META/CERIA_PRECURSOR에 ceric/cerous
표기가 빠져 있던 문제의 회귀 테스트. 단어경계 없이 추가했다가 "glyceric acid"
같은 무관 단어의 부분문자열까지 잡히는 걸 실제 백업 데이터로 확인했었다
(교훈: 이 리뷰의 주제였던 버그를 고치다가 똑같은 실수를 할 뻔함).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filter_offtopic_papers import CERIA_META, CERIA_PRECURSOR


class TestCeriaMeta:
    def test_recognizes_ceric_word(self):
        assert CERIA_META.search("Ceric ammonium nitrate was used as an oxidant.")

    def test_recognizes_cerous_word(self):
        assert CERIA_META.search("Cerous chloride was dissolved in deionized water.")

    def test_does_not_false_trigger_on_glyceric_acid(self):
        # 34차에서 실제로 잡혔던 오탐 — "ceric"이 "glyceric"의 부분문자열로 매칭됨
        assert not CERIA_META.search("Glyceric acid deoxydehydration over Re catalysts")

    def test_still_recognizes_ceo2(self):
        assert CERIA_META.search("CeO2 nanoparticles were synthesized via hydrothermal method")


class TestCeriaPrecursor:
    def test_recognizes_ceric_nitrate_phrase(self):
        assert CERIA_PRECURSOR.search("the precursor solution contained ceric nitrate salt")

    def test_recognizes_cerous_hydroxide_phrase(self):
        assert CERIA_PRECURSOR.search("cerous hydroxide precipitate formed upon addition of base")

    def test_does_not_false_trigger_on_glyceric_acid(self):
        assert not CERIA_PRECURSOR.search("glyceric acid was formed as a byproduct")

    def test_formula_name_pairing_hydroxide_fixed(self):
        # 34차: Ce(OH) 포뮬러 옆에 "cerium carbonate"(다른 화합물)가 잘못 붙어있던
        # 복붙 실수 — "cerium hydroxide"도 인식해야 함
        assert CERIA_PRECURSOR.search("cerium hydroxide was used as the starting material")
