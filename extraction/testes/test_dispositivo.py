from __future__ import annotations

import unittest

from extraction.extractors.dispositivo import extract_dispositivo


class DispositivoTests(unittest.TestCase):
    def test_article_after_law_does_not_capture_law_year(self):
        data = extract_dispositivo("Lei nº 8.078, de 11 de setembro de 1990, art. 14")
        self.assertEqual(data["diploma"], "CDC")
        self.assertEqual(data["artigo"], ["14"])

    def test_article_before_law_does_not_capture_law_number_or_year(self):
        data = extract_dispositivo("art. 373 da Lei nº 13.105/2015")
        self.assertEqual(data["diploma"], "CPC")
        self.assertEqual(data["artigo"], ["373"])

    def test_code_year_without_article_marker_has_no_article(self):
        data = extract_dispositivo("CPC/2015")
        self.assertEqual(data["diploma"], "CPC")
        self.assertEqual(data["artigo"], [])

    def test_plural_articles_and_subdevices(self):
        data = extract_dispositivo("arts. 3º, XI; 5º e 19, XVIII, da Lei 9.472/97")
        self.assertEqual(data["artigo"], ["3", "5", "19"])
        self.assertEqual(data["inciso"], ["XI", "XVIII"])

    def test_paragraph_and_inciso(self):
        data = extract_dispositivo("art. 373, § 1º, inciso II, do CPC")
        self.assertEqual(data["artigo"], ["373"])
        self.assertEqual(data["paragrafo"], ["1"])
        self.assertEqual(data["inciso"], ["II"])

    def test_preposition_de_is_not_a_roman_numeral(self):
        data = extract_dispositivo("Art. 276 — Lei nº 4.737, de 15 de julho de 1965")
        self.assertEqual(data["inciso"], [])

    def test_articles_without_marker_require_known_diploma(self):
        data = extract_dispositivo("421, 422, 964 e 971 do Código Civil")
        self.assertEqual(data["diploma"], "CC")
        self.assertEqual(data["artigo"], ["421", "422", "964", "971"])

    def test_paragraph_is_not_bare_article(self):
        data = extract_dispositivo("1.012, parágrafo 4º, do CPC")
        self.assertEqual(data["artigo"], ["1.012"])
        self.assertEqual(data["paragrafo"], ["4"])

    def test_plural_paragraphs_are_not_articles(self):
        data = extract_dispositivo("art. 64, §§ 2º e 4º, da Constituição")
        self.assertEqual(data["artigo"], ["64"])
        self.assertEqual(data["paragrafo"], ["2", "4"])

    def test_combined_articles_and_plural_paragraphs(self):
        data = extract_dispositivo("art. 266 c/c 255, §§ 1º e 2º, do CPC")
        self.assertEqual(data["artigo"], ["266", "255"])
        self.assertEqual(data["paragrafo"], ["1", "2"])

    def test_articles_resume_after_plural_paragraphs(self):
        data = extract_dispositivo("artigos 162, §§ 1º e 2º, 513 e 522, do CPC")
        self.assertEqual(data["artigo"], ["162", "513", "522"])
        self.assertEqual(data["paragrafo"], ["1", "2"])

    def test_small_plural_paragraphs_remain_paragraphs(self):
        data = extract_dispositivo("art. 85, §§ 2º, 3º, III, 4º, III e 10, do CPC")
        self.assertEqual(data["artigo"], ["85"])
        self.assertEqual(data["paragrafo"], ["2", "3", "4", "10"])


if __name__ == "__main__":
    unittest.main()
