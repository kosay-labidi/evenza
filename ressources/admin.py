from django.contrib import admin

from .models import Affectation, Ressource


@admin.register(Ressource)
class RessourceAdmin(admin.ModelAdmin):
    list_display = ("nom", "type", "quantite")
    list_filter = ("type",)


@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display = ("ressource", "evenement", "quantite", "debut", "fin")
