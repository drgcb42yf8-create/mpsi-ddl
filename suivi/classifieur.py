"""Classe les liens du site de la classe : catégorie (cours, TD, programme de
colle, DS…), année scolaire, identifiant Google Drive.

Les règles sont regroupées ici : si un prof change sa façon de nommer ses
documents, c'est ce fichier qu'on adapte.
"""
from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:  # évite une importation circulaire avec parseur_site
    from .parseur_site import LienSite

PROGRAMME_COLLE = "programme_colle"
COURS = "cours"
TD = "td"
TP = "tp"
INTERRO = "interro"
DS = "ds"
DM = "dm"
AUTRE = "autre"


def _correspond(texte: str, motif: str) -> bool:
    return re.search(motif, texte, re.IGNORECASE) is not None


def est_libelle_corrige(libelle: str) -> bool:
    """'Corrigé', 'cor', 'Indications', 'corrigé AD1'… -> True"""
    return _correspond(libelle.strip(), r"^(corrig|cor$|indications?$|solutions?$|r[ée]sultats?$)")


def categorie(chemin_page: str, section: str, titre: str, libelle: str, categorie_precedente: str) -> str:
    c, s, t, l = chemin_page.lower(), section.lower(), titre.lower(), libelle.strip().lower()

    # 1. Programmes de colle : la page ou la section le dit clairement
    if "programmes-de-colle" in c or ("programme" in s and "colle" in s) or "programme de colle" in t:
        return PROGRAMME_COLLE

    # 2. Le texte du lien est explicite : "TD02", "TP3", "DS1", "Quiz", "Cours"…
    for motif, cat in ((r"^td\s*\d", TD), (r"^tp\s*\d", TP), (r"^ds\s*\d", DS), (r"^dm\s*\d", DM)):
        if _correspond(l, motif):
            return cat
    if "quiz" in l or "interro" in l:
        return INTERRO
    if l.startswith(("cours", "fiche")) or "notes de cours" in l:
        return COURS

    # 3. Un corrigé a la catégorie du document qui le précède sur la ligne
    if est_libelle_corrige(libelle) and categorie_precedente:
        return categorie_precedente

    # 4. Le titre de la ligne : "DS01 (if, for, while)", "TP2 - …", "DM0, révisions"
    for motif, cat in ((r"^ds\s*\d", DS), (r"^dm\s*\d", DM), (r"^tp\s*\d", TP), (r"^td\s*\d", TD)):
        if _correspond(t, motif):
            return cat

    # 5. La section : "TD", "TP", "DS", "DM", "IDC", "Cours", "Devoirs 2025-2026"
    for motif, cat in ((r"^td\b", TD), (r"^tp\b", TP), (r"^ds\b", DS), (r"^dm\b", DM),
                       (r"^idc\b", INTERRO), (r"^cours\b", COURS)):
        if _correspond(s, motif):
            return cat
    if "devoir" in s:
        return DM

    # 6. La page elle-même
    if "chapitres" in c:
        return COURS
    if "devoirs" in c:
        return DM
    return AUTRE


def annee_scolaire(jour: date) -> str:
    """Le 3 octobre 2026 -> '2026-2027' (bascule dès août)."""
    debut = jour.year if jour.month >= 8 else jour.year - 1
    return f"{debut}-{debut + 1}"


def annee_mentionnee(texte: str) -> str:
    """'Devoirs 2025-2026' -> '2025-2026' ; '' si aucune année n'est écrite."""
    m = re.search(r"(20\d\d)\s*[-–/]\s*(20\d\d)", texte)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def identifiant_drive(url: str) -> tuple[str, str]:
    """Renvoie (identifiant, type) avec type parmi 'drive', 'gdoc', 'externe'."""
    morceaux = urlsplit(url)
    hote = (morceaux.hostname or "").lower()
    if hote == "drive.google.com":
        m = re.search(r"/file/d/([A-Za-z0-9_-]+)", morceaux.path)
        if m:
            return m.group(1), "drive"
        ident = parse_qs(morceaux.query).get("id", [""])[0]
        if ident:
            # Les identifiants de Google Docs (44 caractères) sont plus longs que ceux des fichiers (33).
            return ident, ("gdoc" if len(ident) >= 40 else "drive")
    if hote == "docs.google.com":
        m = re.search(r"/(document|spreadsheets|presentation)/d/([A-Za-z0-9_-]+)", morceaux.path)
        if m:
            return m.group(2), ("gdoc" if m.group(1) == "document" else "externe")
    return "", "externe"


def classer(chemin_page: str, matiere: str, liens: list["LienSite"], aujourdhui: date) -> list[dict]:
    """Transforme les liens d'une page en documents classés (dictionnaires prêts pour le JSON)."""
    annee_courante = annee_scolaire(aujourdhui)
    resultat = []
    ligne_en_cours = -1
    categorie_precedente = ""

    for lien in liens:
        if lien.ligne != ligne_en_cours:  # nouvelle ligne : on oublie la catégorie précédente
            ligne_en_cours = lien.ligne
            categorie_precedente = ""

        corrige = est_libelle_corrige(lien.libelle)
        cat = categorie(chemin_page, lien.section, lien.titre, lien.libelle, categorie_precedente)
        drive_id, type_lien = identifiant_drive(lien.url)
        annee = annee_mentionnee(f"{lien.section} {lien.titre} {lien.libelle}") or annee_courante

        resultat.append({
            # Le même PDF peut être lié à deux endroits : la clé inclut titre et libellé.
            "cle": f"{chemin_page}|{drive_id or lien.url}|{lien.titre}|{lien.libelle}",
            "matiere": matiere,
            "page": chemin_page,
            "section": lien.section,
            "titre": lien.titre,
            "libelle": lien.libelle,
            "categorie": cat,
            "corrige": corrige,
            "annee": annee,
            "ordre": lien.ordre,
            "url": lien.url,
            "type_lien": type_lien,
        })
        if not corrige:
            categorie_precedente = cat
    return resultat
