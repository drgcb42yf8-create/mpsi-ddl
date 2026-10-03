'use strict';
/* ---------------------------------------------------------------------------
   Site MPSI DDL : lit les fichiers de docs/donnees/ (préparés par GitHub
   Actions) et les affiche. Les notes sont chiffrées : on les déchiffre ici,
   dans le navigateur, avec la phrase secrète (WebCrypto).
   Tout le texte est inséré avec textContent : jamais de HTML venu des données.
   --------------------------------------------------------------------------- */

const MATIERES = ['Mathématiques', 'Physique-Chimie', 'Anglais', 'Informatique', 'Français', 'TIPE'];
const CLE_STOCKAGE = 'mpsi-cle-notes';

const etat = {
  ressources: [],
  problemes: {},
  enveloppe: null,      // notes chiffrées
  notes: null,          // notes déchiffrées (null = verrouillé)
  majRessources: null,
  filtres: {
    cours: { matiere: '', recherche: '', archives: false },
    annales: { matiere: '', recherche: '', avecDm: false },
  },
};

/* --------------------------------------------------------------------------- outils */

// localStorage peut être bloqué (navigation privée…) : on ne doit jamais planter.
const stockage = {
  lire(cle) { try { return localStorage.getItem(cle); } catch (e) { return null; } },
  ecrire(cle, valeur) { try { localStorage.setItem(cle, valeur); } catch (e) { /* tant pis */ } },
  effacer(cle) { try { localStorage.removeItem(cle); } catch (e) { /* tant pis */ } },
};

// Crée un élément HTML : el('a', { class: 'doc', href: '…' }, 'texte', autreElement)
function el(balise, proprietes = {}, ...enfants) {
  const noeud = document.createElement(balise);
  appliquer(noeud, proprietes);
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    noeud.append(enfant instanceof Node ? enfant : String(enfant));
  }
  return noeud;
}

// Même chose pour les éléments SVG (graphiques).
function svg(balise, proprietes = {}, ...enfants) {
  const noeud = document.createElementNS('http://www.w3.org/2000/svg', balise);
  appliquer(noeud, proprietes);
  for (const enfant of enfants.flat()) {
    if (enfant) noeud.append(enfant instanceof Node ? enfant : String(enfant));
  }
  return noeud;
}

function appliquer(noeud, proprietes) {
  for (const [cle, valeur] of Object.entries(proprietes)) {
    if (valeur === null || valeur === undefined || valeur === false) continue;
    if (cle === 'class') noeud.setAttribute('class', valeur);
    else if (cle === 'texte') noeud.textContent = valeur;
    else if (cle.startsWith('on')) noeud.addEventListener(cle.slice(2), valeur);
    else noeud.setAttribute(cle, valeur === true ? '' : valeur);
  }
}

function grouper(liste, fonctionCle) {
  const groupes = new Map();
  for (const element of liste) {
    const cle = fonctionCle(element);
    if (!groupes.has(cle)) groupes.set(cle, []);
    groupes.get(cle).push(element);
  }
  return groupes;
}

function rangMatiere(matiere) {
  const i = MATIERES.indexOf(matiere);
  return i >= 0 ? i : MATIERES.length;
}

function trierMatieres(matieres) {
  return [...matieres].sort((a, b) => rangMatiere(a) - rangMatiere(b) || a.localeCompare(b, 'fr'));
}

// Couleur fixe par matière (ordre de la palette, jamais recalculée par un filtre).
function couleurMatiere(matiere) {
  const i = MATIERES.indexOf(matiere);
  return `var(--matiere-${i >= 0 && i < 8 ? i + 1 : 8})`;
}

function majuscule(texte) {
  return texte ? texte.charAt(0).toUpperCase() + texte.slice(1) : texte;
}

function nombre(valeur) {
  return valeur.toLocaleString('fr-FR', { maximumFractionDigits: 2 });
}

/* --------------------------------------------------------------------------- dates */

function anneeScolaire(jour = new Date()) {
  const debut = jour.getMonth() >= 7 ? jour.getFullYear() : jour.getFullYear() - 1; // bascule en août
  return `${debut}-${debut + 1}`;
}
const ANNEE_COURANTE = anneeScolaire();

function lundiDe(jour) {
  const resultat = new Date(jour.getFullYear(), jour.getMonth(), jour.getDate());
  resultat.setDate(resultat.getDate() - ((resultat.getDay() + 6) % 7)); // getDay : dimanche = 0
  return resultat;
}

function dateLocale(iso) { // 'AAAA-MM-JJ' -> Date à minuit, heure locale
  const [a, m, j] = iso.split('-').map(Number);
  return new Date(a, m - 1, j);
}

function jourMois(date) {
  return date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' });
}

function periode(lundiIso) {
  const lundi = dateLocale(lundiIso);
  const dimanche = new Date(lundi);
  dimanche.setDate(lundi.getDate() + 6);
  return `du lundi ${jourMois(lundi)} au dimanche ${jourMois(dimanche)}`;
}

function ilYA(date) {
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  if (minutes < 24 * 60) return `il y a ${Math.round(minutes / 60)} h`;
  return `le ${jourMois(date)} à ${date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
}

/* --------------------------------------------------------------------------- documents */

function ressourcesDe(categories, archives = false) {
  return etat.ressources.filter((r) => categories.includes(r.categorie)
    && (archives || (!r.retiree && r.annee === ANNEE_COURANTE)));
}

function trierPage(liste) {
  return [...liste].sort((a, b) => a.page.localeCompare(b.page) || a.ordre - b.ordre);
}

function estNouveau(r) {
  return !r.import_initial && Boolean(r.vue_le) && new Date(r.vue_le) >= lundiDe(new Date());
}

function etiquette(texte, classe) {
  return el('span', { class: `etiquette ${classe}`, texte });
}

function lienDocument(r, texte, principal = false) {
  const urlSure = /^https?:\/\//i.test(r.url) ? r.url : '#';
  return el('a', {
    class: 'doc' + (principal ? ' principal' : '') + (r.retiree ? ' retire' : ''),
    href: urlSure, target: '_blank', rel: 'noopener',
    title: r.retiree ? 'Retiré du site de la classe' : null,
  }, texte);
}

// Texte du bouton d'un document dans une annale : "Sujet", "Corrigé"…
function libelleBouton(r) {
  if (r.corrige) return /^cor$/i.test(r.libelle) ? 'Corrigé' : majuscule(r.libelle);
  if (r.libelle === r.titre) return /^(ds|dm)\s*\d+$/i.test(r.libelle) ? 'Sujet' : 'Ouvrir';
  if (/^(ds|dm)\s*\d+$/i.test(r.libelle) || /^(sujet|énoncé|enonce)$/i.test(r.libelle)) return 'Sujet';
  return majuscule(r.libelle);
}

function titreMatiere(matiere, balise = 'h2') {
  return el(balise, { class: 'titre-matiere' },
    el('span', { class: 'pastille', style: `background:${couleurMatiere(matiere)}` }), matiere);
}

function messageVide(texte) {
  return el('p', { class: 'vide', texte });
}

function aucunDocument() {
  return messageVide(etat.ressources.length
    ? 'Aucun document ne correspond.'
    : 'Les documents apparaîtront après la première mise à jour.');
}

/* Barre de filtres : puces de matières + recherche (+ case à cocher éventuelle).
   "redessiner" ne refait que la liste des résultats, pour garder le clavier ouvert. */
function barreFiltres(filtre, categories, redessiner, caseACocher) {
  const matieres = trierMatieres(new Set(etat.ressources
    .filter((r) => categories.includes(r.categorie)).map((r) => r.matiere)));
  const puces = el('div', { class: 'puces', role: 'group', 'aria-label': 'Matière' });
  const ajouterPuce = (valeur, texte) => {
    const puce = el('button', {
      class: 'puce', type: 'button', 'aria-pressed': String(filtre.matiere === valeur), texte,
      onclick: () => {
        filtre.matiere = valeur;
        puces.querySelectorAll('.puce').forEach((p) => p.setAttribute('aria-pressed', String(p === puce)));
        redessiner();
      },
    });
    puces.append(puce);
  };
  ajouterPuce('', 'Toutes');
  matieres.forEach((m) => ajouterPuce(m, m));

  const recherche = el('input', {
    class: 'recherche', type: 'search', placeholder: 'Rechercher (complexes, TD03, OS2, DS4…)',
    value: filtre.recherche, 'aria-label': 'Rechercher',
    oninput: (e) => { filtre.recherche = e.target.value; redessiner(); },
  });

  const barre = el('div', { class: 'filtres' }, puces, recherche);
  if (caseACocher) {
    const entree = el('input', {
      type: 'checkbox', checked: Boolean(filtre[caseACocher.cle]),
      onchange: (e) => { filtre[caseACocher.cle] = e.target.checked; redessiner(); },
    });
    barre.append(el('label', { class: 'case' }, entree, caseACocher.texte));
  }
  return barre;
}

function filtrer(liste, filtre) {
  const motif = filtre.recherche.trim().toLowerCase();
  return liste.filter((r) => (!filtre.matiere || r.matiere === filtre.matiere)
    && (!motif || `${r.titre} ${r.libelle} ${r.section}`.toLowerCase().includes(motif)));
}

/* --------------------------------------------------------------------------- vue « Semaine » */

function dernierProgrammeParMatiere() {
  const colles = trierPage(ressourcesDe(['programme_colle']));
  const resultat = new Map();
  for (const [matiere, docs] of grouper(colles, (r) => r.matiere)) {
    const lignes = [...grouper(docs, (r) => `${r.page}|${r.titre}`).values()];
    resultat.set(matiere, lignes[lignes.length - 1]); // la dernière ligne publiée
  }
  return resultat;
}

function nomProgramme(r) {
  return /^\d+$/.test(r.titre) ? `Programme n° ${r.titre}` : r.titre;
}

function vueSemaine() {
  const vue = el('div');

  // Programmes de colle
  const colles = el('section', { class: 'carte' }, el('h2', { texte: 'Programmes de colle' }));
  const derniers = dernierProgrammeParMatiere();
  if (!derniers.size) colles.append(aucunDocument());
  for (const matiere of trierMatieres(derniers.keys())) {
    const ligne = derniers.get(matiere);
    colles.append(el('div', { class: 'groupe-ligne' },
      el('div', { class: 'titre-matiere' },
        el('span', { class: 'pastille', style: `background:${couleurMatiere(matiere)}` }), matiere,
        ligne.some(estNouveau) ? etiquette('nouveau', 'nouveau') : null),
      el('div', { class: 'sous-titre', texte: nomProgramme(ligne[0]) }),
      el('div', { class: 'liste-docs' }, ligne.map((r, i) => lienDocument(r, majuscule(/^\d+$/.test(r.libelle) ? 'Ouvrir' : r.libelle), i === 0)))));
  }
  vue.append(colles);

  // Nouveaux documents depuis lundi
  const nouveaux = trierPage(etat.ressources.filter((r) => estNouveau(r) && !r.retiree));
  const carteNouveaux = el('section', { class: 'carte' }, el('h2', { texte: 'Nouveau depuis lundi' }));
  if (!nouveaux.length) carteNouveaux.append(messageVide('Rien de nouveau sur le site de la classe depuis lundi.'));
  for (const [matiere, docs] of grouper(nouveaux, (r) => r.matiere)) {
    carteNouveaux.append(el('div', { class: 'groupe-ligne' }, titreMatiere(matiere, 'div'),
      el('div', { class: 'liste-docs' }, docs.map((r) => lienDocument(r,
        r.titre && r.titre !== r.libelle ? `${r.titre} — ${r.libelle}` : r.libelle)))));
  }
  vue.append(carteNouveaux);

  // Dernières notes
  const carteNotes = el('section', { class: 'carte' }, el('h2', { texte: 'Dernières notes' }));
  if (!etat.enveloppe) {
    carteNotes.append(messageVide('Aucune note pour l\'instant.'));
  } else if (!etat.notes) {
    carteNotes.append(el('a', { class: 'doc principal', href: '#notes', texte: 'Déverrouiller mes notes' }));
  } else if (!etat.notes.length) {
    carteNotes.append(messageVide('Aucune note pour l\'instant.'));
  } else {
    const derniere = etat.notes.reduce((max, n) => (n.semaine_lundi > max ? n.semaine_lundi : max), '');
    const notes = etat.notes.filter((n) => n.semaine_lundi === derniere);
    carteNotes.append(el('p', { class: 'discret', texte: `Semaine ${notes[0].semaine_num} — ${periode(derniere)}` }));
    notes.forEach((n) => carteNotes.append(ligneNote(n)));
  }
  vue.append(carteNotes);
  return vue;
}

/* --------------------------------------------------------------------------- vue « Colles » */

function vueColles() {
  const vue = el('div', {}, el('h2', { texte: 'Programmes de colle' }),
    el('p', { class: 'discret', texte: 'Le plus récent en haut.' }));
  const docs = trierPage(ressourcesDe(['programme_colle']));
  if (!docs.length) { vue.append(aucunDocument()); return vue; }

  const parMatiere = grouper(docs, (r) => r.matiere);
  for (const matiere of trierMatieres(parMatiere.keys())) {
    const carte = el('section', { class: 'carte' }, titreMatiere(matiere, 'h3'));
    const lignes = [...grouper(parMatiere.get(matiere), (r) => `${r.page}|${r.titre}`).values()].reverse();
    lignes.forEach((ligne, i) => {
      carte.append(el('div', { class: 'groupe-ligne' },
        el('div', { class: 'titre' }, nomProgramme(ligne[0]),
          i === 0 ? etiquette('dernier publié', 'en-cours') : null,
          ligne.some(estNouveau) ? etiquette('nouveau', 'nouveau') : null),
        el('div', { class: 'liste-docs' }, ligne.map((r, j) =>
          lienDocument(r, /^\d+$/.test(r.libelle) ? 'Ouvrir' : majuscule(r.libelle), j === 0)))));
    });
    vue.append(carte);
  }
  return vue;
}

/* --------------------------------------------------------------------------- vue « Cours » */

const CATEGORIES_COURS = ['cours', 'td', 'tp', 'interro'];

function vueCours() {
  const filtre = etat.filtres.cours;
  const resultats = el('div');
  const redessiner = () => resultats.replaceChildren(...listeCours(filtre));
  const vue = el('div', {}, el('h2', { texte: 'Cours, TD et TP' }),
    barreFiltres(filtre, CATEGORIES_COURS.concat('autre'), redessiner,
      { cle: 'archives', texte: 'Afficher aussi les années précédentes et les documents retirés' }),
    resultats);
  redessiner();
  return vue;
}

function listeCours(filtre) {
  const blocs = [];
  const docs = trierPage(filtrer(ressourcesDe(CATEGORIES_COURS, filtre.archives), filtre));
  const autres = trierPage(filtrer(ressourcesDe(['autre'], filtre.archives), filtre));
  if (!docs.length && !autres.length) return [aucunDocument()];

  const parMatiere = grouper(docs, (r) => r.matiere);
  for (const matiere of trierMatieres(parMatiere.keys())) {
    const carte = el('section', { class: 'carte' }, titreMatiere(matiere, 'h3'));
    for (const ligne of grouper(parMatiere.get(matiere), (r) => `${r.page}|${r.annee}|${r.section}|${r.titre}`).values()) {
      const seul = ligne.length === 1 && ligne[0].titre === ligne[0].libelle;
      carte.append(el('div', { class: 'groupe-ligne' },
        el('div', { class: 'titre' }, seul ? ligne[0].section || matiere : ligne[0].titre,
          ligne.some(estNouveau) ? etiquette('nouveau', 'nouveau') : null),
        el('div', { class: 'sous-titre', texte: [seul ? '' : ligne[0].section, ligne[0].annee !== ANNEE_COURANTE ? ligne[0].annee : ''].filter(Boolean).join(' · ') }),
        el('div', { class: 'liste-docs' }, ligne.map((r) => lienDocument(r, r.libelle, /^cours/i.test(r.libelle))))));
    }
    blocs.push(carte);
  }

  if (autres.length) {
    const repli = el('details', { class: 'carte repli' }, el('summary', { texte: `Autres documents (${autres.length})` }));
    for (const [matiere, liste] of grouper(autres, (r) => r.matiere)) {
      repli.append(el('div', { class: 'groupe-ligne' }, titreMatiere(matiere, 'div'),
        el('div', { class: 'liste-docs' }, liste.map((r) => lienDocument(r,
          r.titre && r.titre !== r.libelle ? `${r.titre} — ${r.libelle}` : r.libelle)))));
    }
    blocs.push(repli);
  }
  return blocs;
}

/* --------------------------------------------------------------------------- vue « Annales » */

function vueAnnales() {
  const filtre = etat.filtres.annales;
  const resultats = el('div');
  const redessiner = () => resultats.replaceChildren(...listeAnnales(filtre));
  const vue = el('div', {}, el('h2', { texte: 'Annales : DS et corrigés' }),
    barreFiltres(filtre, ['ds', 'dm'], redessiner, { cle: 'avecDm', texte: 'Inclure les DM' }),
    resultats);
  redessiner();
  return vue;
}

function listeAnnales(filtre) {
  const categories = filtre.avecDm ? ['ds', 'dm'] : ['ds'];
  const docs = trierPage(filtrer(ressourcesDe(categories, true), filtre));
  if (!docs.length) return [aucunDocument()];

  const blocs = [];
  const parMatiere = grouper(docs, (r) => r.matiere);
  for (const matiere of trierMatieres(parMatiere.keys())) {
    const carte = el('section', { class: 'carte' }, titreMatiere(matiere, 'h3'));
    const parAnnee = grouper(parMatiere.get(matiere), (r) => r.annee);
    for (const annee of [...parAnnee.keys()].sort().reverse()) {
      const epreuves = grouper(parAnnee.get(annee), (r) => `${r.page}|${r.titre}`);
      const repli = el('details', { class: 'repli', open: true },
        el('summary', { texte: annee === ANNEE_COURANTE ? `${annee} (cette année)` : annee }));
      for (const liste of epreuves.values()) {
        const sujets = liste.filter((r) => !r.corrige);
        const corriges = liste.filter((r) => r.corrige);
        repli.append(el('div', { class: 'groupe-ligne' },
          el('div', { class: 'titre' }, liste[0].titre, liste.some(estNouveau) ? etiquette('nouveau', 'nouveau') : null),
          el('div', { class: 'liste-docs' },
            sujets.map((r) => lienDocument(r, libelleBouton(r), true)),
            corriges.map((r) => lienDocument(r, libelleBouton(r))),
            corriges.length || !/^(ds|dm)\s*\d{1,2}\b/i.test(liste[0].titre)
              ? null : el('span', { class: 'discret', texte: 'pas de corrigé en ligne' }))));
      }
      carte.append(repli);
    }
    blocs.push(carte);
  }
  return blocs;
}

/* --------------------------------------------------------------------------- notes (chiffrées) */

const versOctets = (base64) => Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
const versBase64 = (octets) => btoa(String.fromCharCode(...new Uint8Array(octets)));

async function deriverCle(phrase, sel, iterations) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(phrase), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: sel, iterations, hash: 'SHA-256' },
    base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
}

async function dechiffrerAvec(cle, enveloppe) {
  const clair = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: versOctets(enveloppe.iv) },
    cle, versOctets(enveloppe.donnees));
  return JSON.parse(new TextDecoder().decode(clair));
}

// Si la clé a été mémorisée sur cet appareil (et que la phrase n'a pas changé), on déverrouille seul.
async function essayerCleMemorisee() {
  if (!etat.enveloppe || !window.crypto || !crypto.subtle) return;
  const brut = stockage.lire(CLE_STOCKAGE);
  if (!brut) return;
  try {
    const memoire = JSON.parse(brut);
    if (memoire.sel !== etat.enveloppe.sel) throw new Error('phrase changée');
    const cle = await crypto.subtle.importKey('raw', versOctets(memoire.cle), { name: 'AES-GCM' }, false, ['decrypt']);
    etat.notes = (await dechiffrerAvec(cle, etat.enveloppe)).notes || [];
  } catch (e) {
    stockage.effacer(CLE_STOCKAGE);
  }
}

async function deverrouiller(phrase, memoriser) {
  const enveloppe = etat.enveloppe;
  const cle = await deriverCle(phrase, versOctets(enveloppe.sel), enveloppe.iterations);
  const donnees = await dechiffrerAvec(cle, enveloppe); // échoue si la phrase est fausse
  etat.notes = donnees.notes || [];
  if (memoriser) {
    const brute = await crypto.subtle.exportKey('raw', cle);
    stockage.ecrire(CLE_STOCKAGE, JSON.stringify({ sel: enveloppe.sel, cle: versBase64(brute) }));
  }
}

function formulaireDeverrouillage() {
  const message = el('p', { class: 'erreur', role: 'status' });
  const champ = el('input', {
    class: 'recherche', type: 'password', autocomplete: 'current-password',
    placeholder: 'Phrase secrète', 'aria-label': 'Phrase secrète', required: true,
  });
  const memoriser = el('input', { type: 'checkbox', checked: true });
  const bouton = el('button', { class: 'bouton', type: 'submit', texte: 'Déverrouiller' });

  const formulaire = el('form', {
    onsubmit: async (e) => {
      e.preventDefault();
      bouton.disabled = true;
      bouton.textContent = 'Déchiffrement…';
      message.textContent = '';
      try {
        await deverrouiller(champ.value, memoriser.checked);
        afficherVue();
      } catch (erreur) {
        message.textContent = 'Phrase secrète incorrecte.';
        bouton.disabled = false;
        bouton.textContent = 'Déverrouiller';
      }
    },
  }, champ, el('label', { class: 'case' }, memoriser, 'Se souvenir sur cet appareil'), bouton, message);

  return el('section', { class: 'carte verrou' },
    el('h2', { texte: 'Notes protégées' }),
    el('p', { class: 'discret', texte: 'Tes notes sont chiffrées sur ce site public. Entre ta phrase secrète pour les afficher : elle ne quitte pas ce téléphone.' }),
    formulaire);
}

function ligneNote(n) {
  const valeur = n.note === null || n.note === undefined ? 'non noté' : `${nombre(n.note)}/20`;
  const details = [
    n.colleur,
    n.rang != null && n.effectif != null ? `rang ${n.rang}/${n.effectif}` : null,
    n.moyenne_classe != null ? `classe ${nombre(n.moyenne_classe)}` : null,
    n.ecart_type != null ? `écart-type ${nombre(n.ecart_type)}` : null,
  ].filter(Boolean).join(' · ');
  return el('div', { class: 'note-ligne' },
    el('div', { class: 'titre-matiere' },
      el('span', { class: 'pastille', style: `background:${couleurMatiere(n.matiere)}` }), n.matiere),
    el('div', { class: 'note-valeur', texte: valeur }),
    el('div', { class: 'note-details', texte: details }),
    n.commentaire ? el('details', {}, el('summary', { texte: 'Commentaire' }), el('p', { texte: n.commentaire })) : null);
}

function vueNotes() {
  const vue = el('div');
  if (!etat.enveloppe) {
    vue.append(el('h2', { texte: 'Notes de khôlle' }),
      messageVide('Aucune note pour l\'instant : elles apparaîtront après la première mise à jour réussie.'));
    return vue;
  }
  if (!window.crypto || !crypto.subtle) {
    vue.append(messageVide('Ce navigateur ne permet pas de déchiffrer les notes (il faut une adresse en https).'));
    return vue;
  }
  if (!etat.notes) {
    vue.append(formulaireDeverrouillage());
    return vue;
  }

  const notes = etat.notes;
  if (!notes.length) {
    vue.append(el('h2', { texte: 'Notes de khôlle' }), messageVide('Aucune note pour l\'instant.'));
    return vue;
  }
  const parMatiere = grouper(notes, (n) => n.matiere);
  const matieres = trierMatieres(parMatiere.keys());

  // Moyennes
  vue.append(el('h2', { texte: 'Moyennes' }));
  const grille = el('div', { class: 'moyennes' });
  for (const matiere of matieres) {
    const liste = parMatiere.get(matiere);
    const notees = liste.filter((n) => n.note != null);
    const classe = liste.filter((n) => n.moyenne_classe != null);
    const moyenne = notees.length ? notees.reduce((s, n) => s + n.note, 0) / notees.length : null;
    const moyenneClasse = classe.length ? classe.reduce((s, n) => s + n.moyenne_classe, 0) / classe.length : null;
    grille.append(el('div', { class: 'carte moyenne' },
      el('div', { class: 'titre-matiere' },
        el('span', { class: 'pastille', style: `background:${couleurMatiere(matiere)}` }), matiere),
      el('div', { class: 'valeur', texte: moyenne === null ? '—' : nombre(Math.round(moyenne * 100) / 100) }),
      el('div', { class: 'comparaison', texte: [
        moyenneClasse === null ? null : `classe : ${nombre(Math.round(moyenneClasse * 100) / 100)}`,
        `${notees.length} colle${notees.length > 1 ? 's' : ''} notée${notees.length > 1 ? 's' : ''}`,
      ].filter(Boolean).join(' · ') })));
  }
  vue.append(grille);

  // Évolution : un petit graphique par matière
  vue.append(el('h2', { texte: 'Évolution' }));
  for (const matiere of matieres) {
    const liste = parMatiere.get(matiere);
    if (!liste.some((n) => n.note != null)) continue;
    vue.append(el('section', { class: 'carte' }, titreMatiere(matiere, 'h3'), legende(matiere), graphique(liste, matiere)));
  }

  // Par semaine, la plus récente en haut
  vue.append(el('h2', { texte: 'Par semaine' }));
  const parSemaine = grouper([...notes].sort((a, b) => b.semaine_lundi.localeCompare(a.semaine_lundi)
    || rangMatiere(a.matiere) - rangMatiere(b.matiere)), (n) => n.semaine_lundi);
  for (const [lundi, liste] of parSemaine) {
    vue.append(el('section', { class: 'carte' },
      el('h3', { texte: `Semaine ${liste[0].semaine_num}` }),
      el('p', { class: 'discret', texte: periode(lundi) }),
      liste.map(ligneNote)));
  }

  vue.append(el('p', {}, el('button', {
    class: 'bouton secondaire', type: 'button', texte: 'Verrouiller les notes sur cet appareil',
    onclick: () => { stockage.effacer(CLE_STOCKAGE); etat.notes = null; afficherVue(); },
  })));
  return vue;
}

/* --------------------------------------------------------------------------- graphique */

function legende(matiere) {
  return el('div', { class: 'legende' },
    el('span', {}, svg('svg', { viewBox: '0 0 22 10', 'aria-hidden': 'true' },
      svg('line', { x1: 1, y1: 5, x2: 21, y2: 5, style: `stroke:${couleurMatiere(matiere)};stroke-width:2` })), 'Ta note'),
    el('span', {}, svg('svg', { viewBox: '0 0 22 10', 'aria-hidden': 'true' },
      svg('line', { x1: 1, y1: 5, x2: 21, y2: 5, class: 'moyenne-classe' })), 'Moyenne de la classe'));
}

function graphique(liste, matiere) {
  const notes = [...liste].sort((a, b) => a.semaine_lundi.localeCompare(b.semaine_lundi));
  const semaines = [...new Set(notes.map((n) => n.semaine_lundi))];
  const L = 340, H = 170, GAUCHE = 28, DROITE = 40, HAUT = 12, BAS = 26;
  const x = (s) => (semaines.length === 1 ? (GAUCHE + L - DROITE) / 2
    : GAUCHE + semaines.indexOf(s) * (L - GAUCHE - DROITE) / (semaines.length - 1));
  const y = (v) => H - BAS - (v / 20) * (H - BAS - HAUT);
  const couleur = couleurMatiere(matiere);

  const notees = notes.filter((n) => n.note != null);
  const racine = svg('svg', {
    class: 'graphique', viewBox: `0 0 ${L} ${H}`, role: 'img',
    'aria-label': `${matiere} : ` + notees.map((n) => `semaine ${n.semaine_num} ${nombre(n.note)}`).join(', '),
  });

  // Grille et graduations (0 à 20)
  for (const v of [0, 5, 10, 15, 20]) {
    racine.append(svg('line', { class: v === 0 ? 'axe' : 'grille', x1: GAUCHE, x2: L - DROITE + 8, y1: y(v), y2: y(v) }));
    racine.append(svg('text', { class: 'graduation', x: GAUCHE - 6, y: y(v) + 4, 'text-anchor': 'end' }, String(v)));
  }
  const pas = Math.ceil(semaines.length / 8); // pas plus de 8 étiquettes de semaine
  semaines.forEach((s, i) => {
    if (i % pas !== 0 && i !== semaines.length - 1) return;
    const n = notes.find((m) => m.semaine_lundi === s);
    racine.append(svg('text', { class: 'graduation', x: x(s), y: H - 8, 'text-anchor': 'middle' }, `S${n.semaine_num}`));
  });

  // Moyenne de la classe (pointillés gris)
  const pointsClasse = notes.filter((n) => n.moyenne_classe != null).map((n) => `${x(n.semaine_lundi)},${y(n.moyenne_classe)}`);
  if (pointsClasse.length > 1) racine.append(svg('polyline', { class: 'moyenne-classe', points: pointsClasse.join(' ') }));

  // Tes notes : trait de 2 px et points de 8 px entourés de la couleur du fond
  if (notees.length > 1) {
    racine.append(svg('polyline', {
      points: notees.map((n) => `${x(n.semaine_lundi)},${y(n.note)}`).join(' '),
      style: `fill:none;stroke:${couleur};stroke-width:2;stroke-linejoin:round;stroke-linecap:round`,
    }));
  }
  for (const n of notees) {
    racine.append(svg('circle', { cx: x(n.semaine_lundi), cy: y(n.note), r: 4,
      style: `fill:${couleur};stroke:var(--surface);stroke-width:2` }));
  }
  // Étiquette directe sur la dernière note seulement
  const derniere = notees[notees.length - 1];
  racine.append(svg('text', { class: 'etiquette-point', x: x(derniere.semaine_lundi) + 9, y: y(derniere.note) + 4 },
    nombre(derniere.note)));

  // Zones de toucher (plus grandes que les points) avec infobulle
  for (const n of notees) {
    const texte = `S${n.semaine_num} · ${nombre(n.note)}/20` + (n.moyenne_classe != null ? ` · classe ${nombre(n.moyenne_classe)}` : '');
    const zone = svg('circle', { class: 'zone-touche', cx: x(n.semaine_lundi), cy: y(n.note), r: 14 });
    zone.addEventListener('pointerenter', () => montrerInfobulle(zone, texte));
    zone.addEventListener('click', () => montrerInfobulle(zone, texte));
    zone.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') cacherInfobulle(); });
    racine.append(zone);
  }
  return racine;
}

function montrerInfobulle(cible, texte) {
  const bulle = document.getElementById('infobulle');
  const rect = cible.getBoundingClientRect();
  bulle.textContent = texte;
  bulle.style.left = `${Math.min(Math.max(rect.left + rect.width / 2, 70), window.innerWidth - 70)}px`;
  bulle.style.top = `${rect.top + rect.height / 2 - 6}px`;
  bulle.hidden = false;
}

function cacherInfobulle() {
  document.getElementById('infobulle').hidden = true;
}

/* --------------------------------------------------------------------------- navigation */

const VUES = { semaine: vueSemaine, notes: vueNotes, colles: vueColles, cours: vueCours, annales: vueAnnales };

function vueCourante() {
  const nom = location.hash.slice(1);
  return VUES[nom] ? nom : 'semaine';
}

function afficherVue() {
  const nom = vueCourante();
  document.querySelectorAll('.onglets a').forEach((a) => {
    if (a.dataset.vue === nom) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  cacherInfobulle();
  document.getElementById('contenu').replaceChildren(VUES[nom]());
}

function afficherProblemes() {
  const bandeau = document.getElementById('problemes');
  const messages = Object.values(etat.problemes || {}).filter(Boolean);
  bandeau.replaceChildren(...messages.map((m) => el('p', { texte: m })));
  bandeau.hidden = messages.length === 0;
}

// Heure de la dernière vérification, demandée à GitHub (et lien « Actualiser »).
async function afficherDerniereVerification() {
  const zone = document.getElementById('derniere-verif');
  const repli = etat.majRessources ? `Données du ${jourMois(new Date(etat.majRessources))}` : '';
  const morceaux = location.hostname.match(/^([^.]+)\.github\.io$/i);
  if (!morceaux) { zone.textContent = repli; return; }

  const proprietaire = morceaux[1];
  const depot = location.pathname.split('/').filter(Boolean)[0] || `${proprietaire}.github.io`;
  const lien = document.getElementById('lien-actualiser');
  lien.href = `https://github.com/${proprietaire}/${depot}/actions/workflows/mise-a-jour.yml`;
  lien.hidden = false;
  try {
    const reponse = await fetch(`https://api.github.com/repos/${proprietaire}/${depot}/actions/workflows/mise-a-jour.yml/runs?per_page=1`);
    const donnees = await reponse.json();
    const execution = donnees.workflow_runs && donnees.workflow_runs[0];
    if (!execution) { zone.textContent = repli; return; }
    const quand = ilYA(new Date(execution.updated_at));
    if (execution.status !== 'completed') zone.textContent = 'Mise à jour en cours…';
    else if (execution.conclusion === 'success') zone.textContent = `Vérifié ${quand}`;
    else zone.textContent = `Échec de la dernière mise à jour (${quand})`;
  } catch (e) {
    zone.textContent = repli;
  }
}

async function chargerJson(chemin) {
  try {
    const reponse = await fetch(chemin, { cache: 'no-cache' });
    return reponse.ok ? await reponse.json() : null;
  } catch (e) {
    return null;
  }
}

async function demarrer() {
  const [ressources, etatPublic, enveloppe] = await Promise.all([
    chargerJson('donnees/ressources.json'),
    chargerJson('donnees/etat.json'),
    chargerJson('donnees/notes.chiffre.json'),
  ]);
  etat.ressources = (ressources && ressources.ressources) || [];
  etat.majRessources = ressources && ressources.mis_a_jour;
  etat.problemes = (etatPublic && etatPublic.problemes) || {};
  etat.enveloppe = enveloppe;
  await essayerCleMemorisee();

  afficherProblemes();
  afficherVue();
  afficherDerniereVerification();
}

window.addEventListener('hashchange', () => { afficherVue(); window.scrollTo(0, 0); });
document.addEventListener('pointerdown', (e) => {
  if (!(e.target instanceof Element && e.target.classList.contains('zone-touche'))) cacherInfobulle();
});
window.addEventListener('scroll', cacherInfobulle, { passive: true });

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => { /* hors ligne indisponible : sans gravité */ });
}

demarrer();
