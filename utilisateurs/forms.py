from django import forms
from django.contrib.auth import forms as auth_forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError

from .models import Utilisateur
from .securite import motif_refus_changement
from .validateurs import valider_identifiant, valider_mdp_infos_personnelles, valider_nom, valider_telephone

MSG_EMAIL_PRIS = "Un compte utilise déjà cette adresse e-mail."
MSG_EMAIL_OBLIGATOIRE = "L'adresse e-mail est obligatoire."
MSG_EMAIL_INVALIDE = "Saisissez une adresse e-mail valide, ex. vous@exemple.tn."
MSG_CGU = "Vous devez accepter les conditions d'utilisation pour créer un compte."


def email_deja_utilise(email, sauf_pk=None):
    """Vrai si un autre compte utilise cette adresse (comparaison insensible à la casse)."""
    return Utilisateur.objects.filter(email__iexact=email).exclude(pk=sauf_pk).exists()


# ======================================================================= briques communes
class CoordonneesMixin:
    """Prénom, nom, e-mail et téléphone : mêmes validations dans tous les formulaires de comptes."""
    noms_obligatoires = False
    email_obligatoire = True

    def preparer_coordonnees(self):
        for champ, libelle in (("first_name", "Prénom"), ("last_name", "Nom")):
            if champ in self.fields:
                f = self.fields[champ]
                f.label, f.required = libelle, self.noms_obligatoires
                f.error_messages["required"] = f"Le {libelle.lower()} est obligatoire."
        if "telephone" in self.fields:
            self.fields["telephone"].label = "Téléphone"
            self.fields["telephone"].help_text = ""
        if "email" in self.fields:
            f = self.fields["email"]
            f.required = self.email_obligatoire
            f.error_messages.update({"required": MSG_EMAIL_OBLIGATOIRE, "invalid": MSG_EMAIL_INVALIDE})
        autocompletion = {"first_name": "given-name", "last_name": "family-name", "email": "email",
                          "telephone": "tel", "username": "username"}
        for champ, valeur in autocompletion.items():
            if champ in self.fields:
                self.fields[champ].widget.attrs.setdefault("autocomplete", valeur)

    def clean_first_name(self):
        return valider_nom(self.cleaned_data.get("first_name", ""), "Le prénom")

    def clean_last_name(self):
        return valider_nom(self.cleaned_data.get("last_name", ""), "Le nom")

    def clean_telephone(self):
        return valider_telephone(self.cleaned_data.get("telephone", ""))

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if email and email_deja_utilise(email, sauf_pk=self.instance.pk):   # garder sa propre adresse reste permis
            raise ValidationError(MSG_EMAIL_PRIS)
        return email

    def _post_clean(self):
        """La contrainte d'unicité en base (Lower(email)) est aussi vérifiée par Django à la validation ;
        portant sur une expression, son erreur arrive en « non-champ ». On la rattache au champ e-mail."""
        super()._post_clean()
        generales = self._errors.get(NON_FIELD_ERRORS) if self._errors else None
        if not generales or "email" not in self.fields or MSG_EMAIL_PRIS not in generales:
            return
        restantes = [e for e in generales.as_data() if MSG_EMAIL_PRIS not in e.messages]
        if restantes:
            self._errors[NON_FIELD_ERRORS] = self.error_class(restantes, error_class="nonfield")
        else:
            del self._errors[NON_FIELD_ERRORS]
        if "email" not in self._errors:
            self.add_error("email", MSG_EMAIL_PRIS)


class IdentifiantMixin:
    """« @ » interdit dans un NOUVEL identifiant. Un identifiant existant inchangé est conservé tel quel
    (aucun renommage automatique ; la connexion de ces comptes reste assurée par le backend)."""

    def clean_username(self):
        parent = getattr(super(), "clean_username", None)
        username = parent() if parent else self.cleaned_data["username"]
        if not self.instance.pk or "username" in self.changed_data:
            valider_identifiant(username)
        return username


class MotDePasseCreationMixin:
    """Création de compte : règles Django de settings.py, PUIS « ne contient pas vos informations »."""

    def _post_clean(self):
        super()._post_clean()
        mdp = self.cleaned_data.get("password1")
        if not mdp or self.cleaned_data.get("set_usable_password") is False:
            return
        if not (self.has_error("password1") or self.has_error("password2")):
            try:
                valider_mdp_infos_personnelles(mdp, self.instance)
            except ValidationError as e:
                self.add_error("password2", e)


class MotDePasseNouveauMixin:
    """Changement / réinitialisation (champs new_password1 et new_password2 de Django)."""
    champ_mdp, champ_confirmation = "new_password1", "new_password2"

    def clean(self):
        cleaned = super().clean()
        mdp = cleaned.get(self.champ_mdp)
        if mdp and not self.has_error(self.champ_confirmation):
            try:
                valider_mdp_infos_personnelles(mdp, self.user)
            except ValidationError as e:
                self.add_error(self.champ_confirmation, e)
        return cleaned


# ======================================================================= inscription publique
# Évenza est une agence événementielle, pas une place de marché : l'inscription publique ne crée
# que des comptes Participant ou Client. Les comptes Organisateur, Prestataire et Administrateur
# sont créés par un administrateur (UtilisateurCreationAdminForm, réservé à AdminRequiredMixin).
ROLES_INSCRIPTION_PUBLIQUE = (Utilisateur.Role.PARTICIPANT, Utilisateur.Role.CLIENT)
MSG_ROLE_RESERVE = ("Ce rôle n'est pas disponible à l'inscription. Les comptes organisateur, prestataire "
                    "et administrateur sont créés par l'agence Évenza.")


class InscriptionCompteForm(CoordonneesMixin, IdentifiantMixin, MotDePasseCreationMixin, auth_forms.UserCreationForm):
    """Création de compte publique : uniquement Participant ou Client (contrôlé côté serveur)."""
    noms_obligatoires = True
    role = forms.ChoiceField(choices=[(r.value, r.label) for r in ROLES_INSCRIPTION_PUBLIQUE],
                             error_messages={"invalid_choice": MSG_ROLE_RESERVE})
    # Acceptation vérifiée côté serveur. Le texte des conditions n'est pas fourni par ce module :
    # une page dédiée reste à créer (voir le rapport).
    cgu = forms.BooleanField(required=True, label="J'accepte les conditions d'utilisation d'Évenza",
                             error_messages={"required": MSG_CGU})

    class Meta(auth_forms.UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "telephone", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparer_coordonnees()
        ph = {"username": "ex. sara.benali", "email": "vous@exemple.tn", "telephone": "ex. 22 123 456",
              "first_name": "Sara", "last_name": "Ben Ali"}
        for k, v in ph.items():
            self.fields[k].widget.attrs["placeholder"] = v
        for k in ("first_name", "last_name", "username", "email", "password1", "password2", "cgu"):
            self.fields[k].widget.attrs["required"] = True
        for k in ("password1", "password2"):
            self.fields[k].widget.attrs["autocomplete"] = "new-password"


# ======================================================================= profil
class ProfilForm(CoordonneesMixin, forms.ModelForm):
    """« Mon profil » : uniquement les coordonnées (ni rôle, ni identifiant, ni privilèges)."""
    noms_obligatoires = True

    class Meta:
        model = Utilisateur
        fields = ("first_name", "last_name", "email", "telephone")
        labels = {"first_name": "Prénom", "last_name": "Nom", "email": "Adresse e-mail"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparer_coordonnees()
        self.fields["email"].label = "Adresse e-mail"


class ChangementMotDePasseForm(MotDePasseNouveauMixin, auth_forms.PasswordChangeForm):
    """Ancien mot de passe + nouveau + confirmation (validateurs Django + informations personnelles)."""


class NouveauMotDePasseForm(MotDePasseNouveauMixin, auth_forms.SetPasswordForm):
    """Réinitialisation par lien e-mail."""


# ======================================================================= gestion par l'administrateur
class UtilisateurCreationAdminForm(CoordonneesMixin, IdentifiantMixin, MotDePasseCreationMixin,
                                   auth_forms.UserCreationForm):
    """Ajout d'un compte par l'admin : tous les rôles, e-mail obligatoire (réinitialisation possible).
    Le rôle ADMIN reste un rôle MÉTIER : il n'accorde ni is_staff ni is_superuser."""

    class Meta(auth_forms.UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "telephone", "role", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparer_coordonnees()
        self.fields["is_active"].label = "Compte actif"


class UtilisateurAdminForm(CoordonneesMixin, IdentifiantMixin, forms.ModelForm):
    """Modification d'un compte par l'admin (le mot de passe se change via « Mot de passe oublié »).

    Le statut actif / désactivé n'est pas modifiable ici : il passe par les actions dédiées
    « Désactiver » / « Réactiver » (page de confirmation + garde-fous), que ce formulaire ne doit pas contourner.
    """

    class Meta:
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "telephone", "role")
        labels = {"first_name": "Prénom", "last_name": "Nom"}

    def __init__(self, *args, acteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acteur = acteur
        # un ancien compte sans e-mail peut rester ainsi ; une adresse existante ne peut pas être effacée
        self.email_obligatoire = bool(self.instance.email)
        self.preparer_coordonnees()

    def clean_role(self):
        role = self.cleaned_data["role"]
        motif = motif_refus_changement(self.acteur, self.instance, role=role)   # instance : valeurs d'avant
        if motif:
            raise ValidationError(motif)
        return role
