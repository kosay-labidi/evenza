from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import ModuleRequiredMixin, OrganisateurRequiredMixin, ProprietaireEvenementMixin
from core.permissions import evenements_geres
from evenements.models import Evenement

from .forms import IntervenantForm, SeanceForm
from .models import Intervenant, Seance


class ProgrammesAccueilView(ModuleRequiredMixin, ListView):
    """Page d'entrée du module Programmes : accès direct aux séances de tous les événements gérés."""
    module = "programmes"
    template_name = "programmes/index.html"
    context_object_name = "evenements"
    paginate_by = 12

    def get_queryset(self):
        qs = evenements_geres(self.request.user).annotate(nb_seances=Count("seances")).order_by("-date_debut")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(titre__icontains=q) | Q(seances__titre__icontains=q)).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["prochaines_seances"] = (Seance.objects.filter(evenement__in=evenements_geres(self.request.user),
                                                           fin__gte=timezone.now())
                                     .select_related("evenement").prefetch_related("intervenants")[:8])
        ctx["nb_intervenants"] = Intervenant.objects.count()
        return ctx


class SeanceCreateView(ProprietaireEvenementMixin, CreateView):
    model = Seance
    form_class = SeanceForm

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.evenement = self.get_evenement()
        return form

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)

    def get_success_url(self):
        messages.success(self.request, "Séance ajoutée au programme.")
        return self.object.evenement.get_absolute_url()


class SeanceUpdateView(ProprietaireEvenementMixin, UpdateView):
    model = Seance
    form_class = SeanceForm

    def get_evenement(self):
        return self.get_object().evenement

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.object.evenement, **kwargs)

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()


class SeanceDeleteView(ProprietaireEvenementMixin, DeleteView):
    model = Seance

    def get_evenement(self):
        return self.get_object().evenement

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()


class IntervenantListView(OrganisateurRequiredMixin, ListView):
    model = Intervenant


class IntervenantCreateView(OrganisateurRequiredMixin, CreateView):
    model = Intervenant
    form_class = IntervenantForm
    success_url = reverse_lazy("programmes:intervenants")
