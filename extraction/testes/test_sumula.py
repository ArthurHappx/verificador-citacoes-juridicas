from __future__ import annotations

import unittest

from extraction.extractors.sumula import extract_sumula


class SumulaTests(unittest.TestCase):
    def test_order_is_not_fixed(self):
        data = extract_sumula("STJ, Súmula nº 211")
        self.assertEqual(data["tribunal"], "STJ")
        self.assertEqual(data["numero"], [211])

    def test_plural(self):
        data = extract_sumula("Súmulas 634 e 635 do STF")
        self.assertEqual(data["numero"], [634, 635])

    def test_vinculante_infers_stf(self):
        data = extract_sumula("Súmula Vinculante 10")
        self.assertEqual(data["tribunal"], "STF")
        self.assertTrue(data["vinculante"])

    def test_ocr(self):
        data = extract_sumula("5úmu1a 211 do STJ")
        self.assertEqual(data["numero"], [211])
        self.assertEqual(data["tribunal"], "STJ")

    def test_compact_surface_already_typed_by_ner(self):
        data = extract_sumula("150/STJ")
        self.assertEqual(data["numero"], [150])
        self.assertEqual(data["tribunal"], "STJ")


if __name__ == "__main__":
    unittest.main()
