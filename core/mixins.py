"""Composants réutilisables (approche bottom-up)."""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Autorise l'accès seulement aux rôles listés dans `roles` (l'admin passe toujours)."""
    roles = ()

    def test_func(self):
        u = self.request.user
        return u.is_superuser or u.role == "ADMIN" or u.role in self.roles


class OrganisateurRequiredMixin(RoleRequiredMixin):
    roles = ("ORGANISATEUR",)


class ProprietaireEvenementMixin(OrganisateurRequiredMixin):
    """L'organisateur ne peut modifier que ses propres événements."""

    def get_evenement(self):
        return self.get_object()

    def test_func(self):
        if not super().test_func():
            return False
        u = self.request.user
        return u.is_superuser or u.role == "ADMIN" or self.get_evenement().organisateur_id == u.id


class AdminRequiredMixin(RoleRequiredMixin):
    """Réservé à l'administrateur (superutilisateur ou rôle ADMIN)."""
    roles = ()


class SuppressionMixin:
    """Pour les DeleteView : message de succès, et message clair au lieu d'une erreur 500
    si l'objet est encore utilisé ailleurs (ForeignKey en PROTECT → ProtectedError)."""
    success_message = "« {objet} » a été supprimé."
    protege_message = "Impossible de supprimer « {objet} » : il est encore utilisé par {liens}."

    def form_valid(self, form):
        from django.contrib import messages
        from django.db.models import ProtectedError
        from django.shortcuts import redirect

        nom = str(self.object)
        try:
            reponse = super().form_valid(form)
        except ProtectedError as e:
            liens = sorted({f"{o._meta.verbose_name} « {o} »" for o in list(e.protected_objects)[:3]})
            messages.error(self.request, self.protege_message.format(objet=nom, liens=", ".join(liens)))
            return redirect(self.get_url_si_protege())
        messages.success(self.request, self.success_message.format(objet=nom))
        return reponse

    def get_url_si_protege(self):
        """Page où revenir si la suppression est refusée (par défaut : la page de l'objet, sinon la liste)."""
        return self.object.get_absolute_url() if hasattr(self.object, "get_absolute_url") else self.get_success_url()
