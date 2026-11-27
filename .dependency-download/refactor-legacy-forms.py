from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import Q
from django.utils import timezone

from . import models
from .modules import BY_MODEL, is_admin, scoped


class LocalDateTime(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self):
        super().__init__(format="%Y-%m-%dT%H:%M", attrs={"step": 60})


class StyledForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if widget.is_hidden:
                continue
            if isinstance(widget, forms.CheckboxInput):
                css_class = "form-check-input"
            elif isinstance(widget, forms.Select):
                css_class = "form-select"
            else:
                css_class = "form-control"
            widget.attrs["class"] = css_class
            if isinstance(widget, forms.Textarea):
                widget.attrs["rows"] = 3


class LoginForm(StyledForm, AuthenticationForm):
    username = forms.EmailField(label="Adresse e-mail", max_length=190,
                                widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))

    def clean_username(self):
        return self.cleaned_data["username"].lower()


class RecordForm(StyledForm, forms.ModelForm):
    def __init__(self, *args, actor, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.ModelChoiceField) and field.queryset.model in BY_MODEL:
                model = field.queryset.model
                if not is_admin(actor) and model is models.Event:
                    field.queryset = scoped(actor, BY_MODEL[model])
                    if actor.role == models.Role.PARTICIPANT:
                        field.queryset = field.queryset.filter(status=models.Event.Status.CONFIRMED,
                                                               start_at__gt=timezone.now())
                if not is_admin(actor) and model is models.Participant:
                    field.queryset = scoped(actor, BY_MODEL[model])
                if not is_admin(actor) and model is models.Provider:
                    field.queryset = scoped(actor, BY_MODEL[model])

    def add_error(self, field, error):
        if field is None and isinstance(error, ValidationError) and hasattr(error, "error_dict"):
            visible_errors = {}
            for name, errors in error.error_dict.items():
                target = name if name in self.fields else NON_FIELD_ERRORS
                visible_errors.setdefault(target, []).extend(errors)
            error = ValidationError(visible_errors)
        super().add_error(field, error)

    def clean(self):
        data = super().clean()
        if isinstance(self.instance, models.Event):
            if self.actor.role == models.Role.ORGANIZER and not is_admin(self.actor):
                self.instance.organizer = self.actor
            if self.actor.role == models.Role.CLIENT and not is_admin(self.actor):
                self.instance.client = self.actor
        if isinstance(self.instance, models.Participant) and self.actor.role == models.Role.PARTICIPANT and not is_admin(self.actor):
            self.prepare_participation(data)
        return data

    def prepare_participation(self, data):
        now = timezone.now()
        if not self.instance.pk:
            self.instance.user = self.actor
            self.instance.name = self.actor.name
            self.instance.email = self.actor.email
            event = data.get("event")
            if event and event.registrations.filter(status__in=models.Participant.OCCUPIED).count() >= event.capacity:
                self.instance.status = models.Participant.Status.WAITLIST
            return

        status = data.get("status", self.instance.status)
        changed_status = status != self.instance.status
        if changed_status and (status not in participant_statuses(self.instance) or
                               self.instance.event.start_at <= now or
                               self.instance.event.status == models.Event.Status.CANCELLED):
            self.add_error("status", "Cette réponse n’est plus disponible.")
        if ({"rating", "feedback"} & set(self.changed_data) and
                (self.instance.event.end_at > now or self.instance.event.status == models.Event.Status.CANCELLED)):
            self.add_error(None, "Vous pourrez laisser un avis après l’événement.")


def participant_statuses(record):
    status = models.Participant.Status
    transitions = {
        status.INVITED: (status.CONFIRMED, status.DECLINED),
        status.REGISTERED: (status.CONFIRMED, status.CANCELLED),
        status.CONFIRMED: (status.CANCELLED,),
        status.WAITLIST: (status.CANCELLED,),
    }
    return (record.status, *transitions.get(record.status, ()))


class AccountForm(RecordForm):
    password = forms.CharField(label="Nouveau mot de passe", required=False, max_length=200,
                               strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = models.User
        fields = ("name", "email", "phone", "role", "is_active", "availability", "skills")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].required = not self.instance.pk
        if self.instance.pk:
            self.fields["password"].help_text = "Laissez ce champ vide pour conserver le mot de passe actuel."
        if self.actor and self.instance.pk == self.actor.pk:
            self.fields["role"].disabled = self.fields["is_active"].disabled = True

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password:
            user = models.User(email=data.get("email", ""), name=data.get("name", ""))
            try:
                password_validation.validate_password(password, user)
            except ValidationError as error:
                self.add_error("password", error)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user


class SignupForm(AccountForm):
    class Meta(AccountForm.Meta):
        fields = ("name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, actor=None, **kwargs)
        self.fields["password"].label = "Mot de passe"


class ProfileForm(StyledForm, forms.ModelForm):
    class Meta:
        model = models.User
        fields = ("name", "phone", "availability", "skills")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.role != models.Role.ORGANIZER:
            self.fields.pop("availability")
            self.fields.pop("skills")


def record_form(section, actor, record=None):
    if section.key == "users":
        return AccountForm
    fields = section.fields.split()
    if not is_admin(actor):
        key = section.key
        if actor.role == models.Role.ORGANIZER and key == "events":
            fields = [field for field in fields if field not in {"organizer", "validator"}]
        elif actor.role == models.Role.CLIENT and key == "events":
            fields = ["title", "description", "start_at", "end_at", "location", "type", "capacity", "budget"]
        elif actor.role == models.Role.PROVIDER and key == "providers":
            fields = ["phone", "availability"]
        elif actor.role == models.Role.PROVIDER and key == "reservations":
            fields = ["status"]
        elif actor.role == models.Role.ORGANIZER and key == "reservations":
            fields = [field for field in fields if field != "status"]
            if record and record.status == models.Reservation.Status.ACCEPTED:
                fields = ["rating", "comment"]
        elif actor.role == models.Role.PARTICIPANT:
            if key == "participants":
                fields = ["status", "preference", "rating", "feedback"] if record else ["event", "preference"]
            if key == "complaints":
                fields = ["participant", "subject", "message"]

    class SectionForm(RecordForm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not is_admin(actor):
                self.restrict_fields()

        def restrict_fields(self):
            if section.key == "events" and actor.role == models.Role.ORGANIZER:
                if not record or record.status != models.Event.Status.CONFIRMED:
                    self.fields["status"].choices = [
                        choice for choice in self.fields["status"].choices
                        if choice[0] != models.Event.Status.CONFIRMED
                    ]
            if section.key == "reservations" and actor.role == models.Role.PROVIDER:
                statuses = [record.status]
                if record.status == models.Reservation.Status.PENDING:
                    statuses += [models.Reservation.Status.ACCEPTED, models.Reservation.Status.REJECTED]
                self.fields["status"].choices = [(s, s) for s in statuses]
            if section.key == "participants" and actor.role == models.Role.PARTICIPANT and record:
                choices = participant_statuses(record) if record.event.start_at > timezone.now() else (record.status,)
                self.fields["status"].choices = [(s, s) for s in choices]
                if record.event.end_at > timezone.now() or record.event.status == models.Event.Status.CANCELLED:
                    self.fields.pop("rating")
                    self.fields.pop("feedback")
            if section.key == "reservations" and actor.role == models.Role.ORGANIZER:
                for field in ("rating", "comment"):
                    if field in self.fields and (not record or record.status != models.Reservation.Status.ACCEPTED):
                        self.fields.pop(field)
                if "service" in self.fields:
                    current = Q(pk=record.service_id) if record else Q(pk__isnull=True)
                    self.fields["service"].queryset = self.fields["service"].queryset.filter(
                        Q(status=models.Service.Status.ACTIVE) & ~Q(provider__status=models.Provider.Status.INACTIVE) | current
                    )

    return forms.modelform_factory(section.model, form=SectionForm, fields=fields,
                                  widgets={field: LocalDateTime() for field in ("start_at", "end_at") if field in fields})



class DocumentForm(StyledForm, forms.Form):
    document = forms.FileField(
        label="Document",
        help_text="PDF, PNG ou JPEG, jusqu’à 5 Mo.",
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg"}),
    )

    def clean_document(self):
        from pathlib import PurePath

        file = self.cleaned_data["document"]
        if file.size > 5 * 1024 * 1024 or len(file.name) > 190:
            raise ValidationError("Le fichier dépasse la taille ou la longueur de nom autorisée.")
        formats = {
            ".pdf": ("application/pdf", b"%PDF-"),
            ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
            ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
            ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
        }
        entry = formats.get(PurePath(file.name).suffix.lower())
        if not entry or not file.read(8).startswith(entry[1]):
            raise ValidationError("Choisissez un fichier PDF, PNG ou JPEG valide.")
        file.seek(0)
        self.mime = entry[0]
        return file


class AvailabilityForm(StyledForm, forms.Form):
    start_at = forms.DateTimeField(label="Début du créneau", widget=LocalDateTime())
    end_at = forms.DateTimeField(label="Fin du créneau", widget=LocalDateTime())

    def clean(self):
        data = super().clean()
        if "start_at" in data and "end_at" in data and data["end_at"] <= data["start_at"]:
            self.add_error("end_at", "La fin doit être postérieure au début.")
        return data

