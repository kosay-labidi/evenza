import re
from datetime import timedelta

from django.core import mail
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import models
from .modules import SECTIONS


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EvenzaTests(TestCase):
    password = "Carnaval-Lagon+2026"

    @classmethod
    def setUpTestData(cls):
        cls.admin = models.User.objects.create_superuser("admin@example.com", "Admin", cls.password)
        cls.organizer = models.User.objects.create_user("orga@example.com", "Organisateur", role=models.Role.ORGANIZER)
        cls.guest = models.User.objects.create_user("guest@example.com", "Invitée")
        cls.provider_user = models.User.objects.create_user("offre@example.com", "Partenaire", role=models.Role.PROVIDER)
        cls.customer = models.User.objects.create_user("client@example.com", "Cliente", role=models.Role.CLIENT)
        cls.start = (timezone.now() + timedelta(days=9)).replace(second=0, microsecond=0)
        cls.end = cls.start + timedelta(hours=4)
        cls.event = models.Event.objects.create(title="Gala Évenza", location="Tunis", start_at=cls.start,
                                                end_at=cls.end, capacity=8, organizer=cls.organizer,
                                                client=cls.customer, status=models.Event.Status.CONFIRMED)
        cls.provider = models.Provider.objects.create(name="Horizon", specialty="Photo", city="Tunis",
                                                      email="photo@example.com", user=cls.provider_user)
        cls.service = models.Service.objects.create(provider=cls.provider, name="Portraits", price=250)
        cls.resource = models.Resource.objects.create(name="Projecteurs", quantity=4)
        cls.registration = models.Participant.objects.create(
            event=cls.event, user=cls.guest, name=cls.guest.name, email=cls.guest.email,
            status=models.Participant.Status.CONFIRMED,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    @staticmethod
    def local(value):
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")

    def period(self, start=None, end=None):
        return {"start_at": self.local(start or self.start), "end_at": self.local(end or self.end)}

    def link(self, key, action="list", record=None):
        return SECTIONS[key].url(action, record.pk if record else None)

    def assert_crud(self, key, data, field, initial, updated):
        section = SECTIONS[key]
        create_url = self.link(key, "create")
        self.assertEqual(self.client.get(create_url).status_code, 200)
        response = self.client.post(create_url, data)
        self.assertRedirects(response, self.link(key))
        record = section.model.objects.get(**{field: initial})
        self.assertContains(self.client.get(self.link(key)), self.link(key, "detail", record))
        self.assertEqual(self.client.get(self.link(key, "detail", record)).status_code, 200)
        edit = self.link(key, "update", record)
        self.assertEqual(str(self.client.get(edit).context["form"][field].value()), str(initial))
        data[field] = updated
        if key == "users":
            data["password"] = ""
        self.assertRedirects(self.client.post(edit, data), self.link(key))
        record.refresh_from_db()
        self.assertEqual(str(getattr(record, field)), str(updated))
        delete = self.link(key, "delete", record)
        self.assertEqual(self.client.get(delete).status_code, 200)
        self.assertTrue(section.model.objects.filter(pk=record.pk).exists())
        self.assertRedirects(self.client.post(delete), self.link(key))
        self.assertFalse(section.model.objects.filter(pk=record.pk).exists())

    def test_crud_events(self):
        self.assert_crud("events", {"title": "Atelier photo", "location": "La Marsa", "capacity": 10,
                                    "budget": 50, "type": "Privé", "status": "Brouillon", **self.period()},
                         "title", "Atelier photo", "Atelier vidéo")

    def test_crud_users(self):
        self.assert_crud("users", {"name": "Compte test", "email": "nouveau@example.com",
                                   "role": "Client", "is_active": "on", "password": self.password},
                         "name", "Compte test", "Compte modifié")

    def test_crud_providers(self):
        self.assert_crud("providers", {"name": "Lumière", "specialty": "Traiteur", "city": "Tunis",
                                       "email": "chef@example.com", "status": "Disponible"},
                         "name", "Lumière", "Au soleil")

    def test_crud_programs(self):
        self.assert_crud("programs", {"event": self.event.pk, "title": "Petit déjeuner",
                                      "status": "Planifié", **self.period()},
                         "title", "Petit déjeuner", "Buffet")

    def test_crud_participants(self):
        self.assert_crud("participants", {"event": self.event.pk, "name": "Public",
                                           "email": "public@example.com", "category": "Invité", "status": "Inscrit"},
                         "name", "Public", "Public corrigé")

    def test_crud_resources(self):
        self.assert_crud("resources", {"name": "Chaises", "quantity": 20, "category": "Mobilier",
                                        "status": "Disponible"}, "name", "Chaises", "Fauteuils")

    def test_services_reservations_and_complaints(self):
        self.assert_crud("services", {"provider": self.provider.pk, "name": "Montage", "price": "19.50",
                                      "status": "Actif"}, "name", "Montage", "Retouches")
        self.assert_crud("reservations", {"event": self.event.pk, "service": self.service.pk,
                                          "amount": "21.50", "status": "En attente"}, "amount", "21.50", "42.50")
        self.assert_crud("complaints", {"participant": self.registration.pk, "subject": "Accès",
                                        "message": "Préciser l’entrée.", "status": "Ouverte"},
                         "subject", "Accès", "Entrée")

    def test_allocation_crud_and_capacity(self):
        data = {"event": self.event.pk, "resource": self.resource.pk, "status": "Affecté", **self.period()}
        self.assert_crud("allocations", {**data, "quantity": 2}, "quantity", 2, 3)
        self.assertRedirects(self.client.post(self.link("allocations", "create"), {**data, "quantity": 3}),
                             self.link("allocations"))
        response = self.client.post(self.link("allocations", "create"), {**data, "quantity": 2})
        self.assertFormError(response.context["form"], "quantity", "Quantité disponible sur tout ce créneau : 1.")
        response = self.client.post(self.link("resources", "update", self.resource),
                                    {"name": self.resource.name, "category": "Autre", "quantity": 2,
                                     "status": "Disponible"})
        self.assertFormError(response.context["form"], "quantity", "Cette quantité est inférieure au stock déjà affecté.")

    def test_allocation_uses_peak_concurrency_not_sum(self):
        mid = self.start + timedelta(hours=2)
        for start, end in [(self.start, mid), (mid, self.end)]:
            models.Allocation.objects.create(event=self.event, resource=self.resource, quantity=2,
                                             start_at=start, end_at=end)
        response = self.client.post(self.link("allocations", "create"), {
            "event": self.event.pk, "resource": self.resource.pk, "quantity": 2, "status": "Affecté", **self.period(),
        })
        self.assertRedirects(response, self.link("allocations"))
        response = self.client.get(self.link("resources", "detail", self.resource), self.period())
        self.assertEqual(response.context["available_quantity"], 0)
        self.assertContains(response, "Quantité disponible sur tout le créneau")

    def test_session_date_filter_ignores_exact_midnight_end(self):
        day = timezone.localtime(self.start).replace(hour=0, minute=0)
        for title, start, end in [("Veille", day - timedelta(hours=1), day),
                                  ("Matin", day, day + timedelta(hours=1))]:
            models.Program.objects.create(event=self.event, title=title, start_at=start, end_at=end)
        response = self.client.get(self.link("programs"), {"date": day.date().isoformat()})
        self.assertContains(response, "Matin")
        self.assertNotContains(response, "Veille")

    def test_invalid_dates_and_protected_delete(self):
        data = {"event": self.event.pk, "title": "Session", "status": "Planifié",
                **self.period(self.start - timedelta(hours=1), self.end)}
        response = self.client.post(self.link("programs", "create"), data)
        self.assertFormError(response.context["form"], None,
                             "Le créneau doit être compris dans les dates de l’événement.")
        response = self.client.post(self.link("events", "delete", self.event))
        self.assertContains(response, "Cette fiche est liée")
        self.assertTrue(models.Event.objects.filter(pk=self.event.pk).exists())

    def test_search_filters_pagination_and_csv(self):
        for i in range(14):
            models.Resource.objects.create(name=f"Photophore {i}", quantity=2)
        response = self.client.get(self.link("resources"), {"q": "photophore", "status": "Disponible"})
        self.assertEqual(response.context["paginator"].count, 14)
        self.assertEqual(len(response.context["rows"]), 12)
        self.assertEqual(self.client.get(self.link("resources"), {"q": "photophore", "page": 2})
                         .context["page_obj"].number, 2)
        response = self.client.get(self.link("resources"), {"q": "photophore", "export": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Photophore 13", response.content.decode())
        self.assertNotIn("Projecteurs", response.content.decode())

    def test_dashboard_real_data_and_navigation(self):
        start = timezone.now() - timedelta(days=1)
        models.Event.objects.create(title="Événement passé", start_at=start, end_at=start + timedelta(hours=1),
                                    location="Tunis", capacity=15)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, self.event.title)
        self.assertEqual(sum(response.context["chart_data"]["monthly"]), 1)
        self.assertEqual(sum(response.context["chart_data"]["totals"]), 2)
        for key in ("events", "providers", "users", "programs", "participants", "resources"):
            self.assertContains(response, self.link(key))

    def test_calendar_matches_scoped_event_date_filter(self):
        day = timezone.localtime(self.start).date()
        other = models.Event.objects.create(
            title="Événement hors de mon espace", start_at=self.start,
            end_at=self.end, location="Sousse", capacity=3,
        )
        url = reverse("dashboard")
        month = day.strftime("%Y-%m")
        date_url = f'{self.link("events")}?date={day}'
        self.assertContains(self.client.get(url, {"mois": month}), ", 2 événements")
        self.client.force_login(self.organizer)
        response = self.client.get(url, {"mois": month})
        self.assertContains(response, date_url)
        self.assertContains(response, ", 1 événement")
        self.assertNotContains(response, ", 2 événements")
        filtered = self.client.get(date_url)
        self.assertContains(filtered, self.event.title)
        self.assertNotContains(filtered, other.title)
        self.assertContains(self.client.get(url, {"mois": "10000-13"}), 'id="calendrier"')

    def test_dashboard_create_shortcut_matches_permissions(self):
        create_url = self.link("events", "create")
        self.assertContains(self.client.get(reverse("dashboard")), f'href="{create_url}"')
        self.client.force_login(self.guest)
        self.assertNotContains(self.client.get(reverse("dashboard")), f'href="{create_url}"')

    def test_providers_card_view_preserves_actions_and_filtered_export(self):
        response = self.client.get(self.link("providers"), {"vue": "cartes", "q": "Horizon"})
        self.assertContains(response, 'class="provider-card"')
        for action in ("detail", "update", "delete"):
            self.assertContains(response, self.link("providers", action, self.provider))
        export = self.client.get(self.link("providers"), {"vue": "cartes", "q": "Horizon", "export": "csv"})
        self.assertIn("Horizon", export.content.decode())

    def test_guest_permissions_and_scoped_relations(self):
        unrelated = models.Event.objects.create(
            title="Privé", location="Sfax", start_at=self.start, end_at=self.end, capacity=3,
        )
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(self.link("users")).status_code, 403)
        self.assertEqual(self.client.get(self.link("events", "detail", unrelated)).status_code, 404)
        self.assertEqual(self.client.get(self.link("events", "update", self.event)).status_code, 403)
        self.assertNotContains(self.client.get(self.link("events", "detail", self.event)), "Budget")
        response = self.client.post(self.link("participants", "create"), {"event": self.event.pk})
        self.assertFormError(response.context["form"], None, "Cette adresse est déjà inscrite à cet événement.")
        self.client.force_login(self.organizer)
        response = self.client.post(self.link("programs", "create"), {
            "event": unrelated.pk, "title": "Tentative", "status": "Planifié", **self.period(),
        })
        self.assertTrue(response.context["form"]["event"].errors)
        response = self.client.post(self.link("events", "create"), {
            "title": "Proposition", "status": "Confirmé", "type": "Privé", "capacity": 5, "budget": 0,
            "location": "Tunis", **self.period(),
        })
        self.assertTrue(response.context["form"]["status"].errors)

    def test_create_event_as_client_and_confirm_as_admin(self):
        self.client.force_login(self.customer)
        data = {"title": "Demande", "location": "Tunis", "capacity": 2, "budget": 0, "type": "Privé", **self.period()}
        self.assertRedirects(self.client.post(self.link("events", "create"), {**data, "status": "Confirmé"}),
                             self.link("events"))
        event = models.Event.objects.get(title="Demande")
        self.assertEqual(event.client, self.customer)
        self.assertEqual(event.status, models.Event.Status.DRAFT)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(self.link("events", "update", event), {**data, "status": "Confirmé"}),
                             self.link("events"))
        event.refresh_from_db()
        self.assertEqual(event.validator, self.admin)

    def test_participant_waitlist_and_cancellation(self):
        self.event.capacity = 1
        self.event.save(update_fields=["capacity"])
        other = models.User.objects.create_user("autre@example.com", "Autre")
        self.client.force_login(other)
        self.assertRedirects(self.client.post(self.link("participants", "create"), {"event": self.event.pk}),
                             self.link("participants"))
        waiting = models.Participant.objects.get(user=other)
        self.assertEqual(waiting.status, models.Participant.Status.WAITLIST)
        self.client.force_login(self.guest)
        self.assertRedirects(self.client.post(self.link("participants", "update", self.registration),
                                              {"status": "Annulé"}), self.link("participants"))
        self.assertTrue(self.guest.notifications.filter(message__contains="Annulé").exists())
        self.client.force_login(self.organizer)
        url = reverse("record-operation", args=["participants", waiting.pk, "promote"])
        self.assertRedirects(self.client.post(url), self.link("participants", "detail", waiting))
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, models.Participant.Status.REGISTERED)

    def test_participant_time_conflict(self):
        other = models.Event.objects.create(
            title="Autre événement", location="Tunis", start_at=self.start, end_at=self.end,
            capacity=10, status=models.Event.Status.CONFIRMED,
        )
        self.client.force_login(self.guest)
        response = self.client.post(self.link("participants", "create"), {"event": other.pk})
        self.assertFormError(response.context["form"], None,
                             "Cette personne est déjà inscrite à un événement sur le même créneau.")

    def test_invitation_requires_recipient_and_links_inscription(self):
        invitee = models.User.objects.create_user("invite@example.com", "Invité")
        record = models.Participant.objects.create(
            event=self.event, name=invitee.name, email=invitee.email, status=models.Participant.Status.INVITED,
        )
        self.client.force_login(self.organizer)
        self.client.post(reverse("record-operation", args=["participants", record.pk, "invite"]))
        self.assertEqual(mail.outbox[0].to, [invitee.email])
        token = signing.dumps({"pk": record.pk, "email": record.email}, salt="evenza-invitation")
        url = reverse("invitation", args=[token])
        self.client.force_login(self.guest)
        self.assertEqual(self.client.post(url, {"response": "confirm"}).status_code, 403)
        self.client.force_login(invitee)
        self.assertRedirects(self.client.post(url, {"response": "confirm"}), self.link("participants", "detail", record))
        record.refresh_from_db()
        self.assertEqual(record.user, invitee)
        self.assertEqual(record.status, models.Participant.Status.CONFIRMED)

    def test_provider_can_accept_but_cannot_change_amount(self):
        reservation = models.Reservation.objects.create(event=self.event, service=self.service, amount=50)
        self.client.force_login(self.provider_user)
        self.assertRedirects(self.client.post(self.link("reservations", "update", reservation),
                                              {"status": "Acceptée", "amount": 1}), self.link("reservations"))
        reservation.refresh_from_db()
        self.assertEqual(reservation.amount, 50)
        self.assertEqual(reservation.status, models.Reservation.Status.ACCEPTED)
        self.assertTrue(self.organizer.notifications.filter(message__contains="Acceptée").exists())
        self.assertEqual(self.client.get(self.link("resources")).status_code, 403)

    def test_suggestions_can_be_approved_once(self):
        self.client.force_login(self.organizer)
        response = self.client.post(self.link("suggestions", "create"), {
            "event": self.event.pk, "title": "Ouverture", **self.period(),
        })
        self.assertRedirects(response, self.link("suggestions"))
        record = models.Suggestion.objects.get()
        url = reverse("record-operation", args=["suggestions", record.pk, "approve"])
        self.assertRedirects(self.client.post(url), self.link("suggestions", "detail", record))
        self.assertEqual(self.client.post(url).status_code, 403)
        session = models.Program.objects.get(title=record.title)
        self.assertEqual(session.event, self.event)

    def test_private_documents_and_badge_checkin(self):
        self.client.force_login(self.guest)
        file = SimpleUploadedFile("programme.pdf", b"%PDF-1.4\ncontenu")
        url = reverse("upload-document", args=[self.registration.pk])
        self.assertRedirects(self.client.post(url, {"document": file}),
                             self.link("participants", "detail", self.registration))
        document = models.Document.objects.get()
        download = reverse("download-document", args=[document.pk])
        self.assertEqual(b"".join(self.client.get(download).streaming_content), b"%PDF-1.4\ncontenu")
        badge = self.client.get(reverse("badge", args=[self.registration.pk]))
        self.assertEqual(badge["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", badge.content)
        check = reverse("check-in", args=[self.registration.badge_token])
        self.assertEqual(self.client.post(check).status_code, 403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(download).status_code, 404)
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(check).status_code, 200)
        self.assertRedirects(self.client.post(check), self.link("participants", "detail", self.registration))
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, models.Participant.Status.PRESENT)

    def test_login_logout_signup_reset_and_csrf(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("login") + "?next=/")
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        self.assertRedirects(self.client.post(reverse("signup"), {
            "name": "Nouveau", "email": "Inscription@Example.com", "password": self.password, "role": "Administrateur",
        }), reverse("login"))
        new = models.User.objects.get(email="inscription@example.com")
        self.assertEqual(new.role, models.Role.PARTICIPANT)
        self.assertTrue(new.check_password(self.password))
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": "INSCRIPTION@example.com", "password": self.password,
        }), reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.assertRedirects(self.client.post(reverse("password_reset"), {"email": new.email}),
                             reverse("password_reset_done"))
        link = re.search(r"http://testserver(\S+)", mail.outbox[-1].body).group(1)
        response = self.client.get(link, follow=True)
        self.assertContains(response, "Définir un mot de passe")
        self.assertRedirects(self.client.post(response.redirect_chain[-1][0], {
            "new_password1": "Marais-Papillon+84", "new_password2": "Marais-Papillon+84",
        }), reverse("password_reset_complete"))
        new.refresh_from_db()
        self.assertTrue(new.check_password("Marais-Papillon+84"))
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.admin)
        self.assertEqual(protected.post(self.link("resources", "delete", self.resource)).status_code, 403)
        self.assertTrue(models.Resource.objects.filter(pk=self.resource.pk).exists())

    def test_login_attempt_alert_and_rate_limit(self):
        self.client.logout()
        for _ in range(10):
            response = self.client.post(reverse("login"), {"username": self.admin.email, "password": "wrong"})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("login"), {"username": self.admin.email, "password": self.password})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(models.LoginAttempt.objects.count(), 10)
        self.assertTrue(models.LoginAlert.objects.filter(email=self.admin.email).exists())

