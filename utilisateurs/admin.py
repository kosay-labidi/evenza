"""Administration Django des comptes, alignée sur les règles de la gestion des utilisateurs.

Rôle MÉTIER (``role``) et privilèges TECHNIQUES (``is_staff``, ``is_superuser``) restent distincts :
rien n'est attribué automatiquement. Les garde-fous de l'application s'appliquent aussi ici :
hiérarchie des comptes (core.permissions.peut_gerer_compte), auto-désactivation ou auto-rétrogradation
interdites, dernier administrateur actif protégé, suppressions destructives refusées.
"""
from django.contrib import admin, messages
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import HttpResponseRedirect

from core.permissions import peut_gerer_compte

from .forms import CoordonneesMixin, IdentifiantMixin, MotDePasseCreationMixin, MotDePasseNouveauMixin
from .models import Utilisateur
from .securite import admins_actifs, est_admin_actif, motif_refus_changement, motif_refus_suppression

CHAMPS_PRIVILEGES = ("is_superuser", "is_staff", "groups", "user_permissions")


class ChangementCompteAdminForm(CoordonneesMixin, IdentifiantMixin, auth_forms.UserChangeForm):
    acteur = None   # renseigné par UtilisateurAdmin.get_form

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_obligatoire = bool(self.instance.email)
        self.preparer_coordonnees()

    def clean(self):
        cleaned = super().clean()
        motif = motif_refus_changement(            # instance : valeurs d'avant (construct_instance vient après)
            self.acteur, self.instance,
            is_active=cleaned.get("is_active", self.instance.is_active),
            role=cleaned.get("role", self.instance.role),
            is_superuser=cleaned.get("is_superuser", self.instance.is_superuser))
        if motif:
            raise ValidationError(motif)
        return cleaned


class CreationCompteAdminForm(CoordonneesMixin, IdentifiantMixin, MotDePasseCreationMixin,
                              auth_forms.AdminUserCreationForm):
    acteur = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparer_coordonnees()


class MotDePasseAdminForm(MotDePasseNouveauMixin, auth_forms.AdminPasswordChangeForm):
    champ_mdp, champ_confirmation = "password1", "password2"


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    form = ChangementCompteAdminForm
    add_form = CreationCompteAdminForm
    change_password_form = MotDePasseAdminForm
    list_display = ("username", "email", "role", "is_active", "is_staff", "is_superuser")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    fieldsets = UserAdmin.fieldsets + (("Évenza", {"fields": ("role", "telephone")}),)
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "email", "usable_password", "password1", "password2")}),
        ("Évenza", {"fields": ("first_name", "last_name", "role", "telephone")}),
    )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """Ajout / modification : une IntegrityError (e-mail pris au même instant par une autre requête)
        annule la transaction de l'admin et donne un message clair au lieu d'une erreur 500."""
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError:
            self.message_user(request, "Enregistrement annulé : cette adresse e-mail ou cet identifiant vient "
                                       "d'être utilisé par un autre compte. Vérifiez et réessayez.", messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)
        return type(Form.__name__, (Form,), {"acteur": request.user})

    def get_readonly_fields(self, request, obj=None):
        champs = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:   # seul un superutilisateur accorde ou retire des privilèges techniques
            champs = (*champs, *CHAMPS_PRIVILEGES)
        return champs

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or peut_gerer_compte(request.user, obj))

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        return obj is None or (peut_gerer_compte(request.user, obj) and motif_refus_suppression(obj, request.user) is None)

    def delete_model(self, request, obj):
        self._verifier_suppression(request, [obj])
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """Action groupée « Supprimer » : tout ou rien (aucune suppression partielle silencieuse)."""
        self._verifier_suppression(request, list(queryset))
        super().delete_queryset(request, queryset)

    def _verifier_suppression(self, request, comptes):
        for compte in comptes:
            motif = (None if peut_gerer_compte(request.user, compte) else "Compte protégé.") or \
                motif_refus_suppression(compte, request.user)
            if motif:
                raise PermissionDenied(f"« {compte.username} » : {motif}")
        # contrôle d'ensemble : chaque compte pris seul peut sembler supprimable alors que la sélection
        # contient TOUS les administrateurs actifs restants
        ids = [c.pk for c in comptes]
        if any(est_admin_actif(c) for c in comptes) and not admins_actifs().exclude(pk__in=ids).exists():
            raise PermissionDenied("Cette sélection supprimerait le dernier administrateur actif de la plateforme.")
