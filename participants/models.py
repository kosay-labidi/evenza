import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.urls import reverse

from evenements.models import Evenement


class TypeBillet(models.Model):
    """Catégorie de billet d'un événement (Standard, VIP, Étudiant…)."""
    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="types_billet")
    nom = models.CharField(max_length=60)
    description = models.CharField(max_length=160, blank=True)
    prix = models.DecimalField(max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    quota = models.PositiveIntegerField(null=True, blank=True, help_text="Nombre maximum de places de ce type (vide = sans limite)")

    class Meta:
        verbose_name = "type de billet"
        ordering = ["prix"]

    def __str__(self):
        return f"{self.nom} – {self.prix} DT"

    @property
    def vendus(self):
        return self.inscriptions.filter(statut="CONFIRMEE").aggregate(n=models.Sum("quantite"))["n"] or 0

    @property
    def restants(self):
        return None if self.quota is None else max(0, self.quota - self.vendus)


class Inscription(models.Model):
    """Classe d'association Participant–Événement. Le code sert de billet (QR)."""

    class Statut(models.TextChoices):
        CONFIRMEE = "CONFIRMEE", "Confirmée"
        ATTENTE = "ATTENTE", "Liste d'attente"
        ANNULEE = "ANNULEE", "Annulée"

    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="inscriptions")
    participant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inscriptions")
    date_inscription = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.CONFIRMEE)
    type_billet = models.ForeignKey(TypeBillet, on_delete=models.PROTECT, null=True, blank=True, related_name="inscriptions")
    quantite = models.PositiveSmallIntegerField("nombre de places", default=1,
                                                validators=[MinValueValidator(1), MaxValueValidator(10)])
    montant = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    code_billet = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    present = models.BooleanField(default=False)

    class Meta:
        ordering = ["date_inscription"]
        constraints = [models.UniqueConstraint(fields=["evenement", "participant"], name="une_inscription_par_evenement")]

    def __str__(self):
        return f"{self.participant} – {self.evenement}"

    def get_absolute_url(self):
        return reverse("participants:billet", args=[self.code_billet])

    @property
    def code_court(self):
        return str(self.code_billet).split("-")[0].upper()

    @classmethod
    def inscrire(cls, evenement, participant, type_billet=None, quantite=1):
        """Règle métier : s'il n'y a plus assez de places, la réservation passe en liste d'attente.

        Tout se fait dans une transaction, avec un verrou sur la ligne de l'événement :
        deux réservations simultanées ne peuvent pas dépasser la capacité ni le quota d'un type de billet.
        Lève ValidationError si le participant a déjà une réservation active ou si le quota du type est épuisé.
        """
        with transaction.atomic():
            evenement = Evenement.objects.select_for_update().get(pk=evenement.pk)
            existantes = cls.objects.filter(evenement=evenement, participant=participant)
            if existantes.exclude(statut=cls.Statut.ANNULEE).exists():
                raise ValidationError("Vous avez déjà une réservation pour cet événement.")
            existantes.filter(statut=cls.Statut.ANNULEE).delete()   # une seule ligne par (événement, participant)
            if type_billet is not None:
                type_billet = TypeBillet.objects.get(pk=type_billet.pk, evenement=evenement)
                if type_billet.restants is not None and quantite > type_billet.restants:
                    raise ValidationError(f"Il ne reste que {type_billet.restants} billet(s) « {type_billet.nom} ».")
            prix = type_billet.prix if type_billet else evenement.prix
            statut = cls.Statut.ATTENTE if evenement.places_restantes < quantite else cls.Statut.CONFIRMEE
            return cls.objects.create(evenement=evenement, participant=participant, type_billet=type_billet,
                                      quantite=quantite, montant=prix * quantite, statut=statut)

    def annuler(self):
        """Libère les places et confirme, dans l'ordre d'inscription, les réservations en attente
        qui tiennent dans les places libérées (capacité de l'événement ET quota de leur type de billet)."""
        with transaction.atomic():
            evenement = Evenement.objects.select_for_update().get(pk=self.evenement_id)
            actuelle = type(self).objects.get(pk=self.pk)
            if actuelle.statut == self.Statut.ANNULEE:
                self.statut = actuelle.statut
                return
            etait_confirmee = actuelle.statut == self.Statut.CONFIRMEE
            self.statut = self.Statut.ANNULEE
            self.save(update_fields=["statut"])
            if not etait_confirmee:
                return
            for attente in (evenement.inscriptions.filter(statut=self.Statut.ATTENTE)
                            .select_related("type_billet").order_by("date_inscription", "pk")):
                if attente.quantite > evenement.places_restantes:
                    continue
                t = attente.type_billet
                if t is not None and t.restants is not None and attente.quantite > t.restants:
                    continue
                attente.statut = self.Statut.CONFIRMEE
                attente.save(update_fields=["statut"])


class Avis(models.Model):
    inscription = models.OneToOneField(Inscription, on_delete=models.CASCADE, related_name="avis")
    note = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.note}/5 – {self.inscription}"
