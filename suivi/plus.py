"""Connexion à +PLUS comme un navigateur : page de connexion (jeton CSRF),
envoi du formulaire, puis lecture de la page des notes.

SÉCURITÉ : le mot de passe vient d'un « secret » GitHub (variable d'environnement).
Il n'est jamais affiché, écrit dans un fichier, ni inclus dans un message d'erreur.
"""
from __future__ import annotations

import time
from urllib.parse import urljoin, urlsplit

import requests

from .parseur_connexion import analyser_formulaire, demande_code_double_auth
from .parseur_notes import est_page_de_connexion

ADRESSE = "https://cpgedupuydelome.prepas-plus.fr"
AGENT = "SuiviPrepa/1.0 (application personnelle d'un eleve de MPSI)"
PAUSE_ENTRE_REQUETES = 1.5  # secondes


class ErreurPlus(Exception):
    """Problème de réseau ou page inattendue."""


class IdentifiantsRefuses(Exception):
    """+PLUS refuse l'identifiant ou le mot de passe (ou demande un code)."""


def recuperer_page_notes(identifiant: str, mot_de_passe: str) -> str:
    session = requests.Session()
    session.headers["User-Agent"] = AGENT
    try:
        # Étape 1 : la page de connexion, pour le formulaire et son jeton CSRF
        page = session.get(f"{ADRESSE}/account/login/?next=/colles/mes_notes", timeout=30)
        page.raise_for_status()
        formulaire = analyser_formulaire(page.text)
        if not formulaire.trouve:
            raise ErreurPlus("Le formulaire de connexion +PLUS est introuvable : le site a peut-être changé.")

        # Étape 2 : envoyer le formulaire rempli (sans suivre la redirection, pour la voir)
        champs = list(formulaire.champs) + [(formulaire.champ_identifiant, identifiant),
                                            (formulaire.champ_mot_de_passe, mot_de_passe)]
        cible = urljoin(page.url, formulaire.action) if formulaire.action else page.url
        time.sleep(PAUSE_ENTRE_REQUETES)
        reponse = session.post(cible, data=champs, allow_redirects=False, timeout=30,
                               headers={"Referer": page.url, "Origin": ADRESSE})

        if 300 <= reponse.status_code < 400:
            destination = urljoin(cible, reponse.headers.get("Location", ""))
            if urlsplit(destination).path.startswith("/account/login"):
                raise IdentifiantsRefuses("+PLUS a refusé l'identifiant ou le mot de passe.")
        elif demande_code_double_auth(reponse.text):
            raise IdentifiantsRefuses("+PLUS demande un code de double authentification : "
                                      "la connexion automatique est impossible.")
        else:
            raise IdentifiantsRefuses("+PLUS a refusé l'identifiant ou le mot de passe.")

        # Étape 3 : la page des notes
        time.sleep(PAUSE_ENTRE_REQUETES)
        notes = session.get(f"{ADRESSE}/colles/mes_notes", timeout=30)
        notes.raise_for_status()
        notes.encoding = "utf-8"
    except requests.RequestException as erreur:
        # On ne recopie que le type d'erreur : jamais la requête (qui contient le mot de passe).
        raise ErreurPlus(f"Impossible de joindre +PLUS ({type(erreur).__name__}).") from None

    if urlsplit(notes.url).path.startswith("/account/login") or est_page_de_connexion(notes.text):
        raise ErreurPlus("Connexion à +PLUS acceptée, mais la page des notes reste inaccessible.")
    return notes.text
