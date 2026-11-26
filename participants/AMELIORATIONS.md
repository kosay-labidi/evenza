# Évenza · participants/ : cahier des charges des améliorations

Usage : « Lis participants/AMELIORATIONS.md et fais l'amélioration N ».

## Règle absolue (sans aucune exception)
- Aucun fichier en dehors de `participants/` ne doit être modifié, créé ou supprimé. Cela inclut `settings.py`, `requirements.txt`, `core/`, `evenements/`, `utilisateurs/`, `templates/`, `static/` et tous les fichiers à la racine.
- Ne rien installer : pas de `pip install`, pas de nouvelle bibliothèque Python.
- Si une fonctionnalité demande un changement hors de `participants/`, on ne le fait pas. On réalise une version limitée qui tient entièrement dans `participants/`, ou on abandonne cette partie. On l'écrit dans « Limites ». On ne demande pas l'autorisation : la réponse est toujours non.
- On peut lire les autres applications et utiliser ce qu'elles fournissent déjà (modèles, gabarits de base, mixins), sans jamais les modifier.

## Règles de travail
- Ne pas modifier `ReservationView`, `InscrireView`, `ReservationForm`, `Inscription.inscrire()` ni `Inscription.annuler()`.
- Pas de nouvelle migration : les champs existants suffisent.
- Chaque nouvelle vue a un test d'accès autorisé et un test de refus.
- Fin de chaque amélioration : lancer `python manage.py test` et `python manage.py check`, vérifier avec `git status` que seul `participants/` a changé (sinon annuler le changement fait ailleurs), cocher la case, ne pas faire de commit.
- Gabarits : `list_base.html`, `detail_base.html`, `form_base.html`, `confirm_base.html` (dans `templates/`, lecture seule). Nommage des routes : `<objet>_liste`, `_detail`, `_modifier`, `_supprimer`.

### Repères du code existant (pour ne pas réexplorer)
- Modèles (`models.py`) : `TypeBillet` (evenement, nom, prix, quota, `vendus`, `restants`), `Inscription`, `Avis` (OneToOne vers Inscription).
- `Inscription` : evenement, participant, date_inscription, statut (`CONFIRMEE`, `ATTENTE`, `ANNULEE`), type_billet, quantite, montant, `code_billet` (UUID unique), present. Une seule ligne par (evenement, participant), même annulée.
- Méthodes : `inscrire()`, `annuler()`, `modifier()`, `_promouvoir_liste_attente()`, `motif_refus_modification()`, `modifiable`, `peut_donner_avis`, `code_court`, `get_absolute_url()` (page du billet).
- La liste d'attente est servie par `date_inscription` puis `pk`. Garder cet ordre partout.
- Lecture seule : `Evenement` (titre, date_debut, date_fin, capacite, prix, lieu avec nom/adresse/ville, organisateur, `places_restantes`, `get_absolute_url()`), `Utilisateur` (username, email, role, `est_admin`, `est_organisateur`).
- Permissions : `core.permissions.evenements_geres(user)`. Mixins de `core.mixins` : `ModuleRequiredMixin` (module="participants"), `ProprietaireEvenementMixin` (définir `get_evenement()`), `SuppressionMixin`.
- Routes (`participants:`) : index, mes_inscriptions, inscrire, reserver, inscription_liste, inscription_detail, inscription_modifier, annuler, inscription_annuler, inscription_checkin_annuler, typebillet_liste, typebillet_detail, typebillet_modifier, typebillet_supprimer, type_creer, liste (inscrits d'un événement), checkin, avis, avis_liste, avis_detail, avis_modifier, avis_supprimer, billet.
- Gabarits (`participants/templates/participants/`) : `billet`, `mes_inscriptions`, `checkin`, `inscription_list`, `inscription_detail`, `reservation_choix`, `reservation_recap`, `reservation_modifier`, `inscription_confirm_annuler`, `typebillet_*`, `avis_*`, `index`.
- Tests (`tests.py`) : la classe `GestionBase` fournit les comptes adm, org, org2, a, b (mot de passe `MDP`), les événements e (organisateur org) et e2 (org2), les types vip, std, autre_type, `login(nom)` et `termine()`. En hériter.
- Fichiers Python déjà présents : `apps.py`, `admin.py`, `forms.py`, `navigation.py`. Pas encore de `signals.py` ni de dossier `static/`.

## Améliorations

### [x] 1. Position dans la liste d'attente
- Objectif : le participant voit « Vous êtes Xe sur la liste d'attente » (« 1er » pour la première place).
- Règles : position = nombre de réservations en attente du même événement inscrites avant, plus un. Même ordre que la promotion. Affichée seulement si le statut est `ATTENTE`. Réservation promue ou annulée : plus d'affichage.
- Fichiers : `models.py` (propriété `position_attente`, None si pas en attente), `templates/participants/mes_inscriptions.html`, `templates/participants/billet.html`. Dans `MesInscriptionsView`, éviter une requête par ligne si possible.
- Tests : première, deuxième, promotion après annulation (la position baisse), réservation confirmée (None), réservation d'un autre événement non comptée.

### [ ] 2. Transfert de billet
- Objectif : donner sa réservation confirmée à un autre utilisateur du site, trouvé par nom d'utilisateur ou e-mail (insensible à la casse, correspondance exacte).
- Règles : seulement la réservation du participant connecté, statut `CONFIRMEE`, `present` faux, événement non commencé. Le destinataire est actif, différent de l'expéditeur, sans réservation active pour cet événement. S'il a une ligne annulée pour l'événement, la supprimer dans la même transaction (la contrainte d'unicité l'impose). Un nouveau `code_billet` est généré : l'ancien ne marche plus. Type, quantité, montant et date d'inscription sont conservés.
- Mécanique : nouvelle méthode de modèle `transferer(destinataire)`, avec transaction et verrou sur l'événement comme `inscrire()`. Page de confirmation (GET) avant le transfert (POST), avec messages clairs.
- Fichiers : `models.py`, `forms.py` (formulaire de recherche du destinataire), `views.py`, `urls.py` (`inscription_transferer`), `templates/participants/inscription_transfert.html`, bouton dans `mes_inscriptions.html`.
- Tests : succès (nouveau code, ancien code introuvable sur `billet`), destinataire inconnu, soi-même, déjà inscrit, ligne annulée du destinataire remplacée, billet scanné, événement commencé, réservation annulée ou en attente, réservation d'un autre (404), anonyme.

### [ ] 3. Ajouter au calendrier (.ics)
- Objectif : télécharger un fichier .ics de l'événement depuis le billet et depuis Mes inscriptions.
- Règles : contenu = titre, début, fin, lieu (nom, adresse, ville), identifiant stable basé sur le code du billet. Dates en UTC, fins de ligne CRLF, caractères spéciaux échappés selon la norme. Aucune bibliothèque. Seulement les réservations du participant connecté, non annulées (404 sinon, y compris pour l'organisateur et l'admin).
- Fichiers : `views.py` (réponse `text/calendar` avec téléchargement), `urls.py` (`billet_ics`), boutons dans `billet.html` et `mes_inscriptions.html`.
- Tests : contenu et en-têtes, caractères spéciaux dans le titre, réservation d'un autre (404), annulée (404), anonyme.

### [ ] 4. Notification de la liste d'attente
- Objectif : quand une réservation passe de `ATTENTE` à `CONFIRMEE`, le participant reçoit un e-mail.
- Règles : signal dans `signals.py`, branché dans `apps.py` (méthode `ready`). Mémoriser l'ancien statut avant l'enregistrement, détecter la transition après. Envoi différé après validation de la transaction. Ne pas modifier `annuler()`. Utiliser la configuration e-mail existante telle quelle, sans rien ajouter dans `settings.py`. Pas d'e-mail pour une création, un passage vers un autre statut, ni si le participant n'a pas d'adresse. Un échec d'envoi ne doit jamais faire échouer l'annulation.
- Fichiers : `signals.py` (nouveau), `apps.py`, éventuellement gabarit de texte dans `templates/participants/`.
- Tests (boîte mail de test de Django) : promotion par `annuler()` envoie un e-mail, promotion par `modifier()` aussi, création directe en `CONFIRMEE` n'en envoie pas, pas d'adresse, annulation simple sans e-mail, contenu (événement, date, lien vers le billet).

### [ ] 5. Scan du QR code avec la caméra
- Objectif : sur la page de check-in, un bouton ouvre la caméra, lit le QR code du billet et envoie le code comme la saisie manuelle. La saisie manuelle reste disponible.
- Règles : le QR contient le code complet du billet, déjà accepté par `CheckinForm`. Le scan remplit le champ `code` et envoie le formulaire existant (aucune nouvelle logique serveur). Bibliothèque JS en version fixe, copiée dans `participants/static/participants/`. Si la caméra est refusée ou indisponible, message clair et saisie manuelle. La caméra ne marche qu'en localhost ou en https.
- Fichiers : `participants/static/participants/<bibliothèque>.min.js` (nouveau), `templates/participants/checkin.html` (chargement du script, zone vidéo, bouton). Vérifier que le gabarit parent permet d'ajouter un script, sinon l'inclure dans le contenu.
- Tests : la page de check-in contient le bouton et référence le fichier statique, le fichier est trouvé par les finders statiques, accès organisateur et refus participant. Le scan lui-même est un test manuel.

### [ ] 6. Tableau de bord de l'événement
- Objectif : page pour l'organisateur de l'événement (ou l'admin) avec 4 graphiques Chart.js.
- Règles : calculs dans la vue, données passées en JSON. Taux de remplissage = places confirmées / capacité. Revenus par type de billet = somme des montants des réservations confirmées (« Entrée » quand il n'y a pas de type). Taux de présence = réservations confirmées avec `present` / réservations confirmées. Réservations par jour = nombre de réservations par date d'inscription. Gérer l'absence de données (événement vide, capacité nulle). Chart.js en version fixe, copié dans `participants/static/participants/`.
- Fichiers : `views.py` (`ProprietaireEvenementMixin`), `urls.py` (`tableau_de_bord`, ex. `evenement/<pk>/tableau-de-bord/`), `templates/participants/evenement_tableau.html`, lien dans `templates/participants/inscription_list.html` (quand un événement est fixé) et éventuellement `index.html`.
- Tests : chiffres exacts sur un jeu de données connu, événement sans inscription, organisateur propriétaire et admin autorisés, autre organisateur et participant en 403, anonyme redirigé.

## Limites
À mettre à jour après chaque amélioration. Déjà connues :
- Pas de lien vers ces pages dans le menu principal ni sur la page de l'événement (`evenement_detail.html` appartient à `evenements/`). Les accès passent par le module Participants et Mes billets.
- Les avis ne sont pas affichés sur la page publique de l'événement.
- Le menu « Mes billets » n'est pas surligné sur les nouvelles pages personnelles (`inscription_modifier`, `avis_detail`, `avis_modifier`, `avis_supprimer` et les futures) : la liste `urls_actives` est dans `core/navigation.py`. Effet purement visuel.
- `ORGANISATION_EQUIPE.md` (section 8) ne reflète pas ces nouveautés : il appartient à l'équipe.
- Amélioration 4 : si la configuration e-mail du projet n'envoie pas réellement de courrier (console par exemple), le participant ne reçoit rien en dehors des tests.
- Amélioration 5 : nécessite d'obtenir le fichier JS de la bibliothèque une fois (téléchargement), puis il est servi localement.
- Amélioration 6 : lien seulement depuis les pages de `participants/`.
