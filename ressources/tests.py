from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from evenements.models import Categorie, Evenement, Lieu
from utilisateurs.models import Utilisateur

from .models import Affectation, Ressource


class ConflitTests(TestCase):
    def test_conflit_detecte(self):
        org = Utilisateur.objects.create_user("o", password="x", role="ORGANISATEUR")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="C")
        d = timezone.now() + timedelta(days=3)
        e = Evenement.objects.create(titre="E", categorie=cat, lieu=lieu, organisateur=org,
                                     date_debut=d, date_fin=d + timedelta(hours=4), capacite=10)
        r = Ressource.objects.create(nom="Projecteur", type="MATERIEL", quantite=2)
        Affectation.objects.create(ressource=r, evenement=e, debut=d, fin=d + timedelta(hours=2), quantite=2)
        a = Affectation(ressource=r, evenement=e, debut=d + timedelta(hours=1), fin=d + timedelta(hours=3), quantite=1)
        with self.assertRaises(ValidationError):
            a.full_clean()


class CrudRessourcesTests(TestCase):
    """Ressource : détail / modification / suppression ; Affectation : liste / modification / suppression."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Utilisateur.objects.create_user("org", password="x", role="ORGANISATEUR")
        cls.autre = Utilisateur.objects.create_user("autre", password="x", role="ORGANISATEUR")
        cls.part = Utilisateur.objects.create_user("part", password="x", role="PARTICIPANT")
        cls.admin = Utilisateur.objects.create_user("adm", password="x", role="ADMIN")
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=100)
        cat = Categorie.objects.create(nom="C")
        cls.d = d = timezone.now() + timedelta(days=3)
        cls.evt = Evenement.objects.create(titre="Mon gala", categorie=cat, lieu=lieu, organisateur=cls.org,
                                           date_debut=d, date_fin=d + timedelta(hours=4), capacite=10)
        cls.evt2 = Evenement.objects.create(titre="Gala voisin", categorie=cat, lieu=lieu, organisateur=cls.autre,
                                            date_debut=d, date_fin=d + timedelta(hours=4), capacite=10)
        cls.ecran = Ressource.objects.create(nom="Écran", type="MATERIEL", quantite=2)
        cls.libre = Ressource.objects.create(nom="Minibus", type="VEHICULE", quantite=1)
        cls.aff = Affectation.objects.create(ressource=cls.ecran, evenement=cls.evt, debut=d, fin=d + timedelta(hours=2), quantite=1)
        cls.aff2 = Affectation.objects.create(ressource=cls.ecran, evenement=cls.evt2, debut=d, fin=d + timedelta(hours=2), quantite=1)

    def url(self, nom, *args):
        from django.urls import reverse
        return reverse(f"ressources:{nom}", args=args)

    def msgs(self, r):
        from django.contrib.messages import get_messages
        return [str(m) for m in get_messages(r.wsgi_request)]

    def test_permissions(self):
        pages = [self.url("detail", self.ecran.pk), self.url("modifier", self.ecran.pk),
                 self.url("supprimer", self.ecran.pk), self.url("affectations"),
                 self.url("affectation_modifier", self.aff.pk), self.url("affectation_supprimer", self.aff.pk)]
        self.client.force_login(self.part)
        for p in pages:
            self.assertEqual(self.client.get(p).status_code, 403, p)
        self.client.force_login(self.org)
        for p in pages:
            self.assertEqual(self.client.get(p).status_code, 200, p)
        # un organisateur ne touche pas aux affectations d'un événement qui n'est pas le sien
        self.client.force_login(self.autre)
        self.assertEqual(self.client.get(self.url("affectation_modifier", self.aff.pk)).status_code, 403)
        self.assertEqual(self.client.post(self.url("affectation_supprimer", self.aff.pk)).status_code, 403)
        self.assertTrue(Affectation.objects.filter(pk=self.aff.pk).exists())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url("affectation_modifier", self.aff.pk)).status_code, 200)

    def test_detail_ressource(self):
        self.client.force_login(self.org)
        r = self.client.get(self.url("detail", self.ecran.pk))
        self.assertContains(r, "Mon gala"); self.assertContains(r, "Gala voisin")

    def test_modification_ressource(self):
        self.client.force_login(self.org)
        r = self.client.post(self.url("modifier", self.ecran.pk), {"nom": "Écran géant", "type": "MATERIEL", "quantite": 3})
        self.assertRedirects(r, self.url("detail", self.ecran.pk))
        self.ecran.refresh_from_db(); self.assertEqual((self.ecran.nom, self.ecran.quantite), ("Écran géant", 3))
        self.assertIn("La ressource « Écran géant » a été modifiée.", self.msgs(r))

    def test_suppression_ressource_libre(self):
        self.client.force_login(self.org)
        r = self.client.post(self.url("supprimer", self.libre.pk))
        self.assertRedirects(r, self.url("liste"))
        self.assertFalse(Ressource.objects.filter(pk=self.libre.pk).exists())
        self.assertIn("« Minibus ×1 » a été supprimé.", self.msgs(r))

    def test_suppression_ressource_protegee(self):
        """Ressource encore affectée (PROTECT) : message clair, pas d'erreur 500."""
        self.client.force_login(self.org)
        self.assertContains(self.client.get(self.url("supprimer", self.ecran.pk)), "la suppression sera refusée")
        r = self.client.post(self.url("supprimer", self.ecran.pk))
        self.assertRedirects(r, self.url("detail", self.ecran.pk))
        self.assertTrue(Ressource.objects.filter(pk=self.ecran.pk).exists())
        self.assertTrue(any(m.startswith("Impossible de supprimer « Écran ×2 »") for m in self.msgs(r)))

    def test_liste_affectations_filtree(self):
        self.client.force_login(self.org)
        r = self.client.get(self.url("affectations"))
        self.assertEqual(list(r.context["object_list"]), [self.aff])        # seulement ses événements
        self.client.force_login(self.admin)
        self.assertEqual(len(self.client.get(self.url("affectations")).context["object_list"]), 2)

    def test_modification_affectation_et_conflit(self):
        self.client.force_login(self.org)
        fmt = "%Y-%m-%dT%H:%M"
        data = {"ressource": self.ecran.pk, "debut": timezone.localtime(self.d).strftime(fmt),
                "fin": timezone.localtime(self.d + timedelta(hours=2)).strftime(fmt)}
        # 2 écrans demandés alors que l'événement voisin en utilise déjà 1 sur ce créneau → refus
        r = self.client.post(self.url("affectation_modifier", self.aff.pk), {**data, "quantite": 2})
        self.assertContains(r, "Conflit")
        self.aff.refresh_from_db(); self.assertEqual(self.aff.quantite, 1)
        # en restant à 1 (sa propre ligne n'est pas comptée) → accepté
        r = self.client.post(self.url("affectation_modifier", self.aff.pk), {**data, "quantite": 1, "fin": timezone.localtime(self.d + timedelta(hours=3)).strftime(fmt)})
        self.assertRedirects(r, self.evt.get_absolute_url())
        self.assertIn("Affectation modifiée sans conflit.", self.msgs(r))

    def test_suppression_affectation(self):
        self.client.force_login(self.org)
        r = self.client.post(self.url("affectation_supprimer", self.aff.pk))
        self.assertRedirects(r, self.evt.get_absolute_url())
        self.assertFalse(Affectation.objects.filter(pk=self.aff.pk).exists())
        self.assertTrue(any("a été supprimée" in m for m in self.msgs(r)))
