"""Règles de sécurité propres à la gestion des utilisateurs.

1. Limitation des tentatives (cache Django, aucune table ni dépendance en plus), réutilisée pour la
   connexion et pour les demandes de réinitialisation du mot de passe. Le blocage est temporaire :
   il expire seul après ``DUREE_BLOCAGE`` secondes (fenêtre fixe à partir de la première tentative).
   Limite connue : le cache par défaut (LocMemCache) est propre à chaque processus serveur.
2. Garde-fous des comptes administrateurs : ne pas se désactiver ni se rétrograder soi-même,
   ne jamais perdre le dernier administrateur actif. Utilisés par les formulaires de l'application
   ET par l'administration Django (utilisateurs/admin.py).
3. Origine de confiance des liens envoyés par e-mail (réinitialisation du mot de passe).
"""
import hashlib
import os
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

DUREE_BLOCAGE = 15 * 60      # durée de la fenêtre et du blocage, en secondes

# action -> (maximum par identifiant, maximum par adresse IP), sur DUREE_BLOCAGE
LIMITES = {
    "connexion": (5, 20),            # échecs de connexion
    "reinitialisation": (3, 10),     # demandes de lien « mot de passe oublié » (réussies ou non)
}
MAX_ECHECS_COMPTE, MAX_ECHECS_IP = LIMITES["connexion"]   # noms historiques, utilisés par les tests


# ---------------------------------------------------------------- limitation des tentatives
def _ip(request):
    return request.META.get("REMOTE_ADDR") or "inconnue"   # pas X-Forwarded-For : falsifiable par le client


def _cles(action, request, identifiant):
    ident = hashlib.sha256((identifiant or "").strip().lower().encode()).hexdigest()[:32]
    if action == "reinitialisation":
        # par e-mail quelle que soit l'IP (protège la boîte du destinataire), et par IP (protège le service)
        return f"evenza:{action}:email:{ident}", f"evenza:{action}:ip:{_ip(request)}"
    return f"evenza:{action}:{_ip(request)}:{ident}", f"evenza:{action}:ip:{_ip(request)}"


def limite_atteinte(action, request, identifiant):
    max_ident, max_ip = LIMITES[action]
    cle_ident, cle_ip = _cles(action, request, identifiant)
    return cache.get(cle_ident, 0) >= max_ident or cache.get(cle_ip, 0) >= max_ip


def compter_tentative(action, request, identifiant):
    for cle in _cles(action, request, identifiant):
        cache.add(cle, 0, DUREE_BLOCAGE)        # crée le compteur avec son délai d'expiration
        try:
            cache.incr(cle)
        except ValueError:                      # expiré entre add() et incr()
            cache.set(cle, 1, DUREE_BLOCAGE)


def connexion_bloquee(request, identifiant):
    return limite_atteinte("connexion", request, identifiant)


def enregistrer_echec(request, identifiant):
    compter_tentative("connexion", request, identifiant)


def reinitialiser_echecs(request, identifiant):
    """Après une connexion réussie. Le compteur par IP est conservé (sinon un compte valide
    permettrait de remettre à zéro une attaque sur d'autres identifiants)."""
    cache.delete(_cles("connexion", request, identifiant)[0])


# ---------------------------------------------------------------- comptes administrateurs
def est_admin_actif(user):
    return user.is_active and user.est_admin   # définition du rôle : Utilisateur.est_admin


def admins_actifs():
    """Comptes administrateurs actifs (même définition que ``Utilisateur.est_admin``, en SQL)."""
    from .models import Utilisateur
    return Utilisateur.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(role=Utilisateur.Role.ADMIN))


def autre_admin_actif_existe(user):
    return admins_actifs().exclude(pk=user.pk).exists()


def motif_refus_changement(acteur, compte, *, is_active=None, role=None, is_superuser=None):
    """Pourquoi ce changement de statut ou de privilèges est refusé (None s'il est permis).

    ``compte`` porte les valeurs AVANT le changement ; un paramètre laissé à None reste inchangé.
    Ne vérifie pas QUI peut gérer ce compte (voir ``core.permissions.peut_gerer_compte``).
    """
    if not compte.pk:
        return None
    actif = compte.is_active if is_active is None else is_active
    superu = compte.is_superuser if is_superuser is None else is_superuser
    nouveau_role = compte.role if role is None else role
    restera_admin = actif and (superu or nouveau_role == compte.Role.ADMIN)
    soi_meme = acteur is not None and acteur.pk == compte.pk
    if soi_meme and compte.is_active and not actif:
        return "Vous ne pouvez pas désactiver votre propre compte."
    if soi_meme and compte.is_superuser and not superu:
        return "Vous ne pouvez pas retirer vos propres droits de superutilisateur."
    if soi_meme and est_admin_actif(compte) and not restera_admin:
        return "Vous ne pouvez pas retirer votre propre rôle d'administrateur."
    if est_admin_actif(compte) and not restera_admin and not autre_admin_actif_existe(compte):
        return "Impossible : c'est le dernier administrateur actif de la plateforme."
    return None


def motif_refus_desactivation(cible, acteur):
    """Message expliquant pourquoi ``acteur`` ne peut pas désactiver ``cible`` (None si autorisé)."""
    if cible.pk == acteur.pk:
        return "Vous ne pouvez pas désactiver votre propre compte."
    if not cible.is_active:
        return f"Le compte « {cible.username} » est déjà désactivé."
    return motif_refus_changement(acteur, cible, is_active=False)


def motif_refus_reactivation(cible):
    if cible.is_active:
        return f"Le compte « {cible.username} » est déjà actif."
    return None


# ---------------------------------------------------------------- suppression physique
def donnees_d_autrui(compte):
    """Données appartenant à D'AUTRES utilisateurs qui disparaîtraient en cascade avec ce compte :
    inscriptions (billets) d'autres participants aux événements qu'il organise, et réservations
    de prestataires sur ces événements. Lecture seule, via les relations inverses (aucun import)."""
    evenements = compte.evenements_organises.all()
    Inscription = compte.inscriptions.model
    Reservation = evenements.model._meta.get_field("reservations").related_model
    inscriptions = Inscription.objects.filter(evenement__in=evenements).exclude(participant=compte)
    reservations = Reservation.objects.filter(evenement__in=evenements)
    return {"inscriptions": inscriptions.count(), "reservations": reservations.count()}


def motif_refus_suppression(cible, acteur):
    if acteur is not None and cible.pk == acteur.pk:
        return "Vous ne pouvez pas supprimer votre propre compte."
    if est_admin_actif(cible) and not autre_admin_actif_existe(cible):
        return "Impossible : c'est le dernier administrateur actif de la plateforme."
    autrui = donnees_d_autrui(cible)
    if autrui["inscriptions"] or autrui["reservations"]:
        return (f"Suppression impossible : elle effacerait aussi {autrui['inscriptions']} inscription(s) d'autres "
                f"participants et {autrui['reservations']} réservation(s) de prestataires liées aux événements "
                f"de « {cible.username} ». Désactivez plutôt ce compte : rien ne sera perdu.")
    return None


# ---------------------------------------------------------------- origine de confiance des liens
HOTES_LOCAUX = {"localhost", "127.0.0.1", "[::1]", "testserver"}   # testserver : client de test de Django
VARIABLE_URL_PUBLIQUE = "EVENZA_URL_PUBLIQUE"                     # ex. https://www.mon-domaine.tn


def origine_de_confiance(request):
    """(protocole, hôte) à utiliser dans les liens envoyés par e-mail, ou None si aucune origine sûre.

    1. ``settings.EVENZA_URL_PUBLIQUE`` ou la variable d'environnement du même nom (déploiement) ;
    2. sinon, uniquement en local : l'hôte de la requête s'il désigne cette machine.
    L'en-tête Host d'une requête n'est jamais repris tel quel pour un autre hôte.
    """
    url = (getattr(settings, VARIABLE_URL_PUBLIQUE, "") or os.environ.get(VARIABLE_URL_PUBLIQUE, "")).strip()
    if url:
        morceaux = urlsplit(url)
        if morceaux.scheme in ("http", "https") and morceaux.netloc and not morceaux.path.strip("/"):
            return morceaux.scheme, morceaux.netloc
        return None                                   # valeur mal formée : on refuse plutôt que deviner
    try:
        hote = request.get_host()                     # déjà validé par ALLOWED_HOSTS
    except Exception:                                 # DisallowedHost
        return None
    nom = hote.rsplit(":", 1)[0] if not hote.startswith("[") else hote.split("]")[0] + "]"
    if nom in HOTES_LOCAUX:
        return request.scheme, hote
    return None
