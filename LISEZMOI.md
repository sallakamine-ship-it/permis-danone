# Permis de travail de chantier — Danone (plateforme complète)

Application web complète (backend + frontend) pour la gestion des permis de
travail de chantier, avec registre partagé, comptes sécurisés pour le
personnel Danone, et consultation sans compte pour les sous-traitants via
QR code par secteur.

## Ce que contient cette livraison

- `app.py` — le serveur (FastAPI) : authentification, permis, secteurs/QR,
  cycle de vie (édition, fermeture à deux signatures, fermeture automatique
  à l'échéance), photos, pagination.
- `database.py` — création de la base de données (SQLite, fichier
  `permis.db`, créé automatiquement au premier démarrage).
- `templates/` — les pages HTML (accueil, panneau admin/donneur d'ordre,
  page publique de consultation par secteur).
- `static/` — feuille de style (palette bleu Danone, logo officiel) et
  logique du panneau d'administration.
- `requirements.txt` — la liste des librairies Python nécessaires.

## Comptes créés automatiquement au premier démarrage

Deux comptes (`admin` et `coordinateur`) sont créés automatiquement au tout
premier démarrage, avec un **mot de passe généré aléatoirement** à chaque
installation — jamais codé en dur, jamais affiché dans l'interface ni écrit
dans ce dépôt. Ce mot de passe temporaire s'affiche **une seule fois, dans
les logs du serveur** (onglet "Logs" sur Render, ou la console si tu lances
en local) juste après le premier démarrage — cherche la ligne
"PREMIER DÉMARRAGE".

**Connecte-toi avec ces identifiants puis change les mots de passe
immédiatement** (section "Utilisateurs" dans le panneau admin) avant de
mettre l'application à la disposition de l'équipe.

⚠️ Si cette application a déjà tourné avec l'ancienne version de ce fichier
(comptes `admin` / `Danone2026!` et `coordinateur` / `Sst2026!` codés en
dur), ces mots de passe sont désormais publics puisqu'ils ont été commités
dans ce dépôt — connecte-toi et change-les dès maintenant, ce correctif de
code ne les change pas rétroactivement dans une base déjà créée.


## Logo Danone

Le vrai logo officiel (fichier que tu as fourni) est inclus dans
`static/img/` :
- `logo-danone.png` — le lockup complet (icône + mot-symbole + signature
  "One Planet. One Health"), utilisé en grand sur l'écran de connexion.
- `logo-danone-icon.png` — l'icône seule (rognée automatiquement), utilisée
  à côté du texte "DANONE" dans les barres d'en-tête plus étroites (page
  d'accueil, en-tête admin, page de consultation par secteur).

Le code lui-même ne dessine jamais le logo — il charge ces deux fichiers
(voir `templates/_macros.html`). S'ils venaient à manquer, chaque page
retombe automatiquement sur une marque textuelle stylisée ("★ DANONE") sans
rien casser. Pour changer le fichier du logo plus tard (nouvelle version,
meilleure résolution...), remplace simplement ces deux fichiers — aucune
autre modification n'est nécessaire.

## Palette de couleurs

La palette est celle du vrai bleu Danone (plus aucun jaune ni noir en fond) :
- `#35469C` — bleu marine (mot-symbole "DANONE") — variable `--bleu-danone-fonce`
- `#29A8DF` — bleu ciel (signature "One Planet. One Health") — variable `--bleu-danone-clair`

Ces deux couleurs sont définies une seule fois, en haut de `static/style.css`
— pour ajuster la teinte plus tard, il suffit de changer ces deux valeurs.
La variable `--noir` (`#1a1a1a`) existe encore mais sert uniquement au texte ;
elle n'est plus utilisée comme couleur de fond nulle part dans l'application.
Les couleurs par type de risque (hauteur = bleu, toit = violet, à chaud =
rouge, bonbonnes = orange) sont conservées telles quelles.

Les sous-traitants n'ont **aucun compte** : ils scannent le QR code affiché
dans leur secteur, puis entrent le numéro de permis + le nom de leur
entreprise pour consulter uniquement ce permis-là.

## Installation et démarrage local (test rapide)

Prérequis : Python 3.9 ou plus récent.

```bash
cd permit-platform
python3 -m venv venv
source venv/bin/activate        # sous Windows : venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Puis ouvre `http://localhost:8000/` dans un navigateur.

- Personnel Danone → `http://localhost:8000/admin`
- Une fois connecté, va dans **Secteurs & QR** pour créer un secteur (ex.
  "Entrepôt Nord") ; l'application génère un QR code qui pointe vers
  `http://localhost:8000/secteur/entrepot-nord`.

⚠️ **En local, le QR code pointe vers `localhost` : il ne sera scannable
que depuis un appareil sur le même réseau.** Pour que les sous-traitants
puissent le scanner avec leur téléphone n'importe où, il faut déployer
l'application sur un serveur public (voir plus bas) — les QR codes se
généreront alors avec la bonne adresse automatiquement.

## Déploiement public (recommandé : Render.com, gratuit)

1. Crée un compte sur [render.com](https://render.com).
2. Mets ce dossier dans un dépôt Git (GitHub, GitLab...) — **sans** le
   dossier `venv/` et sans les fichiers `permis.db` / `.secret_key` s'ils
   existent déjà (garde-les hors du dépôt : ce sont des données, pas du
   code).
3. Sur Render : **New +** → **Web Service** → connecte le dépôt.
4. Configuration :
   - **Build command** : `pip install -r requirements.txt`
   - **Start command** : `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Render fournit une URL publique du type
   `https://votre-app.onrender.com`. C'est cette adresse que les QR codes
   utiliseront automatiquement (ils sont générés à partir de l'URL de la
   requête, aucune configuration à faire).
6. **Important — le disque** : sur le plan gratuit de Render, le disque
   n'est pas persistant entre les redéploiements (la base de données et les
   photos seraient effacées à chaque mise à jour du code). Pour un usage
   réel et continu, ajoute un **disque persistant** (Render propose cette
   option, payante mais peu coûteuse) monté par exemple sur `/data`, et
   modifie dans `database.py` / `app.py` les chemins de `permis.db` et du
   dossier `uploads/` pour pointer vers ce disque. Dis-le-moi si tu veux
   que je fasse cette adaptation avant le déploiement définitif.

## Limites connues, en toute transparence

- **Fermeture automatique des permis expirés** : elle se déclenche au
  moment où quelqu'un consulte le permis ou le registre (pas de tâche
  planifiée en continu). En pratique, comme le registre est souvent
  consulté, l'écart est minime, mais un permis expiré qui n'est *jamais*
  revisité ne changera pas de statut tout seul avant la prochaine
  consultation.
- **Fichier `.secret_key`** : généré automatiquement au premier démarrage,
  il sert à signer les sessions. Garde-le confidentiel et ne le mets pas
  dans un dépôt Git public — sinon les sessions pourraient être falsifiées.
- **Photos et base de données** : stockées sur le disque du serveur
  (`permis.db` et `uploads/`). Pense à les sauvegarder régulièrement une
  fois en production.
- Les QR codes imprimés doivent être régénérés/réimprimés si tu changes
  l'adresse de déploiement (ex. passage de test local vers l'adresse
  publique finale), car l'URL est intégrée dans l'image du QR code.

## Ce qui a été testé

Authentification (bons/mauvais identifiants), création/édition de permis,
validation conditionnelle obligatoire (vigie, plan de sauvetage,
surveillance incendie selon les sections cochées), upload de photos,
fermeture officielle à deux signatures électroniques, fermeture
automatique à l'échéance, création de secteurs et génération des QR codes,
pagination du registre (testée avec plus de 30 permis), et surtout
l'isolation par secteur de la consultation publique : un sous-traitant ne
peut consulter que le permis correspondant à son secteur, avec le bon
numéro et le bon nom d'entreprise — toute combinaison incorrecte est
refusée.
