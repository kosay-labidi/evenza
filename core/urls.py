from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("tableau-de-bord/", views.DashboardView.as_view(), name="dashboard"),
    path("a-propos/", views.AProposView.as_view(), name="a_propos"),
    path("contact/", views.ContactView.as_view(), name="contact"),
    path("faq/", views.FaqView.as_view(), name="faq"),
    path("apercu/", views.ApercuView.as_view(), name="apercu"),   # APERÇU TEMPORAIRE (à retirer à l'étape 2)
]
