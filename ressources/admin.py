from django.contrib import admin

from .models import Affectation, Ressource


@admin.register(Ressource)
class RessourceAdmin(admin.ModelAdmin):
    list_display = ("nom", "type", "quantite", "etat")
    list_filter = ("type", "etat")
    search_fields = ("nom",)


@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display = ("ressource", "evenement", "quantite", "debut", "fin")
