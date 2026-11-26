from django.contrib import messages
from django.db.models import Count, DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import OrganisateurRequiredMixin, ProprietaireEvenementMixin

from participants.models import Inscription, TypeBillet

from .forms import EvenementForm, LieuForm
from .models import Categorie, Evenement, Lieu


class EvenementListView(ListView):
    """Catalogue public : événements publiés, recherche par mot-clé, catégorie, ville et date."""
    model = Evenement
    paginate_by = 9

    def get_queryset(self):
        # Sans filtre de statut, le catalogue public ne montre que les événements publiés.
        # Un statut public (publié, annulé, terminé) peut être demandé explicitement.
        # Un brouillon n'est jamais listé ici.
        statuts_publics = {
            Evenement.Statut.PUBLIE,
            Evenement.Statut.ANNULE,
            Evenement.Statut.TERMINE,
        }
        statut = (self.request.GET.get("statut") or "").strip().upper()
        qs = Evenement.objects.select_related("lieu", "categorie").prefetch_related("types_billet")
        qs = qs.filter(statut=statut) if statut in statuts_publics else qs.publies()
        q = self.request.GET.get("q", "").strip()
        cat = self.request.GET.get("categorie")
        if q:
            qs = qs.filter(Q(titre__icontains=q) | Q(description__icontains=q) | Q(lieu__ville__icontains=q))
        if cat and str(cat).isdigit():
            qs = qs.filter(categorie_id=int(cat))
        ville = self.request.GET.get("ville", "").strip()
        if ville:
            qs = qs.filter(lieu__ville__iexact=ville)
        lieu = (self.request.GET.get("lieu") or "").strip()
        if lieu.isdigit():
            qs = qs.filter(lieu_id=int(lieu))
        quand = parse_date(self.request.GET.get("date", "") or "")
        if quand:  # événements à partir de cette date
            qs = qs.filter(date_debut__date__gte=quand)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = Categorie.objects.all()
        ctx["villes"] = Lieu.objects.values_list("ville", flat=True).distinct().order_by("ville")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["statut"] = (self.request.GET.get("statut") or "").strip().upper()
        params = self.request.GET.copy(); params.pop("page", None)
        ctx["filtres"] = params.urlencode()  # pour garder les filtres dans la pagination
        return ctx


class MesEvenementsView(OrganisateurRequiredMixin, ListView):
    """Espace organisateur : tous ses événements, quel que soit le statut."""
    model = Evenement
    template_name = "evenements/mes_evenements.html"

    def get_queryset(self):
        u = self.request.user
        conf = Q(inscriptions__statut="CONFIRMEE")
        qs = (Evenement.objects.select_related("lieu", "categorie")
              .prefetch_related(
                  "seances",
                  Prefetch("types_billet", queryset=TypeBillet.objects.annotate(
                      vendus_n=Coalesce(Sum("inscriptions__quantite", filter=Q(inscriptions__statut="CONFIRMEE")), 0))))
              .annotate(inscrits_n=Coalesce(Sum("inscriptions__quantite", filter=conf), 0),
                        recettes_n=Coalesce(Sum("inscriptions__montant", filter=conf), Value(0, output_field=DecimalField())),
                        presents_n=Count("inscriptions", filter=Q(inscriptions__present=True), distinct=True))
              .order_by("date_debut"))
        return qs if u.est_admin else qs.filter(organisateur=u)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # L'app « social » (archives) n'est pas dans ce dépôt : liste vide, le template reste valide.
        ctx["archives_ids"] = set()
        try:
            from social.models import Interaction
        except ImportError:
            return ctx
        ctx["archives_ids"] = set(Interaction.objects.filter(
            utilisateur=self.request.user, type="ARCHIVE").values_list("evenement_id", flat=True))
        return ctx


class EvenementDetailView(DetailView):
    model = Evenement

    def get_queryset(self):
        qs = Evenement.objects.select_related("lieu", "categorie", "organisateur")
        u = self.request.user
        if u.is_authenticated and u.est_admin:
            return qs
        # Un brouillon n'est visible que par son organisateur (et l'admin).
        visibles = ~Q(statut=Evenement.Statut.BROUILLON)
        if u.is_authenticated:
            visibles |= Q(organisateur=u)
        return qs.filter(visibles)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        e, u = self.object, self.request.user
        ctx["seances"] = e.seances.order_by("date")
        ctx["billets"] = e.types_billet.all()
        ctx["peut_modifier"] = u.is_authenticated and (u.est_admin or e.organisateur_id == u.id)
        ctx["mon_inscription"] = e.inscriptions.filter(participant=u).first() if u.is_authenticated else None
        if ctx["peut_modifier"]:
            ctx["reservations"] = e.reservations.select_related("prestataire", "service")
            ctx["affectations"] = e.affectations.select_related("ressource")
        return ctx


class EvenementCreateView(OrganisateurRequiredMixin, CreateView):
    model = Evenement
    form_class = EvenementForm
    success_url = reverse_lazy("evenements:mes_evenements")

    def form_valid(self, form):
        form.instance.organisateur = self.request.user
        messages.success(self.request, "Événement créé (brouillon). Publiez-le quand il est prêt.")
        return super().form_valid(form)


class EvenementUpdateView(ProprietaireEvenementMixin, UpdateView):
    model = Evenement
    form_class = EvenementForm

    def form_valid(self, form):
        messages.success(self.request, "Événement mis à jour.")
        return super().form_valid(form)


class EvenementDeleteView(ProprietaireEvenementMixin, DeleteView):
    model = Evenement
    success_url = reverse_lazy("evenements:mes_evenements")

    def form_valid(self, form):
        # Garde-fou : supprimer l'événement effacerait en cascade les billets déjà réservés.
        actives = self.object.inscriptions.exclude(statut=Inscription.Statut.ANNULEE).count()
        if actives:
            messages.error(self.request, f"Impossible de supprimer « {self.object} » : {actives} réservation(s) "
                                         f"active(s). Annulez plutôt l'événement.")
            return redirect(self.object)
        messages.success(self.request, "Événement supprimé.")
        return super().form_valid(form)


class ChangerStatutView(ProprietaireEvenementMixin, View):
    """POST uniquement : publier ou annuler un événement."""
    action = None

    def get_object(self):
        return get_object_or_404(Evenement, pk=self.kwargs["pk"])

    def post(self, request, pk):
        e = self.get_object()
        if self.action == "publier":
            e.publier()
            messages.success(request, f"« {e} » est publié.")
        else:
            e.annuler()
            messages.warning(request, f"« {e} » est annulé.")
        return redirect(e)


class LieuListView(OrganisateurRequiredMixin, ListView):
    model = Lieu


class LieuCreateView(OrganisateurRequiredMixin, CreateView):
    model = Lieu
    form_class = LieuForm
    success_url = reverse_lazy("evenements:lieux")
