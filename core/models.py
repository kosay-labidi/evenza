from django.db import models


class MessageContact(models.Model):
    """Message envoyé depuis la page Contact (lu dans l'administration)."""

    class Sujet(models.TextChoices):
        ORGANISER = "ORGANISER", "Organiser un événement"
        BILLET = "BILLET", "Question sur un billet"
        PRESTATAIRE = "PRESTATAIRE", "Devenir prestataire"
        AUTRE = "AUTRE", "Autre"

    nom = models.CharField(max_length=120)
    email = models.EmailField()
    sujet = models.CharField(max_length=12, choices=Sujet.choices, default=Sujet.ORGANISER)
    message = models.TextField()
    date = models.DateTimeField(auto_now_add=True)
    traite = models.BooleanField("traité", default=False)

    class Meta:
        verbose_name = "message de contact"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.nom} – {self.get_sujet_display()}"
