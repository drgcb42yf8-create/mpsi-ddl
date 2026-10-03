"""Lecture du formulaire de connexion de +PLUS (/account/login/).

On lit le formulaire tel qu'il est (champs cachés dont le jeton CSRF, champ
identifiant, champ mot de passe) au lieu de deviner le nom des champs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .outils_html import attribut

OPTIONS = re.IGNORECASE | re.DOTALL


@dataclass
class FormulaireConnexion:
    trouve: bool = False
    action: str = ""                                     # où envoyer le formulaire (peut être vide)
    champs: list[tuple[str, str]] = field(default_factory=list)  # champs cachés, renvoyés tels quels
    champ_identifiant: str = ""
    champ_mot_de_passe: str = ""


def analyser_formulaire(page: str) -> FormulaireConnexion:
    for m_form in re.finditer(r"<form\b([^>]*)>(.*?)</form>", page, OPTIONS):
        f = FormulaireConnexion(action=attribut(m_form.group(1), "action"))
        for m_champ in re.finditer(r"<input\b([^>]*)>", m_form.group(2), OPTIONS):
            attributs = m_champ.group(1)
            nom = attribut(attributs, "name")
            type_ = attribut(attributs, "type").lower() or "text"
            if not nom:
                continue
            if type_ == "password":
                f.champ_mot_de_passe = nom
            elif type_ == "hidden":
                f.champs.append((nom, attribut(attributs, "value")))
            elif type_ in ("text", "email") and not f.champ_identifiant:
                f.champ_identifiant = nom
        # C'est le bon formulaire s'il a un champ mot de passe et un champ identifiant.
        if f.champ_mot_de_passe and f.champ_identifiant:
            f.trouve = True
            return f
    return FormulaireConnexion()


def demande_code_double_auth(page: str) -> bool:
    """Vrai si la page demande un code à usage unique (« otp »)."""
    return re.search(r"""<input\b[^>]*name\s*=\s*["'][^"']*otp[^"']*["']""", page, OPTIONS) is not None
