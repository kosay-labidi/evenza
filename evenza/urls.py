"""URL globales : chaque gestion a son propre fichier urls.py."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("comptes/", include("utilisateurs.urls")),
    path("evenements/", include("evenements.urls")),
    path("programmes/", include("programmes.urls")),
    path("prestataires/", include("prestataires.urls")),
    path("participants/", include("participants.urls")),
    path("ressources/", include("ressources.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "core.views.erreur_403"
handler404 = "core.views.erreur_404"
