from django.urls import path

from . import views

app_name = "ressources"
urlpatterns = [
    path("", views.RessourceListView.as_view(), name="liste"),
    path("nouvelle/", views.RessourceCreateView.as_view(), name="creer"),
    path("evenement/<int:evenement_pk>/affecter/", views.AffectationCreateView.as_view(), name="affecter"),
    # ressource : détail, modification, suppression
    path("<int:pk>/", views.RessourceDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.RessourceUpdateView.as_view(), name="modifier"),
    path("<int:pk>/supprimer/", views.RessourceDeleteView.as_view(), name="supprimer"),
    # affectations : liste, modification, suppression
    path("affectations/", views.AffectationListView.as_view(), name="affectations"),
    path("affectation/<int:pk>/modifier/", views.AffectationUpdateView.as_view(), name="affectation_modifier"),
    path("affectation/<int:pk>/supprimer/", views.AffectationDeleteView.as_view(), name="affectation_supprimer"),
]
