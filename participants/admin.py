from django.contrib import admin

from .models import Avis, Inscription, TypeBillet


@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ("participant", "evenement", "type_billet", "quantite", "montant", "statut", "present")
    list_filter = ("statut", "present", "evenement")
    readonly_fields = ("code_billet",)


admin.site.register(Avis)


@admin.register(TypeBillet)
class TypeBilletAdmin(admin.ModelAdmin):
    list_display = ("nom", "evenement", "prix", "quota")
    list_filter = ("evenement",)
