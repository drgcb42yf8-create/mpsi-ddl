"""Notifications sur le téléphone via ntfy (https://ntfy.sh, gratuit).

Le « sujet » (topic) est un nom au hasard, gardé dans un secret GitHub : il
sert de mot de passe. Les messages restent volontairement courts (matière,
note, semaine) : ni nom de colleur, ni commentaire.
"""
from __future__ import annotations

import requests


def envoyer(sujet: str, titre: str, message: str, lien: str = "") -> None:
    if not sujet:
        return
    corps = {"topic": sujet, "title": titre, "message": message, "tags": ["mortar_board"]}
    if lien:
        corps["click"] = lien
    try:
        requests.post("https://ntfy.sh/", json=corps, timeout=15).raise_for_status()
    except requests.RequestException:
        print("Notification : envoi impossible (sans gravité).")
