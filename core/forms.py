from django import forms

from .models import MessageContact


class ContactForm(forms.ModelForm):
    class Meta:
        model = MessageContact
        fields = ("nom", "email", "sujet", "message")
        widgets = {"message": forms.Textarea(attrs={"rows": 5, "placeholder": "Votre message…"}),
                   "nom": forms.TextInput(attrs={"placeholder": "Votre nom"}),
                   "email": forms.EmailInput(attrs={"placeholder": "vous@exemple.tn"})}
