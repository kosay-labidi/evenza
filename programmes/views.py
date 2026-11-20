from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import OrganisateurRequiredMixin, ProprietaireEvenementMixin
from evenements.models import Evenement

from .forms import IntervenantForm, SeanceForm
from .models import Intervenant, Seance


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
