from __future__ import annotations

import unittest

from extraction.extractors.acordao import extract_acordao
from extraction.ner import Entity


class AcordaoTests(unittest.TestCase):
    def test_standard_stj_citation(self):
        data = extract_acordao("AgInt no AREsp nº 1.996.496/RJ, STJ")
        self.assertEqual(data["tribunal"], "STJ")
        self.assertEqual(data["numero"], "1.996.496")
        self.assertEqual(data["uf"], "RJ")
        self.assertEqual(data["classe_processual"], "AgInt no AREsp")

    def test_fields_in_another_order(self):
        data = extract_acordao(
            "STF, Agravo Interno na Rcl 67.634, da responsabilidade de Flávio Dino 2024"
        )
        self.assertEqual(data["tribunal"], "STF")
        self.assertEqual(data["numero"], "67.634")
        self.assertEqual(data["ano"], 2024)
        self.assertEqual(data["relator"], "Flávio Dino")

    def test_cnj_infers_military_court(self):
        data = extract_acordao("RSE nº 7000592-58.2025.7.00.0000/DF")
        self.assertEqual(data["tribunal"], "STM")
        self.assertEqual(data["numero"], "7000592-58.2025.7.00.0000")
        self.assertEqual(data["uf"], "DF")

    def test_ocr_in_number(self):
        data = extract_acordao("Rec. Esp. No 1.88O.529 - SP, STJ")
        self.assertEqual(data["numero"], "1.880.529")
        self.assertEqual(data["uf"], "SP")

    def test_short_class_does_not_match_inside_words(self):
        data = extract_acordao(
            "REFERENDO NOS EMB.DECL. NA AÇÃO PENAL 2.668 (STF, Min. Alexandre Moraes 2025)"
        )
        self.assertNotEqual(data["classe_processual"], "RE")
        self.assertEqual(data["numero"], "2.668")

    def test_electoral_number_without_check_digits(self):
        data = extract_acordao(
            "ACÓRDÃO ELEITORAL No 10975.2016.6.13.0133, TSE, 2016"
        )
        self.assertEqual(data["numero"], "10975.2016.6.13.0133")

    def test_class_acronym_is_not_reused_as_uf(self):
        data = extract_acordao("AP 2.668, STF, 2025")
        self.assertEqual(data["uf"], None)

    def test_administrative_number_year_is_not_judgment_year(self):
        data = extract_acordao(
            "RECURSO ESPECIAL Nº 1.741.784 - PR (2018/0116304-1), STJ, 2019"
        )
        self.assertEqual(data["ano"], 2019)

    def test_month_year_is_protected(self):
        data = extract_acordao(
            "STF, em dezembro de 2025, AgRg na Rcl 85.965, Rel. Zanin, 2026"
        )
        self.assertEqual(data["ano"], 2026)

    def test_short_number_with_prefix(self):
        data = extract_acordao("QO na cautelar inominada criminal nº 87 - DF, STJ, 2024")
        self.assertEqual(data["numero"], "87")

    def test_spaced_electoral_number_protects_internal_year(self):
        data = extract_acordao(
            "TSE, Recurso Especial Eleitoral nº 598- 2012 6 08 0018, Rel. Gonzaga, 2018"
        )
        self.assertEqual(data["numero"], "598-20126080018")
        self.assertEqual(data["ano"], 2018)

    def test_optional_ner_is_only_a_unique_person_fallback(self):
        class Recognizer:
            def recognize(self, text):
                return [Entity("PERSON", "Maria Silva", 0, 11, 0.99)]

        data = extract_acordao("REsp 1.234/SP, STJ", entity_recognizer=Recognizer())
        self.assertEqual(data["relator"], "Maria Silva")


if __name__ == "__main__":
    unittest.main()
