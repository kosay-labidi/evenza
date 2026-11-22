from django import forms

from .models import Seance


class SeanceForm(forms.ModelForm):
    titre = forms.CharField(
        max_length=30,
        error_messages={"max_length": "Le titre doit avoir au plus 30 caractères."},
        widget=forms.TextInput(attrs={"autocomplete": "off", "maxlength": 30}),
    )

    class Meta:
        model = Seance
        fields = ("titre", "description", "date")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "date": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self.fields["date"].input_formats = ["%Y-%m-%dT%H:%M"]
