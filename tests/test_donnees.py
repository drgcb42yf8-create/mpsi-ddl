"""Tests du chiffrement et des fusions (historique jamais effacé)."""
import unittest

from suivi.chiffrement import PhraseIncorrecte, chiffrer, dechiffrer
from suivi.parseur_notes import NoteColle
from suivi.principal import fusionner_notes, fusionner_ressources


class TestChiffrement(unittest.TestCase):
    def test_aller_retour(self):
        donnees = {"notes": [{"matiere": "Mathématiques", "note": 14.0}]}
        enveloppe = chiffrer(donnees, "une phrase secrète", iterations=1000)  # peu de tours : test rapide
        self.assertNotIn("Mathématiques", str(enveloppe))
        self.assertEqual(dechiffrer(enveloppe, "une phrase secrète"), donnees)

    def test_mauvaise_phrase(self):
        enveloppe = chiffrer({"a": 1}, "bonne phrase", iterations=1000)
        with self.assertRaises(PhraseIncorrecte):
            dechiffrer(enveloppe, "mauvaise phrase")

    def test_meme_sel_nouvel_iv(self):
        e1 = chiffrer({"a": 1}, "p", iterations=1000)
        import base64
        e2 = chiffrer({"a": 1}, "p", sel=base64.b64decode(e1["sel"]), iterations=1000)
        self.assertEqual(e1["sel"], e2["sel"])
        self.assertNotEqual(e1["iv"], e2["iv"])


def note(semaine, code="MATHS.", texte="14", valeur=14.0, commentaire=""):
    return NoteColle(code_matiere=code, matiere="Mathématiques", semaine_num=semaine,
                     semaine_lundi=f"2026-09-{13 + 7 * semaine:02d}", note=valeur, note_texte=texte,
                     colleur="X", commentaire=commentaire)


class TestFusionNotes(unittest.TestCase):
    def test_nouvelles_puis_rien(self):
        liste, nouvelles, change = fusionner_notes([], [note(1), note(2)], "T1")
        self.assertEqual((len(liste), len(nouvelles), change), (2, 2, True))
        self.assertEqual(liste[0]["vue_le"], "T1")
        liste2, nouvelles2, change2 = fusionner_notes(liste, [note(1), note(2)], "T2")
        self.assertEqual((nouvelles2, change2), ([], False))
        self.assertEqual(liste2[0]["vue_le"], "T1")  # la date de première apparition est gardée

    def test_jamais_effacee(self):
        liste, _, _ = fusionner_notes([], [note(1), note(2)], "T1")
        liste2, _, _ = fusionner_notes(liste, [note(2)], "T2")  # la note 1 a disparu de +PLUS
        self.assertEqual(len(liste2), 2)

    def test_commentaire_ajoute_et_note_rendue(self):
        liste, _, _ = fusionner_notes([], [note(1, texte="nn", valeur=None)], "T1")
        liste, nouvelles, change = fusionner_notes(liste, [note(1, commentaire="Bien")], "T2")
        self.assertTrue(change)
        self.assertEqual(len(nouvelles), 1)  # "nn" devenu 14 : signalé
        self.assertEqual(liste[0]["commentaire"], "Bien")


class TestFusionRessources(unittest.TestCase):
    def doc(self, cle, ordre=1):
        return {"cle": cle, "page": "p", "section": "S", "ordre": ordre, "url": "u", "categorie": "cours",
                "corrige": False, "titre": "t", "libelle": "l", "matiere": "M", "annee": "2026-2027",
                "type_lien": "drive"}

    def test_ajout_retrait_retour(self):
        liste, nouveaux, change = fusionner_ressources([], "p", [self.doc("a"), self.doc("b")], "T1", True)
        self.assertEqual((len(nouveaux), change), (2, True))
        self.assertTrue(all(r["import_initial"] for r in liste))

        liste, nouveaux, change = fusionner_ressources(liste, "p", [self.doc("a")], "T2", False)
        self.assertEqual(len(liste), 2)  # "b" n'est pas effacé…
        self.assertTrue(next(r for r in liste if r["cle"] == "b")["retiree"])  # … mais marqué retiré

        liste, nouveaux, change = fusionner_ressources(liste, "p", [self.doc("a"), self.doc("b")], "T3", False)
        self.assertFalse(next(r for r in liste if r["cle"] == "b")["retiree"])
        self.assertEqual(nouveaux, [])

    def test_autre_page_intacte(self):
        liste, _, _ = fusionner_ressources([], "p", [self.doc("a")], "T1", True)
        liste, _, change = fusionner_ressources(liste, "q", [], "T2", False)
        self.assertFalse(change)
        self.assertFalse(liste[0]["retiree"])


if __name__ == "__main__":
    unittest.main()
