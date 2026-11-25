"""Module « Ressources » dans la barre latérale (fichier propre à la gestion des ressources)."""
from core.navigation import Lien, Module
from core.permissions import peut_organiser

MODULE = Module(
    cle="ressources",
    label="Ressources",
    url_name="ressources:liste",
    icone="ressources",
    acces=peut_organiser,
    namespace="ressources",
    description="Salles, matériel et véhicules, affectés sans conflit de créneau.",
    sous_liens=(
        Lien("Catalogue", "ressources:liste", ("liste", "creer", "detail", "modifier", "supprimer")),
        Lien("Affectations", "ressources:affectations",
             ("affectations", "affecter", "affectation_modifier", "affectation_supprimer")),
    ),
)
