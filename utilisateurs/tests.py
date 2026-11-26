import re
from unittest import mock

from django.contrib.auth import SESSION_KEY
from django.contrib.messages import get_messages
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Utilisateur
from .securite import MAX_ECHECS_COMPTE, MAX_ECHECS_IP

MDP = "Mdp-12345!"
LOGIN = reverse("utilisateurs:login")


class BaseUtilisateursTests(TestCase):
    """Trois comptes de référence ; le cache (compteurs de tentatives) est vidé avant chaque test."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = Utilisateur.objects.create_user("chef", "chef@ex.tn", MDP, role="ADMIN")
        cls.orga = Utilisateur.objects.create_user("orga", "orga@ex.tn", MDP, role="ORGANISATEUR")
        cls.part = Utilisateur.objects.create_user("part", "part@ex.tn", MDP, role="PARTICIPANT")

    def setUp(self):
        cache.clear()

    def msgs(self, r):
        return [str(m) for m in get_messages(r.wsgi_request)]

    def connecter(self, ident="part", mdp=MDP, client=None, **extra):
        return (client or self.client).post(LOGIN, {"username": ident, "password": mdp, **extra})


class CrudUtilisateursTests(BaseUtilisateursTests):
    """CRUD des utilisateurs : réservé à l'administrateur."""

    def test_reserve_admin(self):
        urls = [reverse("utilisateurs:utilisateur_liste"), reverse("utilisateurs:utilisateur_creer"),
                reverse("utilisateurs:utilisateur_detail", args=[self.part.pk]),
                reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                reverse("utilisateurs:utilisateur_supprimer", args=[self.part.pk]),
                reverse("utilisateurs:utilisateur_desactiver", args=[self.part.pk]),
                reverse("utilisateurs:utilisateur_reactiver", args=[self.part.pk])]
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
        """Le formulaire de modification change les coordonnées et le rôle, mais plus le statut :
        la désactivation passe obligatoirement par l'action dédiée (confirmation + garde-fous)."""
        self.client.force_login(self.admin)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]), {
            "username": "part", "first_name": "Sara", "last_name": "", "email": "part@ex.tn", "telephone": "",
            "role": "ORGANISATEUR"})   # pas de champ « is_active » envoyé
        self.part.refresh_from_db()
        self.assertEqual((self.part.first_name, self.part.role, self.part.is_active), ("Sara", "ORGANISATEUR", True))
        self.assertIn("Le compte « part » a été modifié.", self.msgs(r))

    def test_modification_ne_contourne_pas_la_desactivation(self):
        self.client.force_login(self.admin)
        url = reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk])
        self.assertNotContains(self.client.get(url), 'name="is_active"')
        self.client.post(url, {"username": "part", "email": "part@ex.tn", "role": "PARTICIPANT", "is_active": ""})
        self.part.refresh_from_db()
        self.assertTrue(self.part.is_active)

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


def donnees_inscription(**kw):
    d = {"role": "PARTICIPANT", "first_name": "Sara", "last_name": "Ben Ali", "username": "sara",
         "email": "sara@ex.tn", "telephone": "22123456", "password1": "Tres-Secret-42", "password2": "Tres-Secret-42",
         "cgu": "on"}   # conditions acceptées (champ obligatoire depuis la correction P03)
    d.update(kw)
    return d


class InscriptionTests(BaseUtilisateursTests):
    """US 1.1 — créer un compte."""
    url = reverse("utilisateurs:register")

    def test_formulaire_en_trois_etapes(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-step="3"')
        for nom in ("role", "first_name", "last_name", "username", "email", "telephone", "password1", "password2"):
            self.assertContains(r, f'name="{nom}"')

    def test_inscription_valide_hachage_et_connexion_automatique(self):
        r = self.client.post(self.url, donnees_inscription())
        self.assertRedirects(r, reverse("core:dashboard"))      # suit la redirection : page 200, toujours connecté
        u = Utilisateur.objects.get(username="sara")
        self.assertNotEqual(u.password, "Tres-Secret-42")
        self.assertTrue(u.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(u.check_password("Tres-Secret-42"))
        self.assertEqual((u.role, u.is_active, u.is_staff, u.is_superuser), ("PARTICIPANT", True, False, False))
        self.assertEqual(int(self.client.session[SESSION_KEY]), u.pk)
        self.assertEqual(self.client.get(reverse("utilisateurs:profil")).status_code, 200)

    def test_email_invalide_ou_vide(self):
        for email in ("pas-un-email", ""):
            r = self.client.post(self.url, donnees_inscription(email=email))
            self.assertTrue(r.context["form"].errors.get("email"), email)
        self.assertFalse(Utilisateur.objects.filter(username="sara").exists())

    def test_doublons_email_et_identifiant(self):
        r = self.client.post(self.url, donnees_inscription(email="PART@EX.TN"))
        self.assertIn("Un compte utilise déjà cette adresse e-mail.", r.context["form"].errors["email"])
        for ident in ("part", "PART"):
            r = self.client.post(self.url, donnees_inscription(username=ident, email="x@ex.tn"))
            self.assertTrue(r.context["form"].errors.get("username"), ident)
        self.assertEqual(Utilisateur.objects.count(), 3)

    def test_seuls_participant_et_client_proposes(self):
        from .forms import ROLES_INSCRIPTION_PUBLIQUE
        from .views import ROLES_INSCRIPTION
        r = self.client.get(self.url)
        valeurs = re.findall(r'name="role" value="(\w+)"', r.content.decode())
        self.assertEqual(valeurs, ["PARTICIPANT", "CLIENT"])
        self.assertNotContains(r, "Organisateur")
        self.assertEqual([v for v, *_ in ROLES_INSCRIPTION], list(ROLES_INSCRIPTION_PUBLIQUE))   # cartes = rôles acceptés

    def test_inscription_participant_et_client(self):
        for i, role in enumerate(("PARTICIPANT", "CLIENT")):
            c = Client()
            r = c.post(self.url, donnees_inscription(role=role, username=f"u{i}", email=f"u{i}@ex.tn"))
            self.assertRedirects(r, reverse("core:dashboard"))
            u = Utilisateur.objects.get(username=f"u{i}")
            self.assertEqual(u.role, role)
            self.assertEqual(int(c.session[SESSION_KEY]), u.pk)

    def test_roles_privilegies_refuses_meme_en_post_force(self):
        from .forms import MSG_ROLE_RESERVE
        for role in ("ORGANISATEUR", "PRESTATAIRE", "ADMIN", "organisateur", ""):
            r = self.client.post(self.url, donnees_inscription(role=role, username=f"x{role}", email=f"x{role}@ex.tn"))
            self.assertEqual(r.status_code, 200, role)
            self.assertTrue(r.context["form"].errors.get("role"), role)
            if role:
                self.assertEqual(r.context["form"].errors["role"], [MSG_ROLE_RESERVE], role)
        self.assertEqual(Utilisateur.objects.count(), 3)
        self.assertFalse(Utilisateur.objects.exclude(pk__in=[self.admin.pk, self.orga.pk, self.part.pk]).exists())

    def test_privileges_ignores(self):
        self.client.post(self.url, donnees_inscription(is_staff="on", is_superuser="on"))
        u = Utilisateur.objects.get(username="sara")
        self.assertFalse(u.is_staff or u.is_superuser)

    def test_mot_de_passe_faible_ou_different(self):
        r = self.client.post(self.url, donnees_inscription(password1="12345678", password2="12345678"))
        self.assertTrue(r.context["form"].errors.get("password2"))
        r = self.client.post(self.url, donnees_inscription(password2="Autre-Secret-99"))
        self.assertTrue(r.context["form"].errors.get("password2"))


class ComptesReservesAdminTests(BaseUtilisateursTests):
    """Organisateurs, prestataires et administrateurs : créés uniquement par un administrateur."""

    def donnees(self, role, n):
        return {"username": f"{role.lower()}{n}", "first_name": "", "last_name": "", "email": f"{role.lower()}{n}@ex.tn",
                "telephone": "", "role": role, "is_active": "on", "password1": "Tres-Secret-42", "password2": "Tres-Secret-42"}

    def test_admin_cree_les_comptes_reserves(self):
        self.client.force_login(self.admin)
        for role in ("ORGANISATEUR", "PRESTATAIRE", "ADMIN"):
            r = self.client.post(reverse("utilisateurs:utilisateur_creer"), self.donnees(role, 1))
            u = Utilisateur.objects.get(username=f"{role.lower()}1")
            self.assertRedirects(r, reverse("utilisateurs:utilisateur_detail", args=[u.pk]))
            self.assertEqual(u.role, role)

    def test_non_admin_ne_peut_pas_creer_de_compte(self):
        for u in (self.orga, self.part):
            self.client.force_login(u)
            r = self.client.post(reverse("utilisateurs:utilisateur_creer"), self.donnees("ORGANISATEUR", 2))
            self.assertEqual(r.status_code, 403)
        self.assertFalse(Utilisateur.objects.filter(username="organisateur2").exists())

    def test_organisateurs_existants_inchanges(self):
        self.orga.refresh_from_db()
        self.assertEqual((self.orga.role, self.orga.is_active), ("ORGANISATEUR", True))
        self.assertTrue(self.orga.est_organisateur)
        self.assertEqual(self.connecter("orga").status_code, 302)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        from core.navigation import get_module
        for module in ("evenements", "programmes", "prestataires", "participants", "ressources"):
            self.assertEqual(self.client.get(reverse(get_module(module).url_name)).status_code, 200, module)
        self.assertEqual(self.client.get(reverse("utilisateurs:utilisateur_liste")).status_code, 403)


class ConsultationTests(BaseUtilisateursTests):
    """US 1.2 — consulter les comptes (complète test_reserve_admin)."""

    def test_admin_liste_recherche_et_detail(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("utilisateurs:utilisateur_liste"))
        self.assertEqual({u.username for u in r.context["object_list"]}, {"chef", "orga", "part"})
        r = self.client.get(reverse("utilisateurs:utilisateur_liste"), {"q": "orga@"})
        self.assertEqual([u.username for u in r.context["object_list"]], ["orga"])
        self.assertContains(self.client.get(reverse("utilisateurs:utilisateur_detail", args=[self.part.pk])), "part@ex.tn")
        self.assertEqual(self.client.get(reverse("utilisateurs:utilisateur_detail", args=[99999])).status_code, 404)

    def test_superutilisateur_sans_role_admin(self):
        self.client.force_login(Utilisateur.objects.create_superuser("root", "root@ex.tn", MDP))
        self.assertEqual(self.client.get(reverse("utilisateurs:utilisateur_liste")).status_code, 200)


class ProfilTests(BaseUtilisateursTests):
    """US 1.3 — modifier son profil."""
    url = reverse("utilisateurs:profil")

    def poster(self, **kw):
        d = {"first_name": "Nour", "last_name": "T", "email": "part@ex.tn", "telephone": "99 123 456"}  # numéro TN valide
        d.update(kw)
        return self.client.post(self.url, d)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.part)

    def test_formulaire_limite_aux_coordonnees(self):
        r = self.client.get(self.url)
        self.assertEqual(r.context["form"].instance.pk, self.part.pk)
        self.assertEqual(set(r.context["form"].fields), {"first_name", "last_name", "email", "telephone"})
        self.assertTrue(r.context["form"].fields["email"].required)

    def test_modification_et_conservation_de_sa_propre_adresse(self):
        r = self.poster(email="PART@ex.tn")          # sa propre adresse, casse différente : acceptée
        self.assertRedirects(r, self.url)
        self.assertIn("Profil mis à jour.", self.msgs(r))
        self.part.refresh_from_db()
        self.assertEqual((self.part.first_name, self.part.email), ("Nour", "PART@ex.tn"))
        self.assertRedirects(self.poster(email="nouvelle@ex.tn"), self.url)

    def test_email_obligatoire_invalide_ou_deja_pris(self):
        cas = {"": "L'adresse e-mail est obligatoire.",
               "nope": "Saisissez une adresse e-mail valide, ex. vous@exemple.tn.",
               "orga@ex.tn": "Un compte utilise déjà cette adresse e-mail.",
               "ORGA@EX.TN": "Un compte utilise déjà cette adresse e-mail."}
        for email, message in cas.items():
            r = self.poster(email=email)
            self.assertEqual(r.status_code, 200, email)
            self.assertEqual(r.context["form"].errors["email"], [message], email)
            echappe = message.replace("'", "&#x27;")
            self.assertContains(r, f'<small class="err">{echappe}</small>')   # rendu avec le style d'erreur Évenza
        self.part.refresh_from_db()
        self.assertEqual(self.part.email, "part@ex.tn")

    def test_pas_d_elevation_de_privileges(self):
        self.poster(role="ADMIN", is_staff="on", is_superuser="on", is_active="", username="hack")
        self.part.refresh_from_db()
        self.assertEqual((self.part.role, self.part.is_staff, self.part.is_superuser, self.part.is_active,
                          self.part.username), ("PARTICIPANT", False, False, True, "part"))

    def test_pas_de_modification_du_profil_d_autrui(self):
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.orga.pk]),
                             {"username": "orga", "email": "pirate@ex.tn", "role": "PARTICIPANT"})
        self.assertEqual(r.status_code, 403)
        self.orga.refresh_from_db()
        self.assertEqual(self.orga.email, "orga@ex.tn")

    def test_anonyme_redirige(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertRedirects(r, f"{LOGIN}?next={self.url}")


class DesactivationTests(BaseUtilisateursTests):
    """US 1.4 — désactivation logique (is_active), réactivation et garde-fous."""

    def url(self, action, u):
        return reverse(f"utilisateurs:utilisateur_{action}", args=[u.pk])

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_page_de_confirmation_sans_effet_en_get(self):
        r = self.client.get(self.url("desactiver", self.part))
        self.assertContains(r, "Désactiver « part » ?")
        self.assertContains(r, "Oui, désactiver")
        self.assertContains(r, 'name="csrfmiddlewaretoken"')
        self.assertContains(r, "Rien n'est supprimé")
        self.part.refresh_from_db()
        self.assertTrue(self.part.is_active)

    def test_boutons_desactiver_et_reactiver(self):
        Utilisateur.objects.filter(pk=self.orga.pk).update(is_active=False)
        r = self.client.get(reverse("utilisateurs:utilisateur_liste"))
        self.assertContains(r, self.url("desactiver", self.part))
        self.assertContains(r, self.url("reactiver", self.orga))
        self.assertNotContains(r, self.url("desactiver", self.admin))      # pas sur sa propre ligne
        self.assertContains(self.client.get(reverse("utilisateurs:utilisateur_detail", args=[self.part.pk])),
                            self.url("desactiver", self.part))
        self.assertContains(self.client.get(reverse("utilisateurs:utilisateur_detail", args=[self.orga.pk])),
                            self.url("reactiver", self.orga))

    def test_desactivation_conserve_le_compte_et_ses_donnees(self):
        nb = Utilisateur.objects.count()
        r = self.client.post(self.url("desactiver", self.part))
        self.assertRedirects(r, reverse("utilisateurs:utilisateur_detail", args=[self.part.pk]))
        self.assertTrue(any("a été désactivé" in m for m in self.msgs(r)))
        self.part.refresh_from_db()
        self.assertFalse(self.part.is_active)
        self.assertEqual(Utilisateur.objects.count(), nb)
        self.assertContains(self.client.get(reverse("utilisateurs:utilisateur_detail", args=[self.part.pk])), "Désactivé")

    def test_compte_desactive_ne_peut_plus_se_connecter_puis_reactive(self):
        self.client.post(self.url("desactiver", self.part))
        visiteur = Client()
        for ident in ("part", "part@ex.tn"):
            r = self.connecter(ident, client=visiteur)
            self.assertEqual(r.status_code, 200, ident)
            self.assertNotIn(SESSION_KEY, visiteur.session)
        r = self.client.post(self.url("reactiver", self.part))
        self.assertTrue(any("a été réactivé" in m for m in self.msgs(r)))
        self.part.refresh_from_db()
        self.assertTrue(self.part.is_active)
        self.assertEqual(self.connecter(client=visiteur).status_code, 302)
        self.assertEqual(int(visiteur.session[SESSION_KEY]), self.part.pk)

    def test_session_existante_bloquee_apres_desactivation(self):
        victime = Client()
        self.assertEqual(self.connecter(client=victime).status_code, 302)
        self.assertEqual(victime.get(reverse("utilisateurs:profil")).status_code, 200)
        self.client.post(self.url("desactiver", self.part))
        r = victime.get(reverse("utilisateurs:profil"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(LOGIN, r["Location"])
        self.assertEqual(victime.get(reverse("core:dashboard")).status_code, 302)

    def test_reinitialisation_mdp_ignore_compte_desactive(self):
        self.client.post(self.url("desactiver", self.part))
        Client().post(reverse("utilisateurs:password_reset"), {"email": "part@ex.tn"})
        self.assertEqual(len(mail.outbox), 0)

    def test_pas_d_auto_desactivation(self):
        r = self.client.get(self.url("desactiver", self.admin))
        self.assertContains(r, "Vous ne pouvez pas désactiver votre propre compte.")
        self.assertNotContains(r, "Oui, désactiver")
        r = self.client.post(self.url("desactiver", self.admin))
        self.assertIn("Vous ne pouvez pas désactiver votre propre compte.", self.msgs(r))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_pas_de_retrait_de_son_propre_role_admin(self):
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.admin.pk]),
                             {"username": "chef", "email": "chef@ex.tn", "role": "PARTICIPANT"})
        self.assertContains(r, "Vous ne pouvez pas retirer votre propre rôle d&#x27;administrateur.")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "ADMIN")

    def test_le_dernier_admin_actif_garde_ses_droits(self):
        """Deux admins : l'un peut retirer le rôle de l'autre ; celui qui reste seul ne peut
        ni se désactiver ni perdre son rôle → la plateforme garde toujours un administrateur actif."""
        adj = Utilisateur.objects.create_user("adj", "adj@ex.tn", MDP, role="ADMIN")
        self.client.force_login(adj)
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[self.admin.pk]),
                             {"username": "chef", "email": "chef@ex.tn", "role": "ORGANISATEUR"})
        self.assertEqual(r.status_code, 302)
        self.client.force_login(self.admin)                    # « chef » n'est plus admin : accès refusé
        self.assertEqual(self.client.get(reverse("utilisateurs:utilisateur_liste")).status_code, 403)
        self.client.force_login(adj)                           # « adj » est désormais le seul admin actif
        self.client.post(self.url("desactiver", adj))
        r = self.client.post(reverse("utilisateurs:utilisateur_modifier", args=[adj.pk]),
                             {"username": "adj", "email": "adj@ex.tn", "role": "PARTICIPANT"})
        self.assertEqual(r.status_code, 200)
        adj.refresh_from_db()
        self.assertEqual((adj.role, adj.is_active), ("ADMIN", True))

    def test_formulaire_refuse_de_retirer_le_role_du_dernier_admin(self):
        """Même sans passer par son propre compte (ex. superutilisateur inactif), le dernier admin par rôle est gardé."""
        from .forms import UtilisateurAdminForm
        f = UtilisateurAdminForm({"username": "chef", "email": "chef@ex.tn", "role": "PARTICIPANT"},
                                 instance=self.admin, acteur=self.orga)
        self.assertFalse(f.is_valid())
        self.assertIn("Impossible : c'est le dernier administrateur actif de la plateforme.", f.errors["role"])

    def test_dernier_admin_ne_peut_pas_etre_desactive(self):
        from .securite import motif_refus_desactivation
        self.assertEqual(motif_refus_desactivation(self.admin, self.orga),
                         "Impossible : c'est le dernier administrateur actif de la plateforme.")
        second = Utilisateur.objects.create_user("adj", "adj@ex.tn", MDP, role="ADMIN")
        self.assertIsNone(motif_refus_desactivation(self.admin, second))
        r = self.client.post(self.url("desactiver", second))
        second.refresh_from_db()
        self.assertFalse(second.is_active)
        self.assertTrue(any("a été désactivé" in m for m in self.msgs(r)))

    def test_actions_inverses_refusees(self):
        self.assertIn("Le compte « part » est déjà actif.", self.msgs(self.client.post(self.url("reactiver", self.part))))
        self.client.post(self.url("desactiver", self.part))
        self.assertIn("Le compte « part » est déjà désactivé.", self.msgs(self.client.post(self.url("desactiver", self.part))))

    def test_reserve_aux_administrateurs(self):
        for u in (self.orga, self.part):
            self.client.force_login(u)
            self.assertEqual(self.client.post(self.url("desactiver", self.orga if u == self.part else self.part)).status_code, 403)
        self.client.logout()
        r = self.client.post(self.url("desactiver", self.part))
        self.assertIn(LOGIN, r["Location"])
        self.part.refresh_from_db(); self.orga.refresh_from_db()
        self.assertTrue(self.part.is_active and self.orga.is_active)

    def test_suppression_distincte_de_la_desactivation(self):
        r = self.client.get(reverse("utilisateurs:utilisateur_supprimer", args=[self.part.pk]))
        self.assertContains(r, "Cette action est définitive")
        self.assertContains(r, self.url("desactiver", self.part))


class AuthentificationTests(BaseUtilisateursTests):
    """US 1.5 — connexion, session, déconnexion, limitation des tentatives."""

    def test_connexion_par_identifiant_ou_email(self):
        r = self.connecter("part", remember="on")
        self.assertRedirects(r, reverse("core:dashboard"))
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.part.pk)
        c = Client()
        self.assertEqual(self.connecter("PART@ex.tn", client=c).status_code, 302)
        self.assertEqual(int(c.session[SESSION_KEY]), self.part.pk)

    def test_identifiants_incorrects(self):
        for ident, mdp in (("part", "mauvais"), ("inconnu", MDP), ("part@ex.tn", "mauvais")):
            r = self.connecter(ident, mdp)
            self.assertContains(r, "Identifiant ou mot de passe incorrect")
            self.assertNotIn(SESSION_KEY, self.client.session)

    def test_se_souvenir_de_moi(self):
        self.connecter()
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        c = Client()
        self.connecter(client=c, remember="on")
        self.assertFalse(c.session.get_expire_at_browser_close())

    def test_nouvelle_cle_de_session_a_la_connexion(self):
        self.client.get(LOGIN)
        session = self.client.session; session["x"] = 1; session.save()
        avant = self.client.cookies["sessionid"].value
        self.connecter()
        self.assertNotEqual(avant, self.client.cookies["sessionid"].value)

    def test_deconnexion_invalide_la_session(self):
        self.connecter()
        cle = self.client.cookies["sessionid"].value
        r = self.client.post(reverse("utilisateurs:logout"))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Session.objects.filter(session_key=cle).exists())
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get(reverse("utilisateurs:profil")).status_code, 302)

    def test_deconnexion_en_get_refusee(self):
        self.client.force_login(self.part)
        self.assertEqual(self.client.get(reverse("utilisateurs:logout")).status_code, 405)

    def test_pages_protegees(self):
        for nom in ("core:dashboard", "utilisateurs:profil", "utilisateurs:utilisateur_liste"):
            r = self.client.get(reverse(nom))
            self.assertRedirects(r, f"{LOGIN}?next={reverse(nom)}", fetch_redirect_response=False)

    def test_redirections_sures(self):
        r = self.connecter(next="https://evil.example/")
        self.assertNotIn("evil.example", r["Location"])
        r = self.connecter(client=Client(), next=reverse("utilisateurs:profil"))
        self.assertRedirects(r, reverse("utilisateurs:profil"), fetch_redirect_response=False)

    def test_limitation_des_tentatives_puis_deblocage(self):
        for _ in range(MAX_ECHECS_COMPTE):
            self.assertEqual(self.connecter(mdp="mauvais").status_code, 200)
        r = self.connecter()                                    # bon mot de passe, mais compte temporairement bloqué
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Trop de tentatives de connexion", status_code=429)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.connecter("orga").status_code, 302)   # les autres comptes ne sont pas bloqués
        cache.clear()                                           # simule l'expiration du délai de blocage
        self.assertEqual(self.connecter(client=Client()).status_code, 302)

    def test_succes_remet_le_compteur_a_zero(self):
        for _ in range(MAX_ECHECS_COMPTE - 1):
            self.connecter(mdp="mauvais")
        self.assertEqual(self.connecter().status_code, 302)
        c = Client()
        for _ in range(MAX_ECHECS_COMPTE - 1):
            self.assertEqual(self.connecter(mdp="mauvais", client=c).status_code, 200)
        self.assertEqual(self.connecter(client=c).status_code, 302)

    def test_limitation_par_adresse_ip(self):
        for i in range(MAX_ECHECS_IP):
            self.connecter(f"inconnu{i}", "mauvais")
        self.assertEqual(self.connecter().status_code, 429)
        self.assertEqual(self.connecter(client=Client(REMOTE_ADDR="10.0.0.2")).status_code, 302)

    def test_aucun_identifiant_de_demonstration_dans_les_pages_publiques(self):
        for nom in ("utilisateurs:login", "utilisateurs:register", "utilisateurs:password_reset", "core:home"):
            html = Client().get(reverse(nom)).content.decode()
            self.assertNotRegex(html, r'data-p="', nom)
            self.assertNotIn("Comptes de démonstration", html, nom)
            self.assertNotRegex(html, r"(Demo|Admin)\d{5}!", nom)


class CsrfTests(BaseUtilisateursTests):
    """Jeton CSRF exigé sur tous les formulaires de la gestion des utilisateurs."""

    def test_post_sans_jeton_refuse(self):
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post(LOGIN, {"username": "part", "password": MDP}).status_code, 403)
        self.assertEqual(c.post(reverse("utilisateurs:register"), donnees_inscription()).status_code, 403)
        c.force_login(self.part)
        self.assertEqual(c.post(reverse("utilisateurs:profil"), {"email": "z@ex.tn"}).status_code, 403)
        self.assertEqual(c.post(reverse("utilisateurs:logout")).status_code, 403)
        c.force_login(self.admin)
        for action in ("desactiver", "supprimer"):
            self.assertEqual(c.post(reverse(f"utilisateurs:utilisateur_{action}", args=[self.part.pk])).status_code, 403)
        self.assertEqual(c.post(reverse("utilisateurs:utilisateur_modifier", args=[self.part.pk]),
                                {"username": "part", "role": "ADMIN"}).status_code, 403)
        self.part.refresh_from_db()
        self.assertEqual((self.part.is_active, self.part.role), (True, "PARTICIPANT"))

    def test_jeton_present_et_accepte(self):
        pages = [(None, "login", []), (None, "register", []), (self.part, "profil", []),
                 (self.admin, "utilisateur_modifier", [self.part.pk]),
                 (self.admin, "utilisateur_desactiver", [self.part.pk]),
                 (self.admin, "utilisateur_supprimer", [self.part.pk])]
        for u, nom, args in pages:
            c = Client()
            if u:
                c.force_login(u)
            self.assertContains(c.get(reverse(f"utilisateurs:{nom}", args=args)), 'name="csrfmiddlewaretoken"', msg_prefix=nom)
        c = Client(enforce_csrf_checks=True)
        jeton = str(c.get(LOGIN).context["csrf_token"])
        self.assertEqual(c.post(LOGIN, {"username": "part", "password": MDP, "csrfmiddlewaretoken": jeton}).status_code, 302)


# ======================================================================= rôles et autorisations
ROLES = ("ADMIN", "ORGANISATEUR", "CLIENT", "PARTICIPANT", "PRESTATAIRE")


class RolesBase(TestCase):
    """Un compte par rôle, plus un superutilisateur dont le rôle n'est pas ADMIN."""

    @classmethod
    def setUpTestData(cls):
        cls.u = {r: Utilisateur.objects.create_user(r.lower(), f"{r.lower()}@ex.tn", MDP, role=r) for r in ROLES}
        cls.root = Utilisateur.objects.create_superuser("root", "root@ex.tn", MDP, role="PARTICIPANT")

    def autorises(self, regle):
        """Rôles (et « root ») pour lesquels ``regle(user)`` est vrai."""
        ok = {r for r in ROLES if regle(self.u[r])}
        return ok | ({"root"} if regle(self.root) else set())


class ProprietesRolesTests(RolesBase):
    """Définition des rôles dans le modèle (source unique de vérité)."""

    def test_proprietes(self):
        attendu = {
            "est_admin": {"ADMIN", "root"},
            "est_organisateur": {"ADMIN", "ORGANISATEUR", "root"},   # Administrateur ⊇ Organisateur
            "est_client": {"CLIENT"},
            "est_participant": {"PARTICIPANT", "root"},                # root a le rôle PARTICIPANT
            "est_prestataire": {"PRESTATAIRE"},
        }
        for prop, roles in attendu.items():
            self.assertEqual(self.autorises(lambda u: getattr(u, prop)), roles, prop)

    def test_roles_externes_exclusifs(self):
        for r in ("CLIENT", "PARTICIPANT", "PRESTATAIRE"):
            u = self.u[r]
            self.assertEqual(sum((u.est_client, u.est_participant, u.est_prestataire)), 1, r)
            self.assertFalse(u.est_organisateur or u.est_admin, r)


class FonctionsPermissionsTests(RolesBase):
    """core.permissions : mêmes règles pour le serveur et la navigation."""

    def test_regles_par_role(self):
        from core import permissions as p
        attendu = {
            p.est_connecte: {*ROLES, "root"},
            p.est_administrateur: {"ADMIN", "root"},
            p.peut_organiser: {"ADMIN", "ORGANISATEUR", "root"},
            p.est_client: {"CLIENT"},
            p.est_participant: {"PARTICIPANT", "root"},
            p.est_prestataire: {"PRESTATAIRE"},
            p.acces_espace_client: {"CLIENT", "ADMIN", "root"},
            p.acces_espace_participant: {"PARTICIPANT", "ADMIN", "root"},
            p.acces_espace_prestataire: {"PRESTATAIRE", "ADMIN", "root"},
        }
        for regle, roles in attendu.items():
            self.assertEqual(self.autorises(regle), roles, regle.__name__)

    def test_anonyme_refuse_partout(self):
        from django.contrib.auth.models import AnonymousUser
        from core import permissions as p
        for regle in (p.est_connecte, p.est_administrateur, p.peut_organiser, p.est_client, p.est_participant,
                      p.est_prestataire, p.acces_espace_client, p.acces_espace_participant,
                      p.acces_espace_prestataire, p.peut_acceder_admin_django):
            self.assertFalse(regle(AnonymousUser()), regle.__name__)
            self.assertFalse(regle(None), regle.__name__)

    def test_peut_gerer_evenement(self):
        from types import SimpleNamespace
        from core.permissions import peut_gerer_evenement
        orga = self.u["ORGANISATEUR"]
        a_lui, a_autrui = SimpleNamespace(organisateur_id=orga.pk), SimpleNamespace(organisateur_id=-1)
        self.assertTrue(peut_gerer_evenement(orga, a_lui))
        self.assertFalse(peut_gerer_evenement(orga, a_autrui))
        self.assertTrue(peut_gerer_evenement(self.u["ADMIN"], a_autrui))
        self.assertTrue(peut_gerer_evenement(self.root, a_autrui))
        for r in ("CLIENT", "PARTICIPANT", "PRESTATAIRE"):   # même s'il figurait comme organisateur
            self.assertFalse(peut_gerer_evenement(self.u[r], SimpleNamespace(organisateur_id=self.u[r].pk)), r)

    def test_evenements_geres_vide_hors_organisation(self):
        from core.permissions import evenements_geres
        for r in ("CLIENT", "PARTICIPANT", "PRESTATAIRE"):
            self.assertFalse(evenements_geres(self.u[r]).exists(), r)

    def test_preparee_admin_django(self):
        from core.permissions import peut_acceder_admin_django
        self.assertTrue(peut_acceder_admin_django(self.root))                # superutilisateur : is_staff
        self.assertFalse(peut_acceder_admin_django(self.u["ADMIN"]))         # rôle ADMIN sans is_staff
        staff = Utilisateur.objects.create_user("staff", "s@ex.tn", MDP, role="ADMIN", is_staff=True, is_active=False)
        self.assertFalse(peut_acceder_admin_django(staff))                   # désactivé

    def test_preparee_fiche_prestataire(self):
        from core.permissions import fiche_prestataire
        from prestataires.models import Prestataire
        presta = self.u["PRESTATAIRE"]
        self.assertIsNone(fiche_prestataire(presta))                         # pas encore rattaché
        fiche = Prestataire.objects.create(nom="Traiteur", compte=presta)
        self.assertEqual(fiche_prestataire(presta), fiche)
        self.assertIsNone(fiche_prestataire(self.u["CLIENT"]))

    def test_preparee_traiter_reservation(self):
        from types import SimpleNamespace
        from core.permissions import peut_traiter_reservation
        presta, orga = self.u["PRESTATAIRE"], self.u["ORGANISATEUR"]
        resa = SimpleNamespace(evenement=SimpleNamespace(organisateur_id=orga.pk),
                               prestataire=SimpleNamespace(compte_id=presta.pk))
        self.assertEqual(self.autorises(lambda u: peut_traiter_reservation(u, resa)),
                         {"ADMIN", "ORGANISATEUR", "PRESTATAIRE", "root"})
        autre = SimpleNamespace(evenement=SimpleNamespace(organisateur_id=-1), prestataire=SimpleNamespace(compte_id=-1))
        self.assertEqual(self.autorises(lambda u: peut_traiter_reservation(u, autre)), {"ADMIN", "root"})


class MixinsTests(RolesBase):
    """core.mixins : anonyme → connexion (302), rôle non autorisé → 403, rôle autorisé → 200."""

    def appeler(self, mixin, user, **attrs):
        from django.contrib.auth.models import AnonymousUser
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponse
        from django.test import RequestFactory
        from django.views import View

        vue = type("Vue", (mixin, View), {"get": lambda self, request: HttpResponse("ok"), **attrs})
        req = RequestFactory().get("/x/")
        req.user = user or AnonymousUser()
        try:
            return vue.as_view()(req).status_code
        except PermissionDenied:
            return 403

    def matrice(self, mixin, **attrs):
        self.assertEqual(self.appeler(mixin, None, **attrs), 302)
        return {r for r in (*ROLES, "root")
                if self.appeler(mixin, self.root if r == "root" else self.u[r], **attrs) == 200}

    def test_mixins_par_role(self):
        from core import mixins as m
        attendu = {
            m.AdminRequiredMixin: {"ADMIN", "root"},
            m.OrganisateurRequiredMixin: {"ADMIN", "ORGANISATEUR", "root"},
            m.ClientRequiredMixin: {"CLIENT", "ADMIN", "root"},
            m.ParticipantRequiredMixin: {"PARTICIPANT", "ADMIN", "root"},
            m.PrestataireRequiredMixin: {"PRESTATAIRE", "ADMIN", "root"},
        }
        for mixin, roles in attendu.items():
            self.assertEqual(self.matrice(mixin), roles, mixin.__name__)

    def test_role_required_mixin_conserve(self):
        from core.mixins import RoleRequiredMixin
        self.assertEqual(self.matrice(RoleRequiredMixin, roles=("CLIENT", "PRESTATAIRE")),
                         {"CLIENT", "PRESTATAIRE", "ADMIN", "root"})

    def test_proprietaire_evenement(self):
        from types import SimpleNamespace
        from core.mixins import ProprietaireEvenementMixin
        orga = self.u["ORGANISATEUR"]
        evt = SimpleNamespace(organisateur_id=orga.pk)
        self.assertEqual(self.matrice(ProprietaireEvenementMixin, get_evenement=lambda self: evt),
                         {"ADMIN", "ORGANISATEUR", "root"})
        autrui = SimpleNamespace(organisateur_id=-1)
        self.assertEqual(self.matrice(ProprietaireEvenementMixin, get_evenement=lambda self: autrui), {"ADMIN", "root"})

    def test_role_verifie_avant_de_charger_l_evenement(self):
        """Un non-organisateur reçoit 403 sans que l'événement soit chargé (pas de 404 révélateur)."""
        from core.mixins import ProprietaireEvenementMixin

        def interdit(self):
            raise AssertionError("get_evenement ne doit pas être appelé")
        for r in ("CLIENT", "PARTICIPANT", "PRESTATAIRE"):
            self.assertEqual(self.appeler(ProprietaireEvenementMixin, self.u[r], get_evenement=interdit), 403, r)


class NavigationRolesTests(RolesBase):
    """La barre latérale n'affiche que ce que le serveur autorise, et aucun lien vers une page inexistante."""

    def nav(self, user):
        from django.test import RequestFactory
        from django.urls import resolve
        from core.navigation import navigation_pour
        req = RequestFactory().get(reverse("core:dashboard"))
        req.user, req.resolver_match = user, resolve(reverse("core:dashboard"))
        n = navigation_pour(req)
        return [i["cle"] for i in n["principale"]], [i["cle"] for i in n["personnelle"]], n

    def test_modules_par_role(self):
        metier = ["evenements", "participants", "programmes", "prestataires", "ressources"]
        attendu = {"ADMIN": ["apercu", *metier, "utilisateurs"], "ORGANISATEUR": ["apercu", *metier],
                   "CLIENT": ["apercu"], "PARTICIPANT": ["apercu"], "PRESTATAIRE": ["apercu"]}
        for r, modules in attendu.items():
            principale, personnelle, _ = self.nav(self.u[r])
            self.assertEqual(principale, modules, r)
            self.assertEqual(personnelle, ["billets", "profil"], r)

    def test_tous_les_liens_existent(self):
        for r in ROLES:
            _, _, n = self.nav(self.u[r])
            for item in n["principale"] + n["personnelle"]:
                reverse(item["url_name"])   # NoReverseMatch si un lien pointait vers une page inexistante

    def test_menu_et_serveur_concordent(self):
        _, _, n_admin = self.nav(self.u["ADMIN"])
        for r in ROLES:
            visibles = {i["cle"] for i in self.nav(self.u[r])[2]["principale"]}
            self.client.force_login(self.u[r])
            for item in n_admin["principale"]:
                code = self.client.get(reverse(item["url_name"])).status_code
                self.assertEqual(code == 200, item["cle"] in visibles, f"{r} → {item['cle']} ({code})")

    def test_espace_declare_par_une_gestion(self):
        """Point d'extension : une gestion déclare ``ESPACE`` dans son navigation.py ; le lien n'apparaît
        qu'aux rôles autorisés. (Simulé ici : aucune gestion ne le déclare encore.)"""
        from core.navigation import Module
        from core.permissions import acces_espace_client
        import utilisateurs.navigation as nav_u
        demo = Module("demandes", "Mes demandes", "utilisateurs:profil", "profil", acces_espace_client,
                      namespace="utilisateurs", urls_actives=())
        with mock.patch.object(nav_u, "ESPACE", (demo,), create=True):
            for r, voit in {"CLIENT": True, "ADMIN": True, "PARTICIPANT": False, "PRESTATAIRE": False,
                            "ORGANISATEUR": False}.items():
                self.assertEqual("demandes" in self.nav(self.u[r])[1], voit, r)
        self.assertNotIn("demandes", self.nav(self.u["CLIENT"])[1])   # sans déclaration : rien d'ajouté


class MatriceAccesServeurTests(RolesBase):
    """Non-régression : accès réels aux pages principales pour chaque rôle."""

    def test_matrice(self):
        tous, orga = {*ROLES}, {"ADMIN", "ORGANISATEUR"}
        pages = {
            "core:dashboard": tous, "utilisateurs:profil": tous, "participants:mes_inscriptions": tous,
            "evenements:liste": tous,
            "evenements:mes_evenements": orga, "evenements:creer": orga, "evenements:lieux": orga,
            "participants:index": orga, "programmes:index": orga, "programmes:intervenants": orga,
            "prestataires:liste": orga, "ressources:liste": orga, "ressources:affectations": orga,
            "utilisateurs:utilisateur_liste": {"ADMIN"}, "utilisateurs:utilisateur_creer": {"ADMIN"},
        }
        for nom, roles in pages.items():
            for r in ROLES:
                self.client.force_login(self.u[r])
                code = self.client.get(reverse(nom)).status_code
                self.assertEqual(code, 200 if r in roles else 403, f"{r} → {nom}")

    def test_inscription_publique_inchangee(self):
        from .forms import InscriptionCompteForm
        self.assertEqual([c for c, _ in InscriptionCompteForm().fields["role"].choices], ["PARTICIPANT", "CLIENT"])
