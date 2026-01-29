# Eventyay AI Coding Instructions

Eventyay is a unified event management platform integrating **Tickets** (sales, registration), **Talk** (CfP, scheduling), and **Video** (virtual events, streaming) components. All components share a single Django codebase and PostgreSQL database.

## Architecture Overview

### Three Components, One Codebase
- **Tickets**: `presale/` (public shop), `control/` (admin), `base/` models (Order, Product, Organizer, Event)
- **Talk**: `cfp/`, `orga/`, `schedule/`, `submission/` (Call for Papers, scheduling, speaker management)
- **Video**: Features in `base/models/room.py`, WebSocket support via Django Channels

### Shared Infrastructure
All components rely on:
- **Authentication**: Single sign-on via `eventyay.base.models.auth.User` and teams for RBAC
- **REST API**: Unified `/api/v1/` endpoints with DRF, organized by routers in [api/urls.py](app/eventyay/api/urls.py)
- **Services**: Email, payments, storage in `base/services/` and `base/email.py`
- **Database**: PostgreSQL with models in `base/models/` (mandatory for setup)
- **Task Queue**: Celery with Redis (eager mode in tests via `CELERY_TASK_ALWAYS_EAGER`)

### Request Flow
Django middleware chain in [config/settings.py](app/eventyay/config/settings.py):
1. CORS, locale detection, security headers
2. **MultiDomainMiddleware** - handles multi-tenant URL routing
3. **EventPermissionMiddleware** - sets `request.event`, permissions, locales
4. Custom CSRF and session handling
5. **PermissionMiddleware** (control app) - enforces login and event access

## Key Patterns & Conventions

### Models & Queries
- **Location**: All shared models in `base/models/` directory, component-specific models in their app folders
- **Scoping**: Use `django_scopes` for multi-tenant queries: `with scope(event=request.event):`
- **QuerySet methods**: Custom querysets on related managers (see [base/models/room.py](app/eventyay/base/models/room.py))
- **Ordering**: Use `OrderedModel` mixin for positional fields

### API Development
- **Serializers**: Use explicit field definitions, avoid `SerializerMethodField` (hard to infer shape)
- **Permissions**: Custom in `api/auth/api_auth.py` - combine `ApiAccessRequiredPermission` + role checks
- **ViewSets**: Inherit from `viewsets.ModelViewSet` in `api/views/` - use routers for auto-URL generation
- **Pagination**: Built-in via `DefaultRouter` and `pagination.py`
- **Webhook support**: Registered in `api/webhooks.py` with signals

### Async & Background Tasks
- **Celery tasks**: Use `@shared_task` decorator in models' `tasks.py` files (autodiscovered via apps.py)
- **Test mode**: `CELERY_TASK_ALWAYS_EAGER = True` makes tasks synchronous for testing
- **Long-running operations**: Use `AsyncMixin` view helper in `base/views/tasks.py` for polling with `AsyncResult`
- **WebSocket**: Django Channels for real-time video/chat (async context managers in tests)

### Django Commands
- **Location**: `{app}/management/commands/` (e.g., `core/management/commands/create_oauth_application.py`)
- **Pattern**: Declare parameters explicitly in `handle(self, ...)`, not via `options` dict

### Frontend Integration
- **Static assets**: SASS compiled to CSS, JS modules (no jQuery), located in `static/` and `webapp/`
- **i18n**: Use `gettext_lazy` for lazy translation; mark strings with `_()` for extraction
- **Templates**: Jinja2 via `jinja-templates/` and Django templates in component apps

## Testing Structure

### Organization
- **Location**: `tests/` mirrors app structure: `tests/tickets/`, `tests/talk/`, `tests/video/`, `tests/stable/`
- **Fixtures**: Pytest with `@pytest.fixture` (see `conftest.py` files)
- **Database**: Use `@pytest.mark.django_db` for database access

### Common Patterns
```python
# Sync tests - typical pattern
@pytest.mark.django_db
def test_api_endpoint(client, event, organizer):
    response = client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/')
    assert response.status_code == 200

# Async tests - Video component uses Channels
@pytest.mark.asyncio
@pytest.mark.django_db
async def test_websocket(world, client_id):
    communicator = WebsocketCommunicator(application, f'/ws/worlds/{world.slug}/')
    connected = await communicator.connect()
    assert connected
```

## Development Workflow

### Setup
1. **Python**: Requires Python 3.12 (via `uv sync --all-extras --all-groups` in `app/` directory)
2. **Database**: PostgreSQL (peer mode recommended, otherwise `eventyay.local.toml` for credentials)
3. **Redis**: Required for caching and Celery (Celery runs eager in tests)

### Build Commands
- **Make targets** (`app/Makefile`): `make localecompile`, `make staticfiles`, `make test`, `make compress`, `make npminstall`
- **Django commands**: `./manage.py migrate`, `./manage.py runserver`, `./manage.py createsuperuser`
- **Celery**: `celery -A eventyay worker -l info` (or use eager mode for development)

### Testing
```bash
# From app/
pytest tests/  # All tests
pytest tests/tickets/api/  # Specific component
make test  # Via Makefile
```

## Code Style & Logging

### Python ([see .github/instructions/python.instructions.md](.github/instructions/python.instructions.md))
- **Imports**: Top of file only (except circular import exceptions)
- **Logging**: Use logger's string interpolation: `logger.info('User %s logged in', username)` not f-strings
- **Exceptions**: Catch specific exceptions, not generic `Exception`
- **Functions**: Don't use private (`_`) prefix unless strongly needed
- **REST**: Avoid `SerializerMethodField` - use explicit fields for clarity

### JavaScript ([see .github/instructions/js.instructions.md](.github/instructions/js.instructions.md))
- **Modules**: ES modules only, no jQuery, external scripts (not inline due to CSP)
- **Errors**: Preserve library error types (e.g., `HTTPError` from `ky`), add comments for error-throwing functions
- **Async**: Use `try/catch` in async functions, bubble up gracefully

### Git Commits
- **Message**: Concise, one-line summary (enough for most Git clients)
- **Multi-part**: Split with blank line into summary + detailed description if needed
- **Avoid**: Don't explain obvious refactoring ("improve readability") - state what changed

## Important Files & Directories

| Path | Purpose |
|------|---------|
| [app/eventyay/base/](app/eventyay/base/) | Core models, services, shared utilities |
| [app/eventyay/api/](app/eventyay/api/) | REST API viewsets, serializers, auth |
| [app/eventyay/control/](app/eventyay/control/) | Organizer/admin web interface |
| [app/eventyay/presale/](app/eventyay/presale/) | Public ticket shop |
| [app/eventyay/common/](app/eventyay/common/) | Middleware, signals, shared checks |
| [app/eventyay/plugins/](app/eventyay/plugins/) | Payment, badge, PDF plugins |
| [app/eventyay/config/](app/eventyay/config/) | Django settings, ASGI/WSGI |
| [app/pyproject.toml](app/pyproject.toml) | Dependencies (Django 5.2, DRF 3.15, Celery 5.4) |
| [app/Makefile](app/Makefile) | Build automation |
| [doc/development/](doc/development/) | Developer docs: setup, architecture, API |

## Common Tasks

### Add API Endpoint
1. Create serializer in `api/serializers/{component}.py` with explicit fields
2. Create ViewSet in `api/views/{component}.py`, inherit from `viewsets.ModelViewSet`
3. Register in `api/urls.py` router (auto-generates URLs)
4. Add permission class combining API tokens + team/event permissions
5. Write tests in `tests/{component}/api/test_*.py` with `@pytest.mark.django_db`

### Add Django Model
1. Define in `base/models/` (shared) or `{app}/models.py` (component-specific)
2. Add `django_scopes` filtering if multi-tenant
3. Create migration: `./manage.py makemigrations app_name`
4. Run: `./manage.py migrate`

### Add Celery Task
1. Create in `{app}/tasks.py` with `@shared_task` decorator
2. Will auto-discover via app's `apps.py` ready() method
3. Call via `task_name.delay()` or `.apply_async()`
4. Use `AsyncResult` to poll status from views (see [base/views/tasks.py](app/eventyay/base/views/tasks.py))

---

**Last Updated**: January 2026 | For questions, see [doc/development/](doc/development/)
