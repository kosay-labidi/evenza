import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Count
from django.http import HttpResponseRedirect, QueryDict
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from core.mixins import AdminRequiredMixin, SuppressionMixin
from core.permissions import peut_gerer_compte

from . import filtres, roles
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


CLE_SESSION_VUE = "utilisateurs_vue"      # mode d'affichage mémorisé dans la session (aucun modèle)


def _qs(params):
    """QueryDict -> « a=1&b=2 » (valeurs encodées)."""
    return params.urlencode()


class UtilisateurListView(AdminRequiredMixin, ListView):
    """Liste des comptes : KPI, recherche, filtres combinables, tri en liste blanche, pagination 10/20/50,
    vue tableau ou cartes (mêmes données, mêmes droits). Toute la logique de filtre est dans filtres.py."""
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_list.html"
    TRIS = filtres.TRIS

    def get_filtres(self):
        if not hasattr(self, "_filtres"):
            self._form = filtres.FiltresForm(self.request.GET)
            self._filtres = self._form.valeurs()
        return self._filtres

    def get_vue(self):
        vue = self.request.GET.get("vue")
        if vue in filtres.VUES:
            self.request.session[CLE_SESSION_VUE] = vue
            return vue
        vue = self.request.session.get(CLE_SESSION_VUE)
        return vue if vue in filtres.VUES else "tableau"

    def get_paginate_by(self, queryset):
        return self.get_filtres().get("par_page") or filtres.PAR_PAGE_DEFAUT

    def get_queryset(self):
        v = self.get_filtres()
        tri = filtres.TRIS[v.get("tri") or filtres.TRI_DEFAUT][1]
        return (filtres.filtrer(Utilisateur.objects.all(), v)
                .annotate(nb_evenements=Count("evenements_organises", distinct=True),
                          nb_inscriptions=Count("inscriptions", distinct=True)).order_by(*tri))

    def paginate_queryset(self, queryset, page_size):
        """Numéro de page hors limites ou invalide : dernière / première page au lieu d'une erreur 404."""
        paginator = self.get_paginator(queryset, page_size, orphans=self.get_paginate_orphans(),
                                       allow_empty_first_page=self.get_allow_empty())
        page = paginator.get_page(self.request.GET.get(self.page_kwarg))
        return paginator, page, page.object_list, page.has_other_pages()

    def params(self, **changements):
        """Paramètres GET actuels (sans « page »), modifiés : valeur None = paramètre retiré."""
        p = self.request.GET.copy()
        p.pop("page", None)
        for cle, val in changements.items():
            p.pop(cle, None)
            if val not in (None, ""):
                p[cle] = val
        return p

    def contexte_kpi(self, v):
        mois = filtres.debut_du_mois().date().isoformat()
        garder = {"tri": v.get("tri"), "par_page": self.request.GET.get("par_page") and v.get("par_page"),
                  "vue": self.get_vue()}
        garder = {k: val for k, val in garder.items() if val}            # valeurs validées uniquement
        cartes = [
            ("total", "Utilisateurs", "Tous les comptes", {}, not (v.get("statut") or v.get("connexion") == "jamais"
                                                                  or v.get("inscrit_du"))),
            ("actifs", "Comptes actifs", "Peuvent se connecter", {"statut": "actif"}, v.get("statut") == "actif"),
            ("desactives", "Désactivés", "Accès bloqué, données conservées", {"statut": "inactif"},
             v.get("statut") == "inactif"),
            ("nouveaux_mois", "Nouveaux ce mois-ci", f"Depuis le {filtres.debut_du_mois():%d/%m}",
             {"inscrit_du": mois}, str(v.get("inscrit_du") or "") == mois and not v.get("inscrit_au")),
            ("jamais_connectes", "Jamais connectés", "Aucune connexion enregistrée", {"connexion": "jamais"},
             v.get("connexion") == "jamais"),
        ]
        valeurs = filtres.indicateurs(Utilisateur.objects.all())
        return [{"cle": cle, "titre": titre, "aide": aide, "valeur": valeurs[cle], "actif": actif,
                 "url": "?" + "&".join(f"{k}={val}" for k, val in {**garder, **params}.items())}
                for cle, titre, aide, params, actif in cartes]

    def contexte_puces(self, v):
        """Filtres actifs sous forme de puces supprimables."""
        form, puces = self._form, []
        for nom, libelle in filtres.FiltresForm.LIBELLES.items():
            val = v.get(nom)
            if val in (None, ""):
                continue
            champ = form.fields[nom]
            texte = dict(champ.choices).get(val, val) if hasattr(champ, "choices") else val
            if hasattr(val, "strftime"):
                texte = val.strftime("%d/%m/%Y")
            puces.append({"libelle": libelle, "valeur": texte, "url": "?" + _qs(self.params(**{nom: None}))})
        return puces

    def contexte_colonnes(self, tri):
        colonnes = {}
        for col, (asc, desc) in filtres.COLONNES_TRI.items():
            etat = "ascending" if tri == asc else "descending" if tri == desc else "none"
            suivant = desc if tri == asc else asc
            colonnes[col] = {"url": "?" + _qs(self.params(tri=suivant)), "aria": etat}
        return colonnes

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        for compte in ctx["object_list"]:
            compte.gerable = peut_gerer_compte(user, compte)
        v = self.get_filtres()
        tri = v.get("tri") or filtres.TRI_DEFAUT
        ctx.update(
            form_filtres=self._form, erreurs_filtres=self._form.errors,
            q=v.get("q", ""), role_actif=v.get("role", ""), statut=v.get("statut", ""), tri=tri,
            tris=[(cle, libelle) for cle, (libelle, _) in filtres.TRIS.items()], roles=Utilisateur.Role.choices,
            par_page=self.get_paginate_by(None), choix_par_page=filtres.PAR_PAGE, vue=self.get_vue(),
            kpis=self.contexte_kpi(v), puces=self.contexte_puces(v), colonnes=self.contexte_colonnes(tri),
            total_global=Utilisateur.objects.count(),
            url_vue_tableau="?" + _qs(self.params(vue="tableau")), url_vue_cartes="?" + _qs(self.params(vue="cartes")),
            selectionnables=any(c.gerable and c.pk != user.pk for c in ctx["object_list"]),
        )
        # Onglets de rôle avec effectifs (selon les autres filtres en cours).
        sans_role = {k: val for k, val in v.items() if k != "role"}
        effectifs = dict(filtres.filtrer(Utilisateur.objects.all(), sans_role).order_by()
                         .values_list("role").annotate(n=Count("pk")))
        ctx["onglets_roles"] = [(val, nom, effectifs.get(val, 0)) for val, nom in Utilisateur.Role.choices]
        ctx["total_tous_roles"] = sum(effectifs.values())
        ctx["filtres"] = _qs(self.params())
        ctx["filtres_sans_role"] = _qs(self.params(role=None))
        return ctx


class UtilisateurDetailView(AdminRequiredMixin, DetailView):
    model = Utilisateur
    template_name = "utilisateurs/utilisateur_detail.html"
    context_object_name = "compte"   # « user » reste l'utilisateur connecté

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        ctx["evenements"] = c.evenements_organises.select_related("lieu")[:10]
        ctx["inscriptions"] = c.inscriptions.select_related("evenement")[:10]
        ctx["peut_gerer"] = peut_gerer_compte(self.request.user, c)
        ctx["protege"] = not ctx["peut_gerer"]
        ctx["fiche_role"] = roles.fiche_role(c.role)
        ctx["acces_admin_django"] = c.is_staff and c.is_active
        # Activité métier : uniquement ce qui existe réellement dans les modèles (lecture seule, comptages).
        activite = {"nb_evenements": c.evenements_organises.count()}
        par_statut = dict(c.inscriptions.order_by().values_list("statut").annotate(n=Count("pk")))
        activite["inscriptions"] = {"total": sum(par_statut.values()), "confirmees": par_statut.get("CONFIRMEE", 0),
                                    "attente": par_statut.get("ATTENTE", 0), "annulees": par_statut.get("ANNULEE", 0)}
        fiche = getattr(c, "prestataire", None)
        if fiche is not None:
            reservations = fiche.reservations.order_by().values_list("statut").annotate(n=Count("pk"))
            activite["prestataire"] = {"fiche": fiche, "reservations": dict(reservations),
                                       "nb_reservations": sum(n for _, n in reservations)}
        ctx["activite"] = activite
        return ctx


class UtilisateurCreateView(AdminRequiredMixin, EnregistrementSurMixin, SuccessMessageMixin, CreateView):
    model = Utilisateur
    form_class = UtilisateurCreationAdminForm
    template_name = "utilisateurs/utilisateur_form.html"
    success_message = "Le compte « %(username)s » a été créé."

    def get_context_data(self, **kwargs):
        return super().get_context_data(catalogue_roles=roles.catalogue(), **kwargs)

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

    def get_context_data(self, **kwargs):
        return super().get_context_data(catalogue_roles=roles.catalogue(), **kwargs)

    def confirmation_requise(self, avant, nouveau):
        """Changement de rôle : il faut une confirmation explicite, pour CE nouveau rôle, à partir du rôle
        actuellement en base (si un autre admin l'a changé entre-temps, on redemande). Vérifié côté serveur."""
        if nouveau == avant.role:
            return False
        post = self.request.POST
        return not (post.get("confirmer_role") == nouveau and post.get("role_initial") == avant.role)

    def contexte_confirmation(self, form, avant, nouveau):
        donnees, avertissements = roles.consequences_changement(avant, nouveau)
        return self.get_context_data(form=form, confirmation={
            "ancien": roles.fiche_role(avant.role), "nouveau": roles.fiche_role(nouveau),
            "comparaison": roles.comparer_roles(avant.role, nouveau),
            "gestion_comptes_retiree": avant.est_admin and not avant.is_superuser and nouveau != Utilisateur.Role.ADMIN,
            "gestion_comptes_accordee": not avant.est_admin and nouveau == Utilisateur.Role.ADMIN,
            "donnees": donnees, "avertissements": avertissements, "role_initial": avant.role})

    def form_valid(self, form):
        try:
            with transaction.atomic():
                verrouiller_admins()
                # nouveau contrôle sous verrou : un autre admin a pu changer d'état entre-temps
                avant = Utilisateur.objects.get(pk=self.object.pk)
                nouveau = form.cleaned_data["role"]
                motif = motif_refus_changement(self.request.user, avant, role=nouveau)
                if motif:
                    form.add_error("role", motif)
                    return self.form_invalid(form)
                if self.confirmation_requise(avant, nouveau):
                    # Rien n'est enregistré : on affiche l'étape de confirmation (même formulaire, mêmes valeurs).
                    return self.render_to_response(self.contexte_confirmation(form, avant, nouveau))
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


MAX_SELECTION = max(filtres.PAR_PAGE)        # une action groupée porte au plus sur une page de résultats


class UtilisateurActionGroupeeView(AdminRequiredMixin, TemplateView):
    """Activation / désactivation de plusieurs comptes (POST uniquement, jeton CSRF).

    1er POST : récapitulatif (concernés, déjà dans le statut, protégés, refusés), rien n'est modifié.
    2e POST (``confirmer``) : TOUT est revérifié sous verrou (verrouiller_admins) ; si un seul compte est
    interdit, rien n'est modifié (tout ou rien). Aucune suppression groupée.
    """
    template_name = "utilisateurs/utilisateur_action_groupee.html"
    http_method_names = ["post"]
    ACTIONS = {"activer": True, "desactiver": False}

    def url_retour(self):
        """Retour à la liste avec ses filtres. On ne réutilise que des paires clé=valeur, jamais une URL."""
        params = QueryDict(self.request.POST.get("retour", "")[:1000])
        return reverse("utilisateurs:utilisateur_liste") + (f"?{params.urlencode()}" if params else "")

    def lire_selection(self):
        """(action, ids, erreur). Identifiants validés : entiers, sans doublon, nombre limité."""
        action = self.request.POST.get("action")
        if action not in self.ACTIONS:
            return None, [], "Action inconnue."
        brut = self.request.POST.getlist("ids")
        try:
            ids = sorted({int(x) for x in brut})
        except (TypeError, ValueError):
            return action, [], "Sélection invalide."
        if not ids:
            return action, [], "Sélectionnez au moins un compte."
        if len(ids) > MAX_SELECTION:
            return action, [], f"Sélection trop grande : {MAX_SELECTION} comptes au maximum à la fois."
        return action, ids, None

    def analyser(self, action, ids):
        """Classe chaque compte sélectionné. Toujours recalculé (jamais repris du 1er POST)."""
        acteur, activer = self.request.user, self.ACTIONS[action]
        comptes = list(Utilisateur.objects.filter(pk__in=ids).order_by("username"))
        r = {"a_modifier": [], "deja": [], "proteges": [], "refuses": [],
             "introuvables": len(set(ids) - {c.pk for c in comptes}), "comptes": comptes}
        for c in comptes:
            if not peut_gerer_compte(acteur, c):
                r["proteges"].append((c, "Compte technique protégé : géré uniquement par un superutilisateur."))
            elif c.is_active == activer:
                r["deja"].append(c)
            elif not activer and c.pk == acteur.pk:
                r["refuses"].append((c, "Vous ne pouvez pas désactiver votre propre compte."))
            else:
                r["a_modifier"].append(c)
        if not activer:
            # Dernier administrateur actif : il doit en rester au moins un APRÈS l'opération groupée.
            admins_vises = [c for c in r["a_modifier"] if c.est_admin]
            if admins_vises and not admins_actifs().exclude(pk__in=[c.pk for c in r["a_modifier"]]).exists():
                for c in admins_vises:
                    r["a_modifier"].remove(c)
                    r["refuses"].append((c, "Impossible : il ne resterait plus aucun administrateur actif."))
        r["bloquant"] = bool(r["proteges"] or r["refuses"] or r["introuvables"])
        return r

    def post(self, request, *args, **kwargs):
        action, ids, erreur = self.lire_selection()
        if erreur:
            messages.error(request, erreur)
            return redirect(self.url_retour())
        if not request.POST.get("confirmer"):
            return self.render_to_response(self.get_context_data(
                action=action, activer=self.ACTIONS[action], analyse=self.analyser(action, ids),
                retour=request.POST.get("retour", ""), url_retour=self.url_retour()))
        try:
            with transaction.atomic():
                verrouiller_admins()
                analyse = self.analyser(action, ids)          # revérifié sous verrou, au moment de la confirmation
                if analyse["bloquant"]:
                    messages.error(request, "Aucun compte n'a été modifié : la sélection contient des comptes "
                                            "protégés, introuvables ou interdits pour cette action.")
                    return redirect(self.url_retour())
                pks = [c.pk for c in analyse["a_modifier"]]
                Utilisateur.objects.filter(pk__in=pks).update(is_active=self.ACTIONS[action])
        except OperationalError:
            messages.error(request, MSG_OPERATION_CONCURRENTE)
            return redirect(self.url_retour())
        verbe = "réactivé" if self.ACTIONS[action] else "désactivé"
        n, deja = len(pks), len(analyse["deja"])
        texte = f"{n} compte{'s' if n > 1 else ''} {verbe}{'s' if n > 1 else ''}."
        if deja:
            texte += f" {deja} déjà dans ce statut (inchangé{'s' if deja > 1 else ''})."
        messages.success(request, texte)
        return redirect(self.url_retour())


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
