from django.urls import path

from . import views

app_name = "programmes"
urlpatterns = [
    path("", views.ProgrammesAccueilView.as_view(), name="index"),            # page d'entrée du module
    path("evenement/<int:evenement_pk>/seance/nouvelle/", views.SeanceCreateView.as_view(), name="seance_creer"),
    path("seance/<int:pk>/modifier/", views.SeanceUpdateView.as_view(), name="seance_modifier"),
    path("seance/<int:pk>/supprimer/", views.SeanceDeleteView.as_view(), name="seance_supprimer"),
    path("evenement/<int:evenement_pk>/programme.pdf", views.ProgrammesPdfView.as_view(), name="export_pdf"),
]
