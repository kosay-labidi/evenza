"""Recherche, filtres, tri et indicateurs de la liste des utilisateurs.

Tous les paramètres GET passent par ``FiltresForm`` (validation côté serveur) : une valeur invalide est
ignorée et signalée, jamais injectée dans la requête. Le tri n'accepte que les clés de ``TRIS``.
"""
from datetime import datetime, time, timedelta

from django import forms
from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Utilisateur

# clé GET -> (libellé, ordre). Les 5 premières clés existaient déjà : elles gardent leur sens.
TRIS = {
    "nom": ("Nom (A → Z)", ("last_name", "first_name", "username")),
    "identifiant": ("Identifiant (A → Z)", ("username",)),
    "recents": ("Inscription (plus récents)", ("-date_joined", "username")),
    "connexion": ("Dernière connexion (récente)", (F("last_login").desc(nulls_last=True), "username")),
    "role": ("Rôle (A → Z)", ("role", "username")),
    "-nom": ("Nom (Z → A)", ("-last_name", "-first_name", "-username")),
    "-identifiant": ("Identifiant (Z → A)", ("-username",)),
    "anciens": ("Inscription (plus anciens)", ("date_joined", "username")),
    "-connexion": ("Dernière connexion (ancienne)", (F("last_login").asc(nulls_first=True), "username")),
    "-role": ("Rôle (Z → A)", ("-role", "username")),
    "statut": ("Statut (actifs d'abord)", ("-is_active", "username")),
    "-statut": ("Statut (désactivés d'abord)", ("is_active", "username")),
}
TRI_DEFAUT = "identifiant"
# Colonnes triables du tableau : clé croissante, clé décroissante.
COLONNES_TRI = {"nom": ("nom", "-nom"), "role": ("role", "-role"), "statut": ("statut", "-statut"),
                "inscription": ("anciens", "recents"), "connexion": ("-connexion", "connexion")}
PAR_PAGE = (10, 20, 50)
PAR_PAGE_DEFAUT = 20
INACTIVITE = {"30": 30, "60": 60, "90": 90}
VUES = ("tableau", "cartes")


class FiltresForm(forms.Form):
    q = forms.CharField(required=False, max_length=100)
    role = forms.ChoiceField(required=False, choices=[("", "Tous les rôles"), *Utilisateur.Role.choices])
    statut = forms.ChoiceField(required=False, choices=[("", "Tous"), ("actif", "Actifs"), ("inactif", "Désactivés")])
    inscrit_du = forms.DateField(required=False)
    inscrit_au = forms.DateField(required=False)
    connecte_du = forms.DateField(required=False)
    connecte_au = forms.DateField(required=False)
    connexion = forms.ChoiceField(required=False, choices=[
        ("", "Toutes"), ("jamais", "Jamais connectés"), ("30", "Pas connectés depuis 30 jours"),
        ("60", "Pas connectés depuis 60 jours"), ("90", "Pas connectés depuis 90 jours")])
    tri = forms.ChoiceField(required=False, choices=[(k, v[0]) for k, v in TRIS.items()])
    par_page = forms.TypedChoiceField(required=False, coerce=int, empty_value=PAR_PAGE_DEFAUT,
                                      choices=[(n, n) for n in PAR_PAGE])

    LIBELLES = {"q": "Recherche", "role": "Rôle", "statut": "Statut", "inscrit_du": "Inscrit depuis le",
                "inscrit_au": "Inscrit jusqu'au", "connecte_du": "Connecté depuis le",
                "connecte_au": "Connecté jusqu'au", "connexion": "Connexion"}

    def __init__(self, data, *args, **kwargs):
        super().__init__(data, *args, **kwargs)
        for nom in ("inscrit_du", "inscrit_au", "connecte_du", "connecte_au"):
            self.fields[nom].widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
            self.fields[nom].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]

    def clean(self):
        data = super().clean()
        for debut, fin in (("inscrit_du", "inscrit_au"), ("connecte_du", "connecte_au")):
            if data.get(debut) and data.get(fin) and data[debut] > data[fin]:
                self.add_error(fin, "La date de fin est antérieure à la date de début.")
        return data

    def valeurs(self):
        """Filtres valides uniquement (un champ en erreur est ignoré, les autres s'appliquent)."""
        self.is_valid()
        return {k: v for k, v in self.cleaned_data.items() if k not in self.errors}


def _debut_jour(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def filtrer(qs, v):
    """Applique les filtres validés (sans tri). ``v`` vient de ``FiltresForm.valeurs()``."""
    q = (v.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                       | Q(email__icontains=q) | Q(telephone__icontains=q))
    if v.get("role"):
        qs = qs.filter(role=v["role"])
    if v.get("statut") in ("actif", "inactif"):
        qs = qs.filter(is_active=v["statut"] == "actif")
    if v.get("inscrit_du"):
        qs = qs.filter(date_joined__gte=_debut_jour(v["inscrit_du"]))
    if v.get("inscrit_au"):
        qs = qs.filter(date_joined__lt=_debut_jour(v["inscrit_au"] + timedelta(days=1)))
    if v.get("connecte_du"):
        qs = qs.filter(last_login__gte=_debut_jour(v["connecte_du"]))
    if v.get("connecte_au"):
        qs = qs.filter(last_login__lt=_debut_jour(v["connecte_au"] + timedelta(days=1)))
    connexion = v.get("connexion")
    if connexion == "jamais":
        qs = qs.filter(last_login__isnull=True)
    elif connexion in INACTIVITE:
        # Pas de connexion depuis N jours : dernière connexion plus ancienne, ou jamais connecté
        # alors que le compte existe depuis plus de N jours (un compte créé hier n'est pas « inactif »).
        seuil = timezone.now() - timedelta(days=INACTIVITE[connexion])
        qs = qs.filter(Q(last_login__lt=seuil) | Q(last_login__isnull=True, date_joined__lt=seuil))
    return qs


def debut_du_mois():
    return timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def indicateurs(qs):
    """Les 5 KPI en UNE requête d'agrégation."""
    return qs.aggregate(
        total=Count("pk"),
        actifs=Count("pk", filter=Q(is_active=True)),
        desactives=Count("pk", filter=Q(is_active=False)),
        nouveaux_mois=Count("pk", filter=Q(date_joined__gte=debut_du_mois())),
        jamais_connectes=Count("pk", filter=Q(last_login__isnull=True)),
    )
