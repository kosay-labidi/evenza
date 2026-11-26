from dataclasses import dataclass
from functools import reduce
from operator import or_

from django.db.models import Q
from django.urls import reverse

from . import models
from .models import Role


@dataclass(frozen=True)
class Module:
    slug: str
    label: str
    title: str
    icon: str
    description: str


MODULES = {item.slug: item for item in (
    Module("evenements", "Événements", "Gestion des événements", "calendar-event",
           "Planifiez vos événements et suivez leur avancement."),
    Module("prestataires", "Prestataires", "Gestion des prestataires", "briefcase",
           "Retrouvez vos partenaires, leurs services et vos réservations."),
    Module("utilisateurs", "Utilisateurs", "Gestion des utilisateurs", "person-gear",
           "Gérez les comptes, les rôles et les accès de votre équipe."),
    Module("programmes", "Programmes", "Gestion des programmes", "clock",
           "Composez le déroulé de vos événements, session après session."),
    Module("participants", "Participants", "Gestion des participants", "people",
           "Retrouvez vos invités et suivez leurs inscriptions et présences."),
    Module("ressources", "Ressources", "Gestion des ressources", "boxes",
           "Suivez votre inventaire et anticipez les besoins en matériel."),
)}


@dataclass(frozen=True)
class Section:
    key: str
    module: str
    path: str
    label: str
    model: type
    fields: str
    columns: str
    search: str
    filter: str = "status"

    def url(self, action="list", pk=None):
        return reverse(f"{self.module}:{self.key}-{action}", args=() if pk is None else (pk,))


SECTIONS = {item.key: item for item in (
    Section("events", "evenements", "", "Événements", models.Event,
            "title description start_at end_at location type capacity budget status client organizer validator",
            "title start_at location type status", "title location description client__name organizer__name"),
    Section("providers", "prestataires", "", "Prestataires", models.Provider,
            "name specialty city email phone availability user status", "name specialty city email status",
            "name specialty city email availability"),
    Section("services", "prestataires", "services/", "Services", models.Service,
            "provider name description price status", "name provider price status", "name provider__name description"),
    Section("reservations", "prestataires", "reservations/", "Réservations", models.Reservation,
            "event service amount status rating comment", "service event amount status rating",
            "event__title service__name service__provider__name"),
    Section("users", "utilisateurs", "", "Utilisateurs", models.User,
            "name email phone role is_active availability skills", "name email role is_active", "name email skills", "role"),
    Section("programs", "programmes", "", "Sessions", models.Program,
            "event title description start_at end_at speaker status", "title event start_at speaker status",
            "title description event__title speaker"),
    Section("suggestions", "programmes", "suggestions/", "Suggestions de programme", models.Suggestion,
            "event title start_at end_at", "title event start_at status", "title event__title"),
    Section("participants", "participants", "", "Inscriptions", models.Participant,
            "event user name email category preference seat status rating feedback", "name email event seat status",
            "name email category event__title seat"),
    Section("complaints", "participants", "reclamations/", "Réclamations", models.Complaint,
            "participant subject message status response", "subject participant status",
            "subject participant__name participant__event__title"),
    Section("resources", "ressources", "", "Ressources", models.Resource,
            "name category quantity status description", "name category quantity status", "name description"),
    Section("allocations", "ressources", "affectations/", "Affectations", models.Allocation,
            "event resource quantity start_at end_at status", "resource event quantity start_at status",
            "resource__name event__title"),
)}
BY_MODEL = {section.model: section for section in SECTIONS.values()}

ORGANIZER_WRITE = {"events", "programs", "suggestions", "participants", "complaints",
                   "resources", "allocations", "reservations"}
PROVIDER_READ = {"providers", "services", "reservations", "events", "programs"}
CLIENT_READ = {"events", "programs"}
PARTICIPANT_READ = {"events", "programs", "participants", "complaints"}


def is_admin(user):
    return user.is_superuser or user.role == Role.ADMIN


def allowed(user, section, action="view"):
    if not user.is_authenticated or not user.is_active:
        return False
    if is_admin(user):
        return True

    key = section.key
    role = user.role
    if action == "view":
        return {
            Role.ORGANIZER: key != "users",
            Role.PROVIDER: key in PROVIDER_READ,
            Role.CLIENT: key in CLIENT_READ,
            Role.PARTICIPANT: key in PARTICIPANT_READ,
        }.get(role, False)
    if role == Role.ORGANIZER:
        return key in ORGANIZER_WRITE
    if role == Role.PROVIDER:
        return key == "services" or (key in {"providers", "reservations"} and action == "change")
    if role == Role.CLIENT:
        return key == "events" and action == "add"
    return (key == "participants" and action in {"add", "change"}) or (key == "complaints" and action == "add")


def scoped(user, section):
    queryset = section.model.objects.all()
    if not allowed(user, section):
        return queryset.none()
    if is_admin(user):
        return queryset

    key = section.key
    if user.role == Role.ORGANIZER:
        event = Q(organizer=user)
        related = Q(event__organizer=user)
        scopes = {"events": event, "programs": related, "reservations": related, "suggestions": related,
                  "participants": related, "allocations": related, "complaints": Q(participant__event__organizer=user)}
    elif user.role == Role.PROVIDER:
        own_events = models.Reservation.objects.filter(service__provider__user=user).values("event")
        scopes = {"providers": Q(user=user), "services": Q(provider__user=user),
                  "reservations": Q(service__provider__user=user), "events": Q(pk__in=own_events),
                  "programs": Q(event__in=own_events)}
    elif user.role == Role.CLIENT:
        scopes = {"events": Q(client=user), "programs": Q(event__client=user)}
    else:
        registrations = models.Participant.objects.filter(user=user).values("event")
        visible = Q(status=models.Event.Status.CONFIRMED) | Q(pk__in=registrations)
        scopes = {"events": visible, "programs": Q(event__status=models.Event.Status.CONFIRMED) | Q(event__in=registrations),
                  "participants": Q(user=user), "complaints": Q(participant__user=user)}
    return queryset.filter(scopes.get(key, Q()))


def search_query(query, fields):
    return reduce(or_, (Q(**{f"{field}__icontains": query}) for field in fields.split()))

