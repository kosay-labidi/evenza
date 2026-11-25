from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import OrganisateurRequiredMixin, ProprietaireEvenementMixin, SuppressionMixin
from evenements.models import Evenement

from .forms import AffectationForm, RessourceForm
from .models import Affectation, Ressource


class RessourceListView(OrganisateurRequiredMixin, ListView):
    model = Ressource


class RessourceCreateView(OrganisateurRequiredMixin, CreateView):
    model = Ressource
    form_class = RessourceForm
    success_url = reverse_lazy("ressources:liste")


class AffectationCreateView(ProprietaireEvenementMixin, CreateView):
    model = Affectation
    form_class = AffectationForm

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_initial(self):
        e = self.get_evenement()
        return {"debut": e.date_debut, "fin": e.date_fin}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.evenement = self.get_evenement()
        return form

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)

    def get_success_url(self):
        messages.success(self.request, "Ressource affectée sans conflit.")
        return self.object.evenement.get_absolute_url()


# ---- Ressource : détail, modification, suppression ----
class RessourceDetailView(OrganisateurRequiredMixin, DetailView):
    model = Ressource

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["affectations"] = self.object.affectations.select_related("evenement", "evenement__lieu")
        return ctx


class RessourceUpdateView(OrganisateurRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Ressource
    form_class = RessourceForm
    success_message = "La ressource « %(nom)s » a été modifiée."

    def get_success_url(self):
        return reverse_lazy("ressources:detail", args=[self.object.pk])


class RessourceDeleteView(OrganisateurRequiredMixin, SuppressionMixin, DeleteView):
    model = Ressource
    success_url = reverse_lazy("ressources:liste")
    protege_message = ("Impossible de supprimer « {objet} » : cette ressource est encore affectée à des événements "
                       "({liens}). Supprimez d'abord ses affectations.")

    def get_url_si_protege(self):
        return reverse_lazy("ressources:detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        return super().get_context_data(nb_affectations=self.object.affectations.count(), **kwargs)


# ---- Affectation : liste, modification, suppression ----
class AffectationListView(OrganisateurRequiredMixin, ListView):
    """Affectations des événements de l'organisateur (toutes pour l'admin)."""
    model = Affectation
    paginate_by = 20

    def get_queryset(self):
        u = self.request.user
        qs = Affectation.objects.select_related("ressource", "evenement", "evenement__lieu")
        if not u.est_admin:
            qs = qs.filter(evenement__organisateur=u)
        evt = self.request.GET.get("evenement")
        if evt:
            qs = qs.filter(evenement_id=evt)
        res = self.request.GET.get("ressource")
        if res:
            qs = qs.filter(ressource_id=res)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        ctx["evenements"] = Evenement.objects.all() if u.est_admin else Evenement.objects.filter(organisateur=u)
        ctx["evenements_choix"] = ctx["evenements"].exclude(statut=Evenement.Statut.ANNULE).order_by("-date_debut")
        ctx["ressources"] = Ressource.objects.all()
        params = self.request.GET.copy(); params.pop("page", None)
        ctx["filtres"] = params.urlencode()
        return ctx


class AffectationUpdateView(ProprietaireEvenementMixin, SuccessMessageMixin, UpdateView):
    model = Affectation
    form_class = AffectationForm
    success_message = "Affectation modifiée sans conflit."

    def get_evenement(self):
        return self.get_object().evenement

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.object.evenement, **kwargs)

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()


class AffectationDeleteView(ProprietaireEvenementMixin, SuppressionMixin, DeleteView):
    model = Affectation
    success_message = "L'affectation « {objet} » a été supprimée."

    def get_evenement(self):
        return self.get_object().evenement

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()
