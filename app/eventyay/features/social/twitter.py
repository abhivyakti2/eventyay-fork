import logging

import requests
from requests_oauthlib import OAuth1
from django.conf import settings

logger = logging.getLogger(__name__)


def post_to_twitter(text: str, token, token_secret=None):
    """Post `text` to Twitter. Supports OAuth1 (token+token_secret) and OAuth2 bearer token.

    Returns: dict response on success, raises Exception on failure.
    """
    if token_secret:
        # OAuth1. Use 1.1 endpoint for status update for widest compat.
        auth = OAuth1(
            settings.TWITTER_CLIENT_ID,
            client_secret=settings.TWITTER_CLIENT_SECRET,
            resource_owner_key=token,
            resource_owner_secret=token_secret,
        )
        url = "https://api.twitter.com/1.1/statuses/update.json"
        resp = requests.post(url, auth=auth, data={"status": text})
    else:
        # Assume token is a bearer token with write permission and use v2 tweets endpoint
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = "https://api.twitter.com/2/tweets"
        resp = requests.post(url, headers=headers, json={"text": text})

    try:
        resp.raise_for_status()
    except Exception as e:  # pragma: no cover - network behaviour
        logger.exception("Twitter posting failed: %s", e)
        raise
    return resp.json()
