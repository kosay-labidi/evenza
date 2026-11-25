"""Module « Prestataires » dans la barre latérale (fichier propre à la gestion des prestataires)."""
from core.navigation import Module
from core.permissions import peut_organiser

MODULE = Module(
    cle="prestataires",
    label="Prestataires",
    url_name="prestataires:liste",
    icone="prestataires",
    acces=peut_organiser,
    namespace="prestataires",
    description="Traiteurs, son, lumière, photo : vos partenaires et leurs réservations.",
)
