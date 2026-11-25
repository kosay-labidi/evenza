"""Module « Événements » dans la barre latérale (fichier propre à la gestion des événements)."""
from core.navigation import Lien, Module
from core.permissions import peut_organiser

MODULE = Module(
    cle="evenements",
    label="Événements",
    url_name="evenements:mes_evenements",
    icone="evenements",
    acces=peut_organiser,
    namespace="evenements",
    description="Créez, publiez et pilotez vos événements et leurs lieux.",
    sous_liens=(
        Lien("Mes événements", "evenements:mes_evenements", ("mes_evenements", "modifier", "supprimer")),
        Lien("Nouvel événement", "evenements:creer", ("creer",)),
        Lien("Lieux", "evenements:lieux", ("lieux", "lieu_creer")),
    ),
)
