from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ScheduledSocialPost


class ScheduledSocialPostForm(forms.ModelForm):
    preview = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput())
    session = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ScheduledSocialPost
        fields = ["session", "template_text", "scheduled_time"]
        widgets = {
            "template_text": forms.Textarea(attrs={"rows": 4}),
            "scheduled_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        event = kwargs.pop("event", None)
        super().__init__(*args, **kwargs)
        if event is not None:
            # Only sessions belonging to this event - defer queryset evaluation
            from eventyay.base.models import Submission
            self.fields["session"].queryset = Submission.objects.filter(event=event)

    def clean_template_text(self):
        t = self.cleaned_data.get("template_text", "")
        if not t.strip():
            raise forms.ValidationError(_("Template text cannot be empty"))
        return t
