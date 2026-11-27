"""Composants réutilisables (approche bottom-up).

Contrôles d'accès : chaque mixin délègue à une fonction de ``core.permissions`` (aucune règle
n'est recodée ici). Anonyme → redirection vers la connexion ; connecté sans le droit → 403.
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ImproperlyConfigured

from . import permissions


class PermissionRequiseMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Base : ``permission`` est une fonction ``(user) -> bool`` de ``core.permissions``."""
    permission = None

    def test_func(self):
        regle = type(self).permission   # lue sur la classe : fonction simple, pas une méthode liée
        if regle is None:
            raise ImproperlyConfigured(f"{type(self).__name__} doit définir « permission » (fonction de "
                                       "core.permissions) ou redéfinir test_func().")
        return regle(self.request.user)


class RoleRequiredMixin(PermissionRequiseMixin):
    """Autorise l'accès seulement aux rôles listés dans `roles` (l'admin passe toujours)."""
    roles = ()

    def test_func(self):
        u = self.request.user
        return permissions.est_administrateur(u) or (permissions.est_connecte(u) and u.role in self.roles)


class AdminRequiredMixin(PermissionRequiseMixin):
    """Réservé à l'administrateur (superutilisateur ou rôle ADMIN)."""
    permission = permissions.est_administrateur


class OrganisateurRequiredMixin(PermissionRequiseMixin):
    """Organisateur ou administrateur."""
    permission = permissions.peut_organiser


class ProprietaireEvenementMixin(OrganisateurRequiredMixin):
    """L'organisateur ne peut modifier que ses propres événements (l'admin : tous)."""

    def get_evenement(self):
        return self.get_object()

    def test_func(self):
        # le rôle est vérifié avant de charger l'événement : un non-organisateur reçoit 403, jamais 404
        return super().test_func() and permissions.peut_gerer_evenement(self.request.user, self.get_evenement())


class ClientRequiredMixin(PermissionRequiseMixin):
    """Espace client (demandes, suivi de ses événements) ; l'admin y accède pour la supervision."""
    permission = permissions.acces_espace_client


class ParticipantRequiredMixin(PermissionRequiseMixin):
    """Espace participant ; l'admin y accède pour la supervision."""
    permission = permissions.acces_espace_participant


class PrestataireRequiredMixin(PermissionRequiseMixin):
    """Espace prestataire (ses réservations) ; l'admin y accède pour la supervision."""
    permission = permissions.acces_espace_prestataire


class ModuleRequiredMixin(PermissionRequiseMixin):
    """Accès à la page d'entrée d'un module : applique la règle déclarée dans ``<app>/navigation.py``.

    Exemple : ``class ParticipantsAccueilView(ModuleRequiredMixin, ListView): module = "participants"``.
    Le menu et ce contrôle serveur utilisent la même fonction ``acces`` : un lien masqué
    est aussi une page refusée (403).
    """
    module = None

    def test_func(self):
        from .navigation import get_module
        return get_module(self.module).acces(self.request.user)


class SuppressionMixin:
    """Pour les DeleteView : message de succès, et message clair au lieu d'une erreur 500
    si l'objet est encore utilisé ailleurs (ForeignKey en PROTECT/RESTRICT → ProtectedError/RestrictedError)."""
    success_message = "« {objet} » a été supprimé."
    protege_message = "Impossible de supprimer « {objet} » : il est encore utilisé par {liens}."

    def form_valid(self, form):
        from django.contrib import messages
        from django.db.models import ProtectedError, RestrictedError
        from django.shortcuts import redirect

        nom = str(self.object)
        try:
            reponse = super().form_valid(form)
        except (ProtectedError, RestrictedError) as e:
            bloquants = getattr(e, "protected_objects", None) or getattr(e, "restricted_objects", ())
            liens = sorted({f"{o._meta.verbose_name} « {o} »" for o in list(bloquants)[:3]})
            messages.error(self.request, self.protege_message.format(objet=nom, liens=", ".join(liens)))
            return redirect(self.get_url_si_protege())
        messages.success(self.request, self.success_message.format(objet=nom))
        return reponse

    def get_url_si_protege(self):
        """Page où revenir si la suppression est refusée (par défaut : la page de l'objet, sinon la liste)."""
        return self.object.get_absolute_url() if hasattr(self.object, "get_absolute_url") else self.get_success_url()
