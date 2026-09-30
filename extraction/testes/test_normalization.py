from __future__ import annotations

import unicodedata
import unittest

from extraction.normalization import normalize_for_matching


class NormalizationTests(unittest.TestCase):
    def test_nfd_without_combining_characters(self):
        normalized = normalize_for_matching("Súmula, Ação e Flávio")
        self.assertEqual(normalized.text, "SUMULA, ACAO E FLAVIO")
        self.assertFalse(any(unicodedata.category(char) == "Mn" for char in normalized.text))

    def test_original_surface_can_be_recovered(self):
        normalized = normalize_for_matching("Rel. Min. Flávio Dino")
        start = normalized.text.index("FLAVIO")
        self.assertEqual(normalized.original_slice(start, start + 11), "Flávio Dino")


if __name__ == "__main__":
    unittest.main()
