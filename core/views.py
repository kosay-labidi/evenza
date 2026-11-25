from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from django.db.models import Count, Q, Sum

from evenements.models import Categorie, Evenement, Lieu
from participants.models import Avis, Inscription
from prestataires.models import Prestataire, Reservation, Service
from ressources.models import Affectation

from .forms import ContactForm
from .models import MessageContact


class HomeView(TemplateView):
    """Page d'accueil publique : prochains événements, catégories, chiffres réels."""
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        a_venir = (Evenement.objects.publies().filter(date_debut__gte=timezone.now())
                   .select_related("lieu", "categorie").prefetch_related("types_billet"))
        ctx["prochains"] = a_venir[:6]
        ctx["vedette"] = a_venir.filter(categorie__nom__iexact="Mariage").first() or a_venir.first()
        ctx["categories"] = (Categorie.objects.annotate(
            nb=Count("evenements", filter=Q(evenements__statut=Evenement.Statut.PUBLIE,
                                            evenements__date_debut__gte=timezone.now()))).order_by("-nb", "nom"))
        ctx["chiffres"] = {
            "evenements": Evenement.objects.publies().count(),
            "places": Inscription.objects.filter(statut=Inscription.Statut.CONFIRMEE).aggregate(n=Sum("quantite"))["n"] or 0,
            "prestataires": Prestataire.objects.count(),
            "lieux": Lieu.objects.count(),
        }
        # FAQ : quelques questions de chaque groupe
        ctx["faq_extrait"] = FAQ[0][1][:3] + FAQ[1][1][:2]
        # Témoignages : uniquement les vrais avis laissés par les participants (aucun texte inventé)
        ctx["avis"] = (Avis.objects.exclude(commentaire="").filter(note__gte=4)
                       .select_related("inscription__participant", "inscription__evenement").order_by("-date")[:3])
        # Services réellement proposés par les prestataires enregistrés
        ctx["types_services"] = [Service.Type(t).label for t in
                                 Service.objects.values_list("type", flat=True).distinct().order_by("type")]
        ctx["galerie"] = list(a_venir[:6])
        ctx["galerie_cats"] = list({e.categorie_id: e.categorie for e in ctx["galerie"]}.values())
        # Maison éditoriale : 4 événements à l'affiche (index 01–04), 2 en alternance, 1 en coupe diagonale
        liste = list(a_venir[:8])
        vedette = ctx["vedette"]
        autres = [e for e in liste if e != vedette]
        ctx["affiche"] = ([vedette] if vedette else []) + autres[:3]
        ctx["alternance"] = autres[:2]
        ctx["mise_en_avant"] = autres[2] if len(autres) > 2 else (autres[0] if autres else vedette)
        ctx["agenda"] = liste[:5]
        ctx["villes"] = Lieu.objects.values_list("ville", flat=True).distinct().order_by("ville")
        return ctx


class DashboardView(LoginRequiredMixin, TemplateView):
    """Tableau de bord adapté au rôle de l'utilisateur connecté."""
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        if u.est_organisateur:
            evts = Evenement.objects.filter(organisateur=u) if not u.est_admin else Evenement.objects.all()
            ctx.update(
                nb_evenements=evts.count(),
                nb_publies=evts.filter(statut=Evenement.Statut.PUBLIE).count(),
                nb_inscrits=Inscription.objects.filter(evenement__in=evts, statut=Inscription.Statut.CONFIRMEE).count(),
                nb_reservations=Reservation.objects.filter(evenement__in=evts).count(),
                nb_affectations=Affectation.objects.filter(evenement__in=evts).count(),
                mes_evenements=evts.select_related("lieu")[:8],
            )
            dates = evts.exclude(statut=Evenement.Statut.ANNULE)
        else:
            dates = Evenement.objects.filter(inscriptions__participant=u).exclude(
                inscriptions__statut=Inscription.Statut.ANNULEE)
        mes = Inscription.objects.filter(participant=u)
        ctx["mes_inscriptions"] = mes.select_related("evenement", "evenement__lieu")[:8]
        ctx["nb_billets"] = mes.filter(statut=Inscription.Statut.CONFIRMEE).count()
        ctx["nb_attente"] = mes.filter(statut=Inscription.Statut.ATTENTE).count()
        ctx["nb_a_venir"] = mes.exclude(statut=Inscription.Statut.ANNULEE).filter(
            evenement__date_debut__gte=timezone.now()).count()
        ctx["calendrier"] = calendrier_du_mois(dates.distinct())
        return ctx


def calendrier_du_mois(evenements):
    """Mois du prochain événement (sinon le mois courant), avec les jours où un événement a lieu."""
    import calendar
    from datetime import date

    aujourd_hui = timezone.localdate()
    prochain = evenements.filter(date_debut__gte=timezone.now()).order_by("date_debut").first()
    ref = timezone.localtime(prochain.date_debut).date() if prochain else aujourd_hui
    du_mois = [e for e in evenements.filter(date_debut__year=ref.year, date_debut__month=ref.month)
               .order_by("date_debut")]
    par_jour = {}
    for e in du_mois:
        par_jour.setdefault(timezone.localtime(e.date_debut).day, []).append(e)
    semaines = [[{"jour": j, "evts": par_jour.get(j, []), "aujourdhui": date(ref.year, ref.month, j) == aujourd_hui}
                 if j else None for j in semaine]
                for semaine in calendar.Calendar(firstweekday=0).monthdayscalendar(ref.year, ref.month)]
    return {"mois": date(ref.year, ref.month, 1), "semaines": semaines, "evenements": du_mois}


class AProposView(TemplateView):
    template_name = "core/a_propos.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["chiffres"] = {"evenements": Evenement.objects.publies().count(),
                           "billets": Inscription.objects.filter(statut=Inscription.Statut.CONFIRMEE).count(),
                           "prestataires": Reservation.objects.values("prestataire").distinct().count()}
        return ctx


class ContactView(CreateView):
    model = MessageContact
    form_class = ContactForm
    template_name = "core/contact.html"
    success_url = reverse_lazy("core:contact")

    def get_initial(self):
        u = self.request.user
        return {"nom": u.get_full_name(), "email": u.email} if u.is_authenticated else {}

    def form_valid(self, form):
        messages.success(self.request, "Merci ! Votre message a bien été envoyé. Nous répondons sous 48 h.")
        return super().form_valid(form)


FAQ = [
    ("Participants", [
        ("Comment réserver un billet ?", "Ouvrez l'événement, cliquez sur « Réserver mes billets », choisissez le type de billet et le nombre de places, vérifiez le récapitulatif puis confirmez. Votre billet QR s'affiche aussitôt."),
        ("Puis-je réserver pour plusieurs personnes ?", "Oui, jusqu'à 10 places en une seule réservation. Un seul QR code est valable pour toutes les places."),
        ("Que se passe-t-il si l'événement est complet ?", "Votre réservation passe en liste d'attente. Dès qu'une place se libère, elle est confirmée automatiquement, dans l'ordre d'inscription."),
        ("Comment annuler ?", "Dans « Mes billets », cliquez sur « Annuler ». Vos places sont libérées pour la liste d'attente."),
        ("Je n'ai pas reçu mon billet.", "Il est toujours disponible dans « Mes billets ». Vous pouvez le télécharger en image ou l'imprimer."),
    ]),
    ("Organisateurs", [
        ("Comment créer un événement ?", "Créez un compte « Organisateur », puis « + Créer ». L'événement reste en brouillon jusqu'à ce que vous le publiiez."),
        ("Puis-je proposer plusieurs prix ?", "Oui : ajoutez des types de billets (Standard, VIP, Étudiant…) avec un prix et, si besoin, un nombre limité de places."),
        ("Comment fonctionne le check-in ?", "Le jour J, ouvrez « Check-in à l'entrée » et saisissez ou scannez le code du billet : la présence est enregistrée."),
        ("Comment éviter les doubles réservations de matériel ?", "Évenza refuse automatiquement une affectation si la ressource n'a plus assez d'unités libres sur le même créneau."),
    ]),
    ("Compte", [
        ("J'ai oublié mon mot de passe.", "Sur la page de connexion, cliquez sur « Mot de passe oublié ? » et indiquez votre e-mail : vous recevrez un lien pour en choisir un nouveau."),
        ("Puis-je me connecter avec mon e-mail ?", "Oui, le nom d'utilisateur ou l'adresse e-mail fonctionnent tous les deux."),
    ]),
]


class FaqView(TemplateView):
    template_name = "core/faq.html"
    extra_context = {"faq": FAQ}


def erreur_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def erreur_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


class ApercuView(TemplateView):
    """APERÇU TEMPORAIRE : verre 3D + toast au scroll (à retirer après intégration dans l'accueil)."""
    template_name = "core/apercu.html"
