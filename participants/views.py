from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView

from core.mixins import ModuleRequiredMixin, ProprietaireEvenementMixin
from core.permissions import evenements_geres
from evenements.models import Evenement

from .forms import AvisForm, CheckinForm, ReservationForm, TypeBilletForm
from .models import Avis, Inscription, TypeBillet


class ParticipantsAccueilView(ModuleRequiredMixin, ListView):
    """Page d'entrée du module Participants : accès direct, sans passer par la page d'un événement.

    Liste les événements que l'utilisateur gère, avec leurs chiffres d'inscription, et renvoie
    vers les écrans existants (liste des inscrits, check-in, types de billets).
    """
    module = "participants"
    template_name = "participants/index.html"
    context_object_name = "evenements"
    paginate_by = 12

    def get_queryset(self):
        qs = evenements_geres(self.request.user).annotate(
            nb_confirmes=Sum("inscriptions__quantite", filter=Q(inscriptions__statut=Inscription.Statut.CONFIRMEE)),
            nb_attente=Count("inscriptions", filter=Q(inscriptions__statut=Inscription.Statut.ATTENTE)),
            nb_presents=Count("inscriptions", filter=Q(inscriptions__present=True)),
        ).order_by("-date_debut")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(titre__icontains=q) | Q(lieu__ville__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        mes = Inscription.objects.filter(evenement__in=evenements_geres(self.request.user))
        ctx["totaux"] = {
            "confirmes": mes.filter(statut=Inscription.Statut.CONFIRMEE).aggregate(n=Sum("quantite"))["n"] or 0,
            "attente": mes.filter(statut=Inscription.Statut.ATTENTE).count(),
            "presents": mes.filter(present=True).count(),
        }
        return ctx


class InscrireView(LoginRequiredMixin, View):
    """POST : s'inscrire à un événement publié."""

    def post(self, request, evenement_pk):
        e = get_object_or_404(Evenement, pk=evenement_pk, statut=Evenement.Statut.PUBLIE)
        if e.types_billet.exists():
            # L'événement propose des types de billets (Standard, VIP…) : il faut passer par le parcours complet.
            return redirect("participants:reserver", evenement_pk=e.pk)
        try:
            insc = Inscription.inscrire(e, request.user)
        except (ValidationError, IntegrityError):
            messages.info(request, "Vous êtes déjà inscrit à cet événement.")
            return redirect(e)
        if insc.statut == Inscription.Statut.ATTENTE:
            messages.warning(request, "Événement complet : vous êtes sur la liste d'attente.")
        else:
            messages.success(request, "Inscription confirmée ! Voici votre billet.")
        return redirect(insc)


class AnnulerInscriptionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        insc = get_object_or_404(Inscription, pk=pk, participant=request.user)
        if insc.statut == Inscription.Statut.ANNULEE:
            messages.info(request, "Cette inscription est déjà annulée.")
        elif insc.evenement.date_debut <= timezone.now():
            messages.error(request, "L'événement a déjà commencé : la réservation ne peut plus être annulée.")
        else:
            insc.annuler()
            messages.info(request, "Inscription annulée.")
        return redirect("participants:mes_inscriptions")


class MesInscriptionsView(LoginRequiredMixin, ListView):
    template_name = "participants/mes_inscriptions.html"

    def get_queryset(self):
        return Inscription.objects.filter(participant=self.request.user).select_related("evenement", "evenement__lieu")


class BilletView(LoginRequiredMixin, DetailView):
    template_name = "participants/billet.html"
    slug_field = slug_url_kwarg = "code_billet"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        i = self.object
        ctx["billet_js"] = {"titre": i.evenement.titre, "date": f"{i.evenement.date_debut:%d/%m/%Y · %H:%M}",
                            "lieu": i.evenement.lieu.nom, "participant": str(i.participant),
                            "billet": f"{i.type_billet.nom if i.type_billet else 'Entrée'} × {i.quantite}",
                            "total": f"{i.montant:.2f} DT" if i.montant else "Gratuit", "code": i.code_court}
        return ctx

    def get_queryset(self):
        u = self.request.user
        qs = Inscription.objects.select_related("evenement", "evenement__lieu", "participant")
        return qs if u.est_admin else qs.filter(participant=u) | qs.filter(evenement__organisateur=u)


class ParticipantsEvenementView(ProprietaireEvenementMixin, ListView):
    template_name = "participants/liste_participants.html"

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_queryset(self):
        return self.get_evenement().inscriptions.select_related("participant")

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)


class CheckinView(ProprietaireEvenementMixin, FormView):
    """Contrôle d'entrée : l'organisateur saisit (ou scanne) le code du billet."""
    form_class = CheckinForm
    template_name = "participants/checkin.html"

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_context_data(self, **kwargs):
        e = self.get_evenement()
        return super().get_context_data(evenement=e, presents=e.inscriptions.filter(present=True).count(), **kwargs)

    def form_valid(self, form):
        e = self.get_evenement()
        code = form.cleaned_data["code"]          # déjà normalisé : 8 à 32 caractères hexadécimaux
        trouves = list(e.inscriptions.filter(statut=Inscription.Statut.CONFIRMEE, code_billet__startswith=code)
                       .select_related("participant")[:2])
        if not trouves:
            messages.error(self.request, "Billet introuvable ou non confirmé pour cet événement.")
        elif len(trouves) > 1:
            messages.error(self.request, "Plusieurs billets correspondent à ce début de code : saisissez le code complet.")
        else:
            insc = trouves[0]
            # Mise à jour conditionnelle : un même billet ne peut pas être validé deux fois, même en simultané.
            if Inscription.objects.filter(pk=insc.pk, present=False).update(present=True):
                messages.success(self.request, f"Bienvenue {insc.participant} ! Entrée enregistrée.")
            else:
                messages.warning(self.request, f"{insc.participant} est déjà entré.")
        return redirect("participants:checkin", evenement_pk=e.pk)


class AvisCreateView(LoginRequiredMixin, CreateView):
    model = Avis
    form_class = AvisForm

    def get_inscription(self):
        insc = get_object_or_404(Inscription.objects.select_related("evenement"), pk=self.kwargs["pk"],
                                 participant=self.request.user, statut=Inscription.Statut.CONFIRMEE)
        if hasattr(insc, "avis"):
            raise Http404("Avis déjà donné.")
        # On ne note qu'un événement auquel on a assisté (check-in) ou qui est terminé.
        if not (insc.present or insc.evenement.date_fin < timezone.now()):
            raise Http404("Vous pourrez donner votre avis après l'événement.")
        return insc

    def get_context_data(self, **kwargs):
        return super().get_context_data(inscription=self.get_inscription(), **kwargs)

    def form_valid(self, form):
        form.instance.inscription = self.get_inscription()
        messages.success(self.request, "Merci pour votre avis !")
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.inscription.evenement.get_absolute_url()


class ReservationView(LoginRequiredMixin, View):
    """Réservation en 3 étapes : 1. choix du billet et des places, 2. récapitulatif + total, 3. confirmation -> billet."""
    template_choix = "participants/reservation_choix.html"
    template_recap = "participants/reservation_recap.html"

    def get_evenement(self):
        return get_object_or_404(Evenement.objects.select_related("lieu", "categorie"), pk=self.kwargs["evenement_pk"],
                                 statut=Evenement.Statut.PUBLIE)

    def deja_inscrit(self, e):
        return e.inscriptions.filter(participant=self.request.user).exclude(statut=Inscription.Statut.ANNULEE).first()

    def get(self, request, evenement_pk):
        e = self.get_evenement()
        insc = self.deja_inscrit(e)
        if insc:
            messages.info(request, "Vous avez déjà une réservation pour cet événement.")
            return redirect(insc)
        return render(request, self.template_choix, {"evenement": e, "form": ReservationForm(evenement=e), "etape": 1})

    def post(self, request, evenement_pk):
        e = self.get_evenement()
        if self.deja_inscrit(e):
            return redirect(self.deja_inscrit(e))
        form = ReservationForm(request.POST, evenement=e)
        if not form.is_valid():
            return render(request, self.template_choix, {"evenement": e, "form": form, "etape": 1})
        d = form.cleaned_data
        if request.POST.get("etape") != "confirmer":       # étape 2 : récapitulatif
            return render(request, self.template_recap, {"evenement": e, "form": form, "etape": 2, **d,
                                                         "complet": e.places_restantes < d["quantite"]})
        # étape 3 : confirmation (les places et quotas sont revérifiés sous verrou dans inscrire())
        try:
            insc = Inscription.inscrire(e, request.user, d.get("type_billet"), d["quantite"])
        except IntegrityError:                               # double clic : la réservation existe déjà
            return redirect(self.deja_inscrit(e) or e)
        except ValidationError as err:
            if self.deja_inscrit(e):
                return redirect(self.deja_inscrit(e))
            form.add_error(None, err)
            return render(request, self.template_choix, {"evenement": e, "form": form, "etape": 1})
        if insc.statut == Inscription.Statut.ATTENTE:
            messages.warning(request, "Plus assez de places : votre réservation est sur la liste d'attente.")
        else:
            messages.success(request, "Réservation confirmée ! Voici votre billet.")
        return redirect(insc)


class TypeBilletCreateView(ProprietaireEvenementMixin, CreateView):
    model = TypeBillet
    form_class = TypeBilletForm

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)

    def form_valid(self, form):
        form.instance.evenement = self.get_evenement()
        messages.success(self.request, "Type de billet ajouté.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()
