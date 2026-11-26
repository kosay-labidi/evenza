# Évenza

> Plateforme web de gestion d'agence événementielle, développée avec **Django** selon l'architecture **MVT**.

## 🎉 SPRINT 1 - MODULE GESTION DES ÉVÉNEMENTS - COMPLÉTÉ ✅

**Le module complet de gestion des événements est maintenant fonctionnel, testé et validé !**

📊 **Résultats:**
- ✅ 4 User Stories complètes (US 2.1-2.4)
- ✅ 22 Tests unitaires (100% OK)
- ✅ CRUD complet avec validations
- ✅ Recherche, filtres et pagination
- ✅ Dashboard organisateur

📚 **Documentation complète:**
- **[RESUME_FINAL.md](RESUME_FINAL.md)** - Vue d'ensemble et quick start
- **[EVENEMENTS_CRUD_VALIDATION.md](EVENEMENTS_CRUD_VALIDATION.md)** - Validation du Sprint Backlog
- **[SPRINT1_EVENEMENTS_COMPLET.md](SPRINT1_EVENEMENTS_COMPLET.md)** - Architecture détaillée
- **[INDEX_DOCUMENTATION.md](INDEX_DOCUMENTATION.md)** - Guide de navigation

🧪 **Tests et démo:**
```bash
python manage.py test evenements        # Tests unitaires
python test_evenements_crud.py         # Test complet automatisé
python demo_evenements.py              # Démo interactive
```

---

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)
![SQLite](https://img.shields.io/badge/BDD-SQLite%20%7C%20PostgreSQL-003B57?logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-65%20OK-2EA44F)
![Licence](https://img.shields.io/badge/projet-acad%C3%A9mique-512D3B)

Projet réalisé dans le cadre du module **Génie logiciel** (ESPRIT, 3IA).
Évenza couvre tout le cycle de vie d'un événement : création et publication, programme et intervenants, billetterie avec QR code, liste d'attente, réservation de prestataires, affectation de ressources et contrôle d'entrée.

---

## Démarrage rapide

```bash
git clone https://github.com/kosay-labidi/evenza.git && cd evenza
python -m venv venv && venv\Scripts\activate   # ou: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_demo
python manage.py runserver
```

Puis ouvrez http://127.0.0.1:8000/ et connectez-vous avec `organisateur` / `Demo12345!`.

> **Travail en équipe** : la répartition des six gestions, les fichiers de chacun, la procédure Git/GitHub
> et l'intégration finale sont décrites dans **[ORGANISATION_EQUIPE.md](ORGANISATION_EQUIPE.md)**.

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Site public et espace professionnel](#site-public-et-espace-professionnel)
- [Stack technique](#stack-technique)
- [Installation](#installation)
- [Comptes de démonstration](#comptes-de-démonstration)
- [Configuration](#configuration)
- [Structure du projet](#structure-du-projet)
- [Règles de gestion](#règles-de-gestion)
- [Tests](#tests)
- [Plan des URL](#plan-des-url)
- [Interface et design](#interface-et-design)
- [Personnalisation](#personnalisation)

---

## Fonctionnalités

| Module | Ce qu'il permet |
|---|---|
| **Utilisateurs** | Inscription en 3 étapes, connexion par nom d'utilisateur **ou** e-mail, mot de passe oublié, profil, rôles (Administrateur, Organisateur, Participant, Prestataire, Client) |
| **Événements** | Catalogue filtrable (catégorie, ville, date), création / modification / suppression, publication, gestion des lieux et catégories |
| **Programmes** | Séances et intervenants rattachés à un événement |
| **Participants** | Réservation en 2 étapes (choix des billets puis récapitulatif), types de billets avec prix et quotas, billet QR imprimable, liste d'attente, check-in, avis |
| **Prestataires** | Catalogue de prestataires et de services, réservation pour un événement |
| **Ressources** | Matériel et salles, affectation sur un créneau avec **détection de conflit** |
| **Vue d'ensemble** | Indicateurs clés, accès direct aux modules autorisés, calendrier du mois avec les événements réels |
| **Pages publiques** | Accueil, À propos, Contact (messages lisibles dans l'admin), FAQ |

## Site public et espace professionnel

La plateforme est organisée en **deux espaces** :

| Espace | Gabarit | Contenu |
|---|---|---|
| **Site public** | `templates/base.html` + `partials/navbar.html` | Accueil (vidéos, animations), catalogue et détail des événements, réservation de billets, connexion / inscription, À propos, Contact, FAQ |
| **Espace professionnel** | `templates/app_base.html` + `partials/sidebar.html` | Vue d'ensemble puis un module par gestion : Événements, Participants, Programmes, Prestataires, Ressources, Utilisateurs ; espace personnel (Mes billets, Mon profil, Retour au site, Déconnexion) |

La barre latérale est **générée** : chaque application déclare son module dans `<app>/navigation.py`
(intitulé, icône, page d'entrée, sous-liens, règle d'accès) et `core/navigation.py` les assemble.
La même règle d'accès est appliquée côté serveur (`core/permissions.py`, `ModuleRequiredMixin`), si bien
qu'un lien masqué correspond toujours à une page refusée (HTTP 403).

| Rôle | Modules visibles |
|---|---|
| Administrateur | Vue d'ensemble + les six modules + Administration Django |
| Organisateur | Vue d'ensemble, Événements, Participants, Programmes, Prestataires, Ressources |
| Participant, Client, Prestataire | Vue d'ensemble, Mes billets, Mon profil |

## Stack technique

- **Back-end** : Python, Django 5.2 (vues génériques, système d'authentification, ORM)
- **Base de données** : SQLite en développement, PostgreSQL envisagé en production
- **Front-end** : templates Django, HTML/CSS et JavaScript sans framework
- **Animations** : IntersectionObserver, View Transitions ; Three.js et GSAP pour l'intro 3D (embarqués dans `static/vendor/`)
- **Images** : Pillow

Architecture **3-tiers** : navigateur web (client), Django (serveur d'application), SQLite/PostgreSQL (serveur de données).

## Installation

**Prérequis** : Python 3.10 ou plus récent (testé avec Python 3.14), `pip`, Git.

```bash
# 1. Cloner le dépôt
git clone https://github.com/kosay-labidi/evenza.git
cd evenza

# 2. Créer et activer un environnement virtuel
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Créer la base de données (les migrations sont versionnées)
python manage.py migrate

# 5. Charger les données de démonstration
python manage.py seed_demo

# 6. Lancer le serveur
python manage.py runserver
```

L'application est alors accessible sur **http://127.0.0.1:8000/**.

Pour vider puis recréer les données de démonstration :

```bash
python manage.py seed_demo --reset
```

## Comptes de démonstration

Créés par `seed_demo` :

| Identifiant | Mot de passe | Rôle |
|---|---|---|
| `admin` | `Admin12345!` | Administrateur (accès à `/admin/`) |
| `organisateur` | `Demo12345!` | Organisateur |
| `participant` | `Demo12345!` | Participant |
| `prestataire` | `Demo12345!` | Prestataire |

> ⚠️ Ces identifiants servent uniquement au développement local. Ne les utilisez pas en production.

## Configuration

Les paramètres sensibles se lisent dans des variables d'environnement (voir `evenza/settings.py`) :

| Variable | Rôle | Valeur par défaut |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clé secrète Django | clé de développement (**à changer en production**) |
| `DJANGO_DEBUG` | `1` = mode debug, `0` = production | `1` |
| `DJANGO_ALLOWED_HOSTS` | Hôtes autorisés si `DEBUG=0`, séparés par des virgules | vide |
| `DJANGO_EMAIL_BACKEND` | Backend d'envoi d'e-mails | `console` (les e-mails s'affichent dans le terminal) |

Autres réglages :
- Langue `fr-fr`, fuseau horaire `Africa/Tunis`.
- Les coordonnées affichées dans le pied de page et la page Contact se règlent dans `EVENZA_CONTACT` (`evenza/settings.py`).
- **Mot de passe oublié en développement** : l'e-mail n'est pas envoyé, il apparaît dans le terminal où tourne `runserver`. Copiez le lien dans le navigateur.

## Structure du projet

Une application Django par domaine de gestion :

```
evenza/
├── evenza/            # Configuration du projet (settings, urls, wsgi, asgi)
├── core/              # Accueil, vue d'ensemble, pages publiques, permissions, navigation, mixins, seed_demo
├── utilisateurs/      # Modèle Utilisateur personnalisé, authentification, profils
├── evenements/        # Événements, lieux, catégories
├── programmes/        # Séances, intervenants
├── participants/      # Types de billets, inscriptions (billets QR), avis
├── prestataires/      # Prestataires, services, réservations
├── ressources/        # Ressources, affectations, détection de conflits
├── templates/         # Gabarits communs : base (public), app_base (espace pro), list/detail/form/confirm_base, partials
├── static/            # CSS, JS, polices, images, vidéos, bibliothèques embarquées
├── media/             # Fichiers téléversés (ignoré par Git)
├── manage.py
└── requirements.txt
```

| App | Modèles principaux |
|---|---|
| `utilisateurs` | `Utilisateur` (hérite d'`AbstractUser`, ajoute un rôle) |
| `evenements` | `Evenement`, `Lieu`, `Categorie` |
| `programmes` | `Seance`, `Intervenant` |
| `participants` | `TypeBillet`, `Inscription`, `Avis` |
| `prestataires` | `Prestataire`, `Service`, `Reservation` |
| `ressources` | `Ressource`, `Affectation` |
| `core` | `MessageContact` |

Chaque application de gestion contient : `models.py`, `views.py`, `forms.py`, `urls.py` (namespace),
`admin.py`, `tests.py`, `navigation.py` (son entrée de menu), `migrations/` et `templates/<app>/`.

**Organisation MVT**
- **Modèle** (`models.py`) : classes du diagramme de classes, règles de validation (`clean()`), attributs dérivés (`@property`) et opérations métier (`publier()`, `inscrire()`…).
- **Vue** (`views.py`) : vues génériques (`ListView`, `DetailView`, `CreateView`, `UpdateView`, `DeleteView`) et contrôle d'accès par rôle (`core/mixins.py`, règles dans `core/permissions.py`).
- **Template** : `templates/base.html` (site public) et `templates/app_base.html` (espace professionnel), gabarits CRUD communs (`list_base`, `detail_base`, `form_base`, `confirm_base`), puis un dossier de templates par application.
- **URL** (`urls.py`) : chaque application a son espace de noms (`evenements:detail`…).

## Règles de gestion

- Un événement se termine après son début, et sa capacité ne dépasse pas celle du lieu.
- Seuls les événements **publiés** apparaissent dans le catalogue.
- Un organisateur ne modifie que **ses propres** événements ; l'administrateur peut tout modifier.
- Quand un événement est complet, l'inscription passe en **liste d'attente** ; une annulation promeut automatiquement la personne suivante.
- Un participant a une seule réservation par événement (contrainte d'unicité), de 1 à 10 places.
- Chaque type de billet (Standard, VIP, Étudiant…) a son prix et peut avoir un quota de places.
- Chaque billet a un code unique (QR) ; le **check-in** enregistre la présence.
- Un prestataire n'est réservé que pour un service qu'il propose.
- Une ressource ne peut pas être affectée au-delà de sa quantité sur un même créneau.
- Une séance se déroule pendant son événement.

## Tests

```bash
python manage.py test
```

65 tests, tous au vert. Ils couvrent les règles métier des applications `evenements`, `participants`, `prestataires`, `ressources`, `programmes` et `utilisateurs`, ainsi que l'architecture commune (`core/tests.py` : menu par rôle, accès direct aux six modules, contrôle des permissions côté serveur).

Vérifications à lancer avant chaque Pull Request :

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Plan des URL

| URL | Page |
|---|---|
| `/` | Accueil |
| `/evenements/` | Catalogue |
| `/evenements/<id>/` | Détail d'un événement (programme, prestataires, ressources) |
| `/evenements/nouveau/`, `/evenements/<id>/modifier/` | Création / modification |
| `/participants/evenement/<id>/reserver/` | Réservation (billets puis récapitulatif) |
| `/participants/billet/<code>/` | Billet QR |
| `/participants/evenement/<id>/checkin/` | Contrôle d'entrée |
| `/tableau-de-bord/` | Vue d'ensemble (espace professionnel) |
| `/evenements/mes-evenements/` | Module Événements |
| `/participants/` | Module Participants |
| `/programmes/` | Module Programmes |
| `/prestataires/` | Module Prestataires |
| `/ressources/` | Module Ressources |
| `/comptes/utilisateurs/` | Module Utilisateurs (administrateur) |
| `/comptes/connexion/` | Connexion |
| `/comptes/inscription/` | Inscription |
| `/comptes/profil/` | Profil |
| `/participants/mes-inscriptions/` | Mes réservations |
| `/comptes/mot-de-passe/oublie/` | Mot de passe oublié |
| `/a-propos/`, `/contact/`, `/faq/` | Pages d'information |
| `/admin/` | Administration Django |

## Interface et design

Direction artistique **« Luxury Editorial × Modern Interactive »** : bordeaux, champagne et crème, grands titres serif et petits sur-titres en capitales espacées.

- **Jetons de couleur** dans le bloc `:root` de `static/css/style.css` (`--color-primary`, `--color-accent`, `--color-background`…). Modifier une couleur à cet endroit la change dans tout le site.
- **Polices** hébergées localement (`static/fonts/`) : Cormorant Garamond (titres) et Inter (texte).
- **Feuilles de style** : `style.css` (design system et pages publiques), `home.css` (accueil), `dashboard.css` (espace professionnel : barre latérale, cartes de modules, états vides), `auth.css` (comptes).
- **Animations** (`static/js/main.js`, `motion.js`) : apparition au défilement (`reveal`, `stagger`), compteurs (`data-count`), titres mot par mot (`data-split`), parallaxe (`data-parallax`), transitions entre pages.
- **Intro vidéo facultative** (`static/js/intro-video.js`) : film de 7 s, 5 plans plein écran (mariage → concert → gala → conférence → festival) avec filtre doré, puis logo « EV » sur fond crème. Fichiers : `static/video/evenza-intro7.{webm,mp4}` (1920×1080) et `evenza-intro7-portrait.{webm,mp4}` (1080×1920, mobile), < 2 Mo chacun ; WebM lu en priorité, MP4 en repli. Jouée une fois par session (`data-max` dans `core/templates/core/_intro.html`). `/?intro=1` la rejoue, `/?intro=0` la saute, Échap la passe. Plans issus de Mixkit (licence gratuite Mixkit, sans attribution obligatoire) : 5382, 48509, 51541, 13193, 4188.
- **Film « Un soir en Méditerranée »** (`static/js/film.js`) : séquence de 30 s en Ken Burns, lancée avec `/?film=1`.
- **Audio optionnel** : déposez `ambiance.mp3` (intro) et/ou `film.mp3` (film) dans `static/audio/`. Sans ces fichiers, tout reste muet, sans erreur.
- **Accessibilité** : si l'utilisateur a activé « réduire les animations », tout s'affiche immédiatement ; sans JavaScript ou sans WebGL, le site fonctionne normalement.

## Personnalisation

- **Logo** : remplacez `static/img/logo.svg` (même nom de fichier) ; il apparaît dans le menu, le pied de page, la barre latérale et les pages de compte.
- **Favicon** : remplacez `static/img/favicon.svg`.
- **Logo PNG** : placez `static/img/logo.png` et remplacez `logo.svg` par `logo.png` dans `templates/partials/navbar.html`, `templates/partials/footer.html` et `templates/auth_base.html`.
- Après un changement, rechargez la page avec **Ctrl + F5**.

---

*Projet académique, ESPRIT, 3IA, Génie logiciel.*
