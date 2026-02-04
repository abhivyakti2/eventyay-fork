from django.db import models
from django.utils.translation import gettext_lazy as _

from eventyay.base.models import Event, User
from eventyay.base.models.submission import Submission


class ScheduledSocialPost(models.Model):
    class Platforms(models.TextChoices):
        TWITTER = "twitter", _("Twitter")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(Submission, on_delete=models.SET_NULL, null=True, blank=True)

    platform = models.CharField(max_length=32, choices=Platforms.choices, default=Platforms.TWITTER)

    template_text = models.TextField(help_text="Template text with placeholders")
    rendered_text = models.TextField(blank=True, null=True)

    scheduled_time = models.DateTimeField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.get_platform_display()}] {self.template_text[:40]}"
