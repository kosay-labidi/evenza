"""Catalogue des rôles pour l'interface (aperçu des permissions, confirmation du changement de rôle, fiche).

Aucune deuxième source de vérité : les modules accessibles sont CALCULÉS en simulant un compte de chaque
rôle et en interrogeant les mêmes fonctions que le menu et les contrôles serveur (``core.navigation``,
``core.permissions``). Seuls les textes de présentation (description, responsabilités, restrictions)
sont rédigés ici. Les règles « préparées » de core.permissions (pas encore utilisées par une vue) sont
signalées comme telles, jamais présentées comme des fonctionnalités disponibles.
"""
from core import navigation, permissions

from .models import Utilisateur

R = Utilisateur.Role

# Textes de présentation uniquement (aucune règle d'accès ici).
TEXTES = {
    R.ADMIN: {
        "description": "Administration et supervision de toute la plateforme.",
        "niveau": "Élevé · supervision",
        "fonctions": ["Gère les comptes, les rôles et les accès (hors comptes techniques protégés)",
                      "Voit et gère tous les événements, inscriptions, prestataires et ressources",
                      "Garde l'accès aux espaces des autres rôles pour la supervision"],
        "restrictions": ["Le rôle Administrateur est un rôle métier : il ne donne pas l'accès à l'administration "
                         "Django (drapeau technique « is_staff » distinct)",
                         "Ne peut ni se désactiver ni retirer son propre rôle d'administrateur",
                         "Le dernier administrateur actif ne peut pas être désactivé ni rétrogradé"],
    },
    R.ORGANISATEUR: {
        "description": "Gestion de ses propres événements et des modules associés.",
        "niveau": "Intermédiaire · ses événements",
        "fonctions": ["Crée et gère ses événements, leur programme et leurs types de billets",
                      "Suit les inscrits, la liste d'attente et le contrôle d'entrée de ses événements",
                      "Réserve des prestataires et affecte des ressources à ses événements"],
        "restrictions": ["N'agit que sur les événements qu'il organise",
                         "Aucun accès à la gestion des utilisateurs"],
    },
    R.CLIENT: {
        "description": "Commanditaire : confie l'organisation de son événement à l'agence.",
        "niveau": "Externe · espace personnel",
        "fonctions": ["Se connecte, gère son profil et peut réserver des billets comme tout compte"],
        "restrictions": ["Aucun module de gestion de l'agence"],
    },
    R.PARTICIPANT: {
        "description": "Participation aux événements et réservation de billets.",
        "niveau": "Externe · espace personnel",
        "fonctions": ["Réserve, modifie et annule ses billets", "Présente son QR code à l'entrée",
                      "Donne un avis après l'événement"],
        "restrictions": ["Aucun module de gestion de l'agence"],
    },
    R.PRESTATAIRE: {
        "description": "Fournisseur de prestations (traiteur, son, lumière…) réservé par l'agence.",
        "niveau": "Externe · espace personnel",
        "fonctions": ["Se connecte et gère son profil ; peut être rattaché à une fiche prestataire"],
        "restrictions": ["Aucun module de gestion de l'agence"],
    },
}

# Règles de core.permissions écrites et testées, mais utilisées par aucune vue (voir ce fichier).
PREPAREES = {
    R.PRESTATAIRE: ["Confirmer ou annuler ses propres réservations (peut_traiter_reservation) : règle prête, "
                    "aucune page ne l'utilise encore"],
}


def _compte_fictif(role):
    """Compte NON enregistré, actif, sans privilège technique : sert uniquement à évaluer les règles."""
    return Utilisateur(role=role, is_active=True, is_staff=False, is_superuser=False)


def modules_accessibles(role):
    """[(clé, libellé)] des modules de la barre latérale autorisés pour ce rôle (mêmes fonctions que le menu)."""
    u = _compte_fictif(role)
    return [(m.cle, m.label) for m in navigation.modules() if m.acces(u)]


def espace_personnel(role):
    u = _compte_fictif(role)
    return [m.label for m in navigation.espace_personnel() if m.acces(u)]


ESPACES_A_VENIR = {R.CLIENT: "espace client (suivi des demandes)",
                   R.PRESTATAIRE: "espace prestataire (consultation de ses réservations)"}


def espaces_dedies(role):
    """Pages personnelles propres au rôle, déclarées par une gestion (variable ESPACE) : calculé, pas supposé."""
    u = _compte_fictif(role)
    communs = {m.cle for m in navigation.ESPACE_PERSONNEL}
    return [m.label for m in navigation.espace_personnel() if m.cle not in communs and m.acces(u)]


def fiche_role(role):
    """Tout ce que l'interface affiche pour un rôle (dict sérialisable en JSON)."""
    textes = dict(TEXTES[role])
    u = _compte_fictif(role)
    dedies = espaces_dedies(role)
    if role in ESPACES_A_VENIR and not dedies:
        textes["restrictions"] = [*textes["restrictions"],
                                  f"Pas encore d'{ESPACES_A_VENIR[role]} : fonctionnalité future, non disponible"]
    return {
        "code": role, "libelle": R(role).label, **textes, "espaces_dedies": dedies,
        "modules": [libelle for _, libelle in modules_accessibles(role)],
        "espace_personnel": espace_personnel(role),
        "gestion_comptes": permissions.est_administrateur(u),
        "supervision_espaces": permissions.acces_espace_client(u) and role != R.CLIENT,
        "preparees": PREPAREES.get(role, []),
    }


def catalogue():
    return {code: fiche_role(code) for code, _ in R.choices}


def comparer_roles(ancien, nouveau):
    """Modules gagnés / perdus lors d'un changement de rôle (calculés, pas déclarés)."""
    avant = dict(modules_accessibles(ancien))
    apres = dict(modules_accessibles(nouveau))
    return {
        "accordes": [apres[c] for c in apres if c not in avant],
        "retires": [avant[c] for c in avant if c not in apres],
        "conserves": [apres[c] for c in apres if c in avant],
    }


def consequences_changement(compte, nouveau_role):
    """Données d'autres gestions liées au compte, lues SANS rien modifier, et avertissements associés.
    Retourne (donnees, avertissements). Aucun changement automatique n'est fait ailleurs."""
    from django.utils import timezone

    donnees, avertissements = {}, []
    peut_organiser_apres = nouveau_role in (R.ADMIN, R.ORGANISATEUR) or compte.is_superuser
    evts = compte.evenements_organises.all()
    nb_evts = evts.count()
    if nb_evts:
        a_venir = evts.filter(date_fin__gte=timezone.now()).exclude(statut="ANNULE").count()
        donnees["Événements organisés"] = nb_evts
        if not peut_organiser_apres:
            avertissements.append(
                f"Ce compte organise {nb_evts} événement{'s' if nb_evts > 1 else ''}"
                f"{f' (dont {a_venir} à venir)' if a_venir else ''}. Ils restent rattachés à lui, mais il ne pourra "
                "plus les gérer : seuls les administrateurs le pourront. Réattribuez-les depuis la gestion des "
                "événements si nécessaire.")
    nb_insc = compte.inscriptions.exclude(statut="ANNULEE").count()
    if nb_insc:
        donnees["Réservations de billets actives"] = nb_insc
    fiche = getattr(compte, "prestataire", None) if hasattr(compte, "prestataire") else None
    if fiche is not None:
        donnees["Fiche prestataire rattachée"] = str(fiche)
        if nouveau_role != R.PRESTATAIRE:
            avertissements.append(f"Le compte est rattaché à la fiche prestataire « {fiche} ». Le lien est conservé, "
                                  "mais le compte ne sera plus reconnu comme prestataire.")
    return donnees, avertissements
