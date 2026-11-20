from unittest import mock

from django.contrib.messages import get_messages
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import Utilisateur


class CrudUtilisateursTests(TestCase):
    """CRUD des utilisateurs : réservé à l'administrateur."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = Utilisateur.objects.create_user("chef", "chef@ex.tn", "Mdp-12345!", role="ADMIN")
        cls.orga = Utilisateur.objects.create_user("orga", "orga@ex.tn", "Mdp-12345!", role="ORGANISATEUR")
        cls.part = Utilisateur.objects.create_user("part", "part@ex.tn", "Mdp-12345!", role="PARTICIPANT")

    def msgs(self, r):
        return [str(m) for m in get_messages(r.wsgi_request)]

    def test_reserve_admin(self):
        urls = [reverse("utilisateurs:utilisateur_liste"), reverse("utilisateurs:utilisateur_creer"),
                reverse("utilisateurs:utilisateur_detail", args=[self.part.pk]),
                reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                reverse("utilisateurs:utilisateur_supprimer", args=[self.part.pk])]
        for u in (self.orga, self.part):
            self.client.force_login(u)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, url)
        self.client.logout()
        self.assertEqual(self.client.get(urls[0]).status_code, 302)   # anonyme → connexion
        self.client.force_login(self.admin)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_liste_et_filtre(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("utilisateurs:utilisateur_liste"), {"role": "ORGANISATEUR"})
        self.assertContains(r, "orga"); self.assertNotContains(r, ">part<")

    def test_ajout(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_creer"), {
            "username": "nouveau", "first_name": "Ali", "last_name": "B", "email": "n@ex.tn", "telephone": "",
            "role": "PRESTATAIRE", "is_active": "on", "password1": "Tres-Secret-42", "password2": "Tres-Secret-42"})
        u = Utilisateur.objects.get(username="nouveau")
        self.assertRedirects(r, reverse("utilisateurs:utilisateur_detail", args=[u.pk]))
        self.assertEqual(u.role, "PRESTATAIRE"); self.assertTrue(u.check_password("Tres-Secret-42"))
        self.assertIn("Le compte « nouveau » a été créé.", self.msgs(r))

    def test_email_unique(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]), {
            "username": "part", "email": "orga@ex.tn", "role": "PARTICIPANT", "is_active": "on"})
        self.assertContains(r, "Un compte utilise déjà cette adresse e-mail.")

    def test_modification(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]), {
            "username": "part", "first_name": "Sara", "last_name": "", "email": "part@ex.tn", "telephone": "",
            "role": "ORGANISATEUR"})   # case « actif » décochée
        self.part.refresh_from_db()
        self.assertEqual((self.part.first_name, self.part.role, self.part.is_active), ("Sara", "ORGANISATEUR", False))
        self.assertIn("Le compte « part » a été modifié.", self.msgs(r))

    def test_suppression(self):
        self.client.force_login(self.admin)
        url = reverse("utilisateurs:utilisateur_supprimer", args=[self.part.pk])
        self.assertContains(self.client.get(url), "Cette action est définitive")
        r = self.client.post(url)
        self.assertRedirects(r, reverse("utilisateurs:utilisateur_liste"))
        self.assertFalse(Utilisateur.objects.filter(pk=self.part.pk).exists())
        self.assertIn("« part » a été supprimé.", self.msgs(r))

    def test_pas_sa_propre_suppression(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_supprimer", args=[self.admin.pk]))
        self.assertTrue(Utilisateur.objects.filter(pk=self.admin.pk).exists())
        self.assertIn("Vous ne pouvez pas supprimer votre propre compte.", self.msgs(r))

    def test_objet_protege_message_clair(self):
        """Une ProtectedError donne un message et une redirection, pas une erreur 500."""
        self.client.force_login(self.admin)
        with mock.patch.object(Utilisateur, "delete", side_effect=ProtectedError("protégé", {self.orga})):
            r = self.client.post(reverse("utilisateurs:utilisateur_supprimer", args=[self.part.pk]))
        self.assertRedirects(r, reverse("utilisateurs:utilisateur_detail", args=[self.part.pk]))
        self.assertTrue(any(m.startswith("Impossible de supprimer « part »") for m in self.msgs(r)))
        self.assertTrue(Utilisateur.objects.filter(pk=self.part.pk).exists())
