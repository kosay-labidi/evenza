from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from utilisateurs.models import Utilisateur

from .models import Seance


class ProgrammesAccueilTests(TestCase):
    """Page d'entrée du module Programmes : accessible directement, limitée aux événements gérés."""

    @classmethod
    def setUpTestData(cls):
        cls.orga = Utilisateur.objects.create_user("orga", password="Mdp-12345!", role="ORGANISATEUR")
        autre = Utilisateur.objects.create_user("autre", password="Mdp-12345!", role="ORGANISATEUR")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="Conférence")
        d = timezone.now() + timedelta(days=2)
        kw = dict(categorie=cat, lieu=lieu, date_debut=d, date_fin=d + timedelta(hours=4), capacite=50)
        cls.e = Evenement.objects.create(titre="Forum IA", organisateur=cls.orga, **kw)
        e2 = Evenement.objects.create(titre="Forum voisin", organisateur=autre, **kw)
        Seance.objects.create(evenement=cls.e, titre="Ouverture", date=d)
        Seance.objects.create(evenement=e2, titre="Séance cachée", date=d)

    def test_accueil_liste_mes_evenements_et_seances(self):
        self.client.force_login(self.orga)
        r = self.client.get(reverse("programmes:index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Forum IA"); self.assertContains(r, "Ouverture")
        self.assertNotContains(r, "Forum voisin"); self.assertNotContains(r, "Séance cachée")
        self.assertContains(r, reverse("programmes:seance_creer", args=[self.e.pk]))

    def test_recherche(self):
        self.client.force_login(self.orga)
        r = self.client.get(reverse("programmes:index"), {"q": "rien"})
        self.assertNotContains(r, reverse("programmes:seance_creer", args=[self.e.pk]))


class ProgrammesPdfPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Utilisateur.objects.create_user("pdf-admin", password="Mdp-12345!", role="ADMIN")
        cls.orga = Utilisateur.objects.create_user("pdf-orga", password="Mdp-12345!", role="ORGANISATEUR")
        cls.participant = Utilisateur.objects.create_user("pdf-participant", password="Mdp-12345!", role="PARTICIPANT")
        cls.prestataire = Utilisateur.objects.create_user("pdf-prestataire", password="Mdp-12345!", role="PRESTATAIRE")
        cls.client_user = Utilisateur.objects.create_user("pdf-client", password="Mdp-12345!", role="CLIENT")
        lieu = Lieu.objects.create(nom="Salle PDF", adresse="1 rue", ville="Tunis", capacite=100)
        categorie = Categorie.objects.create(nom="PDF")
        debut = timezone.now() + timedelta(days=3)
        cls.evenement = Evenement.objects.create(
            titre="Programme public", categorie=categorie, lieu=lieu, organisateur=cls.orga,
            date_debut=debut, date_fin=debut + timedelta(hours=2), capacite=50,
            statut=Evenement.Statut.PUBLIE,
        )
        Seance.objects.create(evenement=cls.evenement, titre="Ouverture", date=debut, description="Lancement")
        cls.brouillon = Evenement.objects.create(
            titre="Programme privé", categorie=categorie, lieu=lieu, organisateur=cls.orga,
            date_debut=debut, date_fin=debut + timedelta(hours=2), capacite=50,
        )

    def test_pdf_public_exportable_par_tous_les_roles_et_visiteur(self):
        url = reverse("programmes:export_pdf", args=[self.evenement.pk])
        for user in (None, self.admin, self.orga, self.participant, self.prestataire, self.client_user):
            if user:
                self.client.force_login(user)
            else:
                self.client.logout()
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, getattr(user, "role", "visiteur"))
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF-"))
            self.assertTrue(response.content.rstrip().endswith(b"%%EOF"))

    def test_brouillon_reste_limite_a_son_organisateur_et_a_l_admin(self):
        url = reverse("programmes:export_pdf", args=[self.brouillon.pk])
        for user in (self.admin, self.orga):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 200)
        for user in (self.participant, self.prestataire, self.client_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 404)
