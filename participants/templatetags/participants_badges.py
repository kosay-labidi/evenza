"""Balises de gabarit de la gestion des participants.

Usage : {% load participants_badges %} puis {% badge_places t.restants %} ou {% badge_places evenement.places_restantes %}.
"""
from django import template
from django.utils.html import format_html

register = template.Library()

SEUIL_PLACES = 5        # en dessous (ou égal), on affiche « Plus que X places »


@register.simple_tag
def badge_places(restants):
    """« Complet » à 0, « Plus que X place(s) » si 1 ≤ X ≤ SEUIL_PLACES, rien sinon (None = sans limite)."""
    if restants is None:
        return ""
    restants = int(restants)
    if restants <= 0:
        return format_html('<span class="badge annulee badge-places">Complet</span>')
    if restants <= SEUIL_PLACES:
        return format_html('<span class="badge attente badge-places">Plus que {} place{}</span>',
                           restants, "s" if restants > 1 else "")
    return ""
