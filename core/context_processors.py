from django.conf import settings

from .navigation import navigation_pour


def evenza(request):
    """Variables disponibles dans tous les templates."""
    return {"NOM_APP": "Évenza", "CONTACT": getattr(settings, "EVENZA_CONTACT", {})}


def navigation(request):
    """Barre latérale de l'espace professionnel, filtrée selon les permissions de l'utilisateur."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {"nav_espace": navigation_pour(request)}
