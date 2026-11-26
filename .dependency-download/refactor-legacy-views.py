import csv
import io
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.db.models.deletion import ProtectedError, RestrictedError
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from . import forms as local_forms, models
from .modules import MODULES, SECTIONS, allowed, is_admin, scoped, search_query


def navigation(request):
    sections = [section for section in SECTIONS.values() if not section.path and allowed(request.user, section)]
    return {
        "navigation": [(MODULES[section.module], section.url()) for section in sections],
        "unread_notifications": (request.user.notifications.filter(read_at__isnull=True).count()
                                 if request.user.is_authenticated else 0),
    }


class SectionView(LoginRequiredMixin, UserPassesTestMixin):
    section = None
    permission = "view"

    def test_func(self):
        return allowed(self.request.user, self.section, self.permission)

    def get_queryset(self):
        queryset = scoped(self.request.user, self.section)
        if self.section.key == "users" and not self.request.user.is_superuser:
            queryset = queryset.filter(is_superuser=False, is_staff=False)
        relations = [field.name for field in self.section.model._meta.fields if field.is_relation]
        return queryset.select_related(*relations) if relations else queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user, section = self.request.user, self.section
        context.update(
            module=MODULES[section.module],
            section=section,
            tabs=[(other, other.url()) for other in SECTIONS.values()
                  if other.module == section.module and allowed(user, other)],
            list_url=section.url(),
            create_url=section.url("create") if allowed(user, section, "add") else None,
        )
        return context

    def row_actions(self, record):
        user, section = self.request.user, self.section
        return {
            "view_url": section.url("detail", record.pk),
            "edit_url": section.url("update", record.pk) if allowed(user, section, "change") else None,
            "delete_url": (section.url("delete", record.pk) if record != user and
                           allowed(user, section, "delete") else None),
        }


def cell_value(record, field):
    value = getattr(record, f"get_{field}_display", None)
    if value:
        return value()
    value = getattr(record, field)
    if isinstance(value, bool):
        return "Actif" if value else "Inactif"
    return "—" if value is None or value == "" else value


def filters_for(section):
    fields = [section.filter]
    if section.key == "events":
        fields.append("type")
    if section.key == "resources":
        fields.append("category")
    if section.key == "users":
        fields.append("is_active")
    return fields


class RecordList(SectionView, ListView):
    template_name = "gestion/list.html"
    paginate_by = 12

    def get_queryset(self):
        self.base_queryset = super().get_queryset()
        queryset = self.base_queryset
        self.query = self.request.GET.get("q", "").strip()[:200]
        fields = self.section.search
        if self.section.key == "events" and not is_admin(self.request.user) and (
                self.request.user.role in (models.Role.PARTICIPANT, models.Role.PROVIDER)):
            fields = "title location description"
        for word in self.query.split():
            queryset = queryset.filter(search_query(word, fields))
        self.filters = []
        for field in filters_for(self.section):
            model_field = self.section.model._meta.get_field(field)
            options = dict(model_field.flatchoices)
            if field == "is_active":
                options = {"1": "Actif", "0": "Inactif"}
            value = self.request.GET.get(field, "")
            if value in options:
                queryset = queryset.filter(**{field: value == "1" if field == "is_active" else value})
            else:
                value = ""
            self.filters.append({"name": field, "label": model_field.verbose_name.capitalize(),
                                 "options": options.items(), "selected": value})
        self.chosen_date = None
        if self.section.key in {"events", "programs", "suggestions", "allocations"}:
            try:
                self.chosen_date = parse_date(self.request.GET.get("date", ""))
            except ValueError:
                pass
            if self.chosen_date:
                start = timezone.make_aware(datetime.combine(self.chosen_date, time.min))
                end = start + timedelta(days=1)
                queryset = queryset.filter(start_at__lt=end, end_at__gt=start)
        self.entity_filters = []
        for field in ("event", "resource"):
            if field not in self.section.fields.split():
                continue
            model_field = self.section.model._meta.get_field(field)
            options = scoped(self.request.user, next(section for section in SECTIONS.values()
                                                     if section.model is model_field.related_model))
            selected = self.request.GET.get(field, "")
            if selected.isascii() and selected.isdecimal() and len(selected) <= 18:
                queryset = queryset.filter(**{f"{field}_id": int(selected)})
            else:
                selected = ""
            self.entity_filters.append({
                "name": field,
                "label": model_field.verbose_name.capitalize(),
                "options": ((str(record.pk), str(record)) for record in options),
                "selected": selected,
            })
        return queryset

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            queryset = self.get_queryset()
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            columns = self.section.columns.split()
            writer.writerow([self.section.model._meta.get_field(field).verbose_name for field in columns])
            for record in queryset.iterator():
                row = [str(cell_value(record, field)) for field in columns]
                writer.writerow(["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in row])
            return HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8",
                                headers={"Content-Disposition": f'attachment; filename="{self.section.key}.csv"'})
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columns = self.section.columns.split()
        context.update(
            title=MODULES[self.section.module].title,
            subtitle=MODULES[self.section.module].description,
            headings=[self.section.model._meta.get_field(field).verbose_name for field in columns],
            rows=[{"cells": [cell_value(record, field) for field in columns], **self.row_actions(record)}
                  for record in context["object_list"]],
            filters=[*self.filters, *self.entity_filters],
            query=self.query,
            date_filter=self.section.key in {"events", "programs", "suggestions", "allocations"},
            chosen_date=self.chosen_date,
            total_count=self.base_queryset.count(),
            filtered_count=context["paginator"].count,
        )
        field = self.section.filter
        choices = dict(self.section.model._meta.get_field(field).flatchoices)
        breakdown = self.base_queryset.order_by().values(field).annotate(total=Count("pk"))
        context["breakdown"] = [(choices.get(row[field], row[field]), row["total"]) for row in breakdown]
        return context


class RecordDetail(SectionView, DetailView):
    template_name = "gestion/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user, record, key = self.request.user, self.object, self.section.key
        fields = self.section.fields.split()
        if key == "events" and not is_admin(user) and user.role in (models.Role.PARTICIPANT, models.Role.PROVIDER):
            fields = [field for field in fields if field not in {"budget", "client", "organizer", "validator"}]
        if key == "suggestions":
            fields.append("status")
        related = {
            "events": (("programs", "event"), ("participants", "event"), ("reservations", "event"), ("allocations", "event")),
            "providers": (("services", "provider"),),
            "participants": (("complaints", "participant"),),
            "resources": (("allocations", "resource"),),
        }
        groups = []
        for related_key, field in related.get(key, ()):
            section = SECTIONS[related_key]
            if allowed(user, section):
                records = scoped(user, section).filter(**{field: record})
                groups.append((section.label, [(str(item), section.url("detail", item.pk)) for item in records[:10]]))
        context.update(
            title=str(record),
            details=[(self.section.model._meta.get_field(field).verbose_name, cell_value(record, field)) for field in fields],
            related_groups=groups,
            operations=available_operations(user, self.section, record),
            **self.row_actions(record),
        )
        if key == "participants":
            context["documents"] = record.documents.defer("content")
            context["document_form"] = local_forms.DocumentForm()
            context["can_upload"] = is_admin(user) or user.role == models.Role.ORGANIZER or record.user_id == user.pk
            if record.status in models.Participant.BADGE_STATUSES and record.event.status != models.Event.Status.CANCELLED:
                context["badge_url"] = reverse("badge", args=[record.pk])
        if key == "events" and (is_admin(user) or user.role == models.Role.ORGANIZER):
            count = record.registrations.filter(status__in=models.Participant.OCCUPIED).count()
            context["details"].extend([("places occupées", f"{count} / {record.capacity}")])
        if key == "providers":
            ratings = scoped(user, SECTIONS["reservations"]).filter(service__provider=record, rating__isnull=False)
            average = ratings.aggregate(value=Avg("rating"))["value"]
            if average is not None:
                context["details"].append(("note moyenne", f"{average:.1f} / 5"))
        if key == "users" and record.role == models.Role.ORGANIZER:
            upcoming = record.organized_events.filter(end_at__gte=timezone.now()).exclude(status=models.Event.Status.CANCELLED)
            context["details"].append(("événements en cours ou à venir", upcoming.count()))
        if key == "resources":
            form = local_forms.AvailabilityForm(self.request.GET or None)
            context["availability_form"] = form
            if form.is_valid():
                context["available_quantity"] = record.available_between(**form.cleaned_data)
        return context


def record_activity(actor, section, pk, action):
    models.Activity.objects.create(user=actor, entity=section.key, record_id=pk, action=action)


def notify(user_id, message):
    if user_id:
        models.Notification.objects.create(user_id=user_id, message=message)


def record_changes(actor, section, record, action, previous_status=None):
    record_activity(actor, section, record.pk, action)
    if previous_status == getattr(record, "status", None):
        return
    key = section.key
    if key == "reservations":
        recipient = (record.event.organizer_id if record.status in
                     (models.Reservation.Status.ACCEPTED, models.Reservation.Status.REJECTED) else
                     record.service.provider.user_id)
        notify(recipient, f"Réservation « {record.service} » · {record.status}.")
    elif key == "participants":
        notify(record.user_id, f"Inscription à « {record.event} » · {record.status}.")
    elif key == "complaints":
        notify(record.participant.user_id, f"Réclamation « {record.subject} » · {record.status}.")
    elif key == "events" and record.status == models.Event.Status.CANCELLED:
        for user_id in record.registrations.exclude(user=None).values_list("user_id", flat=True).distinct():
            notify(user_id, f"L’événement « {record} » a été annulé.")


class RecordEditor(SectionView):
    template_name = "gestion/form.html"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_form_class(self):
        self.previous_status = getattr(self.object, "status", None)
        return local_forms.record_form(self.section, self.request.user, self.object)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "actor": self.request.user}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Modifier · {self.object}" if self.object else f"Ajouter · {self.section.label}"
        return context

    def form_valid(self, form):
        if self.section.key == "events" and is_admin(self.request.user):
            if form.instance.status == models.Event.Status.CONFIRMED and not form.instance.validator_id:
                if self.request.user.role == models.Role.ADMIN:
                    form.instance.validator = self.request.user
        response = super().form_valid(form)
        if self.request.user == self.object and form.cleaned_data.get("password"):
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(self.request, self.object)
        record_changes(self.request.user, self.section, self.object,
                       "Modification" if self.permission == "change" else "Création", self.previous_status)
        messages.success(self.request, "Les informations ont été enregistrées.")
        return response

    def get_success_url(self):
        return self.section.url()


class RecordCreate(RecordEditor, CreateView):
    permission = "add"


class RecordUpdate(RecordEditor, UpdateView):
    permission = "change"


class RecordDelete(SectionView, DeleteView):
    permission = "delete"
    template_name = "gestion/delete.html"

    def get_object(self, queryset=None):
        record = super().get_object(queryset)
        if record == self.request.user:
            raise PermissionDenied
        return record

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Supprimer · {self.object}"
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        pk = self.object.pk
        try:
            response = super().form_valid(form)
        except (ProtectedError, RestrictedError):
            form.add_error(None, "Cette fiche est liée à d’autres enregistrements. Traitez d’abord les fiches associées.")
            return self.form_invalid(form)
        record_activity(self.request.user, self.section, pk, "Suppression")
        messages.success(self.request, "La fiche a été supprimée.")
        return response

    def get_success_url(self):
        return self.section.url()


def available_operations(user, section, record):
    if not allowed(user, section, "change"):
        return []
    actions = []
    if section.key == "suggestions" and record.status == models.Suggestion.Status.PENDING:
        actions += [("approve", "Valider la suggestion"), ("reject", "Rejeter la suggestion")]
    if section.key == "reservations" and (is_admin(user) or user.role == models.Role.ORGANIZER):
        if record.status in (models.Reservation.Status.PENDING, models.Reservation.Status.ACCEPTED):
            actions.append(("cancel", "Annuler la réservation"))
    if section.key == "participants" and (is_admin(user) or user.role == models.Role.ORGANIZER):
        if record.status == models.Participant.Status.WAITLIST:
            actions.append(("promote", "Attribuer une place"))
        if (record.status == models.Participant.Status.INVITED and record.event.start_at > timezone.now() and
                record.event.status != models.Event.Status.CANCELLED):
            actions.append(("invite", "Envoyer l’invitation"))
        if record.status in (models.Participant.Status.INVITED, models.Participant.Status.WAITLIST,
                             models.Participant.Status.REGISTERED) and record.event.start_at > timezone.now() and (
                                 record.event.status != models.Event.Status.CANCELLED):
            actions.append(("remind", "Envoyer un rappel"))
    return [(action, label, reverse("record-operation", args=[section.key, record.pk, action])) for action, label in actions]


@login_required
@require_POST
@transaction.atomic
def record_operation(request, key, pk, operation):
    section = SECTIONS.get(key)
    if section is None or not allowed(request.user, section, "change"):
        raise PermissionDenied
    record = get_object_or_404(scoped(request.user, section), pk=pk)
    if operation not in {action for action, _, _ in available_operations(request.user, section, record)}:
        raise PermissionDenied
    previous = record.status
    try:
        if operation in {"invite", "remind"}:
            send_participant_email(request, record, operation)
            messages.success(request, "Le message a été transmis au service de messagerie.")
            record_activity(request.user, section, pk, "Envoi d’un message")
        else:
            session = None
            if operation == "approve":
                session = models.Program(event=record.event, title=record.title, start_at=record.start_at,
                                         end_at=record.end_at, status=models.Program.Status.CONFIRMED)
                session.full_clean()
                record.status = models.Suggestion.Status.APPROVED
            elif operation == "reject":
                record.status = models.Suggestion.Status.REJECTED
            elif operation == "cancel":
                record.status = models.Reservation.Status.CANCELLED
            elif operation == "promote":
                record.status = models.Participant.Status.REGISTERED
                if record.event.start_at <= timezone.now():
                    raise ValidationError("L’événement a déjà commencé.")
            record.full_clean()
            if session:
                session.save()
                record_activity(request.user, SECTIONS["programs"], session.pk, "Création")
            record.save(update_fields=["status"])
            record_changes(request.user, section, record, "Modification", previous)
            messages.success(request, "L’action a été enregistrée.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    except OSError:
        messages.error(request, "Le service de messagerie est indisponible.")
    return redirect(section.url("detail", pk))


def send_participant_email(request, record, operation):
    from django.core import signing

    if record.status == models.Participant.Status.INVITED:
        token = signing.dumps({"pk": record.pk, "email": record.email}, salt="evenza-invitation")
        url = request.build_absolute_uri(reverse("invitation", args=[token]))
    else:
        url = request.build_absolute_uri(SECTIONS["participants"].url("detail", record.pk))
    subject = "Invitation" if operation == "invite" else "Rappel"
    send_mail(f"Évenza · {subject}", f"{record.name},\n\n{record.event}\n{url}", None, [record.email])


@login_required
@transaction.atomic
def invitation(request, token):
    from django.core import signing
    from django.http import Http404

    try:
        data = signing.loads(token, salt="evenza-invitation", max_age=30 * 86400)
    except signing.BadSignature as error:
        raise Http404 from error
    if request.user.role != models.Role.PARTICIPANT or request.user.email != data["email"]:
        raise PermissionDenied
    record = get_object_or_404(models.Participant, pk=data["pk"], email=data["email"])
    if record.user_id and record.user_id != request.user.pk:
        raise PermissionDenied
    if request.method == "POST":
        response = request.POST.get("response")
        if (response not in {"confirm", "decline"} or record.status != models.Participant.Status.INVITED or
                record.event.start_at <= timezone.now() or record.event.status == models.Event.Status.CANCELLED):
            raise PermissionDenied
        record.user = request.user
        record.status = models.Participant.Status.CONFIRMED if response == "confirm" else models.Participant.Status.DECLINED
        if response == "confirm" and record.event.registrations.filter(
                status__in=models.Participant.OCCUPIED).count() >= record.event.capacity:
            record.status = models.Participant.Status.WAITLIST
        try:
            record.full_clean()
            record.save(update_fields=["user", "status"])
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            record_changes(request.user, SECTIONS["participants"], record, "Réponse à l’invitation",
                           models.Participant.Status.INVITED)
            messages.success(request, "Votre réponse a été enregistrée.")
            return redirect(SECTIONS["participants"].url("detail", record.pk))
    return render(request, "gestion/invitation.html", {"title": "Invitation", "record": record})


class Dashboard(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        user, now = self.request.user, timezone.now()
        events = scoped(user, SECTIONS["events"])
        upcoming = events.filter(start_at__gte=now).exclude(status=models.Event.Status.CANCELLED)
        first = timezone.localdate().replace(day=1)
        months = [first]
        for _ in range(5):
            months.insert(0, (months[0] - timedelta(days=1)).replace(day=1))
        counts = dict(events.filter(start_at__date__gte=months[0], start_at__date__lte=timezone.localdate()).order_by()
                      .annotate(month=TruncMonth("start_at")).values("month").annotate(total=Count("pk"))
                      .values_list("month", "total"))
        monthly_counts = {month.date(): total for month, total in counts.items()}
        statuses = dict(events.order_by().values("status").annotate(total=Count("pk")).values_list("status", "total"))
        modules = [s for s in SECTIONS.values() if not s.path and allowed(user, s)]
        activities = models.Activity.objects.select_related("user")
        if not is_admin(user):
            activities = activities.filter(user=user)
        return {
            "title": "Tableau de bord",
            "kpis": [(MODULES[s.module].label, MODULES[s.module].icon, scoped(user, s).count(), s.url())
                     for s in modules if s.key in {"events", "participants", "providers", "resources"}],
            "links": [(MODULES[s.module], s.url()) for s in modules],
            "events": [(event, SECTIONS["events"].url("detail", event.pk)) for event in upcoming[:5]],
            "activity": [(item, SECTIONS[item.entity].label) for item in activities[:8] if item.entity in SECTIONS],
            "event_list_url": SECTIONS["events"].url(),
            "month_rows": [(month.strftime("%m/%Y"), monthly_counts.get(month, 0)) for month in months],
            "status_rows": list(statuses.items()),
            "chart_data": {
                "months": [month.strftime("%m/%Y") for month in months],
                "monthly": [monthly_counts.get(month, 0) for month in months],
                "statuses": list(statuses),
                "totals": list(statuses.values()),
            },
        }


class SignIn(LoginView):
    template_name = "registration/login.html"
    authentication_form = local_forms.LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        from ipaddress import ip_address

        email = request.POST.get("username", "").strip().lower()[:190]
        try:
            ip = str(ip_address(request.META.get("REMOTE_ADDR", "")))
        except ValueError:
            ip = None
        criteria = Q(email=email)
        if ip:
            criteria |= Q(ip=ip)
        failures = models.LoginAttempt.objects.filter(criteria, success=False,
                                                       created_at__gte=timezone.now() - timedelta(minutes=15))
        failed_count = failures.count()
        if failed_count >= 10:
            form = self.get_form()
            form.add_error(None, "Trop de tentatives. Réessayez dans 15 minutes.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        response = super().post(request, *args, **kwargs)
        models.LoginAttempt.objects.create(email=email, ip=ip, success=request.user.is_authenticated)
        if not request.user.is_authenticated and failed_count == 4:
            models.LoginAlert.objects.create(email=email, ip=ip)
        return response


class Signup(CreateView):
    form_class = local_forms.SignupForm
    template_name = "registration/form.html"
    success_url = reverse_lazy("login")
    extra_context = {"title": "Créer un compte", "submit_label": "S’inscrire"}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Votre compte a été créé. Vous pouvez vous connecter.")
        return response


class Profile(LoginRequiredMixin, UpdateView):
    form_class = local_forms.ProfileForm
    template_name = "gestion/profile.html"
    success_url = reverse_lazy("profile")
    extra_context = {"title": "Paramètres"}

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Votre profil a été mis à jour.")
        return response


class Notifications(LoginRequiredMixin, ListView):
    template_name = "gestion/notifications.html"
    extra_context = {"title": "Notifications"}
    paginate_by = 15

    def get_queryset(self):
        return self.request.user.notifications.all()

    def post(self, request, *args, **kwargs):
        queryset = self.get_queryset().filter(read_at=None)
        if "notification" in request.POST:
            value = request.POST["notification"]
            if not value.isascii() or not value.isdecimal() or len(value) > 18:
                raise PermissionDenied
            queryset = queryset.filter(pk=int(value))
        queryset.update(read_at=timezone.now())
        return redirect("notifications")



@login_required
def badge(request, pk):
    import qrcode
    from qrcode.image.svg import SvgPathImage

    record = get_object_or_404(scoped(request.user, SECTIONS["participants"]),
                               pk=pk, status__in=models.Participant.BADGE_STATUSES)
    if record.event.status == models.Event.Status.CANCELLED:
        raise PermissionDenied
    url = request.build_absolute_uri(reverse("check-in", args=[record.badge_token]))
    image = qrcode.make(url, image_factory=SvgPathImage)
    return HttpResponse(image.to_string(), content_type="image/svg+xml",
                        headers={"Cache-Control": "private, no-store"})


@login_required
@transaction.atomic
def check_in(request, token):
    section = SECTIONS["participants"]
    if request.method not in {"GET", "POST", "HEAD"}:
        return HttpResponse(status=405, headers={"Allow": "GET, HEAD, POST"})
    if not allowed(request.user, section, "change") or request.user.role == models.Role.PARTICIPANT:
        raise PermissionDenied
    record = get_object_or_404(scoped(request.user, section), badge_token=token,
                               status__in=models.Participant.BADGE_STATUSES)
    if record.event.status == models.Event.Status.CANCELLED:
        raise PermissionDenied
    if request.method == "POST":
        previous = record.status
        if previous != models.Participant.Status.PRESENT:
            record.status = models.Participant.Status.PRESENT
            record.save(update_fields=["status"])
            record_changes(request.user, section, record, "Pointage QR", previous)
        messages.success(request, "La présence est enregistrée.")
        return redirect(section.url("detail", record.pk))
    return render(request, "gestion/check_in.html", {"title": "Contrôler un badge", "record": record})


def private_document(user, pk):
    participants = scoped(user, SECTIONS["participants"])
    return get_object_or_404(models.Document, pk=pk, participant__in=participants)


@login_required
@require_POST
@transaction.atomic
def upload_document(request, pk):
    section = SECTIONS["participants"]
    record = get_object_or_404(scoped(request.user, section), pk=pk)
    form = local_forms.DocumentForm(request.POST, request.FILES)
    if form.is_valid():
        file = form.cleaned_data["document"]
        models.Document.objects.create(participant=record, original_name=file.name,
                                       mime=form.mime, size=file.size, content=file.read())
        record_activity(request.user, section, pk, "Dépôt d’un document")
        messages.success(request, "Le document a été ajouté.")
    else:
        messages.error(request, " ".join(error for errors in form.errors.values() for error in errors))
    return redirect(section.url("detail", pk))


@login_required
def download_document(request, pk):
    from django.http import FileResponse

    document = private_document(request.user, pk)
    return FileResponse(io.BytesIO(document.content), as_attachment=True, filename=document.original_name,
                        content_type=document.mime, headers={"Cache-Control": "private, no-store",
                                                             "X-Content-Type-Options": "nosniff"})


@login_required
@require_POST
@transaction.atomic
def delete_document(request, pk):
    document = private_document(request.user, pk)
    participant_id = document.participant_id
    document.delete()
    record_activity(request.user, SECTIONS["participants"], participant_id, "Suppression d’un document")
    messages.success(request, "Le document a été supprimé.")
    return redirect(SECTIONS["participants"].url("detail", participant_id))

