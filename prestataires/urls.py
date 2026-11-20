from django.urls import path

from . import views

app_name = "prestataires"
urlpatterns = [
    path("", views.PrestataireListView.as_view(), name="liste"),
    path("nouveau/", views.PrestataireCreateView.as_view(), name="creer"),
    path("evenement/<int:evenement_pk>/reserver/", views.ReservationCreateView.as_view(), name="reserver"),
    path("reservation/<int:pk>/<str:statut>/", views.ReservationStatutView.as_view(), name="reservation_statut"),
]
