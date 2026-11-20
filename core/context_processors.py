from django.conf import settings


def evenza(request):
    """Variables disponibles dans tous les templates."""
    return {"NOM_APP": "Évenza", "CONTACT": getattr(settings, "EVENZA_CONTACT", {})}
