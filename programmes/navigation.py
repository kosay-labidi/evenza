"""Module « Programmes » dans la barre latérale (fichier propre à la gestion des programmes)."""
from core.navigation import Lien, Module
from core.permissions import peut_organiser

MODULE = Module(
    cle="programmes",
    label="Programmes",
    url_name="programmes:index",
    icone="programmes",
    acces=peut_organiser,
    namespace="programmes",
    description="Séances et horaires de chaque événement.",
    sous_liens=(
        Lien("Séances", "programmes:index", ("index", "seance_creer", "seance_modifier", "seance_supprimer")),
    ),
)
