from django.contrib import admin

from .forms import PrestataireAdminForm
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
    """US 4.6 : liste, filtre par service, sélection des services ; e-mail unique (formulaire)."""
    form = PrestataireAdminForm
    list_display = ("nom", "telephone", "email")
    list_filter = ("services__type", "services")
    search_fields = ("nom", "email", "telephone")
    filter_horizontal = ("services",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    """US 4.7 : supervision de toutes les réservations, filtre par statut."""
    list_display = ("evenement", "prestataire", "service", "montant", "statut", "date_demande")
    list_filter = ("statut", "service__type")
    search_fields = ("evenement__titre", "prestataire__nom")
    list_select_related = ("evenement", "prestataire", "service")
    date_hierarchy = "date_demande"
