# Module Gestion des Événements - ÉVENZA

## 📖 Description

Ce module gère l'ensemble du cycle de vie des événements dans la plateforme ÉVENZA : création, consultation, modification, publication, annulation et suppression.

---

## 🎯 Fonctionnalités

### Pour les Organisateurs

#### Créer un événement
- Remplir le formulaire avec toutes les informations (titre, description, lieu, dates, capacité, prix)
- L'événement est créé en statut **BROUILLON**
- Validations automatiques des données

#### Consulter ses événements
- Tableau de bord avec tous les événements créés
- Statistiques en temps réel (inscrits, recettes, présents)
- Vue 3D interactive (scène)

#### Modifier un événement
- Modifier toutes les informations
- Validations pour protéger l'intégrité des données
- Impossible de réduire la capacité en-dessous du nombre d'inscrits

#### Publier un événement
- Passer du statut BROUILLON à PUBLIÉ
- Rendre l'événement visible au public
- Autoriser les réservations

#### Annuler un événement
- Changer le statut à ANNULÉ
- Bloquer les nouvelles réservations
- L'événement reste visible

#### Supprimer un événement
- Suppression définitive
- Bloqué s'il y a des réservations actives
- Confirmation obligatoire

### Pour les Visiteurs/Participants

#### Consulter le catalogue
- Voir tous les événements publiés
- Recherche par mot-clé
- Filtres: catégorie, ville, date
- Pagination

#### Voir le détail d'un événement
- Toutes les informations
- Programme avec séances
- Types de billets disponibles
- Places restantes
- Bouton de réservation

---

## 📐 Modèles de Données

### Evenement

**Champs principaux:**
```python
titre: CharField(max_length=150)
description: TextField
categorie: ForeignKey(Categorie)
lieu: ForeignKey(Lieu)
organisateur: ForeignKey(User)
date_debut: DateTimeField
date_fin: DateTimeField
capacite: PositiveIntegerField
prix: DecimalField
statut: CharField (BROUILLON, PUBLIE, ANNULE, TERMINE)
affiche: ImageField
```

**Propriétés calculées:**
- `nb_inscrits` - Nombre de places réservées
- `places_restantes` - Places disponibles
- `taux_remplissage` - Pourcentage de remplissage
- `est_complet` - Booléen si complet
- `prix_min` - Prix le plus bas des billets

**Méthodes:**
- `publier()` - Publier l'événement
- `annuler()` - Annuler l'événement
- `clean()` - Validations métier

### Categorie

```python
nom: CharField(max_length=60, unique=True)
image_url: Property (image par défaut)
```

Catégories avec images pré-définies: concert, mariage, conference, gala, festival

### Lieu

```python
nom: CharField(max_length=120)
adresse: CharField(max_length=200)
ville: CharField(max_length=80)
capacite: PositiveIntegerField
```

---

## 🛡️ Règles de Validation

### Création/Modification

1. **Date de fin après date de début**
   ```python
   if date_fin <= date_debut:
       raise ValidationError("La date de fin doit être après la date de début.")
   ```

2. **Capacité limitée par le lieu**
   ```python
   if capacite > lieu.capacite:
       raise ValidationError(f"Le lieu accepte au maximum {lieu.capacite} personnes.")
   ```

3. **Date de début dans le futur (création uniquement)**
   ```python
   if date_debut < timezone.now():
       raise ValidationError("La date de début ne peut pas être dans le passé.")
   ```

4. **Capacité ne peut pas descendre sous les inscrits**
   ```python
   if capacite < nb_inscrits:
       raise ValidationError(f"{nb_inscrits} places sont déjà réservées.")
   ```

### Suppression

- Impossible si des réservations actives existent
- Message d'erreur explicite
- Suggestion d'annuler plutôt que supprimer

---

## 🔒 Permissions

### Matrice des droits

| Action | Anonyme | Participant | Organisateur | Propriétaire | Admin |
|--------|---------|-------------|--------------|--------------|-------|
| Voir liste événements publiés | ✅ | ✅ | ✅ | ✅ | ✅ |
| Voir détail événement publié | ✅ | ✅ | ✅ | ✅ | ✅ |
| Voir brouillon | ❌ | ❌ | ❌ | ✅ | ✅ |
| Créer événement | ❌ | ❌ | ✅ | ✅ | ✅ |
| Modifier événement | ❌ | ❌ | ❌ | ✅ | ✅ |
| Supprimer événement | ❌ | ❌ | ❌ | ✅ | ✅ |
| Publier/Annuler | ❌ | ❌ | ❌ | ✅ | ✅ |

**Mixins utilisés:**
- `OrganisateurRequiredMixin` - Rôle organisateur requis
- `ProprietaireEvenementMixin` - Propriétaire de l'événement requis

---

## 🌐 URLs

```python
# Liste et consultation
/evenements/                              # Liste des événements publiés
/evenements/<int:pk>/                     # Détail d'un événement
/evenements/mes-evenements/               # Dashboard organisateur

# CRUD
/evenements/nouveau/                      # Créer un événement
/evenements/<int:pk>/modifier/            # Modifier un événement
/evenements/<int:pk>/supprimer/           # Supprimer un événement

# Actions
/evenements/<int:pk>/publier/             # Publier un événement
/evenements/<int:pk>/annuler/             # Annuler un événement

# Lieux
/evenements/lieux/                        # Liste des lieux
/evenements/lieux/nouveau/                # Créer un lieu
```

---

## 🎨 Templates

### Structure

```
templates/evenements/
├── evenement_list.html           # Liste avec recherche et filtres
├── evenement_detail.html         # Page détail complète
├── evenement_form.html           # Formulaire création/modification
├── evenement_confirm_delete.html # Confirmation suppression
├── mes_evenements.html           # Dashboard organisateur (scène 3D)
├── lieu_list.html                # Liste des lieux
├── lieu_form.html                # Formulaire lieu
└── _carte.html                   # Composant carte événement
```

### Composants réutilisables

**Carte événement (`_carte.html`)**
```html
{% include "evenements/_carte.html" with e=evenement %}
```

---

## 🧪 Tests

### Lancer les tests

```bash
# Tous les tests du module
python manage.py test evenements

# Tests avec verbosité
python manage.py test evenements -v 2

# Test spécifique
python manage.py test evenements.tests.EvenementCRUDTestCase
```

### Couverture des tests

- ✅ Création avec validations
- ✅ Consultation et filtres
- ✅ Modification avec permissions
- ✅ Suppression avec protection
- ✅ Changements de statut
- ✅ Visibilité selon statut et propriétaire
- ✅ Règles métier

---

## 📊 Exemples d'Utilisation

### Dans une vue

```python
from evenements.models import Evenement

# Récupérer les événements publiés
evenements = Evenement.objects.publies()

# Avec optimisations
evenements = Evenement.objects.publies().select_related('lieu', 'categorie')

# Filtrer par catégorie
concerts = Evenement.objects.filter(categorie__nom="Concert")

# Recherche
resultats = Evenement.objects.filter(
    Q(titre__icontains="jazz") | 
    Q(description__icontains="jazz")
)
```

### Dans un template

```html
{% for evenement in evenements %}
  <div class="card">
    <h3>{{ evenement.titre }}</h3>
    <p>{{ evenement.date_debut|date:"d/m/Y H:i" }}</p>
    <p>{{ evenement.places_restantes }} places restantes</p>
    <span class="badge">{{ evenement.get_statut_display }}</span>
  </div>
{% endfor %}
```

### Créer un événement programmatiquement

```python
from evenements.models import Evenement, Categorie, Lieu
from utilisateurs.models import Utilisateur
from django.utils import timezone
from datetime import timedelta

# Récupérer les objets liés
categorie = Categorie.objects.get(nom="Concert")
lieu = Lieu.objects.get(nom="Salle Principale")
organisateur = Utilisateur.objects.get(username="jean")

# Créer l'événement
evenement = Evenement.objects.create(
    titre="Concert de Jazz",
    description="Une soirée exceptionnelle",
    categorie=categorie,
    lieu=lieu,
    organisateur=organisateur,
    date_debut=timezone.now() + timedelta(days=30),
    date_fin=timezone.now() + timedelta(days=30, hours=3),
    capacite=200,
    prix=50.00
)

# Publier
evenement.publier()
```

---

## 🔧 Configuration

### Settings requis

```python
# django settings
INSTALLED_APPS = [
    ...
    'evenements',
]

# Pour les images
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
```

### Dépendances

- Django >= 4.2
- Pillow (pour les images)
- Module `utilisateurs` (authentification)
- Module `core` (mixins)

---

## 📈 Optimisations

### Requêtes

Les vues utilisent systématiquement:
- `select_related()` pour les FK (lieu, categorie, organisateur)
- `prefetch_related()` pour les relations inverses (seances, types_billet)
- `annotate()` pour les calculs (nb_inscrits, recettes)

### Cache

Propriétés calculées cachées sur l'instance:
- `nb_inscrits`
- `places_restantes`
- `taux_remplissage`

### Index

Index définis sur:
- `statut` (filtres fréquents)
- `date_debut` (tri et filtres)
- `organisateur_id` (dashboard)

---

## 🐛 Dépannage

### Problème: Date dans le passé refusée pour modification

**Solution**: La validation ne s'applique qu'à la création. Pour modifier un événement en cours, la date peut être dans le passé.

### Problème: Impossible de supprimer un événement

**Solution**: Vérifier s'il y a des réservations actives. Annuler l'événement plutôt que le supprimer.

### Problème: Brouillon invisible

**Solution**: Les brouillons ne sont visibles que par leur propriétaire et les admins. Publier l'événement pour le rendre public.

---

## 📞 Support

Pour toute question ou problème:
1. Consulter ce README
2. Vérifier les tests unitaires pour des exemples
3. Consulter la documentation Django
4. Contacter l'équipe de développement

---

## 📄 Licence

Projet ÉVENZA - Sprint 1
