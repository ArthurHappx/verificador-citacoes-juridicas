from __future__ import annotations

import unittest
from pathlib import Path

from retrieval import CanonicalRepository, decide


ROOT = Path(__file__).resolve().parents[2]
HAS_DEVELOPMENT_DATABASE = (
    (ROOT / "data" / "desafio1_bracis.db").is_file()
    and (ROOT / "data" / "canonical_index.sqlite").is_file()
)


@unittest.skipUnless(HAS_DEVELOPMENT_DATABASE, "artefatos de desenvolvimento não distribuídos")
class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = CanonicalRepository(
            ROOT / "data" / "desafio1_bracis.db",
            ROOT / "data" / "canonical_index.sqlite",
        )

    @classmethod
    def tearDownClass(cls):
        cls.repository.close()

    def test_index_represents_current_database(self):
        self.assertEqual(self.repository.metadata["source_row_count"], "1014")

    def test_known_acordao_resolves_uniquely(self):
        result = self.repository.retrieve(
            "acordao",
            {
                "numero": "1883715",
                "tribunal": "STJ",
                "classe_processual_normalizada": "RECURSO ESPECIAL",
                "uf": "SP",
            },
        )
        decision = decide(result)
        self.assertEqual(decision["classificacao"], "real")
        self.assertIsNotNone(decision["resolucao"]["id_canonico"])

    def test_unknown_well_formed_acordao_is_invented(self):
        result = self.repository.retrieve(
            "acordao",
            {"numero": "999999999", "tribunal": "STJ", "classe_processual": "REsp"},
        )
        self.assertEqual(decide(result)["classificacao"], "inventada")


if __name__ == "__main__":
    unittest.main()
