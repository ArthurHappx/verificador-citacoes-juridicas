from __future__ import annotations

import unittest

from identifier.service import _repair_entities


class IdentifierPostprocessingTests(unittest.TestCase):
    def test_adds_high_precision_legal_citation(self):
        text = "Aplica-se o art. 373, I, do CPC ao caso."
        entities = _repair_entities(text, [])
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["tipo"], "LEG")
        self.assertEqual(entities[0]["trecho"], "art. 373, I, do CPC")

    def test_corrects_article_mislabeled_as_acordao(self):
        text = "artigo 186 do Código Civil"
        entities = _repair_entities(
            text,
            [{"tipo": "ACOR", "inicio": 0, "fim": len(text), "trecho": text,
              "span_ok": True, "confianca": 0.8}],
        )
        self.assertEqual(entities[0]["tipo"], "LEG")

    def test_merges_fragmented_process_number(self):
        text = "APL 7357951-18.2020.7.00.0000/RJ"
        entities = _repair_entities(
            text,
            [
                {"tipo": "ACOR", "inicio": 0, "fim": 8, "trecho": text[:8],
                 "span_ok": True, "confianca": 0.8},
                {"tipo": "ACOR", "inicio": 10, "fim": len(text), "trecho": text[10:],
                 "span_ok": True, "confianca": 0.9},
            ],
        )
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["trecho"], text)

    def test_recovers_ocr_broken_reclamacao(self):
        text = "Reclamação n°\u00a033.-\n474 (MA)"
        entities = _repair_entities(text, [])
        self.assertEqual([(item["tipo"], item["trecho"]) for item in entities], [("ACOR", text)])


if __name__ == "__main__":
    unittest.main()
