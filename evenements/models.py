from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify

IMAGES_CATEGORIES = {"concert", "mariage", "conference", "gala", "festival"}


class Categorie(models.Model):
    nom = models.CharField(max_length=60, unique=True)

    class Meta:
        verbose_name = "catégorie"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    @property
    def image_url(self):
        """Photo par défaut de la catégorie (static/img/categories/<slug>.jpg)."""
        slug = slugify(self.nom)
        return static(f"img/categories/{slug if slug in IMAGES_CATEGORIES else 'gala'}.jpg")


class Lieu(models.Model):
    nom = models.CharField(max_length=120)
    adresse = models.CharField(max_length=200)
    ville = models.CharField(max_length=80)
    capacite = models.PositiveIntegerField("capacité")

    class Meta:
        verbose_name_plural = "lieux"
        ordering = ["ville", "nom"]

    def __str__(self):
        return f"{self.nom} ({self.ville})"


class EvenementQuerySet(models.QuerySet):
    def publies(self):
        return self.filter(statut=Evenement.Statut.PUBLIE)


class Evenement(models.Model):
    """Classe centrale du diagramme de classes."""

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        PUBLIE = "PUBLIE", "Publié"
        ANNULE = "ANNULE", "Annulé"
        TERMINE = "TERMINE", "Terminé"

    titre = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="evenements", verbose_name="catégorie")
    lieu = models.ForeignKey(Lieu, on_delete=models.PROTECT, related_name="evenements")
    organisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="evenements_organises")
    date_debut = models.DateTimeField("date de début")
    date_fin = models.DateTimeField("date de fin")
    capacite = models.PositiveIntegerField("capacité")
    prix = models.DecimalField(max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    affiche = models.ImageField(upload_to="evenements/", blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    objects = EvenementQuerySet.as_manager()

    class Meta:
        verbose_name = "événement"
        ordering = ["date_debut"]

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse("evenements:detail", args=[self.pk])

    @property
    def image_url(self):
        """Affiche de l'événement si elle existe, sinon la photo de sa catégorie."""
        return self.affiche.url if self.affiche else self.categorie.image_url

    @property
    def prix_min(self):
        """Prix le plus bas parmi les types de billets (ou le prix de base)."""
        prix = [t.prix for t in self.types_billet.all()]
        return min(prix) if prix else self.prix

    @property
    def taux_remplissage(self):
        return round(self.nb_inscrits * 100 / self.capacite) if self.capacite else 0

    # ---- règles de gestion ----
    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            raise ValidationError({"date_fin": "La date de fin doit être après la date de début."})
        if self.lieu_id and self.capacite and self.capacite > self.lieu.capacite:
            raise ValidationError({"capacite": f"Le lieu accepte au maximum {self.lieu.capacite} personnes."})
        if self.pk and self.capacite is not None and self.capacite < self.nb_inscrits:
            raise ValidationError({"capacite": f"{self.nb_inscrits} places sont déjà réservées : "
                                               f"la capacité ne peut pas être inférieure."})

    # ---- attributs dérivés (/ dans le diagramme UML) ----
    @property
    def nb_inscrits(self):
        """Nombre de places réservées et confirmées (une réservation peut compter plusieurs places)."""
        return self.inscriptions.filter(statut="CONFIRMEE").aggregate(n=models.Sum("quantite"))["n"] or 0

    @property
    def places_restantes(self):
        return max(0, self.capacite - self.nb_inscrits)

    @property
    def est_complet(self):
        return self.places_restantes == 0

    # ---- opérations ----
    def publier(self):
        self.statut = self.Statut.PUBLIE
        self.save(update_fields=["statut"])

    def annuler(self):
        self.statut = self.Statut.ANNULE
        self.save(update_fields=["statut"])
