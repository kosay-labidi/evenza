from django.contrib import admin

from .models import Categorie, Evenement, Lieu

admin.site.register(Categorie)


@admin.register(Lieu)
class LieuAdmin(admin.ModelAdmin):
    list_display = ("nom", "ville", "capacite")
    search_fields = ("nom", "ville")


@admin.register(Evenement)
class EvenementAdmin(admin.ModelAdmin):
    list_display = ("titre", "categorie", "lieu", "date_debut", "statut", "organisateur")
    list_filter = ("statut", "categorie")
    search_fields = ("titre",)
    date_hierarchy = "date_debut"
