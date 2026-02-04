"""
Tests for Social Media Scheduling MVP.

Covers:
- Template rendering logic
- Background execution of scheduled posts
- Organiser UI preview functionality
"""

import datetime as dt

import pytest
from django.utils.timezone import now

from django_scopes import scope, scopes_disabled

from eventyay.base.models import User
from eventyay.base.models import Event
from eventyay.base.models import Submission

from eventyay.features.social.models import ScheduledSocialPost
from eventyay.features.social.render import render_template_text
from eventyay.features.social.tasks import run_due_posts


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_user():
    """Create a test user."""
    with scopes_disabled():
        return User.objects.create_user(
            email="testuser@example.com", password="testpassw0rd!"
        )


@pytest.fixture
def test_event():
    """Create a test event."""
    with scopes_disabled():
        return Event.objects.create(
            name="Test Conference",
            slug="testconf",
            is_public=True,
            email="orga@orga.org",
            locale="en",
            date_from=dt.date.today(),
            date_to=dt.date.today() + dt.timedelta(days=1),
        )


@pytest.fixture
def test_session(test_event, test_user):
    """Create a test submission/session."""
    with scope(event=test_event):
        submission = Submission.objects.create(
            event=test_event,
            title="Test Talk",
            submission_type=test_event.cfp.default_type,
            content_locale="en",
        )
        submission.speakers.add(test_user)
        return submission


@pytest.fixture
def scheduled_post(test_event, test_session, test_user):
    """Create a scheduled social post."""
    with scope(event=test_event):
        post = ScheduledSocialPost.objects.create(
            event=test_event,
            session=test_session,
            created_by=test_user,
            template_text="Join us for {session_title} by {speaker_name} at {event_name}! Start: {start_time}",
            scheduled_time=now() - dt.timedelta(hours=1),  # Past time - due for posting
            status=ScheduledSocialPost.Status.PENDING,
        )
        return post


# =============================================================================
# Template Rendering Tests
# =============================================================================

class TestTemplateRendering:
    """Tests for the render_template_text function."""

    def test_basic_placeholders_render(self):
        """Test that all placeholders render correctly when provided."""
        context = {
            "event_name": "Python Conference 2024",
            "session_title": "Introduction to Testing",
            "speaker_name": "Jane Doe",
            "start_time": "2024-10-15T10:00:00",
        }
        template = "Join us for {session_title} by {speaker_name} at {event_name}! Start: {start_time}"
        
        result = render_template_text(template, context)
        
        expected = "Join us for Introduction to Testing by Jane Doe at Python Conference 2024! Start: 2024-10-15T10:00:00"
        assert result == expected

    def test_missing_placeholders_render_empty(self):
        """Test that missing placeholders render as empty strings without raising exceptions."""
        context = {
            "event_name": "Python Conference 2024",
            # session_title, speaker_name, start_time are missing
        }
        template = "Event: {event_name} | Session: {session_title} | Speaker: {speaker_name} | Time: {start_time}"
        
        # This should NOT raise KeyError
        result = render_template_text(template, context)
        
        assert result == "Event: Python Conference 2024 | Session:  | Speaker:  | Time: "

    def test_empty_context_renders_empty_strings(self):
        """Test that empty context renders all placeholders as empty strings."""
        template = "Event: {event_name} | Session: {session_title} | Speaker: {speaker_name} | Time: {start_time}"
        
        result = render_template_text(template, {})
        
        expected = "Event:  | Session:  | Speaker:  | Time: "
        assert result == expected

    def test_none_context_handled_gracefully(self):
        """Test that None context is handled gracefully."""
        template = "Event: {event_name}"
        
        # Should not raise exception when context is None
        result = render_template_text(template, None)
        
        assert result == "Event: "

    def test_template_without_placeholders(self):
        """Test template without any placeholders returns unchanged."""
        context = {
            "event_name": "Python Conference 2024",
        }
        template = "This is a static message with no placeholders"
        
        result = render_template_text(template, context)
        
        assert result == template

    def test_special_characters_in_context(self):
        """Test that special characters in context values are preserved."""
        context = {
            "event_name": "Conference with 'quotes' & \"double quotes\"",
            "session_title": "Talk with\nnewlines\rand\ttabs",
            "speaker_name": "User with <tags> and &ampersands",
        }
        template = "{event_name} - {session_title} by {speaker_name}"
        
        result = render_template_text(template, context)
        
        assert "Conference with 'quotes'" in result
        assert '"double quotes"' in result
        assert "newlines" in result
        assert "tabs" in result
        assert "<tags>" in result

    def test_partial_context_with_some_values(self):
        """Test rendering with only some placeholders provided."""
        context = {
            "event_name": "Tech Summit",
            "speaker_name": "John Smith",
            # session_title and start_time missing
        }
        template = "Check out {event_name} featuring {speaker_name} in {session_title} at {start_time}"
        
        result = render_template_text(template, context)
        
        expected = "Check out Tech Summit featuring John Smith in  at "
        assert result == expected


# =============================================================================
# Background Execution Tests
# =============================================================================

class TestBackgroundExecution:
    """Tests for run_due_posts function."""

    @pytest.mark.django_db
    def test_post_sent_successfully_with_valid_token(
        self, scheduled_post, test_user, mocker
    ):
        """Test that post is marked SENT when token exists and API call succeeds."""
        # Mock Twitter API call
        mock_post = mocker.patch(
            "eventyay.features.social.tasks.post_to_twitter",
            return_value={"id": "12345"}
        )

        # Create SocialAccount and SocialToken for the user
        from allauth.socialaccount.models import SocialAccount, SocialToken
        
        with scopes_disabled():
            social_account = SocialAccount.objects.create(
                user=test_user,
                provider="twitter",
                uid="12345"
            )
            SocialToken.objects.create(
                account=social_account,
                token="mock_token",
                token_secret="mock_token_secret"
            )

        # Run the task
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify post was sent successfully
        assert scheduled_post.status == ScheduledSocialPost.Status.SENT
        assert scheduled_post.error_message == ""
        assert "Join us for" in scheduled_post.rendered_text
        mock_post.assert_called_once()

    @pytest.mark.django_db
    def test_post_marked_failed_when_no_twitter_account(
        self, scheduled_post, test_user, mocker
    ):
        """Test that post is marked FAILED when no Twitter account is connected."""
        # Ensure no SocialAccount exists for the user
        from allauth.socialaccount.models import SocialAccount
        SocialAccount.objects.filter(user=test_user).delete()

        # Run the task
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify post was marked as failed
        assert scheduled_post.status == ScheduledSocialPost.Status.FAILED
        assert "No connected Twitter account" in scheduled_post.error_message

    @pytest.mark.django_db
    def test_post_marked_failed_when_api_raises_exception(
        self, scheduled_post, test_user, mocker
    ):
        """Test that post is marked FAILED when Twitter API raises an exception."""
        # Create SocialAccount and SocialToken
        from allauth.socialaccount.models import SocialAccount, SocialToken
        
        with scopes_disabled():
            social_account = SocialAccount.objects.create(
                user=test_user,
                provider="twitter",
                uid="12345"
            )
            SocialToken.objects.create(
                account=social_account,
                token="mock_token",
                token_secret="mock_token_secret"
            )

        # Mock Twitter API to raise exception
        mock_post = mocker.patch(
            "eventyay.features.social.tasks.post_to_twitter",
            side_effect=Exception("Twitter API error: Rate limit exceeded")
        )

        # Run the task
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify post was marked as failed
        assert scheduled_post.status == ScheduledSocialPost.Status.FAILED
        assert "Twitter API error" in scheduled_post.error_message
        mock_post.assert_called_once()

    @pytest.mark.django_db
    def test_post_not_processed_when_scheduled_time_in_future(
        self, scheduled_post, test_user, mocker
    ):
        """Test that posts with future scheduled time are not processed."""
        # Update scheduled time to future
        future_time = now() + dt.timedelta(hours=1)
        scheduled_post.scheduled_time = future_time
        scheduled_post.save()

        # Mock Twitter API call
        mock_post = mocker.patch(
            "eventyay.features.social.tasks.post_to_twitter",
            return_value={"id": "12345"}
        )

        # Run the task with current time
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify post is still pending and API was not called
        assert scheduled_post.status == ScheduledSocialPost.Status.PENDING
        mock_post.assert_not_called()

    @pytest.mark.django_db
    def test_post_status_transition_pending_to_sent(self, scheduled_post, test_user, mocker):
        """Test correct status transition: PENDING -> SENT."""
        from allauth.socialaccount.models import SocialAccount, SocialToken
        
        with scopes_disabled():
            social_account = SocialAccount.objects.create(
                user=test_user,
                provider="twitter",
                uid="12345"
            )
            SocialToken.objects.create(
                account=social_account,
                token="mock_token",
                token_secret="mock_token_secret"
            )

        mocker.patch(
            "eventyay.features.social.tasks.post_to_twitter",
            return_value={"id": "12345"}
        )

        # Initial status should be PENDING
        assert scheduled_post.status == ScheduledSocialPost.Status.PENDING

        # Run the task
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify status transitioned to SENT
        assert scheduled_post.status == ScheduledSocialPost.Status.SENT

    @pytest.mark.django_db
    def test_post_status_transition_pending_to_failed(
        self, scheduled_post, test_user, mocker
    ):
        """Test correct status transition: PENDING -> FAILED."""
        from allauth.socialaccount.models import SocialAccount
        
        # Ensure no SocialAccount exists
        SocialAccount.objects.filter(user=test_user).delete()

        # Initial status should be PENDING
        assert scheduled_post.status == ScheduledSocialPost.Status.PENDING

        # Run the task
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify status transitioned to FAILED
        assert scheduled_post.status == ScheduledSocialPost.Status.FAILED

    @pytest.mark.django_db
    def test_post_with_bearer_token_oauth2(self, scheduled_post, test_user, mocker):
        """Test posting with OAuth2 bearer token (no token_secret)."""
        from allauth.socialaccount.models import SocialAccount, SocialToken
        
        with scopes_disabled():
            social_account = SocialAccount.objects.create(
                user=test_user,
                provider="twitter_oauth2",
                uid="12345"
            )
            # OAuth2 uses bearer token (no token_secret)
            SocialToken.objects.create(
                account=social_account,
                token="bearer_token_mock"
            )

        mock_post = mocker.patch(
            "eventyay.features.social.tasks.post_to_twitter",
            return_value={"data": {"id": "67890"}}
        )

        # Run the task
        run_due_posts(now_dt=now())

        # Refresh from database
        scheduled_post.refresh_from_db()

        # Verify post was sent
        assert scheduled_post.status == ScheduledSocialPost.Status.SENT
        # Verify called with bearer token (no token_secret)
        mock_post.assert_called_once_with(scheduled_post.rendered_text, "bearer_token_mock")

    @pytest.mark.django_db
    def test_multiple_posts_processed(self, test_event, test_user, test_session, mocker):
        """Test that multiple due posts are processed in one run."""
        from allauth.socialaccount.models import SocialAccount, SocialToken
        
        with scopes_disabled():
            social_account = SocialAccount.objects.create(
                user=test_user,
                provider="twitter",
                uid="12345"
            )
            SocialToken.objects.create(
                account=social_account,
                token="mock_token",
                token_secret="mock_token_secret"
            )

        mock_post = mocker.patch(
            "eventyay.features.social.tasks.post_to_twitter",
            return_value={"id": "12345"}
        )

        # Create multiple scheduled posts
        with scope(event=test_event):
            posts = []
            for i in range(3):
                post = ScheduledSocialPost.objects.create(
                    event=test_event,
                    session=test_session,
                    created_by=test_user,
                    template_text=f"Post {i}: {{event_name}}",
                    scheduled_time=now() - dt.timedelta(hours=1),
                    status=ScheduledSocialPost.Status.PENDING,
                )
                posts.append(post)

        # Run the task
        run_due_posts(now_dt=now())

        # Verify all posts were processed
        for post in posts:
            post.refresh_from_db()
            assert post.status == ScheduledSocialPost.Status.SENT

        # Verify API was called for each post
        assert mock_post.call_count == 3


# =============================================================================
# Organiser UI Preview Tests
# =============================================================================

class TestPreviewView:
    """Tests for the preview_view function."""

    @pytest.mark.django_db
    def test_preview_success(self, orga_client, test_event, test_session, test_user):
        """Test that preview renders successfully with valid data."""
        with scope(event=test_event):
            # Set session start time for template rendering
            test_session.start = now()
            test_session.save()

        post_data = {
            "session": test_session.pk,
            "template_text": "Join us for {session_title} by {speaker_name}!",
            "scheduled_time": now().isoformat(),
            "preview": "1",
        }

        response = orga_client.post(
            f"/orga/event/{test_event.slug}/settings/social/preview/",
            data=post_data,
        )

        assert response.status_code == 200
        assert "Join us for Test Talk" in response.rendered_content.decode()

    @pytest.mark.django_db
    def test_preview_with_missing_session(
        self, orga_client, test_event, test_user
    ):
        """Test preview handles missing session gracefully."""
        post_data = {
            "session": "",
            "template_text": "Event: {event_name}",
            "scheduled_time": now().isoformat(),
            "preview": "1",
        }

        response = orga_client.post(
            f"/orga/event/{test_event.slug}/settings/social/preview/",
            data=post_data,
        )

        # Should still render with empty session placeholders
        assert response.status_code == 200
        assert "Event: Test Conference" in response.rendered_content.decode()

    @pytest.mark.django_db
    def test_preview_with_invalid_session(
        self, orga_client, test_event, test_user
    ):
        """Test preview handles invalid session ID gracefully."""
        post_data = {
            "session": 99999,  # Non-existent session
            "template_text": "Session: {session_title}",
            "scheduled_time": now().isoformat(),
            "preview": "1",
        }

        response = orga_client.post(
            f"/orga/event/{test_event.slug}/settings/social/preview/",
            data=post_data,
        )

        # Should render with empty placeholder, not crash
        assert response.status_code == 200
        assert "Session:" in response.rendered_content.decode()

    @pytest.mark.django_db
    def test_preview_invalid_form(self, orga_client, test_event):
        """Test preview returns to form on invalid data."""
        post_data = {
            # Missing required fields
            "template_text": "",  # Empty template
            "preview": "1",
        }

        response = orga_client.post(
            f"/orga/event/{test_event.slug}/settings/social/preview/",
            data=post_data,
        )

        # Should render form with errors, not crash
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_preview_redirect_on_get(self, orga_client, test_event):
        """Test that GET request redirects to settings page."""
        response = orga_client.get(
            f"/orga/event/{test_event.slug}/settings/social/preview/"
        )

        assert response.status_code == 302

    @pytest.mark.django_db
    def test_preview_all_placeholders(
        self, orga_client, test_event, test_session, test_user
    ):
        """Test preview renders all placeholders correctly."""
        with scope(event=test_event):
            test_session.start = now()
            test_session.save()

        post_data = {
            "session": test_session.pk,
            "template_text": "Event: {event_name} | Session: {session_title} | Speaker: {speaker_name} | Time: {start_time}",
            "scheduled_time": now().isoformat(),
            "preview": "1",
        }

        response = orga_client.post(
            f"/orga/event/{test_event.slug}/settings/social/preview/",
            data=post_data,
        )

        assert response.status_code == 200
        content = response.rendered_content.decode()
        assert "Event: Test Conference" in content
        assert "Session: Test Talk" in content
        assert "Speaker: testuser@example.com" in content
        # Start time should be present (ISO format)


# =============================================================================
# Model Tests
# =============================================================================

class TestScheduledSocialPostModel:
    """Tests for the ScheduledSocialPost model."""

    @pytest.mark.django_db
    def test_status_choices(self):
        """Test that status choices are correctly defined."""
        assert ScheduledSocialPost.Status.PENDING == "pending"
        assert ScheduledSocialPost.Status.SENT == "sent"
        assert ScheduledSocialPost.Status.FAILED == "failed"

    @pytest.mark.django_db
    def test_platform_choices(self):
        """Test that platform choices are correctly defined."""
        assert ScheduledSocialPost.Platforms.TWITTER == "twitter"

    @pytest.mark.django_db
    def test_string_representation(self, scheduled_post):
        """Test the string representation of the model."""
        str_repr = str(scheduled_post)
        assert "[twitter]" in str_repr
        assert "Join us for" in str_repr

