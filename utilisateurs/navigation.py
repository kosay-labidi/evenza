"""Module « Utilisateurs » dans la barre latérale (fichier propre à la gestion des utilisateurs).

La page « Mon profil » relève de l'espace personnel : voir ``core.navigation.ESPACE_PERSONNEL``.
"""
from core.navigation import Module
from core.permissions import est_administrateur

MODULE = Module(
    cle="utilisateurs",
    label="Utilisateurs",
    url_name="utilisateurs:utilisateur_liste",
    icone="utilisateurs",
    acces=est_administrateur,
    namespace="utilisateurs",
    description="Comptes, rôles et accès de toute la plateforme.",
)
