from django.urls import path

from . import views

app_name = "participants"
urlpatterns = [
    path("", views.ParticipantsAccueilView.as_view(), name="index"),          # page d'entrée du module
    path("mes-inscriptions/", views.MesInscriptionsView.as_view(), name="mes_inscriptions"),
    path("evenement/<int:evenement_pk>/inscrire/", views.InscrireView.as_view(), name="inscrire"),
    path("evenement/<int:evenement_pk>/reserver/", views.ReservationView.as_view(), name="reserver"),
    path("evenement/<int:evenement_pk>/billets/nouveau/", views.TypeBilletCreateView.as_view(), name="type_creer"),
    path("evenement/<int:evenement_pk>/liste/", views.ParticipantsEvenementView.as_view(), name="liste"),
    path("evenement/<int:evenement_pk>/checkin/", views.CheckinView.as_view(), name="checkin"),
    path("inscription/<int:pk>/annuler/", views.AnnulerInscriptionView.as_view(), name="annuler"),
    path("inscription/<int:pk>/avis/", views.AvisCreateView.as_view(), name="avis"),
    path("billet/<uuid:code_billet>/", views.BilletView.as_view(), name="billet"),
]
