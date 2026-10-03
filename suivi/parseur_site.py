"""Lecture d'une page du site de la classe (https://www.mpsiddl.fr.nf, un Google Sites).

On parcourt la zone role="main" dans l'ordre :
  - <h2>, <h3>… : titres de section ("Cours", "TD", "Devoirs 2025-2026")
  - <p> : une ligne, ex. "Chap OS2 : <a>Fiche</a> - <a>Notes de cours</a>".
    Le texte avant le premier lien ("Chap OS2") est le titre de la ligne.
    Une ligne sans lien ("Trigonométrie") sert de titre à la ligne suivante.

IMPORTANT : on n'utilise PAS les noms de classes CSS ("zfr3Q CDt4Ke"…) que
Google génère automatiquement et peut changer à tout moment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from .classifieur import est_libelle_corrige
from .outils_html import attribut, sans_scripts_ni_styles, texte_brut

OPTIONS = re.IGNORECASE | re.DOTALL


@dataclass
class LienSite:
    section: str = ""
    titre: str = ""
    libelle: str = ""
    url: str = ""
    ligne: int = 0   # les liens d'une même ligne ont le même numéro
    ordre: int = 0   # position sur la page


@dataclass
class ResultatSite:
    ok: bool = False
    erreur: str = ""
    titre_page: str = ""
    liens: list[LienSite] = field(default_factory=list)


def url_reelle(href: str) -> str:
    """Adresse réelle d'un lien ; chaîne vide pour les liens à ignorer
    (menu interne, ancres, liens techniques de Google)."""
    h = href.strip()
    if not h or h.startswith(("#", "/")) or h.lower().startswith("mailto:"):
        return ""
    morceaux = urlsplit(h)
    # Google Sites emballe parfois les liens : https://www.google.com/url?q=<vrai lien>&…
    if morceaux.hostname and morceaux.hostname.endswith("google.com") and morceaux.path == "/url":
        h = parse_qs(morceaux.query).get("q", [""])[0]
        morceaux = urlsplit(h)
    if morceaux.scheme not in ("http", "https") or not morceaux.hostname:
        return ""
    hote = morceaux.hostname.lower()
    est_google = hote == "google.com" or hote.endswith(".google.com")
    if est_google and hote not in ("drive.google.com", "docs.google.com"):
        return ""
    return h


def _nettoyer_titre(texte: str) -> str:
    """'Chap OS1 :' -> 'Chap OS1'"""
    return " ".join(texte.split()).rstrip(" :-–—(,;").strip()


def _peut_servir_de_titre(texte: str) -> bool:
    # Court et pas une phrase (sinon "Vous trouverez ici…" deviendrait un titre).
    return bool(texte) and len(texte) <= 60 and not texte.endswith(".")


def analyser(page: str) -> ResultatSite:
    resultat = ResultatSite()
    debut = page.find('role="main"')
    if debut < 0:
        resultat.erreur = 'zone principale (role="main") introuvable'
        return resultat
    zone = sans_scripts_ni_styles(page[debut:])

    section = ""
    titre_en_attente = ""
    numero_ligne = 0
    ordre = 0

    for bloc in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>|<p\b[^>]*>(.*?)</p>", zone, OPTIONS):
        # --- Un titre <hN> ---
        if bloc.group(1) is not None:
            texte = texte_brut(bloc.group(2)).replace("\n", " ")
            if bloc.group(1) == "1":
                resultat.titre_page = resultat.titre_page or texte
            else:
                section = texte
            titre_en_attente = ""
            continue

        # --- Un paragraphe <p>, découpé aux <br> ---
        for sous_ligne in re.split(r"<br\s*/?>", bloc.group(3), flags=OPTIONS):
            numero_ligne += 1
            liens: list[tuple[str, str]] = []
            position_premier = -1
            for m_lien in re.finditer(r"<a\b([^>]*)>(.*?)</a>", sous_ligne, OPTIONS):
                url = url_reelle(attribut(m_lien.group(1), "href"))
                libelle = texte_brut(m_lien.group(2)).replace("\n", " ").strip()
                if not url or not libelle:
                    continue
                if position_premier < 0:
                    position_premier = m_lien.start()
                liens.append((url, libelle))

            if not liens:
                texte = texte_brut(sous_ligne).replace("\n", " ")
                if _peut_servir_de_titre(texte):
                    titre_en_attente = texte
                continue

            titre_ligne = _nettoyer_titre(texte_brut(sous_ligne[:position_premier])) or titre_en_attente
            titre_en_attente = ""

            # Sans titre (ex. "DM1 (cor), DM2 (cor)") : chaque document principal
            # donne son nom aux corrigés qui le suivent ("cor" -> titre "DM1").
            dernier_principal = ""
            for url, libelle in liens:
                corrige = est_libelle_corrige(libelle)
                if titre_ligne:
                    titre = titre_ligne
                elif corrige and dernier_principal:
                    titre = dernier_principal
                else:
                    titre = libelle
                if not corrige:
                    dernier_principal = libelle
                ordre += 1
                resultat.liens.append(LienSite(section=section, titre=titre, libelle=libelle,
                                               url=url, ligne=numero_ligne, ordre=ordre))

    if not resultat.liens:
        resultat.erreur = "aucun document trouvé sur la page"
        return resultat
    resultat.ok = True
    return resultat
