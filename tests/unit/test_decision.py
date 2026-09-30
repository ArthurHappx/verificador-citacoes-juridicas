from __future__ import annotations

import unittest

from retrieval.decision import decide


def retrieval(candidates, *, sufficient=True, attempts=1):
    return {
        "candidatos": candidates,
        "identidade_minima_suficiente": sufficient,
        "tentativas": [
            {"plano": "acordao_completo" if index == 0 else "acordao_sem_relator"}
            for index in range(attempts)
        ],
    }


class DecisionTests(unittest.TestCase):
    def test_unique_complete_is_real(self):
        result = decide(retrieval([{"id_canonico": 42, "campos_conflitantes": []}]))
        self.assertEqual(result["classificacao"], "real")
        self.assertEqual(result["resolucao"], {"id_canonico": 42})
        self.assertEqual(result["decisao"]["regra"], "UNICO_CONSISTENTE_EM_CONSULTA_COMPLETA")

    def test_unique_after_relaxation_is_real_and_audited(self):
        result = decide(
            retrieval([{"id_canonico": 7, "campos_conflitantes": []}], attempts=2)
        )
        self.assertEqual(result["classificacao"], "real")
        self.assertTrue(result["decisao"]["consulta_parcial"])

    def test_multiple_candidates_are_incomplete(self):
        candidates = [
            {"id_canonico": 1, "campos_conflitantes": []},
            {"id_canonico": 2, "campos_conflitantes": []},
        ]
        self.assertEqual(decide(retrieval(candidates))["classificacao"], "incompleta")

    def test_no_candidate_with_sufficient_identity_is_invented(self):
        self.assertEqual(decide(retrieval([]))["classificacao"], "inventada")

    def test_no_candidate_with_insufficient_identity_is_incomplete(self):
        self.assertEqual(
            decide(retrieval([], sufficient=False))["classificacao"], "incompleta"
        )

    def test_technical_error_never_becomes_invented(self):
        result = decide(retrieval([], sufficient=True), technical_error=True)
        self.assertEqual(result["classificacao"], "incompleta")
        self.assertEqual(result["decisao"]["regra"], "ERRO_TECNICO")


if __name__ == "__main__":
    unittest.main()
