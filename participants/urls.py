from django.urls import path

from . import views

app_name = "participants"
urlpatterns = [
    path("", views.ParticipantsAccueilView.as_view(), name="index"),          # page d'entrée du module
    path("mes-inscriptions/", views.MesInscriptionsView.as_view(), name="mes_inscriptions"),
    path("evenement/<int:evenement_pk>/inscrire/", views.InscrireView.as_view(), name="inscrire"),
    path("evenement/<int:evenement_pk>/reserver/", views.ReservationView.as_view(), name="reserver"),
    path("inscriptions/", views.InscriptionListView.as_view(), name="inscription_liste"),
    path("inscription/<int:pk>/", views.InscriptionDetailView.as_view(), name="inscription_detail"),
    path("inscription/<int:pk>/annuler-organisateur/", views.InscriptionAnnulerGestionView.as_view(), name="inscription_annuler"),
    path("inscription/<int:pk>/annuler-checkin/", views.InscriptionCheckinAnnulerView.as_view(), name="inscription_checkin_annuler"),
    path("billets/", views.TypeBilletListView.as_view(), name="typebillet_liste"),
    path("billets/<int:pk>/", views.TypeBilletDetailView.as_view(), name="typebillet_detail"),
    path("billets/<int:pk>/modifier/", views.TypeBilletUpdateView.as_view(), name="typebillet_modifier"),
    path("billets/<int:pk>/supprimer/", views.TypeBilletDeleteView.as_view(), name="typebillet_supprimer"),
    path("evenement/<int:evenement_pk>/billets/nouveau/", views.TypeBilletCreateView.as_view(), name="type_creer"),
    path("evenement/<int:evenement_pk>/liste/", views.ParticipantsEvenementView.as_view(), name="liste"),
    path("evenement/<int:evenement_pk>/checkin/", views.CheckinView.as_view(), name="checkin"),
    path("inscription/<int:pk>/modifier/", views.ModifierInscriptionView.as_view(), name="inscription_modifier"),
    path("inscription/<int:pk>/annuler/", views.AnnulerInscriptionView.as_view(), name="annuler"),
    path("inscription/<int:pk>/avis/", views.AvisCreateView.as_view(), name="avis"),
    path("avis/", views.AvisListView.as_view(), name="avis_liste"),
    path("avis/<int:pk>/", views.AvisDetailView.as_view(), name="avis_detail"),
    path("avis/<int:pk>/modifier/", views.AvisUpdateView.as_view(), name="avis_modifier"),
    path("avis/<int:pk>/supprimer/", views.AvisDeleteView.as_view(), name="avis_supprimer"),
    path("billet/<uuid:code_billet>/", views.BilletView.as_view(), name="billet"),
]
