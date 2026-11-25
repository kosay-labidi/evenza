from django.urls import path

from . import views

app_name = "programmes"
urlpatterns = [
    path("", views.ProgrammesAccueilView.as_view(), name="index"),            # page d'entrée du module
    path("evenement/<int:evenement_pk>/seance/nouvelle/", views.SeanceCreateView.as_view(), name="seance_creer"),
    path("seance/<int:pk>/modifier/", views.SeanceUpdateView.as_view(), name="seance_modifier"),
    path("seance/<int:pk>/supprimer/", views.SeanceDeleteView.as_view(), name="seance_supprimer"),
    path("intervenants/", views.IntervenantListView.as_view(), name="intervenants"),
    path("intervenants/nouveau/", views.IntervenantCreateView.as_view(), name="intervenant_creer"),
]
