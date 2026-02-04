import logging
from datetime import datetime

from celery import shared_task
from django.utils.timezone import now
from django.db import transaction
from allauth.socialaccount.models import SocialAccount, SocialToken

from .models import ScheduledSocialPost
from .render import render_template_text
from .twitter import post_to_twitter

logger = logging.getLogger(__name__)


def _get_twitter_token_for_user(user):
    account = SocialAccount.objects.filter(user=user, provider__in=("twitter", "twitter_oauth2")).first()
    if not account:
        return None
    token = SocialToken.objects.filter(account=account).first()
    if not token:
        return None
    # token.token is often the token string; token.token_secret exists for oauth1
    return token


def run_due_posts(now_dt=None):
    now_dt = now_dt or now()
    posts = ScheduledSocialPost.objects.filter(status=ScheduledSocialPost.Status.PENDING, scheduled_time__lte=now_dt)
    for post in posts.select_related("created_by", "event", "session"):
        with transaction.atomic():
            # Re-fetch to lock
            sp = ScheduledSocialPost.objects.select_for_update().get(pk=post.pk)
            if sp.status != ScheduledSocialPost.Status.PENDING:
                continue
            # Prepare context
            ctx = {
                "event_name": sp.event.name,
                "session_title": sp.session.title if sp.session else "",
                "speaker_name": ", ".join([s.user.get_display_name() for s in getattr(sp.session, "speakers", [])]) if sp.session else "",
                "start_time": sp.session.start.isoformat() if getattr(sp.session, "start", None) else "",
            }
            rendered = render_template_text(sp.template_text, ctx)
            sp.rendered_text = rendered
            sp.save(update_fields=["rendered_text"])

            token = None
            if sp.created_by:
                token = _get_twitter_token_for_user(sp.created_by)

            if not token:
                sp.status = ScheduledSocialPost.Status.FAILED
                sp.error_message = "No connected Twitter account for the creator"
                sp.save(update_fields=["status", "error_message"])
                logger.warning("Scheduled social post %s failed: no token", sp.pk)
                continue

            try:
                if token.token_secret:
                    resp = post_to_twitter(sp.rendered_text, token.token, token_secret=token.token_secret)
                else:
                    resp = post_to_twitter(sp.rendered_text, token.token)
            except Exception as e:  # pragma: no cover - network errors
                sp.status = ScheduledSocialPost.Status.FAILED
                sp.error_message = str(e)
                sp.save(update_fields=["status", "error_message"])
                logger.exception("Posting failed for ScheduledSocialPost %s", sp.pk)
            else:
                sp.status = ScheduledSocialPost.Status.SENT
                sp.error_message = ""
                sp.save(update_fields=["status", "error_message"])


@shared_task(bind=True)
def execute_due_posts(self):
    """Celery task that runs due scheduled social posts."""
    run_due_posts()
