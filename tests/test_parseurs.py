"""Tests des parseurs sur des copies réelles des pages (dossier tests/donnees).

Lancer : python -m unittest discover -s tests -t .
Si le site change : enregistre la nouvelle page dans tests/donnees, relance les
tests, et regarde lesquels échouent pour savoir quoi adapter.
"""
import unittest
from datetime import date
from pathlib import Path

from suivi import outils_html
from suivi.classifieur import (DM, DS, PROGRAMME_COLLE, TD, TP, COURS, annee_mentionnee, annee_scolaire,
                               classer, est_libelle_corrige, identifiant_drive)
from suivi.parseur_connexion import analyser_formulaire, demande_code_double_auth
from suivi.parseur_notes import analyser as analyser_notes, lire_semaine
from suivi.parseur_site import analyser as analyser_site

DONNEES = Path(__file__).parent / "donnees"
AUJOURDHUI = date(2026, 10, 3)


def lire(nom: str) -> str:
    return (DONNEES / nom).read_text(encoding="utf-8")


def classer_page(fichier: str, chemin: str, matiere: str) -> list[dict]:
    resultat = analyser_site(lire(fichier))
    assert resultat.ok, resultat.erreur
    return classer(chemin, matiere, resultat.liens, AUJOURDHUI)


def trouver(ressources, titre=None, libelle=None, annee=None):
    for r in ressources:
        if (titre is None or r["titre"] == titre) and (libelle is None or r["libelle"] == libelle) \
                and (annee is None or r["annee"] == annee):
            return r
    return None


class TestOutils(unittest.TestCase):
    def test_texte_brut(self):
        self.assertEqual(outils_html.texte_brut("<p>Bonjour\n   le <b>monde</b> &amp; co<br>Ligne 2</p>"),
                         "Bonjour le monde & co\nLigne 2")

    def test_attribut(self):
        attributs = ' data-title="non" title = "Rg:1/2" class=\'x\''
        self.assertEqual(outils_html.attribut(attributs, "title"), "Rg:1/2")
        self.assertEqual(outils_html.attribut(attributs, "class"), "x")
        self.assertEqual(outils_html.attribut(attributs, "href"), "")


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.resultat = analyser_notes(lire("notes_exemple_anonyme.html"))
        self.notes = {(n.semaine_num, n.code_matiere): n for n in self.resultat.notes}

    def test_page_lue(self):
        self.assertTrue(self.resultat.ok, self.resultat.erreur)
        self.assertEqual(len(self.resultat.notes), 5)
        self.assertNotIn((1, "PHYS."), self.notes)  # case vide = pas de colle

    def test_non_note(self):
        n = self.notes[(1, "ANG1")]
        self.assertEqual(n.matiere, "Anglais")
        self.assertEqual(n.note_texte, "nn")
        self.assertIsNone(n.note)
        self.assertIsNone(n.rang)
        self.assertEqual(n.effectif, 6)
        self.assertEqual(n.colleur, "DUPONT Alice")

    def test_note_avec_commentaire(self):
        n = self.notes[(1, "MATHS.")]
        self.assertEqual(n.matiere, "Mathématiques")
        self.assertEqual(n.semaine_lundi, "2026-09-14")
        self.assertEqual(n.note, 14.0)
        self.assertEqual((n.rang, n.effectif), (13, 46))
        self.assertAlmostEqual(n.moyenne_classe, 13.27)
        self.assertAlmostEqual(n.ecart_type, 1.94)
        self.assertEqual(n.commentaire,
                         "1. B. Revoir les calculs 2. AB Bien rédigé 3. Penser à l’ensemble de définition")

    def test_virgule_et_accents(self):
        self.assertEqual(self.notes[(2, "MATHS.")].colleur, "Le Gall Hélène")
        self.assertEqual(self.notes[(2, "MATHS.")].commentaire, "")
        physique = self.notes[(2, "PHYS.")]
        self.assertEqual(physique.note, 13.5)
        self.assertEqual(physique.note_texte, "13,5")
        self.assertEqual(physique.commentaire, "TB en cours. Revoir les exercices sur les signes.")
        self.assertEqual(self.notes[(3, "MATHS.")].semaine_lundi, "2026-09-28")

    def test_lire_semaine(self):
        self.assertEqual(lire_semaine("Semaine 12: du lundi 1er décembre 2025 au vendredi 5 décembre 2025"),
                         (12, date(2025, 12, 1)))
        self.assertIsNone(lire_semaine("S1: 14/09-18/09"))

    def test_deux_notes_dans_une_case(self):
        page = ('<table><tr><th>Semaine</th><th>MATHS.</th></tr>'
                '<tr><th><span title="Semaine 5: du lundi 12 octobre 2026 au vendredi 16 octobre 2026">S5</span></th>'
                '<td><span title="A; Rg:1/40; Moy:12; ET:2">18</span><span title="B; Rg:2/40; Moy:12; ET:2">17</span></td>'
                '</tr></table>')
        resultat = analyser_notes(page)
        self.assertTrue(resultat.ok)
        self.assertEqual([n.colleur for n in resultat.notes], ["A", "B"])

    def test_tableau_vide(self):
        resultat = analyser_notes("<table><tr><th>Semaine</th><th>MATHS.</th></tr></table>")
        self.assertTrue(resultat.ok)
        self.assertEqual(resultat.notes, [])

    def test_page_cassee(self):
        resultat = analyser_notes("<html><body><p>Site en maintenance</p></body></html>")
        self.assertFalse(resultat.ok)
        self.assertTrue(resultat.erreur)
        resultat = analyser_notes('<table><tr><th>Semaine</th><th>MATHS.</th></tr>'
                                  '<tr><th>???</th><td><span title="A">12</span></td></tr></table>')
        self.assertFalse(resultat.ok)

    def test_page_de_connexion(self):
        resultat = analyser_notes('<form method="post"><input type="text" name="u">'
                                  '<input type="password" name="p"></form>')
        self.assertFalse(resultat.ok)
        self.assertTrue(resultat.page_de_connexion)


class TestConnexion(unittest.TestCase):
    def test_formulaire(self):
        page = ('<form action="/recherche"><input name="q"></form>'
                '<form action="" method="post">'
                '<input type="hidden" name="csrfmiddlewaretoken" value="a&amp;b">'
                '<input type="hidden" name="login_view-current_step" value="auth">'
                '<input type="text" name="auth-username" autofocus required>'
                '<input type="password" name="auth-password" required>'
                '<button type="submit">Connexion</button></form>')
        f = analyser_formulaire(page)
        self.assertTrue(f.trouve)
        self.assertEqual(f.champ_identifiant, "auth-username")
        self.assertEqual(f.champ_mot_de_passe, "auth-password")
        self.assertEqual(f.champs, [("csrfmiddlewaretoken", "a&b"), ("login_view-current_step", "auth")])
        self.assertFalse(demande_code_double_auth(page))
        self.assertTrue(demande_code_double_auth('<input type="text" name="token-otp_token">'))


class TestSite(unittest.TestCase):
    def test_programmes_de_colle_maths(self):
        resultat = analyser_site(lire("site_maths_programmes.html"))
        self.assertTrue(resultat.ok)
        self.assertEqual(resultat.titre_page, "Mathématiques")
        self.assertEqual(len(resultat.liens), 8)
        premier = resultat.liens[0]
        self.assertEqual((premier.section, premier.titre, premier.libelle),
                         ("Programmes de colle", "Raisonnements, inégalités, trigonométrie", "programme"))
        self.assertEqual(resultat.liens[1].libelle, "démonstrations")
        self.assertEqual(resultat.liens[7].titre, "Nouvelles fonctions usuelles")

        ressources = classer_page("site_maths_programmes.html", "mathématiques/programmes-de-colle", "Mathématiques")
        self.assertTrue(all(r["categorie"] == PROGRAMME_COLLE for r in ressources))
        self.assertTrue(all(r["annee"] == "2026-2027" for r in ressources))

    def test_chapitres_maths(self):
        ressources = classer_page("site_maths_chapitres.html", "mathématiques/chapitres", "Mathématiques")
        td01 = trouver(ressources, libelle="TD01")
        self.assertEqual((td01["titre"], td01["categorie"]), ("Inégalités", TD))
        indications = trouver(ressources, titre="Inégalités", libelle="Indications")
        self.assertEqual(indications["categorie"], TD)
        self.assertTrue(indications["corrige"])
        self.assertEqual(trouver(ressources, libelle="TD02")["titre"], "Trigonométrie")
        self.assertEqual(trouver(ressources, titre="Trigonométrie", libelle="Cours")["categorie"], COURS)
        self.assertEqual(trouver(ressources, libelle="niveau cpge")["type_lien"], "externe")
        self.assertEqual(len({r["cle"] for r in ressources}), len(ressources))  # clés uniques

    def test_physique(self):
        ressources = classer_page("site_physique.html", "physique-chimie", "Physique-Chimie")
        colles = [r["libelle"] for r in ressources if r["section"] == "Programmes de colle"]
        self.assertEqual(colles, ["1", "2", "3", "4"])  # 5 à 29 ne sont que du texte
        self.assertEqual(trouver(ressources, titre="Chap OS1", libelle="Notes de cours")["categorie"], COURS)
        corrige = trouver(ressources, titre="Chap 0", libelle="Corrigé")
        self.assertEqual((corrige["section"], corrige["categorie"], corrige["corrige"]), ("TD", TD, True))
        ancien_ds = trouver(ressources, libelle="DS 2025-2026")
        self.assertEqual((ancien_ds["categorie"], ancien_ds["annee"]), (DS, "2025-2026"))

    def test_devoirs_et_annales(self):
        ressources = classer_page("site_maths_devoirs.html", "mathématiques/devoirs-et-annales", "Mathématiques")
        dm0 = trouver(ressources, titre="DM0, révisions", libelle="sujet")
        self.assertEqual((dm0["categorie"], dm0["annee"]), (DM, "2026-2027"))
        cor = trouver(ressources, titre="DM1", libelle="cor", annee="2025-2026")
        self.assertEqual(cor["categorie"], DM)
        self.assertTrue(cor["corrige"])
        self.assertIsNotNone(trouver(ressources, titre="DM1", libelle="cor", annee="2024-2025"))
        ds5 = trouver(ressources, titre="DS5", libelle="cor", annee="2024-2025")
        self.assertEqual(ds5["categorie"], DS)

    def test_informatique(self):
        ressources = classer_page("site_informatique.html", "informatique", "Informatique")
        ds01 = trouver(ressources, titre="DS01 (if, for, while)", libelle="corrigé")
        self.assertEqual((ds01["categorie"], ds01["annee"]), (DS, "2025-2026"))
        tp1 = trouver(ressources, titre="TP1 - Introduction à Python", libelle="énoncé")
        self.assertEqual((tp1["categorie"], tp1["annee"]), (TP, "2026-2027"))

    def test_document_integre(self):
        # Copie simplifiée de la page « Cahier de texte » : un tableur intégré, sans <p>.
        page = ('<div role="main"><h1>Mathématiques</h1><h2><span>Cahier de texte</span></h2>'
                '<div><a class="oWHwWc" target="_blank" title="Open Spreadsheet, Cahier de texte 2026-2027 in new window" '
                'href="https://drive.google.com/open?id=15ZIl4yGld8lgyIdIOY1NxzAw0pPTC6RhDoi52uUx3ks"></a>'
                '<iframe src="x"></iframe></div></div>')
        resultat = analyser_site(page)
        self.assertTrue(resultat.ok, resultat.erreur)
        self.assertEqual(len(resultat.liens), 1)
        lien = resultat.liens[0]
        self.assertEqual((lien.section, lien.libelle), ("Cahier de texte", "Cahier de texte 2026-2027"))
        ressources = classer("mathématiques/cahier-de-texte", "Mathématiques", resultat.liens, AUJOURDHUI)
        self.assertEqual(ressources[0]["annee"], "2026-2027")

    def test_page_cassee(self):
        self.assertFalse(analyser_site("<html><body>Rien</body></html>").ok)
        resultat = analyser_site('<div role="main"><h1>Maths</h1><p>Bientôt</p></div>')
        self.assertFalse(resultat.ok)
        self.assertTrue(resultat.erreur)


class TestClassifieur(unittest.TestCase):
    def test_regles(self):
        self.assertEqual(annee_scolaire(date(2026, 10, 3)), "2026-2027")
        self.assertEqual(annee_scolaire(date(2027, 3, 1)), "2026-2027")
        self.assertEqual(annee_mentionnee("DS 2025-2026"), "2025-2026")
        self.assertEqual(annee_mentionnee("TIPE session 2026"), "")
        self.assertTrue(est_libelle_corrige("Corrigé"))
        self.assertTrue(est_libelle_corrige("cor"))
        self.assertTrue(est_libelle_corrige("corrigé AD1"))
        self.assertFalse(est_libelle_corrige("Cours complété"))
        self.assertEqual(identifiant_drive("https://drive.google.com/open?id=1ebdt21Qw7dJ71De8RdsjbxNt5cZ_F5iHUnrwpNhfTF4"),
                         ("1ebdt21Qw7dJ71De8RdsjbxNt5cZ_F5iHUnrwpNhfTF4", "gdoc"))
        self.assertEqual(identifiant_drive("https://prepas.org/x"), ("", "externe"))


if __name__ == "__main__":
    unittest.main()
