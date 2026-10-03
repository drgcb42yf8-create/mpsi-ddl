# MPSI DDL — site personnel de suivi

Site pour téléphone qui regroupe :
- les **programmes de colle**, **cours / TD / TP** et **annales de DS avec corrigés** du
  site de la classe (https://www.mpsiddl.fr.nf) ;
- les **notes de khôlle** de +PLUS, **chiffrées** (seul le propriétaire, avec sa phrase
  secrète, peut les lire) ;
- une **notification sur le téléphone** (application ntfy) à chaque nouvelle note ou
  nouveau programme de colle.

Tout tourne sur GitHub, gratuitement : aucun ordinateur n'a besoin d'être allumé.

## Comment ça marche

```
GitHub Actions (.github/workflows/mise-a-jour.yml), toutes les 30 minutes :
  python -m suivi.principal
    ├─ notes +PLUS : au plus une fois toutes les 30 min
    ├─ site de la classe : une fois par semaine (ou au plus 1 fois/heure à la main)
    └─ écrit docs/donnees/*.json (les notes chiffrées), enregistre, publie docs/
GitHub Pages : publie le dossier docs/ (le site)
```

| Dossier | Contenu |
|---|---|
| `suivi/` | programme Python : parseurs, connexion +PLUS, chiffrement, notifications |
| `tests/` | tests des parseurs sur des copies des pages (`tests/donnees/`, page de notes **anonymisée**) |
| `docs/` | le site (HTML/CSS/JS) et ses données (`docs/donnees/`) |

Sécurité :
- Le mot de passe +PLUS est un **secret GitHub** : chiffré, masqué dans les journaux, jamais
  écrit dans un fichier. Si +PLUS le refuse, le programme attend 24 h (ou une relance manuelle)
  avant de réessayer, pour ne jamais bloquer le compte.
- Les notes sont chiffrées (PBKDF2-SHA256, 600 000 tours + AES-256-GCM) avec la phrase secrète
  avant d'être publiées ; le navigateur les déchiffre sur place.
- Les journaux de GitHub Actions sont publics : le programme n'y écrit que des nombres.

---

## Installation (une seule fois)

### 1. Créer le compte et le dépôt
1. Crée un compte sur https://github.com, puis active la **double authentification** :
   photo de profil > *Settings* > *Password and authentication* > *Enable two-factor authentication*.
2. Bouton **+** en haut à droite > *New repository* :
   nom `mpsi-ddl`, **Public**, ne coche rien d'autre > *Create repository*.

### 2. Envoyer les fichiers
1. Sur la page du dépôt vide, clique sur le lien **« uploading an existing file »**.
2. Dans l'Explorateur Windows, ouvre le dossier du projet, sélectionne **tout**
   (Ctrl+A, y compris le dossier `.github` et le fichier `.gitignore`) et fais-le glisser
   dans la page.
3. En bas, *Commit changes*.
4. Vérifie que le dossier `.github` apparaît bien dans la liste des fichiers du dépôt.

> Une première exécution démarre toute seule et peut échouer (croix rouge) : c'est normal,
> la publication n'est pas encore configurée.

### 3. Activer la publication du site
*Settings* (onglet du dépôt) > *Pages* > *Build and deployment* > *Source* : **GitHub Actions**.

### 4. Enregistrer les secrets
*Settings* > *Secrets and variables* > *Actions* > **New repository secret**, quatre fois :

| Name | Secret |
|---|---|
| `PLUS_IDENTIFIANT` | ton nom d'utilisateur +PLUS |
| `PLUS_MOT_DE_PASSE` | ton mot de passe +PLUS |
| `PHRASE_SECRETE` | une phrase que tu inventes pour protéger tes notes (voir ci-dessous) |
| `NTFY_SUJET` | un nom de canal de notification inventé (voir étape 5) |

**Phrase secrète** : au moins 5 mots sans rapport entre eux, par exemple
`girafe-tunnel-violet-sept-parapluie` (n'utilise pas cet exemple). Note-la quelque part
de sûr : sans elle, les notes ne peuvent pas être affichées. Si tu la changes, l'historique
déjà chiffré devient illisible (le site te le signalera).

### 5. Notifications sur le téléphone
1. Installe l'application **ntfy** (Play Store ou App Store, gratuite).
2. Bouton **+** > *Subscribe to topic* : tape le **même nom** que le secret `NTFY_SUJET`.
   Invente un nom long et imprévisible, par exemple `mpsi-` suivi d'une vingtaine de lettres
   et chiffres au hasard : quiconque connaît ce nom peut lire les notifications.

### 6. Première mise à jour
1. Onglet **Actions** du dépôt. Si GitHub le demande, clique sur
   *I understand my workflows, go ahead and enable them*.
2. À gauche, **Mise à jour** > bouton **Run workflow** > *Run workflow*.
3. Attends la coche verte (1 à 2 minutes). Vérifie aussi que **Tests** est vert.

### 7. Sur le téléphone
1. Ouvre `https://<ton-pseudo>.github.io/mpsi-ddl/` (pseudo GitHub en minuscules).
2. Onglet **Notes** : entre ta phrase secrète, coche *Se souvenir sur cet appareil*.
3. Ajoute le site à l'écran d'accueil :
   - Android (Chrome) : menu ⋮ > *Ajouter à l'écran d'accueil* ;
   - iPhone (Safari) : bouton Partager > *Sur l'écran d'accueil*.

---

## Utilisation

- **Actualiser** (en haut du site) : ouvre la page GitHub où lancer une mise à jour
  (*Run workflow*). Les notes ne sont jamais vérifiées plus d'une fois toutes les 30 minutes.
- **Bandeau jaune** : quelque chose ne va pas (mot de passe refusé, page du site de la classe
  qui a changé de forme…). Les données déjà enregistrées ne sont jamais effacées.
- **Changer le mot de passe +PLUS** : mets à jour le secret `PLUS_MOT_DE_PASSE`, puis relance
  la mise à jour à la main.
- GitHub met en pause les tâches automatiques d'un dépôt sans activité pendant 60 jours :
  si ça arrive, onglet *Actions* > *Mise à jour* > *Enable workflow*.

## Si le site de la classe ou +PLUS change

Enregistre la nouvelle page (Ctrl+S > « Page Web, HTML uniquement ») dans `tests/donnees/`,
lance les tests (`python -m unittest discover -s tests -t .`) et regarde lesquels échouent :
ils indiquent ce qu'il faut adapter dans `suivi/`. **Ne publie jamais une vraie page de
notes non anonymisée** : ce dépôt est public.
