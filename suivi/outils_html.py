"""Petits outils pour lire du HTML « à la main » avec des expressions régulières.

Nos pages sont assez simples pour ne pas avoir besoin d'un analyseur HTML complet.
"""
import html
import re

_ESPACES = re.compile(r"\s+")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BALISE = re.compile(r"<[^>]*>")
_BLOCS_INUTILES = re.compile(r"<(script|style|svg)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


def texte_brut(fragment: str) -> str:
    """Transforme du HTML en texte lisible : sans balises, entités décodées,
    retours à la ligne uniquement là où il y avait des <br>."""
    texte = _ESPACES.sub(" ", fragment)  # en HTML, les retours à la ligne du fichier ne comptent pas
    texte = _BR.sub("\n", texte)
    texte = _BALISE.sub("", texte)
    texte = html.unescape(texte)          # "&amp;" -> "&", "&#233;" -> "é"…
    lignes = (" ".join(ligne.split()) for ligne in texte.split("\n"))
    return "\n".join(ligne for ligne in lignes if ligne)


def attribut(attributs: str, nom: str) -> str:
    """Valeur d'un attribut : attribut('class="a" title = "Bonjour"', "title") -> "Bonjour".
    Le (^|\\s) évite de confondre "title" avec "data-title"."""
    motif = r"(?:^|\s)" + re.escape(nom) + r"""\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
    m = re.search(motif, attributs, re.IGNORECASE)
    if not m:
        return ""
    for valeur in m.groups():
        if valeur is not None:
            return html.unescape(valeur)
    return ""


def sans_scripts_ni_styles(page: str) -> str:
    """Enlève les blocs <script>, <style> et <svg> (lourds et inutiles ici)."""
    return _BLOCS_INUTILES.sub("", page)
