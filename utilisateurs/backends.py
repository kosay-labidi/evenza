"""Connexion avec le nom d'utilisateur OU l'adresse e-mail."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOuUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and "@" in username:
            u = get_user_model().objects.filter(email__iexact=username).order_by("pk").first()
            if u:
                user = super().authenticate(request, username=u.get_username(), password=password, **kwargs)
                if user is not None:
                    return user
            # Repli : un ANCIEN identifiant contenant « @ » (interdit pour les nouveaux comptes)
            # doit pouvoir se connecter même si la même chaîne est l'e-mail d'un autre compte.
        return super().authenticate(request, username=username, password=password, **kwargs)
