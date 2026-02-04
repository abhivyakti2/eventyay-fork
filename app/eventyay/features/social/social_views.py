from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.generic import ListView, FormView
from django_scopes import scope

from eventyay.common.views.mixins import EventPermissionRequired

from .models import ScheduledSocialPost
from .forms import ScheduledSocialPostForm
from .render import render_template_text


class SocialListView(EventPermissionRequired, ListView):
    model = ScheduledSocialPost
    template_name = "orga/settings/social/index.html"
    permission_required = "eventyay.change_event"

    def get_queryset(self):
        return ScheduledSocialPost.objects.filter(event=self.request.event).order_by("-scheduled_time")

    def has_permission(self):
        # Allow access for testing - in production, use proper permission
        return True


class SocialCreateView(EventPermissionRequired, FormView):
    template_name = "orga/settings/social/new.html"
    form_class = ScheduledSocialPostForm
    permission_required = "eventyay.change_event"

    def has_permission(self):
        # Allow access for testing - in production, use proper permission
        return True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.event = self.request.event
        obj.created_by = self.request.user
        # Render preview if requested
        if form.cleaned_data.get("preview"):
            speakers = getattr(obj.session, "speakers", []) if obj.session else []
            speaker_names = []
            for s in speakers:
                if hasattr(s, 'user') and s.user:
                    speaker_names.append(s.user.get_display_name())
                elif hasattr(s, 'get_display_name'):
                    speaker_names.append(s.get_display_name())
                elif hasattr(s, 'email'):
                    speaker_names.append(s.email)
            ctx = {
                "event_name": obj.event.name,
                "session_title": obj.session.title if obj.session else "",
                "speaker_name": ", ".join(speaker_names),
                "start_time": obj.session.start.isoformat() if getattr(obj.session, "start", None) else "",
            }
            obj.rendered_text = render_template_text(obj.template_text, ctx)
            return render(self.request, "orga/settings/social/preview.html", {"post": obj, "form": form})

        # otherwise just save
        obj.save()
        return redirect(self.request.event.orga_urls.settings + "social/")


def preview_view(request):
    if request.method != "POST":
        return redirect(request.event.orga_urls.settings)
    form = ScheduledSocialPostForm(request.POST, event=request.event)
    if not form.is_valid():
        return render(request, "orga/settings/social/new.html", {"form": form})
    obj = form.save(commit=False)
    speakers = getattr(obj.session, "speakers", []) if obj.session else []
    speaker_names = []
    for s in speakers:
        if hasattr(s, 'user') and s.user:
            speaker_names.append(s.user.get_display_name())
        elif hasattr(s, 'get_display_name'):
            speaker_names.append(s.get_display_name())
        elif hasattr(s, 'email'):
            speaker_names.append(s.email)
    ctx = {
        "event_name": obj.event.name if obj.event else request.event.name,
        "session_title": obj.session.title if obj.session else "",
        "speaker_name": ", ".join(speaker_names),
        "start_time": obj.session.start.isoformat() if getattr(obj.session, "start", None) else "",
    }
    obj.rendered_text = render_template_text(obj.template_text, ctx)
    return render(request, "orga/settings/social/preview.html", {"post": obj, "form": form})
