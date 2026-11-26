import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, SuppressionMixin
from core.permissions import peut_gerer_compte

from .forms import (MSG_EMAIL_PRIS, ChangementMotDePasseForm, InscriptionCompteForm, NouveauMotDePasseForm,
                    ProfilForm, UtilisateurAdminForm, UtilisateurCreationAdminForm, email_deja_utilise)
from .models import Utilisateur
from .securite import (DUREE_BLOCAGE, VARIABLE_URL_PUBLIQUE, admins_actifs, compter_tentative, connexion_bloquee,
                       donnees_d_autrui, enregistrer_echec, limite_atteinte, motif_refus_changement,
                       motif_refus_desactivation, motif_refus_reactivation, motif_refus_suppression,
                       origine_de_confiance, reinitialiser_echecs)

logger = logging.getLogger(__name__)

# Backend enregistré dans la session à l'inscription : il doit figurer dans AUTHENTICATION_BACKENDS,
# sinon Django ignore la session dès la requête suivante (l'utilisateur serait déconnecté).
BACKEND_CONNEXION = "utilisateurs.backends.EmailOuUsernameBackend"

# Cartes affichées à l'étape 1 de l'inscription : doivent correspondre à forms.ROLES_INSCRIPTION_PUBLIQUE
# (le formulaire refuse de toute façon côté serveur tout autre rôle envoyé en POST).
ROLES_INSCRIPTION = [
    ("PARTICIPANT", "Participant", "Je réserve des billets et je participe à des événements.", "M3 9a2 2 0 0 0 0 4v4h18v-4a2 2 0 0 1 0-4V5H3zM14 5v12"),
    ("CLIENT", "Client", "Je confie l'organisation de mon événement à une agence.", "M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z"),
]


MSG_OPERATION_CONCURRENTE = ("Une autre modification de compte est en cours. Rien n'a été changé : "
                             "réessayez dans un instant.")


def verrouiller_admins():
    """À appeler EN PREMIER dans transaction.atomic(), avant tout contrôle « dernier administrateur ».

    PostgreSQL / MySQL : SELECT … FOR UPDATE sur les admins actifs ; une opération concurrente attend.
    SQLite : FOR UPDATE n'existe pas (Django l'ignore). On exécute donc d'abord une écriture neutre
    (aucune valeur ne change) : SQLite prend alors son verrou d'écriture global AVANT toute lecture de la
    transaction. Une opération concurrente attend la validation de la première (délai : « timeout » de
    SQLite, 5 s par défaut), puis relit l'état validé. Sans cela, les deux transactions lisent puis
    tentent d'écrire, et SQLite les fait échouer (« database is locked ») : vérifié par un test concurrent.
    """
    if connection.vendor == "sqlite":
        admins_actifs().update(is_active=True)        # écriture neutre : verrou d'écriture pris ici
    else:
        list(admins_actifs().select_for_update().values_list("pk", flat=True))


def erreur_unicite(form):
    """IntegrityError à l'enregistrement : une requête concurrente a pris le même e-mail ou identifiant
    entre la validation du formulaire et l'écriture (contraintes d'unicité en base). On l'indique sur le
    champ concerné au lieu d'une erreur 500. À appeler APRÈS la sortie du bloc atomic (transaction annulée)."""
    pk = form.instance.pk if not form.instance._state.adding else None
    email = (form.cleaned_data.get("email") or "").strip()
    username = form.cleaned_data.get("username")
    if email and email_deja_utilise(email, sauf_pk=pk):
        form.add_error("email", MSG_EMAIL_PRIS)
    elif username and Utilisateur.objects.filter(username__iexact=username).exclude(pk=pk).exists():
        form.add_error("username", "Ce nom d'utilisateur vient d'être pris. Choisissez-en un autre.")
    else:
        form.add_error(None, "L'enregistrement a échoué car les données ont changé entre-temps. Réessayez.")


class EnregistrementSurMixin:
    """form_valid() des vues de création / modification de compte : enregistrement atomique, et
    IntegrityError (course sur l'e-mail ou l'identifiant) transformée en erreur de formulaire."""

    def form_valid(self, form):
        try:
            with transaction.atomic():
                return super().form_valid(form)
        except IntegrityError:
            erreur_unicite(form)
            return self.form_invalid(form)


class ConnexionView(auth_views.LoginView):
    template_name = "utilisateurs/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        # trop d'échecs récents : on refuse sans même vérifier le mot de passe (blocage temporaire)
        if connexion_bloquee(request, request.POST.get("username")):
            form = self.get_form_class()(request, initial={"username": request.POST.get("username", "")})
            return self.render_to_response(self.get_context_data(form=form, bloque=True), status=429)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs.setdefault("duree_blocage", DUREE_BLOCAGE // 60)
        return super().get_context_data(**kwargs)

    def form_invalid(self, form):
        enregistrer_echec(self.request, self.request.POST.get("username"))
        return super().form_invalid(form)

    def form_valid(self, form):
        reinitialiser_echecs(self.request, self.request.POST.get("username"))
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

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:   # pas de second compte créé depuis une session ouverte
            messages.info(request, "Vous êtes déjà connecté. Déconnectez-vous pour créer un autre compte.")
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except IntegrityError:                       # e-mail ou identifiant pris au même instant
            erreur_unicite(form)
            return self.form_invalid(form)
        login(self.request, self.object, backend=BACKEND_CONNEXION)
        messages.success(self.request, "Bienvenue sur Évenza ! Votre compte est créé.")
        return response


class ProfilView(LoginRequiredMixin, EnregistrementSurMixin, SuccessMessageMixin, UpdateView):
    form_class = ProfilForm
    template_name = "utilisateurs/profil.html"
    success_url = reverse_lazy("utilisateurs:profil")
    success_message = "Profil mis à jour."

    def get_object(self, queryset=None):
        return self.request.user


class MotDePasseChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    """Changement par l'utilisateur connecté (vue native de Django, réservée aux comptes connectés).
    Django conserve la session courante (update_session_auth_hash) ; les autres sessions du compte,
    liées à l'ancien mot de passe, ne sont plus valides."""
    form_class = ChangementMotDePasseForm
    template_name = "utilisateurs/password_change_form.html"
    success_url = reverse_lazy("utilisateurs:profil")
    success_message = "Votre mot de passe a été modifié. Vos autres sessions ouvertes ont été déconnectées."


# ---- mot de passe oublié : les 4 vues de Django avec nos templates ----
class MotDePasseOublieView(auth_views.PasswordResetView):
    template_name = "utilisateurs/password_reset_form.html"
    email_template_name = "utilisateurs/password_reset_email.html"
    subject_template_name = "utilisateurs/password_reset_subject.txt"
    success_url = reverse_lazy("utilisateurs:password_reset_done")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        if limite_atteinte("reinitialisation", self.request, email):
            # même réponse que d'habitude : ne révèle ni l'existence du compte ni le blocage
            return HttpResponseRedirect(self.get_success_url())
        origine = origine_de_confiance(self.request)
        if origine is None:
            logger.error("Réinitialisation refusée : aucune origine de confiance pour l'hôte %r. Définissez %s "
                         "(ex. https://www.votre-domaine.tn).", self.request.get_host(), VARIABLE_URL_PUBLIQUE)
            form.add_error(None, "La réinitialisation du mot de passe est momentanément indisponible. "
                                 "Contactez l'agence Évenza.")
            return self.form_invalid(form)
        compter_tentative("reinitialisation", self.request, email)
        protocole, hote = origine
        form.save(domain_override=hote, use_https=protocole == "https", request=self.request,
                  token_generator=self.token_generator, from_email=self.from_email,
                  email_template_name=self.email_template_name, subject_template_name=self.subject_template_name,
                  html_email_template_name=self.html_email_template_name, extra_email_context=self.extra_email_context)
        return HttpResponseRedirect(self.get_success_url())


class MotDePasseEnvoyeView(auth_views.PasswordResetDoneView):
    template_name = "utilisateurs/password_reset_done.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(debug_console="console" in settings.EMAIL_BACKEND, **kwargs)


class NouveauMotDePasseView(auth_views.PasswordResetConfirmView):
    form_class = NouveauMotDePasseForm
    template_name = "utilisateurs/password_reset_confirm.html"
    success_url = reverse_lazy("utilisateurs:password_reset_complete")


class MotDePasseModifieView(auth_views.PasswordResetCompleteView):
    template_name = "utilisateurs/password_reset_complete.html"


# ---- CRUD des utilisateurs (réservé à l'administrateur) ----
class GestionCompteMixin(AdminRequiredMixin):
    """Administrateur ET droit de gérer CE compte (hiérarchie : core.permissions.peut_gerer_compte).
    Vérifié côté serveur en GET comme en POST : un ADMIN métier reçoit 403 sur un superutilisateur."""

    def test_func(self):
        return super().test_func() and peut_gerer_compte(self.request.user, self.get_object())


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

    def paginate_queryset(self, queryset, page_size):
        """Numéro de page hors limites ou invalide : dernière / première page au lieu d'une erreur 404."""
        paginator = self.get_paginator(queryset, page_size, orphans=self.get_paginate_orphans(),
                                       allow_empty_first_page=self.get_allow_empty())
        page = paginator.get_page(self.request.GET.get(self.page_kwarg))
        return paginator, page, page.object_list, page.has_other_pages()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for compte in ctx["object_list"]:
            compte.gerable = peut_gerer_compte(self.request.user, compte)
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
        ctx["peut_gerer"] = peut_gerer_compte(self.request.user, self.object)
        return ctx


class UtilisateurCreateView(AdminRequiredMixin, EnregistrementSurMixin, SuccessMessageMixin, CreateView):
    model = Utilisateur
    form_class = UtilisateurCreationAdminForm
    template_name = "utilisateurs/utilisateur_form.html"
    success_message = "Le compte « %(username)s » a été créé."

    def get_success_url(self):
        return reverse_lazy("utilisateurs:utilisateur_detail", args=[self.object.pk])


class UtilisateurUpdateView(GestionCompteMixin, SuccessMessageMixin, UpdateView):
    model = Utilisateur
    form_class = UtilisateurAdminForm
    template_name = "utilisateurs/utilisateur_form.html"
    context_object_name = "compte"
    success_message = "Le compte « %(username)s » a été modifié."

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "acteur": self.request.user}

    def form_valid(self, form):
        try:
            with transaction.atomic():
                verrouiller_admins()
                # nouveau contrôle sous verrou : un autre admin a pu changer d'état entre-temps
                avant = Utilisateur.objects.get(pk=self.object.pk)
                motif = motif_refus_changement(self.request.user, avant, role=form.cleaned_data["role"])
                if motif:
                    form.add_error("role", motif)
                    return self.form_invalid(form)
                return super().form_valid(form)
        except OperationalError:
            form.add_error(None, MSG_OPERATION_CONCURRENTE)
        except IntegrityError:
            erreur_unicite(form)
        return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("utilisateurs:utilisateur_detail", args=[self.object.pk])


class UtilisateurStatutView(GestionCompteMixin, DetailView):
    """Désactivation / réactivation logique d'un compte (champ ``is_active``).

    GET : page de confirmation. POST (jeton CSRF obligatoire) : changement du statut.
    Le compte et ses données (événements, réservations, inscriptions) sont conservés ;
    un compte désactivé ne peut plus se connecter et ses sessions ouvertes ne donnent plus accès.
    """
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_statut_confirm.html"
    context_object_name = "compte"
    activer = False   # False : désactiver, True : réactiver

    def motif_refus(self):
        if self.activer:
            return motif_refus_reactivation(self.object)
        return motif_refus_desactivation(self.object, self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(activer=self.activer, refus=self.motif_refus(),
                   nb_evenements=self.object.evenements_organises.count(),
                   nb_inscriptions=self.object.inscriptions.count())
        return ctx

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                verrouiller_admins()
                self.object = self.get_object()      # relu sous verrou
                refus = self.motif_refus()
                if not refus:
                    self.object.is_active = self.activer
                    self.object.save(update_fields=["is_active"])
        except OperationalError:                     # verrou toujours occupé après le délai d'attente
            messages.error(request, MSG_OPERATION_CONCURRENTE)
            return redirect("utilisateurs:utilisateur_detail", pk=self.kwargs["pk"])
        if refus:
            messages.error(request, refus)
        else:
            etat = "réactivé : il peut de nouveau se connecter" if self.activer else \
                "désactivé : il ne peut plus se connecter (ses données sont conservées)"
            messages.success(request, f"Le compte « {self.object.username} » a été {etat}.")
        return redirect("utilisateurs:utilisateur_detail", pk=self.object.pk)


class UtilisateurDeleteView(GestionCompteMixin, SuppressionMixin, DeleteView):
    """Suppression physique, seulement si elle n'efface aucune donnée appartenant à d'autres utilisateurs."""
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_confirm_delete.html"
    success_url = reverse_lazy("utilisateurs:utilisateur_liste")

    def get_url_si_protege(self):
        return reverse_lazy("utilisateurs:utilisateur_detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["nb_evenements"] = self.object.evenements_organises.count()
        ctx["nb_inscriptions"] = self.object.inscriptions.count()
        ctx["autrui"] = donnees_d_autrui(self.object)
        ctx["refus"] = motif_refus_suppression(self.object, self.request.user)
        return ctx

    def form_valid(self, form):
        try:
            with transaction.atomic():
                verrouiller_admins()
                refus = motif_refus_suppression(self.object, self.request.user)
                if refus:
                    messages.error(self.request, refus)
                    return redirect("utilisateurs:utilisateur_detail", pk=self.object.pk)
                return super().form_valid(form)
        except OperationalError:
            messages.error(self.request, MSG_OPERATION_CONCURRENTE)
            return redirect("utilisateurs:utilisateur_detail", pk=self.object.pk)
