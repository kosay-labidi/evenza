"""Module « Participants » dans la barre latérale (fichier propre à la gestion des participants).

Les pages personnelles du participant (Mes billets, billet, réservation, avis) relèvent de
l'espace personnel : voir ``core.navigation.ESPACE_PERSONNEL``.
"""
from core.navigation import Lien, Module
from core.permissions import peut_organiser

MODULE = Module(
    cle="participants",
    label="Participants",
    url_name="participants:index",
    icone="participants",
    acces=peut_organiser,
    namespace="participants",
    description="Inscrits, listes d'attente, types de billets et contrôle d'entrée.",
    sous_liens=(
        Lien("Synthèse", "participants:index", ("index", "checkin", "tableau_de_bord")),
        Lien("Inscriptions", "participants:inscription_liste", ("inscription_liste", "inscription_detail", "liste")),
        Lien("Avis", "participants:avis_liste", ("avis_liste", "avis_detail", "avis_supprimer")),
        Lien("Types de billets", "participants:typebillet_liste", ("typebillet_liste", "typebillet_detail", "type_creer", "typebillet_modifier", "typebillet_supprimer")),
    ),
)
