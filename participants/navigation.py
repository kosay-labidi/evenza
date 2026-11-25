"""Module « Participants » dans la barre latérale (fichier propre à la gestion des participants).

Les pages personnelles du participant (Mes billets, billet, réservation, avis) relèvent de
l'espace personnel : voir ``core.navigation.ESPACE_PERSONNEL``.
"""
from core.navigation import Module
from core.permissions import peut_organiser

MODULE = Module(
    cle="participants",
    label="Participants",
    url_name="participants:index",
    icone="participants",
    acces=peut_organiser,
    namespace="participants",
    description="Inscrits, listes d'attente, types de billets et contrôle d'entrée.",
)
