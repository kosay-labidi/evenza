"""Navigation de l'espace professionnel (barre latérale).

Chaque gestion déclare SON module dans ``<app>/navigation.py`` (variable ``MODULE``) :
un membre de l'équipe modifie uniquement le fichier de son application pour ajouter
un sous-lien, changer l'icône ou la page d'entrée. Ce fichier-ci (commun) se contente
de les rassembler dans un ordre fixe et de calculer l'élément actif.
"""
from dataclasses import dataclass, field
from importlib import import_module
from typing import Callable

from .permissions import est_connecte


@dataclass(frozen=True)
class Lien:
    """Sous-lien affiché sous le module actif. ``urls`` = noms d'URL (du même namespace) qui l'activent."""
    label: str
    url_name: str
    urls: tuple = ()


@dataclass(frozen=True)
class Module:
    cle: str                      # identifiant court (ex. "participants")
    label: str                    # intitulé visible, sans « Gestion des »
    url_name: str                 # page d'entrée du module (nom d'URL avec namespace)
    icone: str                    # nom d'icône de templates/partials/icon.html
    acces: Callable               # fonction(user) -> bool, vérifiée aussi côté serveur
    namespace: str = ""           # namespace d'URL de l'application
    description: str = ""         # texte de la carte sur la vue d'ensemble
    sous_liens: tuple = field(default_factory=tuple)
    urls_actives: tuple = ()      # si renseigné : seuls ces noms d'URL du namespace activent l'élément


# Ordre d'affichage des six gestions dans la barre latérale.
ORDRE_MODULES = ("evenements", "participants", "programmes", "prestataires", "ressources", "utilisateurs")

APERCU = Module("apercu", "Vue d'ensemble", "core:dashboard", "apercu", est_connecte, namespace="core")

# Espace personnel (« Retour au site » et « Déconnexion » sont ajoutés par le template).
ESPACE_PERSONNEL = (
    Module("billets", "Mes billets", "participants:mes_inscriptions", "billet", est_connecte, namespace="participants",
           urls_actives=("mes_inscriptions", "billet", "avis", "reserver", "inscrire", "annuler")),
    Module("profil", "Mon profil", "utilisateurs:profil", "profil", est_connecte, namespace="utilisateurs",
           urls_actives=("profil",)),
)


def modules():
    """Les six modules métier, dans l'ordre, lus depuis ``<app>/navigation.py``."""
    return [import_module(f"{app}.navigation").MODULE for app in ORDRE_MODULES]


def get_module(cle):
    for m in [APERCU, *modules(), *ESPACE_PERSONNEL]:
        if m.cle == cle:
            return m
    raise KeyError(f"Module inconnu : {cle!r}")


def module_actif(request):
    """Clé du module correspondant à la page affichée (ou None)."""
    match = getattr(request, "resolver_match", None)
    if not match:
        return None
    ns, url = match.namespace, match.url_name
    for m in ESPACE_PERSONNEL:                       # d'abord les pages personnelles (plus spécifiques)
        if m.namespace == ns and url in m.urls_actives:
            return m.cle
    if ns == "core" and url == "dashboard":
        return APERCU.cle
    for m in modules():
        if m.namespace == ns:
            return m.cle
    return None


def navigation_pour(request):
    """Structure prête pour le template : seuls les modules autorisés pour l'utilisateur."""
    user = request.user
    actif = module_actif(request)
    url = getattr(getattr(request, "resolver_match", None), "url_name", None)

    def item(m, avec_sous_liens=True):
        sous = []
        if avec_sous_liens and m.cle == actif:
            sous = [{"label": l.label, "url_name": l.url_name, "actif": url in (l.urls or (l.url_name.split(":")[-1],))}
                    for l in m.sous_liens]
        return {"cle": m.cle, "label": m.label, "url_name": m.url_name, "icone": m.icone,
                "description": m.description, "actif": m.cle == actif, "sous_liens": sous}

    principale = [item(APERCU)] + [item(m) for m in modules() if m.acces(user)]
    personnelle = [item(m, avec_sous_liens=False) for m in ESPACE_PERSONNEL if m.acces(user)]
    courant = next((i for i in principale + personnelle if i["actif"]), None)
    return {"principale": principale, "personnelle": personnelle, "actif": courant}
