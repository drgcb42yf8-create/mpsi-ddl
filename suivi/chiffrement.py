"""Chiffrement des notes avant publication.

Le site est public : les notes y sont donc stockées CHIFFRÉES. Le navigateur
du téléphone les déchiffre avec la phrase secrète (même méthode, via WebCrypto) :
  - clé de 256 bits dérivée de la phrase avec PBKDF2-SHA256 (600 000 tours,
    pour rendre très lent l'essai de phrases au hasard) ;
  - chiffrement AES-256-GCM (qui détecte aussi toute modification).
Le « sel » reste le même tant que la phrase ne change pas : le téléphone peut
ainsi se souvenir de la clé sans redemander la phrase à chaque mise à jour.
"""
from __future__ import annotations

import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000


class PhraseIncorrecte(Exception):
    """La phrase secrète ne permet pas de déchiffrer les données."""


def _b64(octets: bytes) -> str:
    return base64.b64encode(octets).decode("ascii")


def deriver_cle(phrase: str, sel: bytes, iterations: int = ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=iterations)
    return kdf.derive(phrase.encode("utf-8"))


def chiffrer(objet, phrase: str, sel: bytes | None = None, iterations: int = ITERATIONS) -> dict:
    sel = sel or os.urandom(16)
    iv = os.urandom(12)  # toujours nouveau : indispensable pour AES-GCM
    cle = deriver_cle(phrase, sel, iterations)
    clair = json.dumps(objet, ensure_ascii=False).encode("utf-8")
    return {
        "version": 1,
        "methode": "PBKDF2-SHA256 + AES-256-GCM",
        "iterations": iterations,
        "sel": _b64(sel),
        "iv": _b64(iv),
        "donnees": _b64(AESGCM(cle).encrypt(iv, clair, None)),
    }


def dechiffrer(enveloppe: dict, phrase: str):
    sel = base64.b64decode(enveloppe["sel"])
    cle = deriver_cle(phrase, sel, int(enveloppe["iterations"]))
    try:
        clair = AESGCM(cle).decrypt(base64.b64decode(enveloppe["iv"]),
                                    base64.b64decode(enveloppe["donnees"]), None)
    except InvalidTag:
        raise PhraseIncorrecte() from None
    return json.loads(clair.decode("utf-8"))
