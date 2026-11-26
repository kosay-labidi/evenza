from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from utilisateurs.models import Utilisateur

from .models import Categorie, Evenement, Lieu


class EvenementTests(TestCase):
    def setUp(self):
        self.org = Utilisateur.objects.create_user("org", password="Test12345!", role="ORGANISATEUR")
        self.part = Utilisateur.objects.create_user("part", password="Test12345!", role="PARTICIPANT")
        self.lieu = Lieu.objects.create(nom="Salle", adresse="Rue 1", ville="Tunis", capacite=100)
        self.cat = Categorie.objects.create(nom="Concert")
        d = timezone.now() + timedelta(days=10)
        self.e = Evenement.objects.create(titre="Test", categorie=self.cat, lieu=self.lieu, organisateur=self.org,
                                          date_debut=d, date_fin=d + timedelta(hours=3), capacite=50)

    def test_date_fin_apres_debut(self):
        self.e.date_fin = self.e.date_debut - timedelta(hours=1)
        with self.assertRaises(ValidationError):
            self.e.full_clean()

    def test_capacite_limitee_par_lieu(self):
        self.e.capacite = 500
        with self.assertRaises(ValidationError):
            self.e.full_clean()

    def test_brouillon_absent_du_catalogue(self):
        r = self.client.get(reverse("evenements:liste"))
        self.assertNotContains(r, "Test")
        self.e.publier()
        r = self.client.get(reverse("evenements:liste"))
        self.assertContains(r, "Test")

    def test_participant_ne_peut_pas_creer(self):
        self.client.login(username="part", password="Test12345!")
        r = self.client.get(reverse("evenements:creer"))
        self.assertEqual(r.status_code, 403)

    def test_organisateur_cree(self):
        self.client.login(username="org", password="Test12345!")
        r = self.client.get(reverse("evenements:creer"))
        self.assertEqual(r.status_code, 200)

    def test_gerer_depuis_mes_evenements_ouvre_le_bon_programme(self):
        self.client.force_login(self.org)
        response = self.client.get(reverse("evenements:mes_evenements"))
        self.assertContains(response, f'href="{self.e.get_absolute_url()}">Gérer')
        self.assertNotContains(response, f'{self.e.get_absolute_url()}?sans_programmes=1')
        detail = self.client.get(self.e.get_absolute_url())
        self.assertEqual(detail.context["object"].pk, self.e.pk)
        self.assertContains(detail, 'id="programme-timeline"')

    def test_menu_accueil_sans_programmes_conserve_les_autres_modules(self):
        self.client.force_login(self.org)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, 'href="/programmes/"')
        for url_name in ("evenements:mes_evenements", "participants:index", "prestataires:liste", "ressources:liste"):
            self.assertContains(response, f'href="{reverse(url_name)}"')


class RechercheTests(TestCase):
    """Recherche de l'accueil : ville et date, en plus du mot-clé et de la catégorie."""
    def setUp(self):
        org = Utilisateur.objects.create_user("org2", password="Test12345!", role="ORGANISATEUR")
        cat = Categorie.objects.create(nom="Gala")
        tunis = Lieu.objects.create(nom="Théâtre", adresse="Rue 1", ville="Tunis", capacite=500)
        sousse = Lieu.objects.create(nom="Palais", adresse="Rue 2", ville="Sousse", capacite=500)
        d = timezone.now() + timedelta(days=5)
        for titre, lieu, decal in [("Soirée Tunis", tunis, 0), ("Forum Sousse", sousse, 20)]:
            e = Evenement.objects.create(titre=titre, categorie=cat, lieu=lieu, organisateur=org,
                                         date_debut=d + timedelta(days=decal), date_fin=d + timedelta(days=decal, hours=3), capacite=100)
            e.publier()
        self.limite = (d + timedelta(days=10)).date().isoformat()

    def test_filtre_ville(self):
        r = self.client.get(reverse("evenements:liste"), {"ville": "Sousse"})
        self.assertContains(r, "Forum Sousse"); self.assertNotContains(r, "Soirée Tunis")

    def test_filtre_date(self):
        r = self.client.get(reverse("evenements:liste"), {"date": self.limite})
        self.assertContains(r, "Forum Sousse"); self.assertNotContains(r, "Soirée Tunis")

    def test_date_invalide_ignoree(self):
        r = self.client.get(reverse("evenements:liste"), {"date": "pas-une-date"})
        self.assertEqual(r.status_code, 200); self.assertContains(r, "Soirée Tunis")

    def test_accueil_maison_editoriale(self):
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, 'id="mx-titre"')       # titre du hero (cible du focus après l'intro)
        self.assertContains(r, "Des instants précieux")
        self.assertContains(r, 'id="intro"')          # intro présente mais cachée par défaut
        self.assertContains(r, 'name="ville"')
        self.assertEqual(len(r.context["affiche"]), 2)
        # la galerie ne montre que des événements publiés réels, liés à leur page
        self.assertEqual(len(r.context["galerie"]), 2)
        for e in r.context["galerie"]:
            self.assertContains(r, f'href="{e.get_absolute_url()}"')


class CorrectionsEvenementTests(TestCase):
    def setUp(self):
        self.org = Utilisateur.objects.create_user("org", password="Test12345!", role="ORGANISATEUR")
        self.autre = Utilisateur.objects.create_user("autre", password="Test12345!", role="PARTICIPANT")
        self.lieu = Lieu.objects.create(nom="Salle", adresse="Rue 1", ville="Tunis", capacite=100)
        self.cat = Categorie.objects.create(nom="Concert")
        d = timezone.now() + timedelta(days=10)
        self.e = Evenement.objects.create(titre="Brouillon secret", categorie=self.cat, lieu=self.lieu,
                                          organisateur=self.org, date_debut=d, date_fin=d + timedelta(hours=3),
                                          capacite=50)

    def test_brouillon_invisible_pour_anonyme_et_autres(self):
        url = reverse("evenements:detail", args=[self.e.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.login(username="autre", password="Test12345!")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_brouillon_visible_pour_son_organisateur(self):
        self.client.login(username="org", password="Test12345!")
        url = reverse("evenements:detail", args=[self.e.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="programme-timeline"')
        response = self.client.get(url, {"sans_programmes": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="programme-timeline"')

        self.assertContains(response, "À propos")

    def test_suppression_refusee_avec_reservations(self):
        from participants.models import Inscription
        self.e.publier()
        Inscription.inscrire(self.e, self.autre)
        self.client.login(username="org", password="Test12345!")
        self.client.post(reverse("evenements:supprimer", args=[self.e.pk]))
        self.assertTrue(Evenement.objects.filter(pk=self.e.pk).exists())

    def test_capacite_pas_sous_les_inscrits(self):
        from participants.models import Inscription
        self.e.publier()
        Inscription.inscrire(self.e, self.autre, quantite=3)
        self.e.capacite = 2
        with self.assertRaises(ValidationError):
            self.e.full_clean()

    def test_date_debut_passee_refusee_a_la_creation(self):
        from .forms import EvenementForm
        d = timezone.localtime() - timedelta(days=1)
        form = EvenementForm(data={"titre": "T", "categorie": self.cat.pk, "lieu": self.lieu.pk,
                                   "date_debut": d.strftime("%Y-%m-%dT%H:%M"),
                                   "date_fin": (d + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                                   "capacite": 10, "prix": 0})
        self.assertFalse(form.is_valid())
        self.assertIn("date_debut", form.errors)


class ScenePageTests(EvenementTests):
    """Page « Mes événements » (scène 3D) : rendu serveur avec les vraies données."""

    def test_page_organisateur_affiche_evenement_et_chiffres(self):
        from participants.models import Inscription
        self.e.publier()
        Inscription.objects.create(evenement=self.e, participant=self.part, quantite=2, montant=40)
        self.client.login(username="org", password="Test12345!")
        r = self.client.get(reverse("evenements:mes_evenements"))
        self.assertContains(r, "es-card")
        self.assertContains(r, "Test")
        self.assertContains(r, 'data-n="2"')      # inscrits
        self.assertContains(r, "40 DT")           # recettes

    def test_page_sans_evenement(self):
        Evenement.objects.all().delete()
        self.client.login(username="org", password="Test12345!")
        self.assertContains(self.client.get(reverse("evenements:mes_evenements")), "Créez le premier")

    def test_participant_refuse(self):
        self.client.login(username="part", password="Test12345!")
        self.assertNotEqual(self.client.get(reverse("evenements:mes_evenements")).status_code, 200)
