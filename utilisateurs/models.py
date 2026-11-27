import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models.functions import Lower
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .validateurs import valider_photo


def chemin_photo(instance, nom_fichier):
    """media/utilisateurs/<uuid>.<ext> : nom imprévisible, sans le nom d'origine du fichier."""
    extension = nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else "jpg"
    return f"utilisateurs/{uuid.uuid4().hex}.{extension}"


class Utilisateur(AbstractUser):
    """Acteur du système. Le rôle remplace la généralisation du diagramme de classes."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        ORGANISATEUR = "ORGANISATEUR", "Organisateur"
        PARTICIPANT = "PARTICIPANT", "Participant"
        PRESTATAIRE = "PRESTATAIRE", "Prestataire"
        CLIENT = "CLIENT", "Client"

    role = models.CharField(max_length=15, choices=Role.choices, default=Role.PARTICIPANT)
    telephone = models.CharField("téléphone", max_length=20, blank=True)
    photo = models.ImageField("photo de profil", upload_to=chemin_photo, blank=True, validators=[valider_photo])

    class Meta:
        verbose_name = "utilisateur"
        ordering = ["username"]
        constraints = [
            # Unicité de l'e-mail SANS tenir compte de la casse, garantie par la base (y compris entre deux
            # requêtes simultanées). Les e-mails vides restent permis (anciens comptes sans adresse).
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="utilisateur_email_unique_insensible_casse",
                violation_error_message="Un compte utilise déjà cette adresse e-mail.",
            ),
        ]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def initiales(self):
        """Affichées à la place de la photo quand il n'y en a pas."""
        if self.first_name:
            return (self.first_name[:1] + self.last_name[:1]).upper()
        return self.username[:1].upper()

    # ---- Rôles : source unique de vérité (réutilisée par core.permissions, les mixins et les templates) ----
    # Hiérarchie : Administrateur ⊇ Organisateur. Les trois autres rôles sont distincts et non cumulables.
    @property
    def est_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def est_organisateur(self):
        return self.est_admin or self.role == self.Role.ORGANISATEUR

    @property
    def est_client(self):
        return self.role == self.Role.CLIENT

    @property
    def est_participant(self):
        return self.role == self.Role.PARTICIPANT

    @property
    def est_prestataire(self):
        return self.role == self.Role.PRESTATAIRE


# ---- Fichiers de photo : on supprime l'ancien fichier quand la photo est remplacée, retirée ou le compte supprimé.
def _supprimer_fichier_apres_commit(fichier):
    if fichier and fichier.name:
        stockage, nom = fichier.storage, fichier.name
        transaction.on_commit(lambda: stockage.delete(nom))


@receiver(pre_save, sender=Utilisateur)
def photo_remplacee(sender, instance, **kwargs):
    if not instance.pk:
        return
    ancienne = sender.objects.filter(pk=instance.pk).values_list("photo", flat=True).first()
    if ancienne and ancienne != instance.photo.name:
        _supprimer_fichier_apres_commit(sender._meta.get_field("photo").attr_class(instance, sender._meta.get_field("photo"), ancienne))


@receiver(post_delete, sender=Utilisateur)
def photo_compte_supprime(sender, instance, **kwargs):
    _supprimer_fichier_apres_commit(instance.photo)
