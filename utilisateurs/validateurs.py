"""Validations des données de compte, partagées par tous les formulaires de la gestion des utilisateurs
(inscription, profil, formulaires de l'administrateur, administration Django, mots de passe)."""
import re
import unicodedata

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------- prénom et nom
SEPARATEURS_NOM = " '’-."


def normaliser_nom(valeur):
    """Supprime les espaces en trop (début, fin, répétitions)."""
    return " ".join((valeur or "").split())


def valider_nom(valeur, libelle="Ce champ"):
    """Lettres de toutes les écritures (accents, arabe…) et leurs signes diacritiques,
    séparées par espace, apostrophe, trait d'union ou point. Pas de chiffres ni de balises."""
    v = normaliser_nom(valeur)
    if not v:
        return v
    if any(not (unicodedata.category(c)[0] in "LM" or c in SEPARATEURS_NOM) for c in v):
        raise ValidationError(f"{libelle} ne peut contenir que des lettres, des espaces, des apostrophes, "
                              "des traits d'union ou des points.", code="nom_invalide")
    if not unicodedata.category(v[0]).startswith("L") or re.search(r"[ '’\-.]{2,}", v.replace(". ", ".")):
        raise ValidationError(f"{libelle} doit commencer par une lettre et ne pas enchaîner plusieurs séparateurs.",
                              code="nom_invalide")
    return v


# ---------------------------------------------------------------- téléphone
TELEPHONE_TN = re.compile(r"(?:\+216|00216)?[2-9]\d{7}")


def valider_telephone(valeur):
    """Numéro tunisien : 8 chiffres (premier chiffre de 2 à 9), préfixe +216 ou 00216 facultatif.
    Espaces, points et tirets acceptés entre les chiffres. Valeur vide autorisée (champ facultatif)."""
    v = (valeur or "").strip()
    if v and not TELEPHONE_TN.fullmatch(re.sub(r"[\s.\-]", "", v)):
        raise ValidationError("Saisissez un numéro tunisien valide : 8 chiffres, avec ou sans +216 "
                              "(ex. 22 123 456 ou +216 22 123 456).", code="telephone_invalide")
    return v


# ---------------------------------------------------------------- identifiant
def valider_identifiant(valeur):
    """« @ » est réservé aux adresses e-mail : la connexion accepte l'identifiant OU l'e-mail."""
    if "@" in (valeur or ""):
        raise ValidationError("L'identifiant ne peut pas contenir « @ » : il serait confondu avec une adresse "
                              "e-mail lors de la connexion.", code="identifiant_ambigu")
    return valeur


# ---------------------------------------------------------------- mot de passe
LONGUEUR_MIN_INFO = 4   # en dessous, trop de faux positifs (ex. « Ali » dans « Salimata2026 »)


def valider_mdp_infos_personnelles(mot_de_passe, user):
    """Complète UserAttributeSimilarityValidator de Django (qui accepte « sara12345 » pour « sara ») :
    le mot de passe ne doit pas CONTENIR l'identifiant, le prénom, le nom ou la partie locale de l'e-mail."""
    if not mot_de_passe or user is None:
        return
    mdp = mot_de_passe.casefold()
    email = (getattr(user, "email", "") or "").split("@")[0]
    infos = [getattr(user, "username", ""), getattr(user, "first_name", ""), getattr(user, "last_name", ""), email]
    mdp_compact = re.sub(r"[\s'’\-._]+", "", mdp)
    for info in infos:
        info = (info or "").casefold()
        morceaux = [*re.split(r"[\s'’\-._]+", info), re.sub(r"[\s'’\-._]+", "", info)]   # « Ben Ali » → benali
        for morceau in morceaux:
            if len(morceau) >= LONGUEUR_MIN_INFO and (morceau in mdp or morceau in mdp_compact):
                raise ValidationError("Le mot de passe ne doit pas contenir votre identifiant, votre nom ou votre "
                                      "adresse e-mail.", code="mdp_infos_personnelles")
