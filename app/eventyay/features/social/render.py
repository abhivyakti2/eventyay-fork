from typing import Dict


class SafeDict(dict):
    def __missing__(self, key):
        return ""


def render_template_text(template: str, context: Dict) -> str:
    """Render a simple template with placeholders like {event_name}, {session_title}, {speaker_name}, {start_time}.

    Uses Python str.format_map with a SafeDict so missing keys render as empty strings.
    This keeps the behaviour simple and safe for the MVP.
    """
    return template.format_map(SafeDict(context or {}))
