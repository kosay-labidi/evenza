from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse
from django.utils import timezone

from .forms import PrestataireAdminForm, RefusPrestataireForm
from .models import Prestataire, Reservation, Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Catalogue des services (US 4.5) : traiteur, son, lumière, décoration, photo, sécurité."""
    list_display = ("nom", "type", "nb_prestataires")
    list_filter = ("type",)
    search_fields = ("nom",)

    @admin.display(description="Prestataires")
    def nb_prestataires(self, obj):
        return obj.prestataires.count()


@admin.register(Prestataire)
class PrestataireAdmin(admin.ModelAdmin):
    """US 4.6 : liste, filtre par service, sélection des services ; e-mail unique (formulaire).

    Validation : filtre par statut de validation, actions groupées Approuver / Refuser (motif obligatoire,
    saisi sur une page intermédiaire). Seuls les prestataires « En attente » sont traités par ces actions.
    """
    form = PrestataireAdminForm
    list_display = ("nom", "telephone", "email", "statut_validation", "cree_par", "date_validation")
    list_filter = ("statut_validation", "services__type", "services")
    search_fields = ("nom", "email", "telephone")
    filter_horizontal = ("services",)
    readonly_fields = ("cree_par", "valide_par", "date_validation")
    list_select_related = ("cree_par",)
    actions = ("approuver", "refuser")
    fieldsets = (
        (None, {"fields": ("nom", "photo", "telephone", "email", "services", "compte")}),
        ("Validation", {"fields": ("statut_validation", "motif_refus", "cree_par", "valide_par", "date_validation")}),
    )

    def save_model(self, request, obj, form, change):
        """Création dans l'admin : créé par l'admin (APPROUVE par défaut). Statut modifié à la main : on trace qui."""
        if not change:
            obj.cree_par = request.user
        if not change or "statut_validation" in form.changed_data:
            if obj.statut_validation == Prestataire.Validation.EN_ATTENTE:
                obj.valide_par, obj.date_validation = None, None
            else:
                obj.valide_par, obj.date_validation = request.user, timezone.now()
            if obj.statut_validation != Prestataire.Validation.REFUSE:
                obj.motif_refus = ""
        super().save_model(request, obj, form, change)

    def _en_attente(self, request, queryset):
        attente = queryset.filter(statut_validation=Prestataire.Validation.EN_ATTENTE)
        ignores = queryset.count() - attente.count()
        if ignores:
            self.message_user(request, f"{ignores} prestataire(s) déjà traité(s) ignoré(s).", messages.WARNING)
        return attente

    @admin.action(description="Approuver les prestataires sélectionnés")
    def approuver(self, request, queryset):
        attente = list(self._en_attente(request, queryset))
        for p in attente:
            p.approuver(request.user)
        if attente:
            self.message_user(request, f"{len(attente)} prestataire(s) approuvé(s).", messages.SUCCESS)

    @admin.action(description="Refuser les prestataires sélectionnés (motif obligatoire)")
    def refuser(self, request, queryset):
        if "confirmer_refus" in request.POST:
            form = RefusPrestataireForm(request.POST)
            if form.is_valid():
                attente = list(self._en_attente(request, queryset))
                for p in attente:
                    p.refuser(request.user, form.cleaned_data["motif"])
                if attente:
                    self.message_user(request, f"{len(attente)} prestataire(s) refusé(s).", messages.SUCCESS)
                return None
        else:
            form = RefusPrestataireForm()
        attente = queryset.filter(statut_validation=Prestataire.Validation.EN_ATTENTE)
        if not attente.exists():
            self.message_user(request, "Aucun prestataire « En attente » dans la sélection.", messages.WARNING)
            return None
        contexte = {**self.admin_site.each_context(request), "title": "Refuser des prestataires",
                    "opts": self.model._meta, "form": form, "prestataires": attente, "selection": queryset,
                    "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME}
        return TemplateResponse(request, "admin/prestataires/prestataire/refuser.html", contexte)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    """US 4.7 : supervision de toutes les réservations, filtre par statut."""
    list_display = ("evenement", "prestataire", "service", "montant", "statut", "date_demande")
    list_filter = ("statut", "service__type")
    search_fields = ("evenement__titre", "prestataire__nom")
    list_select_related = ("evenement", "prestataire", "service")
    date_hierarchy = "date_demande"

    def has_add_permission(self, request):
        """Supervision seulement : l'admin ne réserve pas (la réservation est faite par l'organisateur)."""
        return False
