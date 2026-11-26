import secrets

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "Administrateur", "Administrateur"
    ORGANIZER = "Organisateur", "Organisateur"
    CLIENT = "Client", "Client"
    PROVIDER = "Prestataire", "Prestataire"
    PARTICIPANT = "Participant", "Participant"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("Une adresse e-mail est requise.")
        user = self.model(email=email.strip().lower(), name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.update(role=Role.ADMIN, is_staff=True, is_superuser=True, is_active=True)
        return self.create_user(email, name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    name = models.CharField("nom complet", max_length=120)
    email = models.EmailField("adresse e-mail", max_length=190, unique=True)
    role = models.CharField("rôle", max_length=20, choices=Role, default=Role.PARTICIPANT)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    availability = models.CharField("disponibilités", max_length=255, blank=True)
    skills = models.CharField("compétences", max_length=255, blank=True)
    is_active = models.BooleanField("compte actif", default=True)
    is_staff = models.BooleanField("accès à l’administration Django", default=False)
    created_at = models.DateTimeField("date de création", auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "utilisateur"
        constraints = [models.UniqueConstraint(Lower("email"), name="evenza_unique_user_email")]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower()
        if self.pk:
            old = User.objects.filter(pk=self.pk).first()
            if old and old.email != self.email and self.registrations.exists():
                raise ValidationError({"email": "Cette adresse est liée à des inscriptions existantes."})
            if old and old.role != self.role:
                links = {
                    Role.ADMIN: self.validated_events,
                    Role.ORGANIZER: self.organized_events,
                    Role.CLIENT: self.client_events,
                    Role.PROVIDER: Provider.objects.filter(user=self),
                    Role.PARTICIPANT: self.registrations,
                }
                if links[old.role].exists():
                    raise ValidationError({"role": "Ce compte est déjà lié à des fiches dans ce rôle."})


class Period(models.Model):
    start_at = models.DateTimeField("début")
    end_at = models.DateTimeField("fin")

    class Meta:
        abstract = True
        constraints = [models.CheckConstraint(condition=Q(end_at__gt=F("start_at")),
                                               name="%(app_label)s_%(class)s_period")]

    def clean(self):
        super().clean()
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError({"end_at": "La fin doit être postérieure au début."})

    def check_event_period(self):
        if self.event_id and self.start_at and self.end_at:
            if self.start_at < self.event.start_at or self.end_at > self.event.end_at:
                raise ValidationError("Le créneau doit être compris dans les dates de l’événement.")


class Event(Period):
    class Status(models.TextChoices):
        DRAFT = "Brouillon", "Brouillon"
        PREPARATION = "En préparation", "En préparation"
        CONFIRMED = "Confirmé", "Confirmé"
        FINISHED = "Terminé", "Terminé"
        CANCELLED = "Annulé", "Annulé"

    class Type(models.TextChoices):
        WEDDING = "Mariage", "Mariage"
        BUSINESS = "Entreprise", "Entreprise"
        PRIVATE = "Privé", "Privé"
        CONFERENCE = "Conférence", "Conférence"
        OTHER = "Autre", "Autre"

    title = models.CharField("nom de l’événement", max_length=160)
    description = models.TextField("description", blank=True)
    location = models.CharField("lieu", max_length=255)
    type = models.CharField("type", max_length=20, choices=Type, default=Type.OTHER)
    capacity = models.PositiveIntegerField("capacité", validators=[MinValueValidator(1)])
    budget = models.DecimalField("budget (TND)", max_digits=12, decimal_places=2, default=0,
                                 validators=[MinValueValidator(0)])
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.DRAFT)
    client = models.ForeignKey(User, models.PROTECT, verbose_name="client", related_name="client_events",
                               blank=True, null=True, limit_choices_to={"role": Role.CLIENT})
    organizer = models.ForeignKey(User, models.PROTECT, verbose_name="organisateur", related_name="organized_events",
                                  blank=True, null=True, limit_choices_to={"role": Role.ORGANIZER})
    validator = models.ForeignKey(User, models.PROTECT, verbose_name="validateur", related_name="validated_events",
                                  blank=True, null=True, limit_choices_to={"role": Role.ADMIN})
    created_at = models.DateTimeField("date de création", auto_now_add=True)

    class Meta(Period.Meta):
        ordering = ("start_at", "pk")
        verbose_name = "événement"
        indexes = [models.Index(fields=["start_at", "status"])]
        constraints = Period.Meta.constraints + [
            models.CheckConstraint(condition=Q(capacity__gt=0, budget__gte=0), name="event_capacity_budget"),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if not self.pk:
            return
        if self.capacity is not None and self.registrations.filter(status__in=Participant.OCCUPIED).count() > self.capacity:
            raise ValidationError({"capacity": "La capacité est inférieure au nombre de places déjà occupées."})
        if self.start_at and self.end_at:
            outside = Q(start_at__lt=self.start_at) | Q(end_at__gt=self.end_at)
            if (self.sessions.filter(outside).exists() or
                    self.suggestions.filter(outside, status=Suggestion.Status.PENDING).exists() or
                    self.allocations.filter(outside, status=Allocation.Status.ASSIGNED).exists()):
                raise ValidationError("Des sessions, suggestions en attente ou affectations actives se trouvent hors de ces dates.")
            registrations = self.registrations.filter(status__in=Participant.OCCUPIED)
            overlaps = Participant.objects.filter(
                event__start_at__lt=self.end_at, event__end_at__gt=self.start_at,
                status__in=Participant.OCCUPIED,
            ).exclude(event=self).exclude(event__status=self.Status.CANCELLED)
            if self.status != self.Status.CANCELLED and (
                overlaps.filter(email__in=registrations.values("email")).exists() or
                overlaps.filter(user__in=registrations.exclude(user=None).values("user")).exists()
            ):
                raise ValidationError("Ce créneau entre en conflit avec une autre inscription des participants.")
            if self.status != self.Status.CANCELLED and Event.objects.filter(pk=self.pk, status=self.Status.CANCELLED).exists():
                for resource in Resource.objects.filter(allocations__event=self,
                                                        allocations__status=Allocation.Status.ASSIGNED).distinct():
                    allocations = resource.allocations.filter(status=Allocation.Status.ASSIGNED).filter(
                        Q(event=self) | ~Q(event__status=self.Status.CANCELLED),
                    )
                    if (resource.status != Resource.Status.AVAILABLE or
                            peak_quantity(allocations.values_list("start_at", "end_at", "quantity")) > resource.quantity):
                        raise ValidationError("Une ressource de cet événement est indisponible sur le créneau.")


class Provider(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "Disponible", "Disponible"
        RESERVED = "Réservé", "Réservé"
        INACTIVE = "Inactif", "Inactif"

    name = models.CharField("raison sociale", max_length=160)
    specialty = models.CharField("spécialité", max_length=120)
    city = models.CharField("ville", max_length=120)
    email = models.EmailField("e-mail", max_length=190)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    availability = models.CharField("disponibilités", max_length=255, blank=True)
    user = models.OneToOneField(User, models.PROTECT, verbose_name="compte prestataire", related_name="provider",
                               blank=True, null=True, limit_choices_to={"role": Role.PROVIDER})
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.AVAILABLE)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "prestataire"

    def __str__(self):
        return self.name


class Service(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "Actif", "Actif"
        INACTIVE = "Inactif", "Inactif"

    provider = models.ForeignKey(Provider, models.PROTECT, verbose_name="prestataire", related_name="services")
    name = models.CharField("nom du service", max_length=160)
    description = models.TextField("description", blank=True)
    price = models.DecimalField("tarif (TND)", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.ACTIVE)

    class Meta:
        ordering = ("name", "pk")
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="service_positive_price")]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.pk:
            previous_provider = Service.objects.filter(pk=self.pk).values_list("provider_id", flat=True).first()
            if previous_provider != self.provider_id and self.reservations.exists():
                raise ValidationError({"provider": "Ce service est déjà associé à des réservations."})


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "En attente", "En attente"
        ACCEPTED = "Acceptée", "Acceptée"
        REJECTED = "Refusée", "Refusée"
        CANCELLED = "Annulée", "Annulée"

    event = models.ForeignKey(Event, models.PROTECT, verbose_name="événement", related_name="reservations")
    service = models.ForeignKey(Service, models.PROTECT, verbose_name="service", related_name="reservations")
    amount = models.DecimalField("montant (TND)", max_digits=12, decimal_places=2, default=0,
                                 validators=[MinValueValidator(0)])
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.PENDING)
    rating = models.PositiveSmallIntegerField("note sur 5", blank=True, null=True,
                                               validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField("avis", blank=True)

    class Meta:
        ordering = ("-pk",)
        verbose_name = "réservation"
        indexes = [models.Index(fields=["event", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="reservation_positive_amount"),
            models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__range=(1, 5)),
                                   name="reservation_rating_range"),
        ]

    def __str__(self):
        return f"{self.service} · {self.event}"

    def clean(self):
        super().clean()
        if self.status not in (self.Status.PENDING, self.Status.ACCEPTED):
            return
        if self.event_id and self.event.status == Event.Status.CANCELLED:
            raise ValidationError("Cet événement est annulé.")
        if self.service_id and (self.service.status == Service.Status.INACTIVE or
                                self.service.provider.status == Provider.Status.INACTIVE):
            raise ValidationError("Ce service ou son prestataire est inactif.")


class Program(Period):
    class Status(models.TextChoices):
        PLANNED = "Planifié", "Planifié"
        CONFIRMED = "Confirmé", "Confirmé"
        FINISHED = "Terminé", "Terminé"

    event = models.ForeignKey(Event, models.PROTECT, verbose_name="événement", related_name="sessions")
    title = models.CharField("titre de la session", max_length=160)
    description = models.TextField("description", blank=True)
    speaker = models.CharField("intervenant", max_length=160, blank=True)
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.PLANNED)

    class Meta(Period.Meta):
        ordering = ("start_at", "pk")
        verbose_name = "session de programme"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.check_event_period()


def badge_token():
    return secrets.token_hex(32)


class Participant(models.Model):
    class Status(models.TextChoices):
        INVITED = "Invité", "Invité"
        REGISTERED = "Inscrit", "Inscrit"
        CONFIRMED = "Confirmé", "Confirmé"
        PRESENT = "Présent", "Présent"
        ABSENT = "Absent", "Absent"
        WAITLIST = "Liste d’attente", "Liste d’attente"
        CANCELLED = "Annulé", "Annulé"
        DECLINED = "Refusé", "Refusé"

    OCCUPIED = (Status.REGISTERED, Status.CONFIRMED, Status.PRESENT, Status.ABSENT)
    BADGE_STATUSES = (Status.CONFIRMED, Status.PRESENT)
    event = models.ForeignKey(Event, models.PROTECT, verbose_name="événement", related_name="registrations")
    user = models.ForeignKey(User, models.PROTECT, verbose_name="compte participant", related_name="registrations",
                             null=True, blank=True, limit_choices_to={"role": Role.PARTICIPANT})
    name = models.CharField("nom complet", max_length=120)
    email = models.EmailField("e-mail", max_length=190)
    category = models.CharField("catégorie", max_length=80, default="Invité")
    preference = models.CharField("préférence de placement", max_length=160, blank=True)
    seat = models.CharField("place attribuée", max_length=80, blank=True)
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.REGISTERED)
    badge_token = models.CharField(max_length=64, unique=True, default=badge_token, editable=False)
    rating = models.PositiveSmallIntegerField("note sur 5", blank=True, null=True,
                                               validators=[MinValueValidator(1), MaxValueValidator(5)])
    feedback = models.TextField("avis", blank=True)
    created_at = models.DateTimeField("date d’inscription", auto_now_add=True)

    class Meta:
        ordering = ("name", "pk")
        indexes = [models.Index(fields=["event", "status"])]
        constraints = [
            models.UniqueConstraint(Lower("email"), F("event"), name="unique_participant_event_email"),
            models.UniqueConstraint(fields=["event", "user"], name="unique_participant_event_user"),
            models.UniqueConstraint(Lower("seat"), F("event"),
                                    condition=Q(status__in=("Inscrit", "Confirmé", "Présent", "Absent")) & ~Q(seat=""),
                                    name="unique_occupied_event_seat"),
            models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__range=(1, 5)),
                                   name="participant_rating_range"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower()
        if not self.event_id:
            return
        if self.user_id and self.email != self.user.email:
            raise ValidationError({"email": "Utilisez l’adresse e-mail du compte associé."})
        if Participant.objects.filter(event_id=self.event_id, email__iexact=self.email).exclude(pk=self.pk).exists():
            raise ValidationError({"email": "Cette adresse est déjà inscrite à cet événement."})
        if self.status not in self.OCCUPIED:
            return
        if self.event.status == Event.Status.CANCELLED:
            raise ValidationError("Cet événement est annulé.")
        occupied = Participant.objects.filter(status__in=self.OCCUPIED).exclude(pk=self.pk)
        same_event = occupied.filter(event_id=self.event_id)
        if same_event.count() >= self.event.capacity:
            raise ValidationError("La capacité de l’événement est atteinte. Utilisez la liste d’attente.")
        if self.seat and same_event.filter(seat__iexact=self.seat).exists():
            raise ValidationError({"seat": "Cette place est déjà attribuée."})
        identity = Q(email__iexact=self.email)
        if self.user_id:
            identity |= Q(user_id=self.user_id)
        if occupied.filter(identity, event__start_at__lt=self.event.end_at,
                           event__end_at__gt=self.event.start_at).exclude(event_id=self.event_id).exclude(
                               event__status=Event.Status.CANCELLED).exists():
            raise ValidationError("Cette personne est déjà inscrite à un événement sur le même créneau.")


class Resource(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "Disponible", "Disponible"
        MAINTENANCE = "Maintenance", "Maintenance"
        UNAVAILABLE = "Indisponible", "Indisponible"

    class Category(models.TextChoices):
        FURNITURE = "Mobilier", "Mobilier"
        SOUND = "Son & lumière", "Son & lumière"
        DECOR = "Décoration", "Décoration"
        SPACE = "Espace", "Espace"
        OTHER = "Autre", "Autre"

    name = models.CharField("nom de la ressource", max_length=160)
    category = models.CharField("catégorie", max_length=20, choices=Category, default=Category.OTHER)
    quantity = models.PositiveIntegerField("quantité totale")
    status = models.CharField("état", max_length=20, choices=Status, default=Status.AVAILABLE)
    description = models.TextField("description", blank=True)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "ressource"

    def __str__(self):
        return self.name

    def available_between(self, start_at, end_at, exclude_pk=None):
        if self.status != self.Status.AVAILABLE:
            return 0
        overlapping = self.allocations.filter(
            status=Allocation.Status.ASSIGNED, start_at__lt=end_at, end_at__gt=start_at,
        ).exclude(pk=exclude_pk).exclude(event__status=Event.Status.CANCELLED)
        periods = ((max(start, start_at), min(end, end_at), quantity)
                   for start, end, quantity in overlapping.values_list("start_at", "end_at", "quantity"))
        return self.quantity - peak_quantity(periods)

    def clean(self):
        super().clean()
        if not self.pk:
            return
        current = self.allocations.filter(status=Allocation.Status.ASSIGNED,
                                          end_at__gt=timezone.now()).exclude(event__status=Event.Status.CANCELLED)
        peak = peak_quantity(current.values_list("start_at", "end_at", "quantity"))
        if self.quantity is not None and peak > self.quantity:
            raise ValidationError({"quantity": "Cette quantité est inférieure au stock déjà affecté."})
        if peak and self.status != self.Status.AVAILABLE:
            raise ValidationError({"status": "Annulez les affectations en cours ou à venir avant de rendre la ressource indisponible."})


def peak_quantity(periods):
    changes = []
    for start, end, quantity in periods:
        changes.extend(((start, quantity), (end, -quantity)))
    used = peak = 0
    for _, delta in sorted(changes):
        used += delta
        peak = max(peak, used)
    return peak


class Allocation(Period):
    class Status(models.TextChoices):
        ASSIGNED = "Affecté", "Affecté"
        CANCELLED = "Annulé", "Annulé"

    event = models.ForeignKey(Event, models.PROTECT, verbose_name="événement", related_name="allocations")
    resource = models.ForeignKey(Resource, models.PROTECT, verbose_name="ressource", related_name="allocations")
    quantity = models.PositiveIntegerField("quantité", validators=[MinValueValidator(1)])
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.ASSIGNED)

    class Meta(Period.Meta):
        ordering = ("-start_at", "pk")
        verbose_name = "affectation"
        indexes = [models.Index(fields=["resource", "start_at", "end_at"])]
        constraints = Period.Meta.constraints + [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="allocation_positive_quantity"),
        ]

    def __str__(self):
        return f"{self.resource} · {self.event}"

    def clean(self):
        super().clean()
        if self.status != self.Status.ASSIGNED:
            return
        self.check_event_period()
        if self.event_id and self.event.status == Event.Status.CANCELLED:
            raise ValidationError("Cet événement est annulé.")
        if not (self.resource_id and self.start_at and self.end_at and self.quantity):
            return
        if self.resource.status != Resource.Status.AVAILABLE:
            raise ValidationError({"resource": "Cette ressource est indisponible."})
        available = self.resource.available_between(self.start_at, self.end_at, exclude_pk=self.pk)
        if self.quantity > available:
            raise ValidationError({"quantity": f"Quantité disponible sur tout ce créneau : {available}."})


class Complaint(models.Model):
    class Status(models.TextChoices):
        OPEN = "Ouverte", "Ouverte"
        IN_PROGRESS = "En cours", "En cours"
        RESOLVED = "Résolue", "Résolue"

    participant = models.ForeignKey(Participant, models.PROTECT, verbose_name="inscription", related_name="complaints")
    subject = models.CharField("objet", max_length=160)
    message = models.TextField("message")
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.OPEN)
    response = models.TextField("réponse", blank=True)

    class Meta:
        ordering = ("-pk",)
        verbose_name = "réclamation"

    def __str__(self):
        return self.subject


class Suggestion(Period):
    class Status(models.TextChoices):
        PENDING = "En attente", "En attente"
        APPROVED = "Validée", "Validée"
        REJECTED = "Rejetée", "Rejetée"

    event = models.ForeignKey(Event, models.PROTECT, verbose_name="événement", related_name="suggestions")
    title = models.CharField("titre proposé", max_length=160)
    status = models.CharField("statut", max_length=20, choices=Status, default=Status.PENDING, editable=False)

    class Meta(Period.Meta):
        ordering = ("start_at", "pk")
        verbose_name = "suggestion de programme"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.check_event_period()


class Notification(models.Model):
    user = models.ForeignKey(User, models.CASCADE, related_name="notifications")
    message = models.CharField("message", max_length=500)
    read_at = models.DateTimeField("lue le", null=True, blank=True)
    created_at = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.message


class Activity(models.Model):
    user = models.ForeignKey(User, models.SET_NULL, null=True, blank=True)
    entity = models.CharField("gestion", max_length=60)
    record_id = models.PositiveBigIntegerField("identifiant")
    action = models.CharField("action", max_length=60)
    created_at = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "activité"

    def __str__(self):
        return f"{self.action} · {self.entity}"


class LoginAttempt(models.Model):
    email = models.CharField(max_length=190, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    success = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["email", "created_at"]), models.Index(fields=["ip", "created_at"])]

    def __str__(self):
        return self.email



class LoginAlert(models.Model):
    email = models.EmailField(max_length=190, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "alerte de connexion"

    def __str__(self):
        return self.email or "Connexions échouées"


class Document(models.Model):
    participant = models.ForeignKey(Participant, models.PROTECT, related_name="documents")
    original_name = models.CharField("nom du fichier", max_length=190)
    mime = models.CharField("type de fichier", max_length=100)
    size = models.PositiveIntegerField("taille")
    content = models.BinaryField(editable=False)
    created_at = models.DateTimeField("date de dépôt", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.original_name

