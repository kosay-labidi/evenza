"""Intégrité des comptes : contrainte d'unicité de l'e-mail en base (C10) et opérations concurrentes (C09).

La concurrence RÉELLE (deux requêtes simultanées, base SQLite sur fichier) est démontrée par la suite
d'audit hors projet ; ici on vérifie de façon déterministe chacun des maillons qu'elle utilise."""
from unittest import mock

from django.contrib import admin
from django.contrib.auth import SESSION_KEY
from django.core.cache import cache
from django.db import IntegrityError, OperationalError, connection, transaction
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .forms import MSG_EMAIL_PRIS
from .models import Utilisateur
from .tests import donnees_inscription

MDP = "Mdp-Integrite-2026!"
CONCURRENT = "Une autre modification de compte est en cours"


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Utilisateur.objects.create_user("chef", "chef@ex.tn", MDP, role="ADMIN")
        cls.admin2 = Utilisateur.objects.create_user("adjoint", "adjoint@ex.tn", MDP, role="ADMIN")
        cls.part = Utilisateur.objects.create_user("part", "part@ex.tn", MDP, role="PARTICIPANT")

    def setUp(self):
        cache.clear()

    def msgs(self, r):
        from django.contrib.messages import get_messages
        return [str(m) for m in get_messages(r.wsgi_request)]


def sans_controles_applicatifs():
    """Simule une requête concurrente gagnante : les contrôles du formulaire voient l'e-mail libre,
    seule la base peut encore refuser (chemin IntegrityError)."""
    return [mock.patch("utilisateurs.forms.email_deja_utilise", return_value=False),
            mock.patch.object(Utilisateur, "validate_constraints", return_value=None)]


class ContrainteEmailTests(Base):
    def test_base_refuse_un_doublon_quelle_que_soit_la_casse(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Utilisateur.objects.create_user("autre", "PART@EX.TN", MDP)

    def test_emails_vides_multiples_permis(self):
        Utilisateur.objects.create_user("v1", "", MDP)
        Utilisateur.objects.create_user("v2", "", MDP)
        self.assertEqual(Utilisateur.objects.filter(email="").count(), 2)

    def test_contrainte_declaree_dans_la_base(self):
        with connection.cursor() as c:
            noms = connection.introspection.get_constraints(c, Utilisateur._meta.db_table)
        self.assertIn("utilisateur_email_unique_insensible_casse", noms)
        self.assertTrue(noms["utilisateur_email_unique_insensible_casse"]["unique"])

    def test_validation_django_de_la_contrainte_rattachee_au_champ_email(self):
        """Contrôle applicatif contourné : la validation des contraintes du modèle prend le relais."""
        from .forms import InscriptionCompteForm
        with mock.patch("utilisateurs.forms.email_deja_utilise", return_value=False):
            f = InscriptionCompteForm(donnees_inscription(email="Part@Ex.Tn"))
            self.assertFalse(f.is_valid())
        self.assertEqual(f.errors["email"], [MSG_EMAIL_PRIS])
        self.assertNotIn("__all__", f.errors)

    def test_verification_prealable_de_la_migration(self):
        """Sans doublon, la vérification passe (le cas « doublon présent » est testé sur une copie de base)."""
        from importlib import import_module
        from django.apps import apps
        verifier = import_module("utilisateurs.migrations.0002_email_unique_insensible_casse").verifier_absence_de_doublons
        verifier(apps, mock.Mock(connection=connection))


class IntegrityErrorVuesTests(Base):
    """Chaque vue qui enregistre un e-mail transforme l'IntegrityError en erreur de formulaire (pas de 500)."""

    def poster(self, url, data, user=None):
        c = Client()
        if user:
            c.force_login(user)
        patches = sans_controles_applicatifs()
        for p in patches:
            p.start()
        try:
            return c, c.post(url, data)
        finally:
            for p in patches:
                p.stop()

    def test_inscription(self):
        n = Utilisateur.objects.count()
        c, r = self.poster(reverse("utilisateurs:register"), donnees_inscription(email="PART@ex.tn"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"].errors["email"], [MSG_EMAIL_PRIS])
        self.assertEqual(Utilisateur.objects.count(), n)
        self.assertNotIn(SESSION_KEY, c.session)                         # aucune connexion automatique

    def test_profil(self):
        _, r = self.poster(reverse("utilisateurs:profil"),
                           {"first_name": "Nour", "last_name": "T", "email": "CHEF@ex.tn", "telephone": ""}, self.part)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"].errors["email"], [MSG_EMAIL_PRIS])
        self.part.refresh_from_db()
        self.assertEqual(self.part.email, "part@ex.tn")

    def test_creation_et_modification_par_l_admin(self):
        _, r = self.poster(reverse("utilisateurs:utilisateur_creer"), {
            "username": "nouveau", "email": "Part@ex.tn", "role": "CLIENT", "is_active": "on",
            "password1": "Lune-Orage-71", "password2": "Lune-Orage-71"}, self.admin)
        self.assertEqual(r.context["form"].errors["email"], [MSG_EMAIL_PRIS])
        self.assertFalse(Utilisateur.objects.filter(username="nouveau").exists())
        _, r = self.poster(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                           {"username": "part", "email": "chef@EX.tn", "role": "PARTICIPANT"}, self.admin)
        self.assertEqual(r.context["form"].errors["email"], [MSG_EMAIL_PRIS])
        self.part.refresh_from_db()
        self.assertEqual(self.part.email, "part@ex.tn")

    def test_admin_django(self):
        root = Utilisateur.objects.create_superuser("root", "root@ex.tn", MDP)
        c = Client(); c.force_login(root)
        url = reverse("admin:utilisateurs_utilisateur_change", args=[self.part.pk])
        with mock.patch.object(admin.site._registry[Utilisateur], "save_model",
                               side_effect=IntegrityError("UNIQUE constraint failed")):
            r = c.post(url, {"username": "part", "email": "part@ex.tn", "role": "PARTICIPANT", "is_active": "on",
                             "date_joined_0": "2026-01-01", "date_joined_1": "00:00:00"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(any("Enregistrement annulé" in m for m in self.msgs(r)))


class VerrouConcurrenceTests(Base):
    """C09 : verrou pris AVANT toute lecture ; dépassement du délai traité proprement."""

    def test_verrou_sqlite_est_une_ecriture_en_tete_de_transaction(self):
        from .views import verrouiller_admins
        with CaptureQueriesContext(connection) as q, transaction.atomic():
            verrouiller_admins()
        sql = [x["sql"].lstrip().upper() for x in q.captured_queries if not x["sql"].upper().startswith(("SAVEPOINT", "RELEASE"))]
        if connection.vendor == "sqlite":
            self.assertTrue(sql[0].startswith("UPDATE"), sql[0])
        else:
            self.assertIn("FOR UPDATE", sql[0])

    def test_verrou_ne_change_aucune_donnee(self):
        from .views import verrouiller_admins
        avant = list(Utilisateur.objects.values_list("pk", "is_active", "role", "email").order_by("pk"))
        with transaction.atomic():
            verrouiller_admins()
        self.assertEqual(list(Utilisateur.objects.values_list("pk", "is_active", "role", "email").order_by("pk")), avant)

    def test_verrou_avant_le_controle_dans_chaque_operation(self):
        """Dans désactivation, modification et suppression, le premier ordre SQL de la transaction est le verrou."""
        c = Client(); c.force_login(self.admin)
        cas = [(reverse("utilisateurs:utilisateur_desactiver", args=[self.part.pk]), {}),
               (reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                {"username": "part", "email": "part@ex.tn", "role": "CLIENT"}),
               (reverse("utilisateurs:utilisateur_supprimer", args=[self.admin2.pk]), {})]
        for url, data in cas:
            with CaptureQueriesContext(connection) as q:
                c.post(url, data)
            sql = [x["sql"].upper() for x in q.captured_queries]
            # instruction de verrouillage : écriture neutre (SQLite) ou SELECT … FOR UPDATE (autres moteurs)
            est_verrou = (lambda s: s.startswith('UPDATE "UTILISATEURS_UTILISATEUR" SET "IS_ACTIVE" = ')
                          or "FOR UPDATE" in s)
            i = next((k for k, s in enumerate(sql) if est_verrou(s)), None)
            self.assertIsNotNone(i, f"{url} : aucun verrou")
            self.assertTrue(sql[i - 1].startswith("SAVEPOINT"), f"{url} : le verrou n'ouvre pas la transaction")
            # rien n'est écrit sur le compte visé avant le verrou
            self.assertFalse(any(s.startswith(("UPDATE", "DELETE")) for s in sql[:i]), f"{url} : écriture avant verrou")

    def test_delai_depasse_message_propre(self):
        c = Client(); c.force_login(self.admin)
        with mock.patch("utilisateurs.views.verrouiller_admins", side_effect=OperationalError("database is locked")):
            r = c.post(reverse("utilisateurs:utilisateur_desactiver", args=[self.part.pk]))
            self.assertEqual(r.status_code, 302)
            self.assertTrue(any(CONCURRENT in m for m in self.msgs(r)))
            r = c.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                       {"username": "part", "email": "part@ex.tn", "role": "CLIENT"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(any(CONCURRENT in e for e in r.context["form"].non_field_errors()))
            r = c.post(reverse("utilisateurs:utilisateur_supprimer", args=[self.part.pk]))
            self.assertEqual(r.status_code, 302)
            self.assertTrue(any(CONCURRENT in m for m in self.msgs(r)))
        self.part.refresh_from_db()
        self.assertEqual((self.part.is_active, self.part.role), (True, "PARTICIPANT"))
