from django.contrib.auth.models import AbstractUser
from django.db import models


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

    class Meta:
        verbose_name = "utilisateur"
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def est_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def est_organisateur(self):
        return self.est_admin or self.role == self.Role.ORGANISATEUR
