"""Lecture de la page « Mes notes de colle » de +PLUS (/colles/mes_notes).

Structure de la page (octobre 2026) :
    <table>
      <tr><th>Semaine</th><th>ANG1</th><th>MATHS.</th>…</tr>          <- en-tête
      <tr>
        <th><span title="Semaine 1: du lundi 14 septembre 2026 au …">S1…</span></th>
        <td><span title="Colleur; Rg:13/46; Moy:13,27; ET:1,94">14</span></td>
        <td><details><summary><span title="…">13,5</span></summary>
              Commentaire: …</details></td>
        <td></td>                                            <- pas de colle
      </tr>
    </table>
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .outils_html import attribut, texte_brut

OPTIONS = re.IGNORECASE | re.DOTALL

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}


@dataclass
class NoteColle:
    code_matiere: str = ""            # tel que sur +PLUS : "MATHS.", "PHYS.", "ANG1"
    matiere: str = ""                 # nom lisible : "Mathématiques"
    semaine_num: int = 0
    semaine_lundi: str = ""           # "AAAA-MM-JJ"
    note: float | None = None         # None si la colle n'est pas notée ("nn")
    note_texte: str = ""              # texte brut : "14", "13,5", "nn"
    colleur: str = ""
    commentaire: str = ""
    rang: int | None = None
    effectif: int | None = None
    moyenne_classe: float | None = None
    ecart_type: float | None = None


@dataclass
class ResultatNotes:
    ok: bool = False
    page_de_connexion: bool = False   # on a reçu la page de login (session expirée…)
    erreur: str = ""
    avertissements: list[str] = field(default_factory=list)
    notes: list[NoteColle] = field(default_factory=list)


def lire_nombre(texte: str) -> float | None:
    """'13,27' -> 13.27 ; renvoie None si ce n'est pas un nombre."""
    try:
        return float(texte.strip().replace(",", "."))
    except ValueError:
        return None


def nom_matiere(code: str) -> str:
    c = code.strip().upper()
    noms = [("MATH", "Mathématiques"), ("PHYS", "Physique-Chimie"), ("ANG", "Anglais"),
            ("FR", "Français"), ("INFO", "Informatique"), ("SI", "Sciences de l'ingénieur"),
            ("ALL", "Allemand"), ("ESP", "Espagnol")]
    for debut, nom in noms:
        if c.startswith(debut):
            return nom
    return code.strip()


def est_page_de_connexion(page: str) -> bool:
    return re.search(r"""<input\b[^>]*type\s*=\s*["']?password""", page, OPTIONS) is not None


def lire_semaine(texte: str) -> tuple[int, date] | None:
    """'Semaine 3: du lundi 28 septembre 2026 au …' -> (3, date(2026, 9, 28))."""
    m = re.search(r"Semaine\s*(\d+)\s*:\s*du\s+\S+\s+(\d{1,2})(?:er)?\s+(\S+)\s+(\d{4})", texte, OPTIONS)
    if not m:
        return None
    mois = MOIS.get(m.group(3).lower())
    if not mois:
        return None
    try:
        jour = date(int(m.group(4)), mois, int(m.group(2)))
    except ValueError:
        return None
    lundi = jour - timedelta(days=jour.weekday())  # par sécurité, si ce n'était pas un lundi
    return int(m.group(1)), lundi


def _lire_infobulle(infobulle: str, note: NoteColle) -> None:
    """Lit 'MARTIN Paul; Rg:13/46; Moy:13,27; ET:1,94'."""
    premier = infobulle.split(";")[0].strip()
    if ":" not in premier:
        note.colleur = premier
    m = re.search(r"Rg\s*:\s*(\d+|None)\s*/\s*(\d+)", infobulle, OPTIONS)
    if m:
        note.rang = int(m.group(1)) if m.group(1).isdigit() else None
        note.effectif = int(m.group(2))
    m = re.search(r"Moy\s*:\s*(-?\d+(?:[.,]\d+)?)", infobulle, OPTIONS)
    if m:
        note.moyenne_classe = lire_nombre(m.group(1))
    m = re.search(r"ET\s*:\s*(-?\d+(?:[.,]\d+)?)", infobulle, OPTIONS)
    if m:
        note.ecart_type = lire_nombre(m.group(1))


def _premiere_infobulle(fragment: str) -> str:
    for m in re.finditer(r"<span\b([^>]*)>", fragment, OPTIONS):
        titre = attribut(m.group(1), "title")
        if titre:
            return titre
    return ""


def analyser(page: str) -> ResultatNotes:
    resultat = ResultatNotes()

    if est_page_de_connexion(page):
        resultat.page_de_connexion = True
        resultat.erreur = "+PLUS a renvoyé la page de connexion au lieu des notes."
        return resultat

    # 1. Le tableau des notes
    m_tableau = re.search(r"<table\b[^>]*>(.*?)</table>", page, OPTIONS)
    if not m_tableau:
        if "notes de colle" in page.lower():
            # En début d'année, il n'y a peut-être encore aucune note.
            resultat.ok = True
            resultat.avertissements.append("Aucun tableau de notes sur la page.")
        else:
            resultat.erreur = "Le tableau des notes est introuvable : le site +PLUS a peut-être changé."
        return resultat

    codes_matieres: list[str] = []
    entete_trouvee = False
    lignes_lues = 0

    # 2. Ligne par ligne
    for m_ligne in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", m_tableau.group(1), OPTIONS):
        cellules = [(m.group(1).lower(), m.group(2))
                    for m in re.finditer(r"<(th|td)\b[^>]*>(.*?)</\1>", m_ligne.group(1), OPTIONS)]
        if not cellules:
            continue

        # L'en-tête : uniquement des <th> ("Semaine", "ANG1", "MATHS.", …)
        if not entete_trouvee:
            if all(type_ == "th" for type_, _ in cellules) and len(cellules) >= 2:
                codes_matieres = [texte_brut(contenu) for _, contenu in cellules[1:]]
                entete_trouvee = True
            continue

        # Une ligne de semaine : la première cellule donne la semaine
        premiere = cellules[0][1]
        semaine = lire_semaine(_premiere_infobulle(premiere) + " " + texte_brut(premiere))
        if semaine is None:
            resultat.avertissements.append("Une semaine du tableau est illisible.")
            continue
        lignes_lues += 1
        numero, lundi = semaine

        for i, (_, contenu) in enumerate(cellules[1:]):
            if i >= len(codes_matieres):
                resultat.avertissements.append(f"Semaine {numero} : colonne sans matière ignorée.")
                break
            code = codes_matieres[i]

            # Une case contient 0, 1 ou plusieurs notes : <details> (avec commentaire) ou <span>
            for m in re.finditer(r"<details\b[^>]*>(.*?)</details>|<span\b([^>]*)>(.*?)</span>", contenu, OPTIONS):
                note = NoteColle(code_matiere=code, matiere=nom_matiere(code),
                                 semaine_num=numero, semaine_lundi=lundi.isoformat())
                if m.group(1) is not None:
                    bloc = m.group(1)
                    infobulle = _premiere_infobulle(bloc)
                    m_resume = re.search(r"<summary\b[^>]*>(.*?)</summary>", bloc, OPTIONS)
                    if m_resume:
                        texte_note = texte_brut(m_resume.group(1))
                        commentaire = texte_brut(bloc[m_resume.end():])
                        note.commentaire = re.sub(r"^\s*Commentaires?\s*:?\s*", "", commentaire, flags=OPTIONS).strip()
                    else:
                        texte_note = texte_brut(bloc)
                else:
                    infobulle = attribut(m.group(2), "title")
                    texte_note = texte_brut(m.group(3))

                if not infobulle and not texte_note:
                    continue  # span décoratif
                _lire_infobulle(infobulle, note)
                note.note_texte = texte_note.strip()
                valeur = lire_nombre(note.note_texte)
                if valeur is not None and 0 <= valeur <= 20:
                    note.note = valeur
                resultat.notes.append(note)

    if not entete_trouvee:
        resultat.erreur = "L'en-tête du tableau des notes (liste des matières) est introuvable."
        return resultat
    if lignes_lues == 0 and resultat.avertissements:
        resultat.erreur = "Aucune semaine du tableau n'a pu être lue : le format des dates a peut-être changé."
        return resultat

    resultat.ok = True
    return resultat
