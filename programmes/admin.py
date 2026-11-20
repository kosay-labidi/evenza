from django.contrib import admin

from .models import Intervenant, Seance

admin.site.register(Intervenant)


@admin.register(Seance)
class SeanceAdmin(admin.ModelAdmin):
    list_display = ("titre", "evenement", "debut", "fin", "salle")
    list_filter = ("evenement",)
