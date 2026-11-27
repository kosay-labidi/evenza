import csv
import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from core.mixins import ModuleRequiredMixin, ProprietaireEvenementMixin, SuppressionMixin
from core.permissions import evenements_geres
from evenements.models import Evenement

from .calendrier import ics_inscription
from .forms import AvisForm, CheckinForm, ModificationReservationForm, ReservationForm, TransfertForm, TypeBilletForm
from .models import Avis, Inscription, TypeBillet


def _entier(valeur):
    """Convertit un paramètre GET en entier, ou None s'il est absent ou invalide."""
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _filtres(request):
    """Paramètres GET sans « page » : conservés dans les liens de pagination (voir partials/pagination.html)."""
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


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
    """Annulation par le participant : GET = page de confirmation, POST = annulation (toujours via Inscription.annuler(),
    qui passe la réservation en « Annulée » et promeut la liste d'attente ; la ligne n'est pas supprimée)."""
    template_name = "participants/inscription_confirm_annuler.html"

    def get_inscription(self, request, pk):
        return get_object_or_404(Inscription.objects.select_related("evenement", "type_billet"), pk=pk,
                                 participant=request.user)

    def refus(self, insc):
        """(niveau, message) si l'annulation est impossible, sinon None."""
        if insc.statut == Inscription.Statut.ANNULEE:
            return messages.info, "Cette inscription est déjà annulée."
        if insc.evenement.date_debut <= timezone.now():
            return messages.error, "L'événement a déjà commencé : la réservation ne peut plus être annulée."
        return None

    def get(self, request, pk):
        insc = self.get_inscription(request, pk)
        refus = self.refus(insc)
        if refus:
            refus[0](request, refus[1])
            return redirect("participants:mes_inscriptions")
        return render(request, self.template_name, {"inscription": insc, "evenement": insc.evenement})

    def post(self, request, pk):
        insc = self.get_inscription(request, pk)
        refus = self.refus(insc)
        if refus:
            refus[0](request, refus[1])
        else:
            insc.annuler()
            messages.info(request, "Inscription annulée.")
        return redirect("participants:mes_inscriptions")


class TransfertInscriptionView(LoginRequiredMixin, FormView):
    """Transfert de SA réservation à un autre utilisateur : 1. saisie du destinataire, 2. confirmation, 3. transfert.
    Toute la règle métier (statut, présence, date, destinataire, verrou) est dans ``Inscription.transferer()``."""
    form_class = TransfertForm
    template_name = "participants/inscription_transfert.html"

    def get_inscription(self):
        if not hasattr(self, "_inscription"):
            self._inscription = get_object_or_404(
                Inscription.objects.select_related("evenement", "evenement__lieu", "type_billet"), pk=self.kwargs["pk"],
                participant=self.request.user)                    # jamais la réservation d'un autre
        return self._inscription

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            motif = self.get_inscription().motif_refus_transfert()
            if motif:
                messages.error(request, motif)
                return redirect("participants:mes_inscriptions")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        insc = self.get_inscription()
        return super().get_context_data(inscription=insc, evenement=insc.evenement, **kwargs)

    def form_valid(self, form):
        insc, dest = self.get_inscription(), form.cleaned_data["destinataire"]
        if self.request.POST.get("etape") != "confirmer":                # étape 2 : confirmation
            return self.render_to_response(self.get_context_data(form=form, destinataire=dest, confirmation=True))
        try:
            insc.transferer(dest)
        except ValidationError as err:
            form.add_error(None, err)
            return self.form_invalid(form)
        messages.success(self.request, f"Billet transféré à {dest}. Votre ancien QR code n'est plus valable.")
        return redirect("participants:mes_inscriptions")


class BilletIcsView(LoginRequiredMixin, View):
    """Fichier .ics (« Ajouter au calendrier ») d'une réservation non annulée du participant connecté (404 sinon,
    y compris pour l'organisateur et l'admin)."""

    def get(self, request, code_billet):
        insc = get_object_or_404(Inscription.objects.select_related("evenement", "evenement__lieu", "type_billet")
                                 .exclude(statut=Inscription.Statut.ANNULEE),
                                 code_billet=code_billet, participant=request.user)
        contenu = ics_inscription(insc, request.build_absolute_uri(insc.get_absolute_url()))
        reponse = HttpResponse(contenu, content_type="text/calendar; charset=utf-8")
        reponse["Content-Disposition"] = f'attachment; filename="evenza-{insc.code_court}.ics"'
        return reponse


class MesInscriptionsView(LoginRequiredMixin, ListView):
    template_name = "participants/mes_inscriptions.html"

    def get_queryset(self):
        return (Inscription.objects.filter(participant=self.request.user)
                .select_related("evenement", "evenement__lieu", "avis"))


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


class InscriptionFiltresMixin:
    """Liste d'inscriptions pour l'organisateur : filtre par statut, recherche et pagination.
    Les sous-classes fournissent ``base_queryset()`` (déjà limité aux événements que l'utilisateur gère)."""
    template_name = "participants/inscription_list.html"
    paginate_by = 15

    def base_queryset(self):
        raise NotImplementedError

    def get_queryset(self):
        qs = self.base_queryset().select_related("participant", "evenement", "type_billet").order_by("-date_inscription", "-pk")
        statut = self.request.GET.get("statut")
        if statut in Inscription.Statut.values:
            qs = qs.filter(statut=statut)
        q = self.request.GET.get("q", "").strip()
        if q:
            cond = (Q(participant__username__icontains=q) | Q(participant__first_name__icontains=q)
                    | Q(participant__last_name__icontains=q) | Q(participant__email__icontains=q)
                    | Q(evenement__titre__icontains=q))
            code = re.sub(r"[\s-]", "", q).lower()
            if re.fullmatch(r"[0-9a-f]{6,32}", code):                 # recherche aussi par début de code de billet
                cond |= Q(code_billet__startswith=code)
            qs = qs.filter(cond)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(q=self.request.GET.get("q", ""), statut=self.request.GET.get("statut", ""),
                   statuts=Inscription.Statut.choices, filtres=_filtres(self.request))
        return ctx


class InscriptionListView(ModuleRequiredMixin, InscriptionFiltresMixin, ListView):
    """Liste globale des inscriptions des événements gérés : filtre par événement et par statut."""
    module = "participants"

    def base_queryset(self):
        qs = Inscription.objects.filter(evenement__in=evenements_geres(self.request.user))
        evenement = _entier(self.request.GET.get("evenement"))
        return qs.filter(evenement_id=evenement) if evenement else qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement_filtre=_entier(self.request.GET.get("evenement")),
                                        evenements_choix=evenements_geres(self.request.user).order_by("-date_debut"),
                                        **kwargs)


class ParticipantsEvenementView(ProprietaireEvenementMixin, InscriptionFiltresMixin, ListView):
    """Inscrits d'un événement (même gabarit que la liste globale, événement fixé)."""

    def get_evenement(self):
        if not hasattr(self, "_evenement"):
            self._evenement = get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])
        return self._evenement

    def base_queryset(self):
        return self.get_evenement().inscriptions.all()

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)


class InscriptionExportCsvView(InscriptionListView):
    """Export CSV des inscriptions : mêmes permissions et mêmes filtres (q, statut, evenement) que la liste.
    Encodage utf-8-sig et séparateur « ; » pour qu'Excel (en français) l'ouvre directement."""
    paginate_by = None
    COLONNES = ("Nom", "E-mail", "Type de billet", "Quantité", "Montant (DT)", "Statut", "Date d'inscription",
                "Présent", "Code")

    @staticmethod
    def cellule(valeur):
        """Neutralise les formules (=, +, -, @) qu'un tableur exécuterait à l'ouverture."""
        texte = str(valeur)
        return f"'{texte}" if texte[:1] in ("=", "+", "-", "@", "\t", "\r") else texte

    def render_to_response(self, context, **kwargs):
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = f'attachment; filename="inscriptions-{timezone.localdate():%Y%m%d}.csv"'
        # utf-8-sig = UTF-8 précédé d'une seule marque BOM. (Avec charset=utf-8-sig, HttpResponse encoderait chaque
        # écriture à part et répéterait la BOM au début de chaque ligne.)
        reponse.write("﻿")
        ecrivain = csv.writer(reponse, delimiter=";")
        ecrivain.writerow(self.COLONNES)
        for i in context["object_list"]:
            p = i.participant
            ecrivain.writerow([self.cellule(v) for v in (
                p.get_full_name() or p.username, p.email,
                i.type_billet.nom if i.type_billet else "Entrée", i.quantite,
                f"{i.montant:.2f}".replace(".", ","), i.get_statut_display(),
                timezone.localtime(i.date_inscription).strftime("%d/%m/%Y %H:%M"),
                "Oui" if i.present else "Non", i.code_court)])
        return reponse


class TableauBordView(ProprietaireEvenementMixin, TemplateView):
    """Tableau de bord d'un événement (mêmes accès que la liste de ses inscrits) : indicateurs + 3 graphiques.
    Tous les chiffres sont calculés ici par agrégations ORM, puis passés au gabarit avec json_script."""
    template_name = "participants/evenement_tableau.html"

    def get_evenement(self):
        if not hasattr(self, "_evenement"):
            self._evenement = get_object_or_404(Evenement.objects.select_related("lieu"), pk=self.kwargs["evenement_pk"])
        return self._evenement

    def get_context_data(self, **kwargs):
        e = self.get_evenement()
        S = Inscription.Statut
        qs = e.inscriptions.all()
        conf = qs.filter(statut=S.CONFIRMEE)
        par_statut = dict(qs.values_list("statut").annotate(n=Count("pk")))
        c = conf.aggregate(places=Coalesce(Sum("quantite"), 0), ca=Coalesce(Sum("montant"), Decimal("0")),
                           n=Count("pk"), presents=Count("pk", filter=Q(present=True)))
        note = Avis.objects.filter(inscription__evenement=e).aggregate(m=Avg("note"), n=Count("pk"))
        indicateurs = {
            "confirmes": par_statut.get(S.CONFIRMEE, 0), "places_confirmees": c["places"],
            "attente": par_statut.get(S.ATTENTE, 0), "annules": par_statut.get(S.ANNULEE, 0),
            "taux_remplissage": round(c["places"] * 100 / e.capacite) if e.capacite else 0,
            "chiffre_affaires": c["ca"],
            "taux_presence": round(c["presents"] * 100 / c["n"]) if c["n"] else 0, "presents": c["presents"],
            "note_moyenne": round(note["m"], 1) if note["m"] is not None else None, "nb_avis": note["n"],
        }
        ventes = (conf.values("type_billet__nom").annotate(places=Sum("quantite"), ca=Sum("montant"))
                  .order_by("-places", "type_billet__nom"))
        par_jour = (qs.annotate(jour=TruncDate("date_inscription")).values("jour")
                    .annotate(n=Count("pk")).order_by("jour"))
        graphiques = {
            "statuts": {"labels": [lib for code, lib in S.choices], "valeurs": [par_statut.get(code, 0) for code, _ in S.choices]},
            "ventes": {"labels": [v["type_billet__nom"] or "Entrée" for v in ventes],
                       "places": [v["places"] for v in ventes], "ca": [float(v["ca"]) for v in ventes]},
            "jours": {"labels": [f"{j['jour']:%d/%m}" for j in par_jour], "valeurs": [j["n"] for j in par_jour]},
        }
        return super().get_context_data(evenement=e, indicateurs=indicateurs, graphiques=graphiques,
                                        vide=not qs.exists(), **kwargs)


class InscriptionDetailView(ModuleRequiredMixin, DetailView):
    """Détail d'une inscription pour l'organisateur de l'événement (ou l'admin)."""
    module = "participants"
    template_name = "participants/inscription_detail.html"

    def get_queryset(self):
        return (Inscription.objects.filter(evenement__in=evenements_geres(self.request.user))
                .select_related("participant", "evenement", "evenement__lieu", "type_billet"))


class CheckinView(ProprietaireEvenementMixin, FormView):
    """Contrôle d'entrée : l'organisateur saisit (ou scanne) le code du billet."""
    form_class = CheckinForm
    template_name = "participants/checkin.html"

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_context_data(self, **kwargs):
        e = self.get_evenement()
        return super().get_context_data(evenement=e, presents=e.inscriptions.filter(present=True).count(), **kwargs)

    def veut_json(self):
        """Le scan par caméra (fetch) demande une réponse JSON ; le formulaire classique garde la redirection."""
        return "application/json" in self.request.headers.get("Accept", "")

    def controler(self, e, code):
        """Valide un billet. Retourne (résultat, niveau, message) ; résultat ∈ valide, deja_present, inconnu,
        non_confirme, ambigu."""
        trouves = list(e.inscriptions.filter(statut=Inscription.Statut.CONFIRMEE, code_billet__startswith=code)
                       .select_related("participant")[:2])
        if len(trouves) > 1:
            return "ambigu", "error", "Plusieurs billets correspondent à ce début de code : saisissez le code complet."
        if not trouves:
            autre = e.inscriptions.filter(code_billet__startswith=code).first()
            if autre:
                return ("non_confirme", "error",
                        f"Billet non confirmé ({autre.get_statut_display().lower()}) : entrée refusée.")
            return "inconnu", "error", "Billet introuvable pour cet événement."
        insc = trouves[0]
        # Mise à jour conditionnelle : un même billet ne peut pas être validé deux fois, même en simultané.
        if Inscription.objects.filter(pk=insc.pk, present=False).update(present=True):
            return "valide", "success", f"Bienvenue {insc.participant} ! Entrée enregistrée."
        return "deja_present", "warning", f"{insc.participant} est déjà entré."

    def form_valid(self, form):
        e = self.get_evenement()
        resultat, niveau, message = self.controler(e, form.cleaned_data["code"])   # code déjà normalisé
        if self.veut_json():
            return JsonResponse({"resultat": resultat, "niveau": niveau, "message": message,
                                 "presents": e.inscriptions.filter(present=True).count()})
        getattr(messages, niveau)(self.request, message)
        return redirect("participants:checkin", evenement_pk=e.pk)

    def form_invalid(self, form):
        if self.veut_json():
            return JsonResponse({"resultat": "invalide", "niveau": "error",
                                 "message": " ".join(form.errors.get("code", ["Code invalide."]))}, status=400)
        return super().form_invalid(form)


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


class TypeBilletListView(ModuleRequiredMixin, ListView):
    """Liste globale des types de billets des événements gérés : filtre par événement, recherche, pagination."""
    module = "participants"
    template_name = "participants/typebillet_list.html"
    paginate_by = 12

    def get_queryset(self):
        qs = (TypeBillet.objects.filter(evenement__in=evenements_geres(self.request.user))
              .select_related("evenement")
              .annotate(nb_vendus=Coalesce(Sum("inscriptions__quantite",
                                               filter=Q(inscriptions__statut=Inscription.Statut.CONFIRMEE)), 0))
              .order_by("-evenement__date_debut", "prix", "pk"))
        evenement = _entier(self.request.GET.get("evenement"))
        if evenement:
            qs = qs.filter(evenement_id=evenement)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(evenement__titre__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for t in ctx["object_list"]:                       # places restantes : None = quota illimité
            t.reste = None if t.quota is None else max(0, t.quota - t.nb_vendus)
        ctx.update(q=self.request.GET.get("q", ""), filtres=_filtres(self.request),
                   evenement_filtre=_entier(self.request.GET.get("evenement")),
                   evenements_choix=evenements_geres(self.request.user).order_by("-date_debut"))
        return ctx


class TypeBilletUpdateView(ProprietaireEvenementMixin, SuccessMessageMixin, UpdateView):
    """Modification d'un type de billet (le quota ne peut pas passer sous le nombre de billets vendus : voir le formulaire)."""
    model = TypeBillet
    form_class = TypeBilletForm
    success_message = "« %(nom)s » a été modifié."
    success_url = reverse_lazy("participants:typebillet_liste")

    def get_evenement(self):
        return self.get_object().evenement

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.object.evenement, **kwargs)


class TypeBilletDeleteView(ProprietaireEvenementMixin, SuppressionMixin, DeleteView):
    """Suppression avec confirmation. Si des inscriptions utilisent ce type (FK en PROTECT), SuppressionMixin
    refuse avec un message clair au lieu d'une erreur 500."""
    model = TypeBillet
    success_url = reverse_lazy("participants:typebillet_liste")

    def get_evenement(self):
        return self.get_object().evenement


class InscriptionActionView(ModuleRequiredMixin, View):
    """Base des actions POST de l'organisateur sur une inscription (jamais de GET, jamais de suppression physique).

    L'inscription doit appartenir à un événement géré par l'utilisateur (l'admin gère tout) : sinon 404.
    """
    module = "participants"
    http_method_names = ["post"]

    def post(self, request, pk):
        insc = get_object_or_404(Inscription.objects.filter(evenement__in=evenements_geres(request.user))
                                 .select_related("participant", "evenement"), pk=pk)
        self.agir(request, insc)
        return redirect("participants:inscription_detail", pk=insc.pk)

    def agir(self, request, insc):
        raise NotImplementedError


class InscriptionAnnulerGestionView(InscriptionActionView):
    """Annulation par l'organisateur : passe obligatoirement par Inscription.annuler() (statut ANNULEE, places
    libérées, liste d'attente promue). La ligne n'est pas supprimée."""

    def agir(self, request, insc):
        if insc.statut == Inscription.Statut.ANNULEE:
            messages.info(request, "Cette inscription est déjà annulée.")
        elif insc.present:
            messages.error(request, f"{insc.participant} est déjà entré : annulez d'abord son check-in.")
        else:
            insc.annuler()
            messages.success(request, f"Inscription de {insc.participant} annulée. Les places libérées "
                                      "ont été proposées à la liste d'attente.")


class InscriptionCheckinAnnulerView(InscriptionActionView):
    """Annule un check-in (entrée validée par erreur)."""

    def agir(self, request, insc):
        # Mise à jour conditionnelle, comme le check-in : pas de double traitement en cas de requêtes simultanées.
        if Inscription.objects.filter(pk=insc.pk, present=True).update(present=False):
            messages.success(request, f"Entrée de {insc.participant} annulée.")
        else:
            messages.info(request, f"{insc.participant} n'est pas marqué comme présent.")


class AvisListView(ModuleRequiredMixin, ListView):
    """Avis des événements gérés (organisateur : les siens, admin : tous) : filtre par événement et par note, recherche."""
    module = "participants"
    template_name = "participants/avis_list.html"
    paginate_by = 12

    def get_queryset(self):
        qs = (Avis.objects.filter(inscription__evenement__in=evenements_geres(self.request.user))
              .select_related("inscription__participant", "inscription__evenement").order_by("-date", "-pk"))
        evenement = _entier(self.request.GET.get("evenement"))
        if evenement:
            qs = qs.filter(inscription__evenement_id=evenement)
        note = _entier(self.request.GET.get("note"))
        if note in range(1, 6):
            qs = qs.filter(note=note)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(commentaire__icontains=q) | Q(inscription__participant__username__icontains=q)
                           | Q(inscription__participant__first_name__icontains=q)
                           | Q(inscription__participant__last_name__icontains=q)
                           | Q(inscription__evenement__titre__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        moyenne = self.object_list.aggregate(m=Avg("note"))["m"]
        ctx.update(q=self.request.GET.get("q", ""), filtres=_filtres(self.request), moyenne=moyenne,
                   evenement_filtre=_entier(self.request.GET.get("evenement")), note_filtre=_entier(self.request.GET.get("note")),
                   notes=range(5, 0, -1), evenements_choix=evenements_geres(self.request.user).order_by("-date_debut"))
        return ctx


class AvisUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    """Modification de son propre avis (réservée à l'auteur)."""
    model = Avis
    form_class = AvisForm
    success_message = "Votre avis a été modifié."
    success_url = reverse_lazy("participants:mes_inscriptions")

    def test_func(self):
        return self.get_object().inscription.participant_id == self.request.user.id

    def get_context_data(self, **kwargs):
        return super().get_context_data(inscription=self.object.inscription, **kwargs)


class AvisAccesMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Accès à un avis : son auteur, l'organisateur de l'événement concerné, ou l'admin (403 pour les autres)."""

    def test_func(self):
        avis, u = self.get_object(), self.request.user
        return avis.inscription.participant_id == u.id or evenements_geres(u).filter(pk=avis.inscription.evenement_id).exists()


class AvisDetailView(AvisAccesMixin, DetailView):
    model = Avis
    template_name = "participants/avis_detail.html"

    def get_queryset(self):
        return Avis.objects.select_related("inscription__participant", "inscription__evenement", "inscription__type_billet")

    def get_context_data(self, **kwargs):
        return super().get_context_data(est_auteur=self.object.inscription.participant_id == self.request.user.id, **kwargs)


class AvisDeleteView(AvisAccesMixin, SuppressionMixin, DeleteView):
    """Suppression d'un avis : par son auteur, ou par modération (organisateur de l'événement, admin)."""
    model = Avis
    success_message = "L'avis « {objet} » a été supprimé."

    def get_success_url(self):
        if self.object.inscription.participant_id == self.request.user.id:
            return reverse_lazy("participants:mes_inscriptions")
        return reverse_lazy("participants:avis_liste")


class TypeBilletDetailView(ProprietaireEvenementMixin, DetailView):
    """Détail d'un type de billet : prix, quota, vendus / restants et réservations qui l'utilisent."""
    model = TypeBillet
    template_name = "participants/typebillet_detail.html"

    def get_queryset(self):
        return TypeBillet.objects.select_related("evenement")

    def get_evenement(self):
        return self.get_object().evenement

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["inscriptions"] = self.object.inscriptions.select_related("participant").order_by("-date_inscription")
        return ctx


class ModifierInscriptionView(LoginRequiredMixin, FormView):
    """Le participant modifie SA réservation (type de billet, nombre de places) avant le début de l'événement.
    Toute la règle métier (places, quotas, montant, liste d'attente) est dans ``Inscription.modifier()``."""
    form_class = ModificationReservationForm
    template_name = "participants/reservation_modifier.html"

    def get_inscription(self):
        if not hasattr(self, "_inscription"):
            self._inscription = get_object_or_404(
                Inscription.objects.select_related("evenement", "type_billet"), pk=self.kwargs["pk"],
                participant=self.request.user)                    # jamais la réservation d'un autre
        return self._inscription

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            motif = self.get_inscription().motif_refus_modification()
            if motif:
                messages.error(request, motif)
                return redirect("participants:mes_inscriptions")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "inscription": self.get_inscription()}

    def get_context_data(self, **kwargs):
        insc = self.get_inscription()
        return super().get_context_data(inscription=insc, evenement=insc.evenement, **kwargs)

    def form_valid(self, form):
        insc = self.get_inscription()
        d = form.cleaned_data
        avant = (insc.type_billet_id, insc.quantite)
        try:
            insc.modifier(d.get("type_billet"), d["quantite"])
        except ValidationError as err:
            form.add_error(None, err)
            return self.form_invalid(form)
        if (insc.type_billet_id, insc.quantite) == avant:
            messages.info(self.request, "Aucune modification : votre réservation est inchangée.")
            return redirect("participants:mes_inscriptions")
        if insc.statut == Inscription.Statut.ATTENTE:
            messages.warning(self.request, "Réservation modifiée : elle reste sur la liste d'attente.")
        else:
            messages.success(self.request, f"Réservation modifiée : {insc.quantite} place(s), "
                                           f"total {insc.montant:.2f} DT.")
        return redirect(insc)
