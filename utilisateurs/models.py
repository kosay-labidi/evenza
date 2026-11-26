from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


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
