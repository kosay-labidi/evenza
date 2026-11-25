"""Règles d'accès partagées par les six gestions (une seule source de vérité).

Ces fonctions sont utilisées :
  - côté serveur, par les mixins de ``core.mixins`` (``ModuleRequiredMixin``…) ;
  - pour construire la barre latérale (``core.navigation``).

Le menu et le contrôle d'accès appliquent donc exactement la même règle.
Hiérarchie existante (inchangée) : Administrateur ⊇ Organisateur.
"""


def est_connecte(user):
    return bool(user and user.is_authenticated)


def est_administrateur(user):
    """Superutilisateur ou rôle ADMIN."""
    return est_connecte(user) and user.est_admin


def peut_organiser(user):
    """Organisateur ou administrateur (propriété ``est_organisateur`` du modèle Utilisateur)."""
    return est_connecte(user) and user.est_organisateur


def evenements_geres(user):
    """Événements que l'utilisateur a le droit de gérer : tous pour l'admin, les siens pour un organisateur."""
    from evenements.models import Evenement   # import tardif : évite toute dépendance circulaire au chargement

    if not peut_organiser(user):
        return Evenement.objects.none()
    qs = Evenement.objects.select_related("lieu", "categorie")
    return qs if user.est_admin else qs.filter(organisateur=user)
