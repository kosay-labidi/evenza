from django.contrib import admin

from .models import Seance


@admin.register(Seance)
class SeanceAdmin(admin.ModelAdmin):
    list_display = ("titre", "evenement", "description", "date")
    list_filter = ("evenement",)
