import os
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

old_name = "0002_alter_allocation_status_alter_complaint_status_and_more"
backup = sorted(Path("backups").glob("evenza-avant-refactorisation-*.sqlite3"))[-1]
probe = Path(".dependency-download") / f"architecture-rehearsal-{uuid4().hex[:8]}.sqlite3"
assert not probe.exists()
with sqlite3.connect(backup) as source, sqlite3.connect(probe) as target:
    source.backup(target)

os.environ["DJANGO_DB_PATH"] = str(probe.resolve())
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django
django.setup()
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

history = MigrationExecutor(connection).loader.project_state([
    ("gestion", old_name), ("admin", "0003_logentry_add_action_flag_choices"), ("sessions", "0001_initial"),
]).apps
model = lambda name: history.get_model("gestion", name)
ct = history.get_model("contenttypes", "ContentType")
permission = history.get_model("auth", "Permission")
group = history.get_model("auth", "Group")
log = history.get_model("admin", "LogEntry")
user = model("User").objects.create(name="Architecture QA", email="arch-qa@example.test")
start = timezone.now() + timedelta(days=30)
end = start + timedelta(hours=2)
event = model("Event").objects.create(title="Migration QA", location="Tunis", start_at=start, end_at=end, capacity=3)
provider = model("Provider").objects.create(name="Provider QA", specialty="QA", city="Tunis", email="provider@example.test")
service = model("Service").objects.create(provider=provider, name="Service QA", price=100)
model("Reservation").objects.create(event=event, service=service)
program = model("Program").objects.create(event=event, title="Program QA", start_at=start, end_at=end)
model("Suggestion").objects.create(event=event, title="Suggestion QA", start_at=start, end_at=end)
participant = model("Participant").objects.create(user=user, event=event, name=user.name, email=user.email)
model("Document").objects.create(participant=participant, original_name="qa.pdf", mime="application/pdf", size=4, content=b"%PDF")
model("Complaint").objects.create(participant=participant, subject="QA", message="QA")
resource = model("Resource").objects.create(name="Resource QA", quantity=5)
model("Allocation").objects.create(event=event, resource=resource, start_at=start, end_at=end, quantity=2)
model("Notification").objects.create(user=user, message="QA")
model("Activity").objects.create(user=user, entity="events", record_id=event.pk, action="QA")
model("LoginAlert").objects.create(email=user.email)
model("LoginAttempt").objects.create(email=user.email, success=True)
event_ct = ct.objects.get(app_label="gestion", model="event")
event_permission = permission.objects.get(content_type=event_ct, codename="view_event")
team = group.objects.create(name="Architecture QA")
team.permissions.add(event_permission)
user.groups.add(team)
user.user_permissions.add(event_permission)
log.objects.create(user=user, content_type=event_ct, object_id=str(event.pk), object_repr="Migration QA", action_flag=1)

def snapshot():
    with sqlite3.connect(probe) as database:
        assert database.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert not database.execute("PRAGMA foreign_key_check").fetchall()
        schema = database.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        tables = {name for kind, name, _, _ in schema if kind == "table"}
        excluded = {"django_migrations", "django_content_type", "sqlite_sequence"}
        rows = {table: database.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
                for table in tables - excluded}
        types = database.execute("SELECT id, app_label, model FROM django_content_type ORDER BY id").fetchall()
        sequences = database.execute("SELECT name, seq FROM sqlite_sequence WHERE name <> 'django_migrations' ORDER BY name").fetchall()
    return schema, rows, types, sequences

original = snapshot()
label_by_model = {
    "event": "evenements", "provider": "prestataires", "service": "prestataires", "reservation": "prestataires",
    "program": "programmes", "suggestion": "programmes", "participant": "participants", "document": "participants",
    "complaint": "participants", "resource": "ressources", "allocation": "ressources", "notification": "accounts",
    "loginattempt": "accounts", "loginalert": "accounts", "activity": "dashboard",
}
expected_types = [(pk, label_by_model.get(name, label) if label == "gestion" else label, name)
                  for pk, label, name in original[2]]
for phase in ("forward", "backward", "forward-again"):
    if phase == "backward":
        call_command("migrate", "gestion", old_name, interactive=False, verbosity=0)
    else:
        call_command("migrate", interactive=False, verbosity=0)
    current = snapshot()
    assert current[0] == original[0], f"SQL schema changed: {phase}"
    assert current[1] == original[1], f"Rows changed: {phase}"
    assert current[2] == (original[2] if phase == "backward" else expected_types), f"Content type identity changed: {phase}"
    assert current[3] == original[3], f"Sequences changed: {phase}"
    if phase != "backward":
        from django.contrib.auth import get_user_model
        from django.contrib.admin.models import LogEntry
        from apps.evenements.models import Event
        from apps.participants.models import Document

        live_user = get_user_model().objects.get(pk=user.pk)
        assert live_user.has_perm("evenements.view_event")
        assert live_user.groups.get().permissions.get().pk == event_permission.pk
        assert live_user.user_permissions.get().pk == event_permission.pk
        assert LogEntry.objects.get(user=live_user).content_type_id == event_ct.pk
        assert LogEntry.objects.get(user=live_user).get_edited_object() == Event.objects.get(pk=event.pk)
        assert bytes(Document.objects.get(participant_id=participant.pk).content) == b"%PDF"
    print(f"{phase}: schema, business rows, sequences, permission and content type IDs preserved")

