from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, OrganisateurRequiredMixin, ProprietaireEvenementMixin, SuppressionMixin
from core.permissions import evenements_geres
from evenements.models import Evenement

from .forms import PrestataireForm, ReservationForm
from .models import Prestataire, Reservation, Service, image_prestataires


def _event_return_url(request, evenement):
    url = evenement.get_absolute_url()
    return f"{url}?sans_programmes=1" if request.GET.get("sans_programmes") == "1" else url


def _next_sur(request):
    """URL « next » (POST ou GET) si elle reste sur ce site, sinon None."""
    url = request.POST.get("next") or request.GET.get("next")
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return None


# ---- Prestataires : liste, détail, ajout, modification, suppression ----
EN_COURS = (Reservation.Statut.DEMANDEE, Reservation.Statut.CONFIRMEE)


class PrestataireListView(OrganisateurRequiredMixin, ListView):
    """Liste en cartes : recherche (?q=), filtre par type de service (?service=), 9 cartes par page."""
    model = Prestataire
    paginate_by = 9

    def get_filtres(self):
        q = self.request.GET.get("q", "").strip()
        service = self.request.GET.get("service", "")
        if service not in Service.Type.values:
            service = ""
        return q, service

    def get_queryset(self):
        q, service = self.get_filtres()
        qs = Prestataire.objects.all()
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(email__icontains=q) | Q(telephone__icontains=q))
        if service:
            # Sous-requête : évite les doublons de lignes dus à la jointure sur les services.
            qs = qs.filter(pk__in=Prestataire.objects.filter(services__type=service).values("pk"))
        return (qs.annotate(nb_reservations=Count("reservations", distinct=True),
                            nb_en_cours=Count("reservations", filter=Q(reservations__statut__in=EN_COURS),
                                              distinct=True))
                .prefetch_related("services").order_by("nom"))

    def get_context_data(self, **kwargs):
        q, service = self.get_filtres()
        filtres = urlencode({k: v for k, v in (("q", q), ("service", service)) if v})
        stats = {
            "nb_prestataires": Prestataire.objects.count(),
            "nb_types": Service.objects.values("type").distinct().count(),
            "nb_demandees": Reservation.objects.filter(statut=Reservation.Statut.DEMANDEE,
                                                       evenement__in=evenements_geres(self.request.user)).count(),
        }
        return super().get_context_data(q=q, service_actif=service, types_service=Service.Type.choices,
                                        filtres=filtres, stats=stats, bandeau_url=image_prestataires("bandeau"),
                                        **kwargs)


class PrestataireDetailView(OrganisateurRequiredMixin, DetailView):
    model = Prestataire

    def get_queryset(self):
        return Prestataire.objects.prefetch_related("services")

    def get_context_data(self, **kwargs):
        # L'admin voit toutes les réservations du prestataire ; l'organisateur, celles de ses événements.
        resas = (self.object.reservations.select_related("evenement", "service")
                 .filter(evenement__in=evenements_geres(self.request.user))
                 .order_by("-evenement__date_debut", "-date_demande"))
        total = resas.filter(statut=Reservation.Statut.CONFIRMEE).aggregate(t=Sum("montant"))["t"] or 0
        nb = resas.count()
        nb_confirmees = resas.filter(statut=Reservation.Statut.CONFIRMEE).count()
        taux = round(100 * nb_confirmees / nb) if nb else 0
        return super().get_context_data(reservations=resas, total_confirme=total, nb_confirmees=nb_confirmees,
                                        taux_confirmation=taux, **kwargs)


class PrestataireReserverView(OrganisateurRequiredMixin, DetailView):
    """Bouton « Réserver » d'une carte : choisir l'événement, puis le formulaire est pré-rempli."""
    model = Prestataire
    template_name = "prestataires/prestataire_reserver.html"

    def get_context_data(self, **kwargs):
        evts = evenements_geres(self.request.user).exclude(statut=Evenement.Statut.ANNULE).order_by("-date_debut")
        return super().get_context_data(evenements_choix=evts, **kwargs)


class ApercuCarteMixin:
    """Image de couverture par défaut de l'aperçu en direct (aucun service coché)."""

    def get_context_data(self, **kwargs):
        return super().get_context_data(couverture_defaut=image_prestataires("bandeau"), **kwargs)


class PrestataireCreateView(OrganisateurRequiredMixin, ApercuCarteMixin, SuccessMessageMixin, CreateView):
    model = Prestataire
    form_class = PrestataireForm
    success_message = "Le prestataire « %(nom)s » a été ajouté."

    def get_success_url(self):
        return self.object.get_absolute_url()


class PrestataireUpdateView(AdminRequiredMixin, ApercuCarteMixin, SuccessMessageMixin, UpdateView):
    model = Prestataire
    form_class = PrestataireForm
    success_message = "Le prestataire « %(nom)s » a été modifié."

    def get_success_url(self):
        return self.object.get_absolute_url()


class PrestataireDeleteView(AdminRequiredMixin, SuppressionMixin, DeleteView):
    """Suppression avec page de confirmation ; refusée avec un message clair si des réservations existent."""
    model = Prestataire
    success_url = reverse_lazy("prestataires:liste")
    success_message = "Le prestataire « {objet} » a été supprimé."
    protege_message = ("Impossible de supprimer « {objet} » : ce prestataire a encore des réservations "
                       "({liens}). Annulez-les ou supprimez-les d'abord.")

    def get_url_si_protege(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        liees = self.object.reservations.select_related("evenement", "service").order_by("-date_demande")
        return super().get_context_data(nb_reservations=liees.count(), reservations_liees=liees[:8], **kwargs)


# ---- Réservations ----
class ReservationCreateView(ProprietaireEvenementMixin, CreateView):
    model = Reservation
    form_class = ReservationForm

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        pk = self.request.GET.get("prestataire", "")
        if pk.isdigit():
            initial["prestataire"] = pk
        return initial

    def form_valid(self, form):
        form.instance.evenement = self.get_evenement()
        form.instance.statut = Reservation.Statut.DEMANDEE
        messages.success(self.request, "Demande de réservation envoyée au prestataire.")
        return super().form_valid(form)

    def get_success_url(self):
        return _next_sur(self.request) or _event_return_url(self.request, self.object.evenement)


class ReservationsEvenementView(ProprietaireEvenementMixin, ListView):
    """Réservations d'un événement, avec les boutons Confirmer / Annuler (US 4.4.1)."""
    model = Reservation
    template_name = "prestataires/reservations_evenement.html"

    def get_evenement(self):
        if not hasattr(self, "_evenement"):
            self._evenement = get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])
        return self._evenement

    def get_queryset(self):
        return (self.get_evenement().reservations.select_related("prestataire", "service")
                .prefetch_related("prestataire__services"))

    def get_context_data(self, **kwargs):
        """Kanban : une colonne par statut, dans l'ordre Demandées → Confirmées → Annulées."""
        resas = list(self.object_list)
        colonnes = [{"code": code, "libelle": f"{libelle}s", "reservations": [r for r in resas if r.statut == code]}
                    for code, libelle in Reservation.Statut.choices]
        total = sum((r.montant for r in resas if r.statut == Reservation.Statut.CONFIRMEE), 0)
        return super().get_context_data(evenement=self.get_evenement(), colonnes=colonnes, total_confirme=total,
                                        **kwargs)


class ReservationStatutView(ProprietaireEvenementMixin, View):
    """POST : fait évoluer le statut d'une réservation selon ``Reservation.TRANSITIONS``.

    Redirige vers le paramètre « next » s'il est sûr, sinon vers « Réservations de l'événement ».
    """
    http_method_names = ["post"]

    def get_evenement(self):
        return get_object_or_404(Reservation, pk=self.kwargs["pk"]).evenement

    def post(self, request, pk, statut):
        r = get_object_or_404(Reservation, pk=pk)
        try:
            r.changer_statut(statut)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"Réservation de « {r.prestataire} » : {r.get_statut_display().lower()}.")
        return redirect(_next_sur(request) or reverse("prestataires:reservations_evenement", args=[r.evenement_id]))
