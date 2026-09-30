from __future__ import annotations

import unittest

from extraction import extract_citation


class ExtractorContractTests(unittest.TestCase):
    def test_type_mapping(self):
        citation = extract_citation("Súmula 331 do TST", "SUM", citation_id="c7")
        self.assertEqual(citation["id"], "c7")
        self.assertEqual(citation["tipo"], "jurisprudencia")
        self.assertEqual(citation["natureza"], "sumula")

    def test_unknown_type_fails_explicitly(self):
        with self.assertRaises(ValueError):
            extract_citation("qualquer", "OUTRO")


if __name__ == "__main__":
    unittest.main()
