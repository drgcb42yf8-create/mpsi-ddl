"""Programme lancé par GitHub Actions (toutes les 30 minutes, ou à la main).

Fréquences (jamais plus souvent) :
  - notes +PLUS        : au plus une fois toutes les 30 minutes ;
  - site de la classe  : une fois par semaine, ou au plus une fois par heure
                         quand on lance la mise à jour à la main.
Règle d'or : on n'efface jamais rien. Une note reste pour toujours ; un document
qui disparaît du site est seulement marqué « retiré ».

Fichiers :
  docs/donnees/ressources.json    documents du site de la classe (public)
  docs/donnees/notes.chiffre.json notes de khôlle, CHIFFRÉES
  docs/donnees/etat.json          problèmes à afficher sur le site (public)
  .etat/etat.json                 heures des dernières vérifications (non publié)

Les journaux de GitHub Actions sont publics : on n'y écrit que des nombres.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from . import notifications
from .chiffrement import PhraseIncorrecte, chiffrer, dechiffrer
from .classifieur import PROGRAMME_COLLE, classer
from .parseur_notes import NoteColle
from .parseur_notes import analyser as analyser_notes
from .parseur_site import analyser as analyser_site
from .plus import ErreurPlus, IdentifiantsRefuses, recuperer_page_notes

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_PUBLIC = RACINE / "docs" / "donnees"
FICHIER_RESSOURCES = DOSSIER_PUBLIC / "ressources.json"
FICHIER_NOTES = DOSSIER_PUBLIC / "notes.chiffre.json"
FICHIER_ETAT_PUBLIC = DOSSIER_PUBLIC / "etat.json"
FICHIER_ETAT_PRIVE = RACINE / ".etat" / "etat.json"

INTERVALLE_NOTES = timedelta(minutes=30)
INTERVALLE_SITE = timedelta(days=7)
INTERVALLE_SITE_MANUEL = timedelta(hours=1)
ATTENTE_APRES_REFUS = timedelta(hours=24)  # mot de passe refusé : on ne réessaie pas en boucle

ADRESSE_SITE_CLASSE = "https://www.mpsiddl.fr.nf/"
PAGES_DU_SITE = [
    ("mathématiques/programmes-de-colle", "Mathématiques"),
    ("mathématiques/chapitres", "Mathématiques"),
    ("mathématiques/devoirs-et-annales", "Mathématiques"),
    ("mathématiques/cahier-de-texte", "Mathématiques"),
    ("mathématiques", "Mathématiques"),
    ("physique-chimie", "Physique-Chimie"),
    ("informatique", "Informatique"),
    ("tipe", "TIPE"),
]
AGENT = "SuiviPrepa/1.0 (application personnelle d'un eleve de MPSI)"
PAUSE_ENTRE_PAGES = 1.5  # secondes


# --------------------------------------------------------------------------- outils

def maintenant_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def depuis_iso(texte: str | None) -> datetime | None:
    if not texte:
        return None
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None


def est_du(etat: dict, cle: str, intervalle: timedelta) -> bool:
    derniere = depuis_iso(etat.get(cle))
    return derniere is None or datetime.now(timezone.utc) - derniere >= intervalle


def lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def ecrire_json_si_change(chemin: Path, objet) -> bool:
    """N'écrit que si le contenu change (sinon GitHub enregistrerait une modification inutile)."""
    texte = json.dumps(objet, ensure_ascii=False, indent=1) + "\n"
    if chemin.exists() and chemin.read_text(encoding="utf-8") == texte:
        return False
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return True


def adresse_du_site_web() -> str:
    """https://<pseudo>.github.io/<dépôt>/ à partir des variables de GitHub Actions."""
    depot = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in depot:
        return ""
    proprietaire, nom = depot.split("/", 1)
    return f"https://{proprietaire.lower()}.github.io/{nom}/"


# --------------------------------------------------------------------------- fusions (testées)

def fusionner_notes(historique: list[dict], lues: list[NoteColle], maintenant: str):
    """Ajoute les notes lues à l'historique. Renvoie (liste, nouvelles, changement)."""
    liste = [dict(n) for n in historique]
    index = {(n["semaine_lundi"], n["code_matiere"], n["colleur"]): n for n in liste}
    nouvelles, change = [], False

    for note in lues:
        d = asdict(note)
        cle = (d["semaine_lundi"], d["code_matiere"], d["colleur"])
        ancienne = index.get(cle)
        if ancienne is None:
            d["vue_le"] = maintenant
            liste.append(d)
            index[cle] = d
            nouvelles.append(d)
            change = True
            continue
        # Déjà connue : mise à jour (un commentaire a pu être ajouté). Une note qui
        # change (ex. "nn" devenu "14") est signalée comme nouvelle.
        note_changee = ancienne.get("note_texte") != d["note_texte"] and d["note"] is not None
        for champ, valeur in d.items():
            if ancienne.get(champ) != valeur:
                ancienne[champ] = valeur
                change = True
        if note_changee:
            nouvelles.append(ancienne)

    liste.sort(key=lambda n: (n["semaine_lundi"], n["matiere"]), reverse=True)
    return liste, nouvelles, change


def fusionner_ressources(liste: list[dict], page: str, classees: list[dict], maintenant: str,
                         import_initial: bool):
    """Met à jour les documents d'une page. Renvoie (liste, nouveaux, changement)."""
    liste = [dict(r) for r in liste]
    index = {r["cle"]: r for r in liste}
    vues, nouvelles, change = set(), [], False

    for r in classees:
        vues.add(r["cle"])
        ancienne = index.get(r["cle"])
        if ancienne is None:
            nouvelle = dict(r, vue_le=maintenant, retiree=False, import_initial=import_initial)
            liste.append(nouvelle)
            index[r["cle"]] = nouvelle
            nouvelles.append(nouvelle)
            change = True
            continue
        for champ in ("section", "ordre", "url", "categorie"):
            if ancienne.get(champ) != r[champ]:
                ancienne[champ] = r[champ]
                change = True
        if ancienne.get("retiree"):
            ancienne["retiree"] = False
            change = True

    # Ce qui était sur cette page et n'y est plus : « retiré », jamais effacé.
    for r in liste:
        if r["page"] == page and r["cle"] not in vues and not r.get("retiree"):
            r["retiree"] = True
            change = True
    return liste, nouvelles, change


# --------------------------------------------------------------------------- synchronisations

def synchroniser_site(problemes: dict, aujourdhui: date, maintenant: str) -> None:
    donnees = lire_json(FICHIER_RESSOURCES, {})
    ressources = donnees.get("ressources", [])
    import_initial = not ressources
    erreurs, nouveaux, change = [], [], False

    session = requests.Session()
    session.headers["User-Agent"] = AGENT
    for i, (chemin, matiere) in enumerate(PAGES_DU_SITE):
        if i:
            time.sleep(PAUSE_ENTRE_PAGES)
        try:
            reponse = session.get(ADRESSE_SITE_CLASSE + quote(chemin, safe="/"), timeout=30)
            reponse.raise_for_status()
        except requests.RequestException as erreur:
            erreurs.append(f"page « {chemin} » inaccessible ({type(erreur).__name__})")
            continue
        reponse.encoding = "utf-8"
        resultat = analyser_site(reponse.text)
        if not resultat.ok:
            erreurs.append(f"la page « {chemin} » a changé de forme ({resultat.erreur})")
            continue
        classees = classer(chemin, matiere, resultat.liens, aujourdhui)
        ressources, nouv, ch = fusionner_ressources(ressources, chemin, classees, maintenant, import_initial)
        nouveaux += nouv
        change = change or ch

    if change:
        ecrire_json_si_change(FICHIER_RESSOURCES, {"version": 1, "mis_a_jour": maintenant,
                                                   "ressources": ressources})
    problemes["site"] = (f"Mise à jour incomplète du site de la classe : {' ; '.join(erreurs)}. "
                         "Les documents déjà enregistrés sont conservés.") if erreurs else None
    print(f"Site de la classe : {len(nouveaux)} nouveaux documents, {len(erreurs)} page(s) en erreur.")

    # Notification : seulement les nouveaux programmes de colle (pas au tout premier import)
    if nouveaux and not import_initial:
        colles = [r for r in nouveaux if r["categorie"] == PROGRAMME_COLLE and not r["corrige"]]
        if colles:
            lignes = [f"{r['matiere']} : {r['titre']}" for r in colles]
            notifications.envoyer(os.environ.get("NTFY_SUJET", ""), "Nouveau programme de colle",
                                  "\n".join(lignes), adresse_du_site_web() + "#colles")


def synchroniser_notes(etat: dict, problemes: dict, maintenant: str) -> None:
    identifiant = os.environ.get("PLUS_IDENTIFIANT", "")
    mot_de_passe = os.environ.get("PLUS_MOT_DE_PASSE", "")
    phrase = os.environ.get("PHRASE_SECRETE", "")
    if not (identifiant and mot_de_passe and phrase):
        problemes["notes"] = ("Notes non récupérées : il manque un des secrets GitHub "
                              "PLUS_IDENTIFIANT, PLUS_MOT_DE_PASSE ou PHRASE_SECRETE.")
        print("Notes : secrets manquants.")
        return

    # 1. L'historique chiffré (s'il existe déjà)
    enveloppe = lire_json(FICHIER_NOTES, None)
    historique, sel = [], None
    if enveloppe:
        try:
            historique = dechiffrer(enveloppe, phrase).get("notes", [])
            sel = base64.b64decode(enveloppe["sel"])
        except PhraseIncorrecte:
            problemes["notes"] = ("Impossible de déchiffrer l'historique des notes : la phrase secrète "
                                  "(secret PHRASE_SECRETE) a changé. Remets l'ancienne, ou supprime "
                                  "docs/donnees/notes.chiffre.json pour repartir de zéro.")
            print("Notes : historique indéchiffrable, rien n'est modifié.")
            return

    # 2. La page +PLUS
    try:
        page = recuperer_page_notes(identifiant, mot_de_passe)
    except IdentifiantsRefuses as erreur:
        etat["refus_identifiants_le"] = maintenant
        problemes["notes"] = (f"{erreur} Mets à jour le secret PLUS_MOT_DE_PASSE sur GitHub, "
                              "puis relance la mise à jour à la main.")
        print("Notes : identifiants refusés.")
        return
    except ErreurPlus as erreur:
        problemes["notes"] = str(erreur)
        print("Notes : +PLUS injoignable ou inattendu.")
        return
    etat.pop("refus_identifiants_le", None)

    # 3. Lecture et fusion
    resultat = analyser_notes(page)
    if not resultat.ok:
        problemes["notes"] = (f"Impossible de lire la page des notes +PLUS : {resultat.erreur} "
                              "Les notes déjà enregistrées sont conservées.")
        print("Notes : page illisible.")
        return

    premiere_fois = not historique
    liste, nouvelles, change = fusionner_notes(historique, resultat.notes, maintenant)
    if change:
        ecrire_json_si_change(FICHIER_NOTES, chiffrer({"mis_a_jour": maintenant, "notes": liste}, phrase, sel))
    problemes["notes"] = None
    print(f"Notes : {len(resultat.notes)} lues, {len(nouvelles)} nouvelle(s).")

    # 4. Notification
    sujet = os.environ.get("NTFY_SUJET", "")
    if not nouvelles:
        return
    if premiere_fois:
        notifications.envoyer(sujet, "Notes importées", f"{len(nouvelles)} notes de khôlle importées.",
                              adresse_du_site_web() + "#notes")
        return
    lignes = []
    for n in nouvelles:
        valeur = f"{n['note_texte']}/20" if n["note"] is not None else "non noté"
        lignes.append(f"{n['matiere']} : {valeur} (semaine {n['semaine_num']})")
    notifications.envoyer(sujet, "Nouvelle note de khôlle" if len(lignes) == 1 else "Nouvelles notes de khôlle",
                          "\n".join(lignes), adresse_du_site_web() + "#notes")


# --------------------------------------------------------------------------- programme principal

def main() -> int:
    maintenant = maintenant_iso()
    aujourdhui = datetime.now(ZoneInfo("Europe/Paris")).date()
    manuel = os.environ.get("MANUEL") == "true"

    etat = lire_json(FICHIER_ETAT_PRIVE, {})
    problemes = dict(lire_json(FICHIER_ETAT_PUBLIC, {}).get("problemes", {}))

    # Site de la classe
    if est_du(etat, "derniere_verif_site", INTERVALLE_SITE_MANUEL if manuel else INTERVALLE_SITE):
        etat["derniere_verif_site"] = maintenant
        synchroniser_site(problemes, aujourdhui, maintenant)
    else:
        print("Site de la classe : pas encore l'heure de le revérifier.")

    # Notes +PLUS (après un refus, on attend 24 h, sauf relance à la main).
    # Sans les secrets, on ne contacte pas +PLUS : le créneau de 30 min n'est donc pas utilisé.
    secrets_presents = all(os.environ.get(nom) for nom in ("PLUS_IDENTIFIANT", "PLUS_MOT_DE_PASSE", "PHRASE_SECRETE"))
    if not secrets_presents:
        problemes["notes"] = ("Notes non récupérées : il manque un des secrets GitHub "
                              "PLUS_IDENTIFIANT, PLUS_MOT_DE_PASSE ou PHRASE_SECRETE.")
        print("Notes : secrets manquants.")
    elif not manuel and not est_du(etat, "refus_identifiants_le", ATTENTE_APRES_REFUS):
        print("Notes : identifiants refusés récemment, on attend une relance manuelle.")
    elif est_du(etat, "derniere_verif_notes", INTERVALLE_NOTES):
        etat["derniere_verif_notes"] = maintenant  # même en cas d'échec : on n'insiste pas
        synchroniser_notes(etat, problemes, maintenant)
    else:
        print("Notes : déjà vérifiées il y a moins de 30 minutes.")

    FICHIER_ETAT_PRIVE.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_ETAT_PRIVE.write_text(json.dumps(etat, indent=1) + "\n", encoding="utf-8")
    ecrire_json_si_change(FICHIER_ETAT_PUBLIC,
                          {"problemes": {cle: msg for cle, msg in problemes.items() if msg}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
