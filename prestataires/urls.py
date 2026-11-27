from django.urls import path

from . import views

app_name = "prestataires"
urlpatterns = [
    path("", views.PrestataireListView.as_view(), name="liste"),
    path("nouveau/", views.PrestataireCreateView.as_view(), name="creer"),
    path("a-valider/", views.PrestatairesAValiderView.as_view(), name="a_valider"),
    path("<int:pk>/approuver/", views.PrestataireValidationView.as_view(decision="approuver"), name="approuver"),
    path("<int:pk>/refuser/", views.PrestataireValidationView.as_view(decision="refuser"), name="refuser"),
    path("<int:pk>/", views.PrestataireDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.PrestataireUpdateView.as_view(), name="modifier"),
    path("<int:pk>/supprimer/", views.PrestataireDeleteView.as_view(), name="supprimer"),
    path("<int:pk>/reserver/", views.PrestataireReserverView.as_view(), name="reserver_prestataire"),
    path("evenement/<int:evenement_pk>/reserver/", views.ReservationCreateView.as_view(), name="reserver"),
    path("evenement/<int:evenement_pk>/reservations/", views.ReservationsEvenementView.as_view(),
         name="reservations_evenement"),
    path("reservation/<int:pk>/<str:statut>/", views.ReservationStatutView.as_view(), name="reservation_statut"),
]
