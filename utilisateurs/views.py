from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, SuppressionMixin

from .forms import InscriptionCompteForm, ProfilForm, UtilisateurAdminForm, UtilisateurCreationAdminForm
from .models import Utilisateur

ROLES_INSCRIPTION = [
    ("PARTICIPANT", "Participant", "Je réserve des billets et je participe à des événements.", "M3 9a2 2 0 0 0 0 4v4h18v-4a2 2 0 0 1 0-4V5H3zM14 5v12"),
    ("ORGANISATEUR", "Organisateur", "Je crée et je gère des événements.", "M3 4h18v17H3zM3 9h18M8 2v4M16 2v4"),
    ("CLIENT", "Client", "Je confie l'organisation de mon événement à une agence.", "M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z"),
]


class ConnexionView(auth_views.LoginView):
    template_name = "utilisateurs/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)          # session fermée avec le navigateur
        messages.success(self.request, f"Bonjour {form.get_user().first_name or form.get_user().username} !")
        return super().form_valid(form)


class InscriptionCompteView(CreateView):
    """Inscription en 3 étapes (profil, coordonnées, sécurité) dans un seul formulaire."""
    form_class = InscriptionCompteForm
    template_name = "utilisateurs/register.html"
    success_url = reverse_lazy("core:dashboard")
    extra_context = {"roles": ROLES_INSCRIPTION}

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Bienvenue sur Évenza ! Votre compte est créé.")
        return response


class ProfilView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    form_class = ProfilForm
    template_name = "utilisateurs/profil.html"
    success_url = reverse_lazy("utilisateurs:profil")
    success_message = "Profil mis à jour."

    def get_object(self, queryset=None):
        return self.request.user


# ---- mot de passe oublié : les 4 vues de Django avec nos templates ----
class MotDePasseOublieView(auth_views.PasswordResetView):
    template_name = "utilisateurs/password_reset_form.html"
    email_template_name = "utilisateurs/password_reset_email.html"
    subject_template_name = "utilisateurs/password_reset_subject.txt"
    success_url = reverse_lazy("utilisateurs:password_reset_done")


class MotDePasseEnvoyeView(auth_views.PasswordResetDoneView):
    template_name = "utilisateurs/password_reset_done.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(debug_console="console" in settings.EMAIL_BACKEND, **kwargs)


class NouveauMotDePasseView(auth_views.PasswordResetConfirmView):
    template_name = "utilisateurs/password_reset_confirm.html"
    success_url = reverse_lazy("utilisateurs:password_reset_complete")


class MotDePasseModifieView(auth_views.PasswordResetCompleteView):
    template_name = "utilisateurs/password_reset_complete.html"


# ---- CRUD des utilisateurs (réservé à l'administrateur) ----
class UtilisateurListView(AdminRequiredMixin, ListView):
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_list.html"
    paginate_by = 20

    def get_queryset(self):
        qs = Utilisateur.objects.annotate(nb_evenements=Count("evenements_organises", distinct=True),
                                          nb_inscriptions=Count("inscriptions", distinct=True)).order_by("username")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q)
                           | Q(last_name__icontains=q) | Q(email__icontains=q))
        role = self.request.GET.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["roles"] = Utilisateur.Role.choices
        params = self.request.GET.copy(); params.pop("page", None)
        ctx["filtres"] = params.urlencode()
        return ctx


class UtilisateurDetailView(AdminRequiredMixin, DetailView):
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_detail.html"
    context_object_name = "compte"   # « user » reste l'utilisateur connecté

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["evenements"] = self.object.evenements_organises.select_related("lieu")[:10]
        ctx["inscriptions"] = self.object.inscriptions.select_related("evenement")[:10]
        return ctx


class UtilisateurCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    model = Utilisateur
    form_class = UtilisateurCreationAdminForm
    template_name = "utilisateurs/utilisateur_form.html"
    success_message = "Le compte « %(username)s » a été créé."

    def get_success_url(self):
        return reverse_lazy("utilisateurs:utilisateur_detail", args=[self.object.pk])


class UtilisateurUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Utilisateur
    form_class = UtilisateurAdminForm
    template_name = "utilisateurs/utilisateur_form.html"
    context_object_name = "compte"
    success_message = "Le compte « %(username)s » a été modifié."

    def get_success_url(self):
        return reverse_lazy("utilisateurs:utilisateur_detail", args=[self.object.pk])


class UtilisateurDeleteView(AdminRequiredMixin, SuppressionMixin, DeleteView):
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_confirm_delete.html"
    success_url = reverse_lazy("utilisateurs:utilisateur_liste")

    def get_url_si_protege(self):
        return reverse_lazy("utilisateurs:utilisateur_detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nb_evenements"] = self.object.evenements_organises.count()
        ctx["nb_inscriptions"] = self.object.inscriptions.count()
        return ctx

    def form_valid(self, form):
        if self.object.pk == self.request.user.pk:   # garde-fou : on ne supprime pas son propre compte ici
            messages.error(self.request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect("utilisateurs:utilisateur_detail", pk=self.object.pk)
        return super().form_valid(form)
