from django.urls import path

from . import views

app_name = "programmes"
urlpatterns = [
    path("evenement/<int:evenement_pk>/seance/nouvelle/", views.SeanceCreateView.as_view(), name="seance_creer"),
    path("evenement/<int:evenement_pk>/seances/api/", views.SeanceCreateApiView.as_view(), name="seances_api_creer"),
    path("evenement/<int:evenement_pk>/programme.pdf", views.ProgrammePdfView.as_view(), name="programme_pdf"),
    path("seance/<int:pk>/api/", views.SeanceUpdateApiView.as_view(), name="seance_api_modifier"),
    path("seance/<int:pk>/api/supprimer/", views.SeanceDeleteApiView.as_view(), name="seance_api_supprimer"),
    path("seance/<int:pk>/modifier/", views.SeanceUpdateView.as_view(), name="seance_modifier"),
    path("seance/<int:pk>/supprimer/", views.SeanceDeleteView.as_view(), name="seance_supprimer"),
]
