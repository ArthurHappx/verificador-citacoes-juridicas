from __future__ import annotations

import csv
import unittest
from pathlib import Path

from extraction import extract_citation
from pipeline.enrichment import enrich_extraction
from retrieval import CanonicalRepository, decide


ROOT = Path(__file__).resolve().parents[2]
TYPE_TO_NER = {"lei": "LEG", "jurisprudencia": None}
HAS_REGRESSION_FIXTURES = all(
    path.is_file()
    for path in (
        ROOT / "data" / "desafio1_bracis.db",
        ROOT / "data" / "canonical_index.sqlite",
        Path(__file__).with_name("goldenset_offsets.csv"),
    )
)


@unittest.skipUnless(HAS_REGRESSION_FIXTURES, "fixtures oficiais não redistribuídas")
class GoldRetrievalRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = CanonicalRepository(
            ROOT / "data" / "desafio1_bracis.db",
            ROOT / "data" / "canonical_index.sqlite",
        )

    @classmethod
    def tearDownClass(cls):
        cls.repository.close()

    def test_all_192_gold_surfaces_keep_expected_decision(self):
        failures = []
        path = Path(__file__).with_name("goldenset_offsets.csv")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 192)

        for row in rows:
            ner_type = TYPE_TO_NER[row["tipo"]]
            if ner_type is None:
                ner_type = "SUM" if row["trecho"].strip().lower().startswith(("súm", "sum", "5úm")) else "ACOR"
            extracted = extract_citation(row["trecho"].replace("\\n", "\n"), ner_type)
            data, _ = enrich_extraction(
                extracted["trecho"], extracted["natureza"], extracted["dados"]
            )
            result = decide(self.repository.retrieve(extracted["natureza"], data))
            actual_id = str((result["resolucao"] or {}).get("id_canonico") or "")
            expected_id = row["id_canonico"].strip()
            if result["classificacao"] != row["classificacao"] or (
                expected_id and actual_id != expected_id
            ):
                failures.append(
                    (row["documento_id"], row["citacao_id"], row["classificacao"],
                     result["classificacao"], expected_id, actual_id)
                )
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
