# ÉVENZA — Organisation de l'équipe

> Document de travail commun aux six membres du groupe : architecture, répartition des six gestions,
> fichiers de chacun, règles de collaboration Git/GitHub et procédure d'intégration finale.
> Le terme « gestion » est employé ici au sens technique et académique ; dans l'interface, les modules
> portent des intitulés courts (Événements, Participants…).

## Sommaire

1. [Architecture du projet](#1-architecture-du-projet)
2. [Répartition des six gestions](#2-répartition-des-six-gestions)
3. [Fichiers propres à chaque gestion](#3-fichiers-propres-à-chaque-gestion)
4. [Fichiers communs (coordination obligatoire)](#4-fichiers-communs-coordination-obligatoire)
5. [Relations entre les applications](#5-relations-entre-les-applications)
6. [Routes principales](#6-routes-principales)
7. [Rôles et permissions](#7-rôles-et-permissions)
8. [État des CRUD : existant et manquant](#8-état-des-crud--existant-et-manquant)
9. [Conventions de développement d'un module](#9-conventions-de-développement-dun-module)
10. [Procédure GitHub](#10-procédure-github)
11. [Conflits Git et migrations Django](#11-conflits-git-et-migrations-django)
12. [Installation et lancement](#12-installation-et-lancement)
13. [Intégration finale](#13-intégration-finale)

---

## 1. Architecture du projet

```
evenza/
├── evenza/                 # configuration : settings.py, urls.py (un include par application)
├── core/                   # commun : site public, vue d'ensemble, permissions, navigation, mixins
│   ├── permissions.py      #   règles d'accès (peut_organiser, est_administrateur, evenements_geres)
│   ├── navigation.py       #   assemble la barre latérale à partir des <app>/navigation.py
│   ├── mixins.py           #   RoleRequiredMixin, OrganisateurRequiredMixin, ProprietaireEvenementMixin,
│   │                       #   AdminRequiredMixin, ModuleRequiredMixin, SuppressionMixin
│   ├── context_processors.py
│   └── tests.py            #   tests de l'architecture commune (menu, accès, permissions)
├── utilisateurs/           # gestion 1
├── evenements/             # gestion 2
├── participants/           # gestion 3
├── prestataires/           # gestion 4
├── programmes/             # gestion 5
├── ressources/             # gestion 6
├── templates/              # gabarits et composants partagés
│   ├── base.html           #   site public (navbar + footer)
│   ├── app_base.html       #   espace professionnel (barre latérale + barre supérieure)
│   ├── list_base.html      #   page principale / liste d'un module (recherche, filtres, pagination)
│   ├── detail_base.html    #   page de détails
│   ├── form_base.html      #   formulaire d'ajout / de modification
│   ├── confirm_base.html   #   confirmation de suppression
│   ├── auth_base.html      #   pages de compte (connexion, inscription…)
│   └── partials/           #   sidebar, topbar, icon, messages, pagination, search_bar,
│                           #   empty_state, crud_actions, choix_evenement, form_fields, banner…
└── static/                 # CSS (style, dashboard, home, auth), JS, polices, images, vidéos
```

Chaque application de gestion possède : `models.py`, `views.py`, `forms.py`, `urls.py` (avec `app_name`),
`admin.py`, `tests.py`, `navigation.py`, `apps.py`, `migrations/`, `templates/<app>/`.
Un dossier `static/<app>/` peut être créé si un module a besoin de CSS/JS spécifiques (aucun n'en a besoin
aujourd'hui : les composants communs suffisent).

### Deux espaces distincts

| Espace | Gabarit | Pages |
|---|---|---|
| Site public | `base.html` | Accueil, catalogue et détail des événements, réservation de billets, connexion, inscription, À propos, Contact, FAQ |
| Espace professionnel | `app_base.html` | Vue d'ensemble, six modules, espace personnel (Mes billets, Mon profil, Retour au site, Déconnexion) |

### Barre latérale modulaire

Chaque application déclare **son** entrée de menu dans `<app>/navigation.py` :

```python
MODULE = Module(
    cle="programmes",
    label="Programmes",                     # jamais « Gestion des … »
    url_name="programmes:index",            # page d'entrée du module
    icone="programmes",                     # nom défini dans templates/partials/icon.html
    acces=peut_organiser,                   # règle vérifiée AUSSI côté serveur
    namespace="programmes",
    description="Séances, horaires, salles et intervenants de chaque événement.",
    sous_liens=(Lien("Séances", "programmes:index", ("index", "seance_creer", ...)),
                Lien("Intervenants", "programmes:intervenants", ("intervenants", "intervenant_creer"))),
)
```

`core/navigation.py` les lit dans l'ordre fixe `ORDRE_MODULES` et calcule le module actif d'après le
namespace de l'URL. **Ajouter un sous-lien ne demande donc de modifier que le fichier de son application.**

---

## 2. Répartition des six gestions

| # | Gestion | Branche | Application | Responsable |
|---|---|---|---|---|
| 1 | Gestion des utilisateurs | `gestion-utilisateurs` | `utilisateurs/` | Membre 1 — *nom à compléter* |
| 2 | Gestion des événements | `gestion-evenements` | `evenements/` | Membre 2 — *nom à compléter* |
| 3 | Gestion des participants | `gestion-participants` | `participants/` | Membre 3 — *nom à compléter* |
| 4 | Gestion des prestataires | `gestion-prestataires` | `prestataires/` | Membre 4 — *nom à compléter* |
| 5 | Gestion des programmes | `gestion-programmes` | `programmes/` | Membre 5 — *nom à compléter* |
| 6 | Gestion des ressources | `gestion-ressources` | `ressources/` | Membre 6 — *nom à compléter* |

Un **référent intégration** (à désigner) relit les Pull Requests touchant les fichiers communs et réalise
la fusion finale.

---

## 3. Fichiers propres à chaque gestion

Chaque membre peut modifier librement les fichiers de son application :

| Gestion | Fichiers dont le membre est responsable |
|---|---|
| Utilisateurs | `utilisateurs/models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `navigation.py`, `backends.py`, `migrations/`, `templates/utilisateurs/*` |
| Événements | `evenements/models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `navigation.py`, `migrations/`, `templates/evenements/*` |
| Participants | `participants/models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `navigation.py`, `migrations/`, `templates/participants/*` |
| Prestataires | `prestataires/models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `navigation.py`, `migrations/`, `templates/prestataires/*` |
| Programmes | `programmes/models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `navigation.py`, `migrations/`, `templates/programmes/*` |
| Ressources | `ressources/models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `navigation.py`, `services.py`, `migrations/`, `templates/ressources/*` |

Cas partagés à signaler dans la PR :

- `evenements/templates/evenements/evenement_detail.html` affiche aussi les sections Programme,
  Prestataires, Ressources et Participants d'un événement. Le responsable Événements en est propriétaire ;
  les autres membres lui proposent leurs changements de **leur** section.
- `participants/views.py` contient aussi la réservation de billets du site public (`ReservationView`,
  `BilletView`, `MesInscriptionsView`) : toute modification doit garder les tests de billetterie au vert.

---

## 4. Fichiers communs (coordination obligatoire)

Ne les modifier **qu'après accord du groupe** (message sur le canal de l'équipe + relecture du référent) :

| Fichier / dossier | Pourquoi |
|---|---|
| `evenza/settings.py`, `evenza/urls.py` | Configuration globale, une erreur casse tout le projet |
| `core/permissions.py`, `core/mixins.py` | Règles d'accès utilisées par les six gestions |
| `core/navigation.py` | Ordre des modules, espace personnel |
| `core/views.py`, `core/templates/core/*` | Site public et vue d'ensemble (lisent les modèles de plusieurs apps) |
| `core/management/commands/seed_demo.py` | Données de démonstration communes |
| `templates/*.html`, `templates/partials/*` | Gabarits et composants partagés |
| `static/css/*`, `static/js/*`, `static/img/*`, `static/video/*` | Identité visuelle, animations, vidéos |
| `utilisateurs/models.py` (champ `role`, propriétés `est_admin`, `est_organisateur`) | Base de toutes les permissions |
| `evenements/models.py` (modèle `Evenement`) | Clé étrangère des quatre autres gestions |
| `requirements.txt`, `.gitignore`, `README.md`, `ORGANISATION_EQUIPE.md` | Projet commun |

Une nouvelle icône ou un nouveau style ? Proposez-le dans une PR courte et dédiée, séparée de votre CRUD.

---

## 5. Relations entre les applications

```
                     utilisateurs.Utilisateur
                      ▲        ▲          ▲
          organisateur│        │participant│compte (0..1)
                      │        │           │
 evenements.Categorie ─┤   participants.Inscription ──► participants.TypeBillet
 evenements.Lieu ──────┤        │                            │
                      ▼        ▼                            ▼
                     evenements.Evenement  ◄──────────────────┘
                      ▲        ▲          ▲
         seances      │        │reservations       affectations
 programmes.Seance ───┘        │                   └─── ressources.Affectation ──► ressources.Ressource
     └── M2M ── programmes.Intervenant
                   prestataires.Reservation ──► prestataires.Prestataire ── M2M ── prestataires.Service
```

| De | Vers | Type | Suppression |
|---|---|---|---|
| `Evenement.organisateur` | `Utilisateur` | FK | CASCADE |
| `Evenement.categorie`, `Evenement.lieu` | `Categorie`, `Lieu` | FK | PROTECT |
| `TypeBillet.evenement`, `Inscription.evenement` | `Evenement` | FK | CASCADE |
| `Inscription.participant` | `Utilisateur` | FK | CASCADE |
| `Inscription.type_billet` | `TypeBillet` | FK | PROTECT |
| `Avis.inscription` | `Inscription` | 1–1 | CASCADE |
| `Seance.evenement` | `Evenement` | FK (composition) | CASCADE |
| `Seance.intervenants` | `Intervenant` | M2M | — |
| `Prestataire.compte` | `Utilisateur` | 1–1 optionnel | SET_NULL |
| `Reservation.evenement` / `.prestataire` / `.service` | `Evenement` / `Prestataire` / `Service` | FK | CASCADE / PROTECT / PROTECT |
| `Affectation.evenement` / `.ressource` | `Evenement` / `Ressource` | FK | CASCADE / PROTECT |

**Dépendances de code** (toutes à sens unique, aucune circulaire) :

- `participants`, `programmes`, `prestataires`, `ressources` → `evenements.models` (clé étrangère) et `core`.
- `evenements.views` → `participants.models.Inscription` (refus de supprimer un événement avec des réservations actives).
- `core.views` (accueil, vue d'ensemble) → modèles de toutes les applications (lecture seule, pour les chiffres).
- Toutes les applications → `core.mixins`, `core.permissions`, `core.navigation`.

Règle : **ne pas importer les vues d'une autre gestion**. Pour pointer vers une autre gestion, utilisez son
nom d'URL (`{% url 'programmes:seance_creer' e.pk %}`) ; pour une donnée, passez par son modèle.

---

## 6. Routes principales

| Module | Page d'entrée | Autres routes (namespace) |
|---|---|---|
| Vue d'ensemble | `/tableau-de-bord/` → `core:dashboard` | `core:home`, `core:a_propos`, `core:contact`, `core:faq` |
| Utilisateurs | `/comptes/utilisateurs/` → `utilisateurs:utilisateur_liste` | `utilisateur_creer`, `utilisateur_detail`, `utilisateur_modifier`, `utilisateur_supprimer`, `login`, `logout`, `register`, `profil`, `password_reset*` |
| Événements | `/evenements/mes-evenements/` → `evenements:mes_evenements` | `liste` (catalogue public), `detail`, `creer`, `modifier`, `supprimer`, `publier`, `annuler`, `lieux`, `lieu_creer` |
| Participants | `/participants/` → `participants:index` | `liste` (inscrits d'un événement), `checkin`, `type_creer`, `reserver`, `inscrire`, `annuler`, `avis`, `billet`, `mes_inscriptions` |
| Programmes | `/programmes/` → `programmes:index` | `seance_creer`, `seance_modifier`, `seance_supprimer`, `intervenants`, `intervenant_creer` |
| Prestataires | `/prestataires/` → `prestataires:liste` | `creer`, `reserver`, `reservation_statut` |
| Ressources | `/ressources/` → `ressources:liste` | `creer`, `detail`, `modifier`, `supprimer`, `affectations`, `affecter`, `affectation_modifier`, `affectation_supprimer` |

Toutes les pages d'entrée sont **accessibles directement depuis le menu** : il n'est plus nécessaire de
passer par la page d'un événement pour gérer les participants, les séances, les réservations de
prestataires ou les affectations de ressources (sélecteur d'événement intégré au module).

---

## 7. Rôles et permissions

### Correspondance acteurs UML ↔ rôles Django

Le rôle est le champ `Utilisateur.role` (`TextChoices`), qui remplace la généralisation du diagramme de classes.

| Acteur (cas d'utilisation) | Rôle Django | Inscription publique | Héritage |
|---|---|---|---|
| Administrateur | `ADMIN` (ou `is_superuser`) | non (créé par l'admin) | ⊇ Organisateur (`est_admin` ⇒ `est_organisateur`) |
| Organisateur | `ORGANISATEUR` | oui | — |
| Participant | `PARTICIPANT` (défaut) | oui | — |
| Client | `CLIENT` | oui | — |
| Prestataire | `PRESTATAIRE` | non (créé par l'admin, lié via `Prestataire.compte`) | — |

Les cinq acteurs existent bien dans le code. Aucune règle d'héritage n'a été modifiée et aucun rôle n'a été ajouté.

### Accès aux modules (menu **et** contrôle serveur)

| Module | Admin | Organisateur | Participant | Client | Prestataire | Règle |
|---|:-:|:-:|:-:|:-:|:-:|---|
| Vue d'ensemble | ✓ | ✓ | ✓ | ✓ | ✓ | `est_connecte` |
| Événements | ✓ | ✓ (ses événements) | — | — | — | `peut_organiser` + `ProprietaireEvenementMixin` |
| Participants | ✓ | ✓ (ses événements) | — | — | — | `peut_organiser` + `evenements_geres()` |
| Programmes | ✓ | ✓ (ses événements) | — | — | — | idem |
| Prestataires | ✓ | ✓ | — | — | — | `peut_organiser` (annuaire partagé) |
| Ressources | ✓ | ✓ | — | — | — | `peut_organiser` (catalogue partagé) |
| Utilisateurs | ✓ | — | — | — | — | `est_administrateur` |
| Mes billets, Mon profil | ✓ | ✓ | ✓ | ✓ | ✓ | `est_connecte` |

- Toutes les vues de gestion sont protégées par un mixin (`OrganisateurRequiredMixin`,
  `ProprietaireEvenementMixin`, `AdminRequiredMixin`, `ModuleRequiredMixin`) : un utilisateur non autorisé
  reçoit une **403**, un visiteur anonyme est redirigé vers la connexion.
- Les données sont filtrées côté serveur : un organisateur ne voit et ne modifie que ses événements
  (et leurs séances, inscrits, réservations, affectations) ; l'administrateur voit tout.
- `core/tests.py` vérifie ces règles pour les cinq rôles.

### Points à décider par le groupe

- **Client** et **Prestataire** n'ont pas encore de fonctionnalités dédiées : ils disposent du même espace
  qu'un participant (vue d'ensemble, billets, profil). Les cas d'utilisation correspondants (ex. « consulter
  mes demandes de réservation » pour un prestataire, « demander l'organisation d'un événement » pour un
  client) restent à développer par les gestions concernées (voir §8).
- Les référentiels **Lieux, Intervenants, Prestataires, Ressources** sont partagés entre organisateurs :
  tout organisateur peut les modifier. C'est le comportement existant ; à confirmer.

---

## 8. État des CRUD : existant et manquant

Légende : ✓ existant et testé · ◐ partiel · ✗ manquant (à développer par le responsable de la gestion).

### 1. Utilisateurs (`utilisateurs`)

| Objet | Liste | Ajout | Détails | Modification | Suppression | Recherche / filtres / pagination |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Utilisateur (admin) | ✓ | ✓ | ✓ | ✓ | ✓ (garde-fous) | ✓ / ✓ rôle / ✓ |
| Profil (soi-même) | — | ✓ inscription | ✓ | ✓ | ✗ | — |

Manquant : changement de mot de passe depuis le profil (seul « mot de passe oublié » existe), activation /
désactivation rapide depuis la liste, suppression de son propre compte.

### 2. Événements (`evenements`)

| Objet | Liste | Ajout | Détails | Modification | Suppression | Recherche / filtres / pagination |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Événement | ✓ catalogue public + « Mes événements » | ✓ | ✓ | ✓ | ✓ (refus si réservations) | ✓ catalogue / ✗ dans « Mes événements » |
| Publication / annulation | — | — | — | ✓ | — | — |
| Lieu | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Catégorie | ✗ | ✗ | ✗ | ✗ | ✗ | (admin Django uniquement) |

Manquant : recherche, filtre par statut et pagination dans « Mes événements » ; CRUD complet des lieux et
des catégories ; passage au statut « Terminé ».

### 3. Participants (`participants`)

| Objet | Liste | Ajout | Détails | Modification | Suppression | Recherche / filtres / pagination |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Inscription | ✓ par événement, ✓ « Mes billets », ◐ page d'entrée (synthèse par événement) | ✓ réservation 3 étapes | ✓ billet QR | ✗ (côté organisateur) | ◐ annulation par le participant | ◐ recherche page d'entrée |
| Check-in | — | ✓ | — | — | — | — |
| Type de billet | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Avis | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |

Manquant : liste globale des inscrits avec filtres (statut, événement), modification / annulation d'une
inscription par l'organisateur, CRUD des types de billets, liste et modération des avis.
**Ne pas modifier** `Inscription.inscrire()` / `annuler()` sans relancer les tests (verrous, liste d'attente).

### 4. Prestataires (`prestataires`)

| Objet | Liste | Ajout | Détails | Modification | Suppression | Recherche / filtres / pagination |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Prestataire | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Service | ✗ | ✗ | ✗ | ✗ | ✗ | (admin Django uniquement) |
| Réservation | ◐ (sur la page de l'événement) | ✓ (depuis le module ou l'événement) | ✗ | ◐ statut (confirmer ; annuler sans bouton) | ✗ | ✗ |

Manquant : détails / modification / suppression d'un prestataire, CRUD des services, liste des
réservations dans le module, bouton d'annulation, espace du rôle Prestataire (ses demandes).

### 5. Programmes (`programmes`)

| Objet | Liste | Ajout | Détails | Modification | Suppression | Recherche / filtres / pagination |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Séance | ◐ page d'entrée (par événement + prochaines séances) | ✓ | ✗ | ✓ | ✓ | ◐ recherche / ✗ / ✓ |
| Intervenant | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |

Manquant : page de détails d'une séance, liste complète des séances filtrable, message de succès après
modification/suppression, détails / modification / suppression des intervenants.

### 6. Ressources (`ressources`)

| Objet | Liste | Ajout | Détails | Modification | Suppression | Recherche / filtres / pagination |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Ressource | ✓ | ✓ | ✓ | ✓ | ✓ (refus si affectée) | ✗ |
| Affectation | ✓ | ✓ (depuis le module ou l'événement) | ◐ (via la ressource) | ✓ | ✓ | ✓ filtres / ✓ |

Manquant : recherche et filtre par type dans le catalogue, pagination du catalogue.

---

## 9. Conventions de développement d'un module

**Nommage**

| Élément | Convention | Exemple |
|---|---|---|
| Vues | `<Objet>ListView`, `<Objet>DetailView`, `<Objet>CreateView`, `<Objet>UpdateView`, `<Objet>DeleteView` | `IntervenantUpdateView` |
| Templates | `<app>/<objet>_list.html`, `_detail.html`, `_form.html`, `_confirm_delete.html` | `programmes/intervenant_detail.html` |
| Noms d'URL (nouveaux) | `<objet>_liste`, `<objet>_detail`, `<objet>_creer`, `<objet>_modifier`, `<objet>_supprimer` | `programmes:intervenant_modifier` |
| Chemins | `<objet>/`, `<objet>/<int:pk>/`, `<objet>/nouveau/`, `<objet>/<int:pk>/modifier/`, `<objet>/<int:pk>/supprimer/` | `intervenants/3/modifier/` |
| Page d'entrée | nom `index` (ou existant conservé) | `participants:index` |

Les noms d'URL existants (`evenements:liste`, `ressources:creer`…) sont **conservés** : ils sont utilisés par
les templates et les tests. Ne pas les renommer.

**Squelette d'une page CRUD**

```python
# views.py
from core.mixins import OrganisateurRequiredMixin, SuppressionMixin

class IntervenantUpdateView(OrganisateurRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Intervenant
    form_class = IntervenantForm
    success_message = "« %(nom)s » a été modifié."
    success_url = reverse_lazy("programmes:intervenants")

class IntervenantDeleteView(OrganisateurRequiredMixin, SuppressionMixin, DeleteView):
    model = Intervenant
    success_url = reverse_lazy("programmes:intervenants")
```

```django
{# templates/programmes/intervenant_list.html #}
{% extends "list_base.html" %}{% block title %}Intervenants{% endblock %}
{% block heading %}Intervenants{% endblock %}
{% block page_actions %}<a class="btn primary" href="{% url 'programmes:intervenant_creer' %}">+ Nouvel intervenant</a>{% endblock %}
{% block list %}
  {% for i in object_list %}…
     {% url 'programmes:intervenant_modifier' i.pk as u_mod %}{% url 'programmes:intervenant_supprimer' i.pk as u_sup %}
     {% include "partials/crud_actions.html" with modifier=u_mod supprimer=u_sup %}
  {% empty %}{% include "partials/empty_state.html" with icone="programmes" titre="Aucun intervenant" %}{% endfor %}
{% endblock %}
```

- Formulaire : `{% extends "form_base.html" %}` (blocs `eyebrow`, `heading`, `submit`, `cancel`).
- Suppression : `{% extends "confirm_base.html" %}` (bloc `details`) + `SuppressionMixin` côté vue.
- Messages : `messages.success / error` ou `SuccessMessageMixin` — affichés par `partials/messages.html`.
- Recherche : paramètre GET `q` (+ variable de contexte `q`) ; filtres supplémentaires dans le bloc `filters`
  et la variable `filtres` (paramètres GET sans `page`) pour la pagination.
- Permissions : toujours un mixin sur la vue **et** filtrer le queryset (`evenements_geres(user)`).
- Pour une action liée à un événement depuis la page du module : `partials/choix_evenement.html`.
- Intitulés : jamais « Gestion des … » dans les titres, menus et boutons.
- Tests : chaque nouvelle vue a au moins un test d'accès autorisé et un test de refus (403).

---

## 10. Procédure GitHub

> Les branches ne sont pas créées automatiquement : chaque membre crée la sienne au début du travail.

### Mise en place (une fois)

```bash
git clone https://github.com/kosay-labidi/evenza.git
cd evenza
git checkout main && git pull origin main
git checkout -b gestion-programmes          # remplacer par sa propre branche
git push -u origin gestion-programmes
```

### Cycle quotidien

```bash
git checkout gestion-programmes
git fetch origin
git merge origin/main                        # récupérer le travail déjà intégré (voir §11 en cas de conflit)

# … développer dans SON application …

python manage.py check
python manage.py makemigrations programmes    # seulement si models.py a changé, et seulement pour son app
python manage.py makemigrations --check --dry-run
python manage.py test

git status                                   # vérifier qu'aucun fichier commun n'est modifié par erreur
git add programmes/
git commit -m "programmes: CRUD des intervenants (détail, modification, suppression)"
git push
```

### Messages de commit

Format `<app>: <action au présent>` — ex. `participants: liste globale des inscrits avec filtre par statut`,
`commun: ajout de l'icône « calendrier » dans partials/icon.html`.

### Pull Request

1. Sur GitHub : **New pull request** → base `main` ← compare `gestion-<module>`.
2. Titre : `[Programmes] CRUD intervenants`.
3. Description : ce qui a été fait, captures d'écran, migrations ajoutées, fichiers communs touchés (et pourquoi),
   résultat de `python manage.py test`.
4. Au moins **un relecteur** d'une autre gestion + le référent intégration si un fichier commun est modifié.
5. Fusion par le référent (« Squash and merge » ou « Create a merge commit », au choix du groupe) uniquement si
   les trois vérifications passent.
6. Après fusion, chaque membre fait `git merge origin/main` dans sa branche.

### Interdits

- `git push --force` sur `main` ou sur la branche d'un autre membre.
- Committer `db.sqlite3`, `media/`, `venv/`, `.venv/`, `.env` (déjà dans `.gitignore`).
- Modifier ou supprimer une migration déjà poussée sur `main`.
- Modifier les fichiers d'une autre gestion sans accord de son responsable.

---

## 11. Conflits Git et migrations Django

### Résoudre un conflit Git

```bash
git fetch origin
git merge origin/main
# Git liste les fichiers en conflit : les ouvrir, garder les DEUX contributions quand c'est possible,
# supprimer les marqueurs <<<<<<< ======= >>>>>>>
git add <fichiers résolus>
python manage.py check && python manage.py test
git commit                                   # termine la fusion
git push
```

Fichiers où des conflits sont probables : `evenement_detail.html`, `templates/partials/*`, `static/css/dashboard.css`,
`core/views.py`. En cas de doute, appeler le responsable du fichier plutôt que d'écraser sa version.
Pour annuler une fusion qui tourne mal (avant le commit) : `git merge --abort`.

### Migrations

- Chaque membre ne crée des migrations **que pour son application** : `python manage.py makemigrations <app>`.
- Ne jamais modifier, renommer ou supprimer une migration déjà présente sur `main`.
- Ne jamais réinitialiser la base partagée ; `db.sqlite3` reste local (non versionné).
  Données de test : `python manage.py seed_demo` (ou `--reset` pour repartir de zéro **en local**).
- Si deux branches ajoutent une migration à la **même** application (ex. deux `0005_…`), après la fusion :
  ```bash
  python manage.py makemigrations --merge <app>
  python manage.py migrate
  python manage.py test
  ```
- Une migration qui dépend d'une autre application (nouvelle FK vers `Evenement`, par exemple) doit être
  fusionnée **après** la migration dont elle dépend : le signaler dans la PR.
- Avant chaque PR : `python manage.py makemigrations --check --dry-run` doit afficher « No changes detected ».

---

## 12. Installation et lancement

```bash
git clone https://github.com/kosay-labidi/evenza.git
cd evenza
python -m venv venv
venv\Scripts\activate                 # Windows  (macOS / Linux : source venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo            # comptes de démonstration (voir README)
python manage.py runserver
```

- Site public : http://127.0.0.1:8000/
- Espace professionnel : http://127.0.0.1:8000/tableau-de-bord/ (après connexion)
- Administration Django : http://127.0.0.1:8000/admin/

---

## 13. Intégration finale

1. **Gel des fonctionnalités** : date fixée par le groupe ; après cette date, uniquement des corrections.
2. Chaque membre met sa branche à jour (`git merge origin/main`), relance les trois vérifications et ouvre sa PR.
3. **Ordre de fusion recommandé** (suit les dépendances des modèles) :
   1. `gestion-utilisateurs`
   2. `gestion-evenements`
   3. `gestion-participants`
   4. `gestion-programmes`
   5. `gestion-prestataires`
   6. `gestion-ressources`
4. Après **chaque** fusion, sur `main` :
   ```bash
   git pull origin main
   python manage.py migrate
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py test
   ```
   Les branches restantes intègrent `main` avant leur propre fusion.
5. **Recette finale** avec `seed_demo` : parcours visiteur (accueil, catalogue, réservation, billet), parcours
   organisateur (créer, publier, programme, prestataire, ressource, check-in), parcours administrateur
   (utilisateurs), et vérification du menu pour chacun des cinq rôles.
6. Mise à jour du README (fonctionnalités, nombre de tests) et étiquette de version (`git tag v1.0`) une fois
   la recette validée par le groupe.
