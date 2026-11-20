from django.urls import path

from . import views

app_name = "evenements"
urlpatterns = [
    path("", views.EvenementListView.as_view(), name="liste"),
    path("mes-evenements/", views.MesEvenementsView.as_view(), name="mes_evenements"),
    path("nouveau/", views.EvenementCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.EvenementDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.EvenementUpdateView.as_view(), name="modifier"),
    path("<int:pk>/supprimer/", views.EvenementDeleteView.as_view(), name="supprimer"),
    path("<int:pk>/publier/", views.ChangerStatutView.as_view(action="publier"), name="publier"),
    path("<int:pk>/annuler/", views.ChangerStatutView.as_view(action="annuler"), name="annuler"),
    path("lieux/", views.LieuListView.as_view(), name="lieux"),
    path("lieux/nouveau/", views.LieuCreateView.as_view(), name="lieu_creer"),
]
