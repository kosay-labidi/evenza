from django.contrib import admin

from .models import Prestataire, Reservation, Service

admin.site.register(Service)


@admin.register(Prestataire)
class PrestataireAdmin(admin.ModelAdmin):
    list_display = ("nom", "telephone", "email")
    filter_horizontal = ("services",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("evenement", "prestataire", "service", "montant", "statut")
    list_filter = ("statut",)
