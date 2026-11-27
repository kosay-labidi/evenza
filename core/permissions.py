"""Règles d'accès partagées par les six gestions (une seule source de vérité).

Ces fonctions sont utilisées :
  - côté serveur, par les mixins de ``core.mixins`` (``ModuleRequiredMixin``, ``ClientRequiredMixin``…) ;
  - pour construire la barre latérale (``core.navigation``).

Le menu et le contrôle d'accès appliquent donc exactement la même règle.
La définition des rôles reste dans le modèle (``Utilisateur.est_admin``, ``est_client``…) ;
ce fichier y ajoute la condition « connecté » et les règles qui portent sur un objet.

Hiérarchie (inchangée) : Administrateur ⊇ Organisateur. Client, Participant et Prestataire
sont des rôles externes distincts. Pour les espaces dédiés à un rôle, l'administrateur
garde toujours l'accès (supervision), comme pour les autres gestions.
"""


# ------------------------------------------------------------------ rôles
def est_connecte(user):
    return bool(user and user.is_authenticated)


def est_administrateur(user):
    """Superutilisateur ou rôle ADMIN."""
    return est_connecte(user) and user.est_admin


def peut_organiser(user):
    """Organisateur ou administrateur (propriété ``est_organisateur`` du modèle Utilisateur)."""
    return est_connecte(user) and user.est_organisateur


def est_client(user):
    """Rôle CLIENT (commanditaire d'un événement auprès de l'agence)."""
    return est_connecte(user) and user.est_client


def est_participant(user):
    """Rôle PARTICIPANT (réserve des billets)."""
    return est_connecte(user) and user.est_participant


def est_prestataire(user):
    """Rôle PRESTATAIRE (fournisseur réservé par l'agence)."""
    return est_connecte(user) and user.est_prestataire


def acces_espace_client(user):
    """Pages réservées aux clients ; l'administrateur y a accès pour la supervision."""
    return est_client(user) or est_administrateur(user)


def acces_espace_participant(user):
    return est_participant(user) or est_administrateur(user)


def acces_espace_prestataire(user):
    return est_prestataire(user) or est_administrateur(user)


# ------------------------------------------------------------------ hiérarchie des comptes
# Rôle MÉTIER (champ ``role``) et privilèges TECHNIQUES (``is_staff`` : accès à l'admin Django,
# ``is_superuser`` : tous les droits) sont distincts et ne s'attribuent jamais l'un par l'autre.
#   niveau 2 : superutilisateur
#   niveau 1 : compte technique (is_staff) sans superutilisateur
#   niveau 0 : tout autre compte, y compris un ADMIN métier
# Un administrateur métier gère les comptes de niveau 0 ; seul un superutilisateur gère les comptes
# techniques et les superutilisateurs (sinon : changement d'e-mail → réinitialisation → prise de contrôle).
def niveau_technique(user):
    return 2 if user.is_superuser else 1 if user.is_staff else 0


def peut_gerer_compte(acteur, cible):
    """Modifier, désactiver, réactiver ou supprimer ``cible`` depuis la gestion des utilisateurs.
    Les garde-fous propres à chaque action (soi-même, dernier admin…) s'ajoutent à cette règle."""
    if not est_administrateur(acteur):
        return False
    return acteur.pk == cible.pk or niveau_technique(cible) == 0 or acteur.is_superuser


# ------------------------------------------------------------------ règles portant sur un objet
def peut_gerer_evenement(user, evenement):
    """Administrateur : tous les événements. Organisateur : seulement ceux qu'il organise."""
    return est_administrateur(user) or (peut_organiser(user) and evenement.organisateur_id == user.id)


def evenements_geres(user):
    """Événements que l'utilisateur a le droit de gérer : tous pour l'admin, les siens pour un organisateur."""
    from evenements.models import Evenement   # import tardif : évite toute dépendance circulaire au chargement

    if not peut_organiser(user):
        return Evenement.objects.none()
    qs = Evenement.objects.select_related("lieu", "categorie")
    return qs if user.est_admin else qs.filter(organisateur=user)


# ------------------------------------------------------------------ préparées, pas encore appliquées
# Ces règles correspondent aux constats de l'audit des rôles. Elles sont testées, mais aucune vue
# ni aucun template ne les utilise encore : leur application relève d'autres gestions ou de
# fichiers partagés (voir le rapport transmis à chaque membre du groupe).
def peut_acceder_admin_django(user):
    """L'admin Django exige ``is_staff`` : un compte ADMIN sans ce drapeau y est refusé.
    À utiliser pour afficher (ou non) le lien « Administration Django »."""
    return est_connecte(user) and user.is_active and user.is_staff


def fiche_prestataire(user):
    """Fiche ``Prestataire`` rattachée au compte (champ ``Prestataire.compte``), ou None."""
    if not est_prestataire(user):
        return None
    from prestataires.models import Prestataire   # import tardif, lecture seule

    return Prestataire.objects.filter(compte=user).first()


def peut_traiter_reservation(user, reservation):
    """Confirmer / annuler une réservation de prestataire : l'admin, l'organisateur de l'événement,
    ou le prestataire concerné (compte rattaché à la fiche réservée)."""
    if peut_gerer_evenement(user, reservation.evenement):
        return True
    return est_prestataire(user) and reservation.prestataire.compte_id == user.id

