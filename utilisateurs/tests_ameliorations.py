"""Tests des améliorations du CRUD des utilisateurs (lots 1 et 2) et des contrôles renforcés de la photo."""
import io
from datetime import timedelta

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core import navigation

from . import roles
from .forms import ProfilForm
from .models import Utilisateur

MDP = "Mdp-12345!"
LISTE = reverse("utilisateurs:utilisateur_liste")
GROUPE = reverse("utilisateurs:utilisateur_action_groupee")


def modifier_url(u):
    return reverse("utilisateurs:utilisateur_modifier", args=[u.pk])


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        mk = Utilisateur.objects.create_user
        cls.admin = mk("chef", "chef@ex.tn", MDP, role="ADMIN", first_name="Hela", last_name="Chef")
        cls.orga = mk("orga", "orga@ex.tn", MDP, role="ORGANISATEUR", first_name="Omar", last_name="Ben Salah",
                      telephone="22123456")
        cls.part = mk("part", "part@ex.tn", MDP, role="PARTICIPANT", first_name="Sara", last_name="Zitouni")
        cls.client_ = mk("cli", "cli@ex.tn", MDP, role="CLIENT")
        cls.presta = mk("presta", "presta@ex.tn", MDP, role="PRESTATAIRE")
        cls.root = Utilisateur.objects.create_superuser("root", "root@ex.tn", MDP)
        cls.inactif = mk("dormeur", "dormeur@ex.tn", MDP, role="PARTICIPANT", is_active=False)
        ancien = timezone.now() - timedelta(days=200)
        Utilisateur.objects.filter(pk=cls.orga.pk).update(last_login=timezone.now() - timedelta(days=45),
                                                          date_joined=ancien)
        Utilisateur.objects.filter(pk=cls.part.pk).update(last_login=timezone.now() - timedelta(days=2),
                                                          date_joined=ancien)
        Utilisateur.objects.filter(pk=cls.inactif.pk).update(date_joined=ancien)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.admin)

    def noms(self, **params):
        r = self.client.get(LISTE, params)
        self.assertEqual(r.status_code, 200)
        return [u.username for u in r.context["object_list"]]

    def msgs(self, r):
        return [str(m) for m in get_messages(r.wsgi_request)]


# =============================================================== Amélioration 1 : KPI
class KpiTests(Base):
    def test_valeurs_reelles(self):
        r = self.client.get(LISTE)
        k = {c["cle"]: c["valeur"] for c in r.context["kpis"]}
        tous = Utilisateur.objects.all()
        self.assertEqual(k["total"], tous.count())
        self.assertEqual(k["actifs"], tous.filter(is_active=True).count())
        self.assertEqual(k["desactives"], 1)
        self.assertEqual(k["jamais_connectes"], tous.filter(last_login__isnull=True).count())
        self.assertEqual(k["nouveaux_mois"], tous.filter(date_joined__gte=timezone.localtime().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)).count())

    def test_kpi_globaux_independants_des_filtres(self):
        k = {c["cle"]: c["valeur"] for c in self.client.get(LISTE, {"q": "orga"}).context["kpis"]}
        self.assertEqual(k["total"], Utilisateur.objects.count())

    def test_carte_cliquable_et_carte_active(self):
        r = self.client.get(LISTE)
        carte = next(c for c in r.context["kpis"] if c["cle"] == "desactives")
        r = self.client.get(LISTE + carte["url"])
        self.assertEqual([u.username for u in r.context["object_list"]], ["dormeur"])
        actives = [c["cle"] for c in r.context["kpis"] if c["actif"]]
        self.assertEqual(actives, ["desactives"])
        self.assertContains(r, 'data-kpi="desactives"')

    def test_kpi_en_une_requete(self):
        from .filtres import indicateurs
        with self.assertNumQueries(1):
            indicateurs(Utilisateur.objects.all())


# =============================================================== Amélioration 2 : filtres, tri, pagination
class FiltresTriTests(Base):
    def test_recherche_par_telephone_prenom_nom(self):
        self.assertEqual(self.noms(q="22123"), ["orga"])
        self.assertEqual(self.noms(q="zitou"), ["part"])
        self.assertEqual(self.noms(q="Omar"), ["orga"])

    def test_filtres_combines(self):
        self.assertEqual(self.noms(role="PARTICIPANT", statut="actif"), ["part", "root"])  # root : rôle par défaut
        self.assertEqual(self.noms(role="PARTICIPANT", statut="inactif"), ["dormeur"])
        hier = (timezone.localdate() - timedelta(days=1)).isoformat()
        recents = self.noms(inscrit_du=hier, role="CLIENT")
        self.assertEqual(recents, ["cli"])
        self.assertNotIn("orga", self.noms(inscrit_du=hier))

    def test_connexion_jamais_et_inactivite(self):
        jamais = set(self.noms(connexion="jamais"))
        self.assertIn("cli", jamais)
        self.assertNotIn("orga", jamais)
        self.assertEqual(set(self.noms(connexion="30")), {"orga", "dormeur"})   # vu il y a 45 j ; jamais vu depuis 200 j
        self.assertEqual(set(self.noms(connexion="60")), {"dormeur"})
        debut = (timezone.localdate() - timedelta(days=50)).isoformat()
        fin = (timezone.localdate() - timedelta(days=40)).isoformat()
        self.assertEqual(self.noms(connecte_du=debut, connecte_au=fin), ["orga"])

    def test_dates_invalides_ignorees_avec_message(self):
        r = self.client.get(LISTE, {"inscrit_du": "31/02/2026", "role": "ORGANISATEUR"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([u.username for u in r.context["object_list"]], ["orga"])   # le reste s'applique
        self.assertContains(r, "Filtre ignoré")
        r = self.client.get(LISTE, {"inscrit_du": "2026-05-10", "inscrit_au": "2026-05-01"})
        self.assertContains(r, "antérieure à la date de début")

    def test_tri_liste_blanche_et_sens(self):
        self.assertEqual(self.noms(tri="nom; DROP TABLE"), self.noms())             # valeur inconnue : tri par défaut
        asc, desc = self.noms(tri="identifiant"), self.noms(tri="-identifiant")
        self.assertEqual(asc, sorted(asc))
        self.assertEqual(desc, list(reversed(asc)))
        statut = self.noms(tri="-statut")
        self.assertEqual(statut[0], "dormeur")
        connexion = self.noms(tri="connexion")
        self.assertEqual(connexion[:3], ["chef", "part", "orga"])               # plus récente d'abord (chef : force_login)
        self.assertEqual(self.noms(tri="-connexion")[-3:], ["orga", "part", "chef"])
        r = self.client.get(LISTE, {"tri": "nom"})
        self.assertEqual(r.context["colonnes"]["nom"]["aria"], "ascending")
        self.assertIn("tri=-nom", r.context["colonnes"]["nom"]["url"])

    def test_par_page_et_pagination_conserve_les_filtres(self):
        for i in range(25):
            Utilisateur.objects.create_user(f"p{i:02d}", f"p{i}@ex.tn", MDP, role="PARTICIPANT")
        r = self.client.get(LISTE, {"role": "PARTICIPANT", "par_page": 10, "tri": "-identifiant"})
        self.assertEqual(len(r.context["object_list"]), 10)
        self.assertContains(r, "role=PARTICIPANT")
        self.assertIn("par_page=10", r.context["filtres"])
        self.assertIn("tri=-identifiant", r.context["filtres"])
        self.assertEqual(len(self.client.get(LISTE, {"par_page": 50}).context["object_list"]), 32)
        self.assertEqual(self.client.get(LISTE, {"par_page": 999}).context["par_page"], 20)

    def test_puces_supprimables_et_etat_vide(self):
        r = self.client.get(LISTE, {"q": "zzz", "statut": "actif"})
        puces = {p["libelle"]: p["url"] for p in r.context["puces"]}
        self.assertEqual(set(puces), {"Recherche", "Statut"})
        self.assertNotIn("q=", puces["Recherche"])
        self.assertIn("statut=actif", puces["Recherche"])
        self.assertContains(r, "Aucun utilisateur ne correspond")
        self.assertContains(r, "Réinitialiser les filtres")


# =============================================================== Amélioration 3 : tableau / cartes
class VuesTests(Base):
    def test_cartes_memes_donnees_et_memorisation(self):
        tableau = self.noms(role="PARTICIPANT")
        r = self.client.get(LISTE, {"role": "PARTICIPANT", "vue": "cartes"})
        self.assertEqual([u.username for u in r.context["object_list"]], tableau)
        self.assertContains(r, 'class="u-cartes"')
        r = self.client.get(LISTE)                                              # mémorisé en session
        self.assertEqual(r.context["vue"], "cartes")
        self.assertEqual(self.client.get(LISTE, {"vue": "pirate"}).context["vue"], "cartes")
        self.assertEqual(self.client.get(LISTE, {"vue": "tableau"}).context["vue"], "tableau")

    def test_cartes_respectent_les_protections(self):
        r = self.client.get(LISTE, {"vue": "cartes"})
        html = r.content.decode()
        for action in ("modifier", "desactiver", "supprimer"):
            self.assertNotIn(reverse(f"utilisateurs:utilisateur_{action}", args=[self.root.pk]), html)
        self.assertIn(modifier_url(self.part), html)
        self.assertNotIn(f'value="{self.root.pk}" form="u-groupe"', html)        # pas de case pour un compte protégé
        self.assertNotIn(f'value="{self.admin.pk}" form="u-groupe"', html)       # ni pour soi-même


# =============================================================== Amélioration 4 : fiche
class FicheTests(Base):
    def fiche(self, u):
        r = self.client.get(reverse("utilisateurs:utilisateur_detail", args=[u.pk]))
        self.assertEqual(r.status_code, 200)
        return r

    def test_organisateur(self):
        from evenements.models import Categorie, Evenement, Lieu
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=50)
        d = timezone.now() + timedelta(days=3)
        Evenement.objects.create(titre="Gala", categorie=Categorie.objects.create(nom="C"), lieu=lieu,
                                 organisateur=self.orga, date_debut=d, date_fin=d + timedelta(hours=2), capacite=10)
        r = self.fiche(self.orga)
        self.assertEqual(r.context["activite"]["nb_evenements"], 1)
        self.assertContains(r, "Événements organisés")
        self.assertEqual(r.context["fiche_role"]["modules"], [m.label for m in navigation.modules()
                                                              if m.cle != "utilisateurs"])

    def test_participant(self):
        r = self.fiche(self.part)
        self.assertEqual(r.context["activite"]["inscriptions"]["total"], 0)
        self.assertContains(r, "Aucun module de gestion")
        self.assertContains(r, "Depuis la dernière connexion")                  # vu il y a 2 jours
        self.assertContains(self.fiche(self.client_), "Jamais connecté")

    def test_prestataire_avec_et_sans_fiche(self):
        self.assertContains(self.fiche(self.presta), "Aucune fiche rattachée")
        from prestataires.models import Prestataire
        Prestataire.objects.create(nom="Son Pro", compte=self.presta, email="son@ex.tn")
        r = self.fiche(self.presta)
        self.assertEqual(str(r.context["activite"]["prestataire"]["fiche"]), "Son Pro")
        self.assertContains(r, "Préparées, pas encore appliquées")

    def test_client_sans_fonctionnalite_fictive(self):
        r = self.fiche(self.client_)
        self.assertContains(r, "Aucune donnée « client » propre")
        self.assertContains(r, "fonctionnalité future, non disponible")

    def test_compte_protege(self):
        r = self.fiche(self.root)
        self.assertContains(r, "Compte technique protégé")
        self.assertNotContains(r, modifier_url(self.root))


# =============================================================== Amélioration 5 : aperçu du rôle
class ApercuRoleTests(Base):
    def test_catalogue_calcule_depuis_les_regles(self):
        cat = roles.catalogue()
        self.assertEqual(set(cat), set(Utilisateur.Role.values))
        self.assertIn("Utilisateurs", cat["ADMIN"]["modules"])
        self.assertNotIn("Utilisateurs", cat["ORGANISATEUR"]["modules"])
        for r in ("PARTICIPANT", "CLIENT", "PRESTATAIRE"):
            self.assertEqual(cat[r]["modules"], [])
        self.assertTrue(cat["ADMIN"]["gestion_comptes"])
        self.assertFalse(cat["ORGANISATEUR"]["gestion_comptes"])

    def test_formulaires_contiennent_l_apercu(self):
        for url in (reverse("utilisateurs:utilisateur_creer"), modifier_url(self.part)):
            r = self.client.get(url)
            self.assertContains(r, 'id="catalogue-roles"')
            self.assertContains(r, "data-role-apercu")
            self.assertContains(r, "utilisateurs/js/utilisateurs.js")


# =============================================================== Amélioration 6 : confirmation du rôle
class ChangementRoleTests(Base):
    def donnees(self, u, **kw):
        d = {"username": u.username, "email": u.email, "first_name": u.first_name, "last_name": u.last_name,
             "telephone": u.telephone, "role": u.role}
        d.update(kw)
        return d

    def test_etape_de_confirmation_puis_enregistrement(self):
        r = self.client.post(modifier_url(self.part), self.donnees(self.part, role="ORGANISATEUR"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Confirmer le changement")
        self.assertEqual(r.context["confirmation"]["comparaison"]["retires"], [])
        self.assertIn("Événements", r.context["confirmation"]["comparaison"]["accordes"])
        self.part.refresh_from_db()
        self.assertEqual(self.part.role, "PARTICIPANT")                         # rien d'enregistré
        r = self.client.post(modifier_url(self.part), self.donnees(self.part, role="ORGANISATEUR",
                             confirmer_role="ORGANISATEUR", role_initial="PARTICIPANT"))
        self.assertEqual(r.status_code, 302)
        self.part.refresh_from_db()
        self.assertEqual(self.part.role, "ORGANISATEUR")

    def test_modification_ordinaire_sans_confirmation(self):
        r = self.client.post(modifier_url(self.part), self.donnees(self.part, first_name="Nour"))
        self.assertEqual(r.status_code, 302)
        self.part.refresh_from_db()
        self.assertEqual(self.part.first_name, "Nour")

    def test_confirmation_manipulee_ou_perimee(self):
        # confirmation donnée pour un AUTRE rôle que celui envoyé
        r = self.client.post(modifier_url(self.part), self.donnees(self.part, role="ADMIN",
                             confirmer_role="ORGANISATEUR", role_initial="PARTICIPANT"))
        self.assertContains(r, "Confirmer le changement")
        # le rôle a changé entre l'affichage et la confirmation (autre administrateur)
        Utilisateur.objects.filter(pk=self.part.pk).update(role="CLIENT")
        r = self.client.post(modifier_url(self.part), self.donnees(self.part, role="ORGANISATEUR",
                             confirmer_role="ORGANISATEUR", role_initial="PARTICIPANT"))
        self.assertContains(r, "Confirmer le changement")
        self.part.refresh_from_db()
        self.assertEqual(self.part.role, "CLIENT")

    def test_garde_fous_meme_avec_confirmation(self):
        r = self.client.post(modifier_url(self.admin), self.donnees(self.admin, role="PARTICIPANT",
                             confirmer_role="PARTICIPANT", role_initial="ADMIN"))
        self.assertContains(r, "Vous ne pouvez pas retirer votre propre rôle")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "ADMIN")
        r = self.client.post(modifier_url(self.root), self.donnees(self.root, role="PARTICIPANT",
                             confirmer_role="PARTICIPANT", role_initial=self.root.role))
        self.assertEqual(r.status_code, 403)                                    # compte protégé

    def test_un_admin_retrograde_un_autre_apres_confirmation(self):
        adj = Utilisateur.objects.create_user("adj", "adj@ex.tn", MDP, role="ADMIN")
        self.client.force_login(adj)
        r = self.client.post(modifier_url(self.admin), self.donnees(self.admin, role="ORGANISATEUR"))
        self.assertTrue(r.context["confirmation"]["gestion_comptes_retiree"])
        r = self.client.post(modifier_url(self.admin), self.donnees(self.admin, role="ORGANISATEUR",
                             confirmer_role="ORGANISATEUR", role_initial="ADMIN"))
        self.assertEqual(r.status_code, 302)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "ORGANISATEUR")

    def test_avertissement_evenements_organises(self):
        from evenements.models import Categorie, Evenement, Lieu
        lieu = Lieu.objects.create(nom="L", adresse="a", ville="Tunis", capacite=50)
        d = timezone.now() + timedelta(days=3)
        Evenement.objects.create(titre="Gala", categorie=Categorie.objects.create(nom="C"), lieu=lieu,
                                 organisateur=self.orga, date_debut=d, date_fin=d + timedelta(hours=2), capacite=10)
        r = self.client.post(modifier_url(self.orga), self.donnees(self.orga, role="PARTICIPANT"))
        c = r.context["confirmation"]
        self.assertEqual(c["donnees"]["Événements organisés"], 1)
        self.assertIn("dont 1 à venir", c["avertissements"][0])
        self.assertIn("Événements", c["comparaison"]["retires"])


# =============================================================== Amélioration 7 : actions groupées
class ActionsGroupeesTests(Base):
    def poster(self, action, ids, confirmer=False, retour="role=PARTICIPANT&statut=actif", client=None):
        d = {"action": action, "ids": [str(i) for i in ids], "retour": retour}
        if confirmer:
            d["confirmer"] = "1"
        return (client or self.client).post(GROUPE, d)

    def actifs(self, *comptes):
        return [Utilisateur.objects.get(pk=c.pk).is_active for c in comptes]

    def test_recapitulatif_sans_modification_puis_confirmation(self):
        r = self.poster("desactiver", [self.part.pk, self.orga.pk, self.inactif.pk])
        self.assertEqual(r.status_code, 200)
        a = r.context["analyse"]
        self.assertEqual((len(a["a_modifier"]), len(a["deja"]), a["bloquant"]), (2, 1, False))
        self.assertEqual(self.actifs(self.part, self.orga), [True, True])        # rien de modifié
        r = self.poster("desactiver", [self.part.pk, self.orga.pk, self.inactif.pk], confirmer=True)
        self.assertRedirects(r, LISTE + "?role=PARTICIPANT&statut=actif", fetch_redirect_response=False)
        self.assertEqual(self.actifs(self.part, self.orga), [False, False])
        self.assertIn("2 comptes désactivés. 1 déjà dans ce statut (inchangé).", self.msgs(r))
        r = self.poster("activer", [self.part.pk, self.orga.pk], confirmer=True)
        self.assertEqual(self.actifs(self.part, self.orga), [True, True])

    def test_tout_ou_rien_soi_meme_ou_compte_protege(self):
        for ids in ([self.part.pk, self.admin.pk], [self.part.pk, self.root.pk]):
            r = self.poster("desactiver", ids)
            self.assertTrue(r.context["analyse"]["bloquant"])
            self.assertNotContains(r, 'name="confirmer"')
            r = self.poster("desactiver", ids, confirmer=True)                  # requête forgée
            self.assertEqual(self.actifs(self.part), [True])
            self.assertIn("Aucun compte n'a été modifié", " ".join(self.msgs(r)))

    def test_dernier_administrateur_actif(self):
        adj = Utilisateur.objects.create_user("adj", "adj@ex.tn", MDP, role="ADMIN")
        # L'acteur reste admin : désactiver tous les AUTRES administrateurs est permis…
        r = self.poster("desactiver", [adj.pk, self.part.pk])
        self.assertFalse(r.context["analyse"]["bloquant"])
        # … et la règle « au moins un admin actif après l'opération » reste vérifiée sur l'ensemble :
        # si l'acteur n'est plus admin actif en base (changé entre-temps), retirer le dernier est refusé en bloc.
        from django.test import RequestFactory
        from .views import UtilisateurActionGroupeeView
        Utilisateur.objects.filter(pk__in=[self.admin.pk, self.root.pk]).update(is_active=False)
        vue = UtilisateurActionGroupeeView()
        vue.request = RequestFactory().post(GROUPE)
        vue.request.user = self.admin
        analyse = vue.analyser("desactiver", [adj.pk])
        self.assertTrue(analyse["bloquant"])
        self.assertIn("plus aucun administrateur", analyse["refuses"][0][1])

    def test_validation_des_identifiants(self):
        r = self.poster("desactiver", ["abc"])
        self.assertIn("Sélection invalide.", self.msgs(r))
        r = self.poster("desactiver", [])
        self.assertIn("Sélectionnez au moins un compte.", self.msgs(r))
        r = self.poster("supprimer", [self.part.pk])
        self.assertIn("Action inconnue.", self.msgs(r))
        r = self.poster("desactiver", list(range(1, 60)))
        self.assertTrue(any("Sélection trop grande" in m for m in self.msgs(r)))
        r = self.poster("desactiver", [self.part.pk, 999999], confirmer=True)    # identifiant inexistant
        self.assertEqual(self.actifs(self.part), [True])

    def test_get_interdit_csrf_et_permissions(self):
        self.assertEqual(self.client.get(GROUPE).status_code, 405)
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        self.assertEqual(c.post(GROUPE, {"action": "desactiver", "ids": [self.part.pk], "confirmer": "1"}).status_code, 403)
        c = Client()
        c.force_login(self.orga)
        self.assertEqual(self.poster("desactiver", [self.part.pk], confirmer=True, client=c).status_code, 403)
        self.assertEqual(self.actifs(self.part), [True])

    def test_retour_ne_peut_pas_sortir_de_la_liste(self):
        r = self.poster("activer", [self.inactif.pk], confirmer=True, retour="//evil.example/?x=1")
        self.assertTrue(r["Location"].startswith(LISTE + "?"))

    def test_revérifie_au_moment_de_la_confirmation(self):
        r = self.poster("desactiver", [self.part.pk])
        self.assertFalse(r.context["analyse"]["bloquant"])
        Utilisateur.objects.filter(pk=self.part.pk).update(is_staff=True)        # devient compte technique entre-temps
        self.poster("desactiver", [self.part.pk], confirmer=True)
        self.assertEqual(self.actifs(self.part), [True])


# =============================================================== Photo : contrôles renforcés
def image(fmt="PNG", taille=(20, 20), nom="photo.png"):
    from PIL import Image
    tampon = io.BytesIO()
    Image.new("RGB", taille, "red").save(tampon, fmt)
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


class PhotoRenforceeTests(Base):
    def formulaire(self, fichier):
        data = {"first_name": "Sara", "last_name": "Z", "email": "part@ex.tn", "telephone": ""}
        return ProfilForm(data, {"photo": fichier}, instance=self.part)

    def test_format_reel_verifie(self):
        f = self.formulaire(image("GIF", nom="faux.png"))
        self.assertFalse(f.is_valid())
        self.assertIn("photo", f.errors)
        self.assertTrue(self.formulaire(image("PNG")).is_valid())
        self.assertTrue(self.formulaire(image("WEBP", nom="ok.webp")).is_valid())

    def test_svg_et_dimensions(self):
        svg = SimpleUploadedFile("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", content_type="image/svg+xml")
        self.assertFalse(self.formulaire(svg).is_valid())
        self.assertFalse(self.formulaire(image("PNG", taille=(4001, 10))).is_valid())
