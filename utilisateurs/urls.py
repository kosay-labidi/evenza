from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "utilisateurs"
urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("inscription/", views.InscriptionCompteView.as_view(), name="register"),
    path("profil/", views.ProfilView.as_view(), name="profil"),
    # mot de passe oublié
    path("mot-de-passe/oublie/", views.MotDePasseOublieView.as_view(), name="password_reset"),
    path("mot-de-passe/envoye/", views.MotDePasseEnvoyeView.as_view(), name="password_reset_done"),
    path("mot-de-passe/<uidb64>/<token>/", views.NouveauMotDePasseView.as_view(), name="password_reset_confirm"),
    path("mot-de-passe/modifie/", views.MotDePasseModifieView.as_view(), name="password_reset_complete"),
    # gestion des utilisateurs (administrateur)
    path("utilisateurs/", views.UtilisateurListView.as_view(), name="utilisateur_liste"),
    path("utilisateurs/nouveau/", views.UtilisateurCreateView.as_view(), name="utilisateur_creer"),
    path("utilisateurs/<int:pk>/", views.UtilisateurDetailView.as_view(), name="utilisateur_detail"),
    path("utilisateurs/<int:pk>/modifier/", views.UtilisateurUpdateView.as_view(), name="utilisateur_modifier"),
    path("utilisateurs/<int:pk>/supprimer/", views.UtilisateurDeleteView.as_view(), name="utilisateur_supprimer"),
]
