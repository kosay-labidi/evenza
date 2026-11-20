from django.contrib import admin

from .models import MessageContact


@admin.register(MessageContact)
class MessageContactAdmin(admin.ModelAdmin):
    list_display = ("nom", "email", "sujet", "date", "traite")
    list_filter = ("sujet", "traite")
    list_editable = ("traite",)
