from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView

from core.mixins import OrganisateurRequiredMixin, ProprietaireEvenementMixin
from core.permissions import evenements_geres
from evenements.models import Evenement

from .forms import PrestataireForm, ReservationForm
from .models import Prestataire, Reservation


class PrestataireListView(OrganisateurRequiredMixin, ListView):
    model = Prestataire

    def get_queryset(self):
        return Prestataire.objects.prefetch_related("services")

    def get_context_data(self, **kwargs):
        # Accès direct à la réservation d'un prestataire, sans passer par la page de l'événement.
        evts = evenements_geres(self.request.user).exclude(statut=Evenement.Statut.ANNULE).order_by("-date_debut")
        return super().get_context_data(evenements_choix=evts, **kwargs)


class PrestataireCreateView(OrganisateurRequiredMixin, CreateView):
    model = Prestataire
    form_class = PrestataireForm
    success_url = reverse_lazy("prestataires:liste")


class ReservationCreateView(ProprietaireEvenementMixin, CreateView):
    model = Reservation
    form_class = ReservationForm

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)

    def form_valid(self, form):
        form.instance.evenement = self.get_evenement()
        messages.success(self.request, "Demande de réservation envoyée au prestataire.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()


class ReservationStatutView(ProprietaireEvenementMixin, View):
    """POST : fait évoluer le statut d'une réservation de prestataire selon les transitions autorisées."""
    S = Reservation.Statut
    TRANSITIONS = {
        S.DEMANDEE: {S.CONFIRMEE, S.ANNULEE},
        S.CONFIRMEE: {S.ANNULEE},
        S.ANNULEE: set(),          # une réservation annulée est définitive : on en crée une nouvelle
    }

    def get_evenement(self):
        return get_object_or_404(Reservation, pk=self.kwargs["pk"]).evenement

    def post(self, request, pk, statut):
        r = get_object_or_404(Reservation, pk=pk)
        if statut not in self.TRANSITIONS.get(r.statut, set()):
            messages.error(request, f"Impossible de passer une réservation « {r.get_statut_display()} » "
                                    f"à ce statut.")
            return redirect(r.evenement)
        r.statut = statut
        r.save(update_fields=["statut"])
        messages.success(request, f"Réservation : {r.get_statut_display()}.")
        return redirect(r.evenement)
