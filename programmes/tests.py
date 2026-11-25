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
        Seance.objects.create(evenement=cls.e, titre="Ouverture", debut=d, fin=d + timedelta(hours=1))
        Seance.objects.create(evenement=e2, titre="Séance cachée", debut=d, fin=d + timedelta(hours=1))

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
