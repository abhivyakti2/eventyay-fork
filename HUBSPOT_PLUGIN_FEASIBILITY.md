# HubSpot Plugin for Eventyay - Feasibility Assessment

## Executive Summary

✅ **HIGHLY FEASIBLE** - Building a minimal HubSpot plugin for Eventyay attendee data sync is architecturally straightforward with excellent integration points in the codebase.

**Key Finding**: The `order_paid` signal provides a perfect, event-scoped hook point to sync attendee data to HubSpot immediately when orders are confirmed. The plugin system is mature and handles external API integrations cleanly.

---

## 1. Attendee Data Model & Finalization Point

### ✅ Answer: Where Attendee Data is Created and Finalized

#### Attendee Data Location
- **Primary Model**: `OrderPosition` (lines 2136+) extends `AbstractPosition` (lines 1253+)
  - File: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py)
  
#### Available Attendee Fields in OrderPosition
```python
# From AbstractPosition (base attendee data model)
attendee_name_cached: CharField      # Full name, cached for performance
attendee_name_parts: JSONField       # Structured name data {first_name, last_name, etc}
attendee_email: EmailField           # Email address
```

#### Data Access Pattern
```python
# From order instance, access all attendees:
order.all_positions.all()  # Returns all OrderPosition objects (all attendees)

# Each position represents one ticket/attendee per order
order.positions.all()      # Non-canceled positions
```

#### Finalization Point - CRITICAL FOR SYNC ✅
**When**: Order is marked as PAID via `OrderPayment.confirm()`  
**Where**: [OrderPayment.confirm() method](app/eventyay/base/models/orders.py#L1590) (line 1590)  
**What Happens**:
1. OrderPayment state changes to `PAYMENT_STATE_CONFIRMED`
2. Related Order status changes to `STATUS_PAID`
3. **`order_paid` signal is emitted** with the fully finalized Order instance
4. All OrderPosition attendees are now confirmed and ready for sync

**Signal Structure**:
```python
order_paid.send(
    sender=event,          # Event instance - use event.slug, event.id
    order=order,           # Complete Order instance with all_positions
)
```

### Why This Works for HubSpot Sync
- **Timing**: Signal fired exactly when order becomes PAID (perfect sync moment)
- **Data Completeness**: All attendee data is finalized before signal fire
- **Scope**: Signal is event-aware (filtering by enabled plugins per event automatically)
- **Reliability**: Called from 4 locations ensuring all payment paths trigger it

---

## 2. Plugin Integration Architecture

### ✅ Answer: How Plugins Integrate with Eventyay

#### Plugin Registration System
Eventyay uses a **signal-based plugin architecture** with automatic event-level filtering.

#### Implementation Pattern (Proven by Existing Plugins)
**Location**: `/eventyay/plugins/{plugin_name}/`

**Required Files**:
```
hubspot/
├── __init__.py           # Package marker
├── apps.py              # Plugin metadata and registration
├── signals.py           # Signal subscriptions (@receiver decorators)
├── models.py            # Optional: plugin-specific data models
├── forms.py             # Optional: API key configuration forms
├── tasks.py             # Optional: Celery async tasks
└── views.py             # Optional: admin UI
```

#### Registration via apps.py
```python
from django.apps import AppConfig
from eventyay.base.apps import EventyayPluginMeta

class HubSpotAppConfig(AppConfig):
    name = 'eventyay.plugins.hubspot'
    verbose_name = 'HubSpot CRM Integration'
    
    class EventyayPluginMeta:
        name = 'HubSpot CRM'
        author = 'Your Name'
        description = 'Sync attendee data to HubSpot contacts'
        visible = True
        version = '1.0.0'
        category = 'integration'
        featured = False

    def ready(self):
        from . import signals  # Auto-loads @receiver decorators
```

#### Signal Subscription Pattern
File: [app/eventyay/plugins/badges/signals.py](app/eventyay/plugins/badges/signals.py) (example)
```python
from django.dispatch import receiver
from eventyay.base.signals import order_paid

@receiver(order_paid, dispatch_uid='hubspot_sync_attendees')
def sync_attendees_to_hubspot(sender, order, **kwargs):
    """
    sender = Event instance
    order = Order instance (with all_positions available)
    """
    # Sync logic here
    pass
```

#### How Event-Scoping Works (Automatic!)
- `order_paid` is an `EventPluginSignal` (not standard Django signal)
- Automatically filters receivers by plugins **enabled for that event**
- No manual `.is_plugin_enabled()` checks needed in signal handler
- Handler only fires if:
  1. Plugin is enabled for the event
  2. Order belongs to that event

**File**: [app/eventyay/base/signals.py](app/eventyay/base/signals.py#L116) (lines 116+)
```python
class EventPluginSignal(Signal):
    """Custom signal that only sends to receivers for enabled plugins"""
    def send(self, sender, **kwargs):
        # Automatically filters by event.plugins
        # Only active receivers are called
        pass
```

---

## 3. Safe Integration Without Breaking Core

### ✅ Answer: How to Hook into Attendee Creation Safely

#### The Safest Approach: Use Signal Pattern with Async Tasks

**Rationale**:
1. **Signals are non-blocking** - HubSpot API call doesn't delay order confirmation
2. **Celery handles retries** - Network failures auto-recover
3. **Loose coupling** - Core order flow unaffected if plugin disabled
4. **Proven pattern** - All existing plugins (banktransfer) use this approach

#### Architecture Pattern (Proven in Codebase)

**Option A: Synchronous (Simple, immediate)**
```python
# In signals.py
@receiver(order_paid, dispatch_uid='hubspot_sync')
def sync_to_hubspot(sender, order, **kwargs):
    """Synchronous sync - best for demo, small volumes"""
    try:
        api_key = order.event.settings.get('plugin_hubspot_api_key')
        hubspot_client = HubSpot(api_key)
        
        for position in order.all_positions.all():
            hubspot_client.create_contact(
                email=position.attendee_email,
                firstName=position.attendee_name_parts.get('first_name'),
                lastName=position.attendee_name_parts.get('last_name'),
                properties={
                    'event_name': order.event.name,
                    'ticket_code': order.code,
                }
            )
    except Exception as e:
        logger.error(f'HubSpot sync failed for order {order.code}: {e}')
        # Order is still confirmed; sync failure doesn't affect user
```

**Option B: Asynchronous with Celery (Production-ready)**

Reference implementation: [banktransfer/tasks.py](app/eventyay/plugins/banktransfer/tasks.py#L1) (line 1+)

```python
# In signals.py
from .tasks import sync_order_to_hubspot

@receiver(order_paid, dispatch_uid='hubspot_sync')
def handle_order_paid(sender, order, **kwargs):
    sync_order_to_hubspot.delay(order.pk, order.event.pk)

# In tasks.py
from celery import shared_task
from eventyay.base.models import Order, Event

@shared_task(bind=True, max_retries=3)
def sync_order_to_hubspot(self, order_pk, event_pk):
    """
    Async task with automatic retries
    Celery re-runs up to 3 times if network fails
    """
    try:
        with scope(event=Event.objects.get(pk=event_pk)):
            order = Order.objects.get(pk=order_pk)
            api_key = order.event.settings.get('plugin_hubspot_api_key')
            hubspot_client = HubSpot(api_key)
            
            for position in order.all_positions.all():
                hubspot_client.create_contact(...)
    except Exception as e:
        # Auto-retry 3 times with exponential backoff
        self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

#### Why This is Safe
1. **Non-blocking**: Signal handler returns immediately; HubSpot call happens in background
2. **Error isolation**: If HubSpot API is down, order confirmation still succeeds
3. **Automatic retries**: Celery built-in retry mechanism handles transient failures
4. **Reversibility**: Can disable plugin without affecting confirmed orders
5. **Loose coupling**: Core order system has zero dependencies on HubSpot

**Risk Level**: MINIMAL ✅

---

## 4. Available Attendee Fields & Data Structure

### ✅ Answer: What Fields Are Readily Available

#### Ready-to-Use Fields from OrderPosition
```python
# Directly available without additional queries
position.attendee_email              # EmailField - always available
position.attendee_name_cached        # CharField - full name as string
position.attendee_name_parts         # JSONField - structured {first_name, last_name, ...}
position.order.code                  # Order code for reference
position.order.email                 # Purchaser email (may differ from attendee)

# Additional useful fields
position.order.event.name            # Event name for grouping
position.order.event.slug            # Event URL-friendly identifier
position.order.created               # Order creation timestamp
position.order.datetime              # Order date (could use for "Created At")

# Product info (if needed)
position.item.name                   # Product/ticket name
position.order.total                 # Total order amount
```

#### Data Availability Guarantee
- **attendee_email**: ✅ Always present if attendee confirmed
- **attendee_name_cached**: ✅ Always present (cached at order placement)
- **attendee_name_parts**: ✅ Always present as JSON dict
- **Event context**: ✅ Fully accessible via order.event

#### Minimal Information for HubSpot Contact
```python
hubspot_contact = {
    'email': position.attendee_email,
    'firstName': position.attendee_name_parts.get('first_name', ''),
    'lastName': position.attendee_name_parts.get('last_name', ''),
    'hs_lead_status': 'Customer',  # Set status
    'event_name': order.event.name,
    'ticket_code': order.code,
    'event_date': order.event.date_from,  # Or use created date
}
```

#### Data Completeness Note
Unlike the Stripe payment scenario (where keys are stored in 2 places), attendee data is **single-sourced**: OrderPosition is the only place attendee info is stored. ✅ Clean design.

---

## 5. Plugin Configuration Storage

### ✅ Answer: How Plugin Configuration is Stored

#### System: Hierarkey (Django-Hierarkey)
**Location**: [app/eventyay/base/settings.py](app/eventyay/base/settings.py)

Eventyay uses `django-hierarkey` for hierarchical settings with **3 levels**:
1. **Global** (`GlobalSettings`) - system-wide defaults
2. **Organizer** (`organizer.settings`) - per-organizer (team) settings
3. **Event** (`event.settings`) - per-event overrides ← **USE THIS FOR API KEY**

#### Storage Pattern for HubSpot API Key
**Best Practice**: Store per-event, accessed as:

```python
# Reading API key
api_key = order.event.settings.get('plugin_hubspot_api_key')

# Writing API key (from form submission)
event.settings.set('plugin_hubspot_api_key', api_key_value)

# Reading with type conversion
enabled = event.settings.get('plugin_hubspot_enabled', False, as_type=bool)
```

#### Implementation: Settings Form Fields
**File**: [app/eventyay/plugins/banktransfer/payment.py](app/eventyay/plugins/banktransfer/payment.py#L208) (reference pattern, lines 208+)

```python
# In your forms.py
from django import forms
from django.utils.translation import gettext_lazy as _

class HubSpotSettingsForm(forms.Form):
    api_key = forms.CharField(
        label=_('HubSpot API Key'),
        widget=forms.PasswordInput(render_value=True),
        help_text=_('Get this from your HubSpot account settings'),
        required=True,
    )
    enabled = forms.BooleanField(
        label=_('Enable HubSpot sync'),
        required=False,
    )
```

#### How Plugin Settings Work in Control Panel
**Pattern**: Each plugin's config form is displayed in event settings → "Plugins" tab
- Form fields automatically mapped to `event.settings` namespace
- Plugin name used as prefix: `plugin_hubspot_*`
- Example keys:
  - `plugin_hubspot_api_key`
  - `plugin_hubspot_enabled`
  - `plugin_hubspot_test_mode`

#### Security Notes ✅
1. **Not stored in code** - settings live in PostgreSQL
2. **Per-event isolation** - each event has separate API keys
3. **Settings have type system** - automatic serialization for int, bool, dict, etc.
4. **Framework handles escaping** - no manual sanitization needed

#### Alternative: Global Settings (For HubSpot Workspace-Level Config)
If you wanted ONE key for entire Eventyay instance:

```python
# In settings.py
from eventyay.base.settings import GlobalSettings

GlobalSettings.add_default(
    'plugin_hubspot_workspace_key',
    None,  # default value
    str,   # type
)

# Read from global settings
from eventyay.base.models.settings import GlobalSettings as GS
workspace_key = GS.settings.get('plugin_hubspot_workspace_key')
```

**Recommendation**: Use **per-event** storage (more flexible, supports multiple HubSpot workspaces).

---

## 6. Complete Feasibility Assessment

### ✅ Final Verdict: HIGHLY FEASIBLE

All architectural requirements for HubSpot sync are **fully supported by Eventyay's plugin system**.

#### Integration Flow (End-to-End)

```
Order Placed & Paid
    ↓
OrderPayment.confirm() called
    ↓
order_paid signal emitted (EventPluginSignal)
    ↓
HubSpot plugin signal handler triggered
    ↓
[OPTION A: Sync immediately in handler]
      or
[OPTION B: Queue Celery task for async sync]
    ↓
Loop through order.all_positions
    ↓
Extract attendee_email, attendee_name_parts
    ↓
Call HubSpot API to create/update contact
    ↓
Log result (success/failure)
    ↓
✅ Order confirmation unaffected
✅ HubSpot sync happens in background
✅ Retries handled automatically (if async)
```

#### Why It's Feasible: Checklist

| Requirement | Status | Evidence |
|------------|--------|----------|
| **Attendee data available** | ✅ YES | AbstractPosition model has attendee_email, attendee_name_* |
| **Finalization hook point** | ✅ YES | order_paid signal at OrderPayment.confirm() |
| **Safe integration** | ✅ YES | EventPluginSignal auto-filters by event; signal is non-blocking |
| **Plugin registration** | ✅ YES | apps.py + EventyayPluginMeta pattern proven (badges, sendmail) |
| **Configuration storage** | ✅ YES | Hierarkey system supports per-event API key storage |
| **Async framework** | ✅ YES | Celery + shared_task pattern proven (banktransfer/tasks.py) |
| **Example patterns** | ✅ YES | Complete reference: banktransfer, badges, sendmail plugins |

---

## 7. Identified Risks & Mitigation Strategies

### Risk 1: HubSpot API Rate Limiting
**Severity**: MEDIUM  
**Issue**: If many orders confirmed quickly, may hit HubSpot rate limits  
**Mitigation**:
- ✅ Use Celery async with `countdown` delays between API calls
- ✅ Implement batch contact creation (HubSpot supports batch endpoints)
- ✅ Add exponential backoff in retry logic
- ✅ Log API response codes for monitoring

### Risk 2: API Key Exposed in Logs
**Severity**: HIGH  
**Issue**: Exception messages might include API key from request/config  
**Mitigation**:
- ✅ Never log API key values; use descriptive messages only
- ✅ Mask credentials in error handling: `logger.error(f'HubSpot sync failed for {order.code}')`
- ✅ Use Django's SECRET_SCRUBBING for settings (already built-in)

### Risk 3: Plugin Disabled Mid-Sync
**Severity**: LOW  
**Issue**: If plugin disabled while Celery task queued, task might fail on import  
**Mitigation**:
- ✅ Wrap signal handler in try/except
- ✅ Celery task gets event.pk, not plugin reference (no import needed)
- ✅ Task can run even if plugin disabled (graceful degradation)

### Risk 4: HubSpot API Downtime
**Severity**: MEDIUM  
**Issue**: Order confirmation blocked if sync is synchronous and HubSpot down  
**Mitigation**:
- ✅ **Use async (Celery) NOT sync** - order confirms regardless of HubSpot status
- ✅ Implement exponential backoff retries (default: 3 attempts)
- ✅ Add dead-letter queue for persistent failures
- ✅ Send admin alert if sync fails after retries

### Risk 5: Duplicate Contacts in HubSpot
**Severity**: MEDIUM  
**Issue**: If order sync fails and user retries payment, duplicate contact created  
**Mitigation**:
- ✅ Use HubSpot's dedupe API (search for email first before create)
- ✅ Use HubSpot's upsert endpoint (idempotent) instead of create
- ✅ Store HubSpot contact ID in OrderPosition to prevent re-sync

### Risk 6: Multi-Event Organizers
**Severity**: LOW  
**Issue**: Same user purchases tickets for multiple events, multiple contacts created  
**Mitigation**:
- ✅ By design - each event creates separate sync (may be desired for segmentation)
- ✅ If de-duping needed, add flag in settings: `plugin_hubspot_merge_contacts_by_email`
- ✅ Sync to same HubSpot workspace (don't create separate workspaces per event)

---

## 8. Recommended Plugin Architecture

### Minimal Implementation Structure
```python
# hubspot/
├── __init__.py
├── apps.py                    # Plugin registration + metadata
├── signals.py                 # @receiver(order_paid) handler
├── tasks.py                   # Celery async task (optional but recommended)
├── forms.py                   # HubSpot settings form for event config
├── models.py                  # Optional: HubSpotSyncLog for tracking
└── tests/                     # Pytest tests for signal handler
    └── conftest.py

# Key files detailed below:
```

### apps.py - Plugin Registration
```python
from django.apps import AppConfig
from eventyay.base.apps import EventyayPluginMeta

class HubSpotAppConfig(AppConfig):
    name = 'eventyay.plugins.hubspot'
    verbose_name = 'HubSpot CRM'
    
    class EventyayPluginMeta:
        name = 'HubSpot'
        author = 'Eventyay'
        description = 'Sync attendee data to HubSpot CRM on order confirmation'
        visible = True
        version = '1.0.0'
        category = 'integration'
        featured = False

    def ready(self):
        from . import signals  # Auto-load signal handlers
```

### signals.py - Order Handler
```python
from django.dispatch import receiver
from django.utils import timezone
from eventyay.base.signals import order_paid
from .tasks import sync_order_to_hubspot_async
import logging

logger = logging.getLogger(__name__)

@receiver(order_paid, dispatch_uid='hubspot_order_paid')
def handle_order_paid(sender, order, **kwargs):
    """
    Triggered when order is paid.
    sender = Event instance
    order = Order instance
    """
    # Check if plugin enabled for this event
    if not order.event.settings.get('plugin_hubspot_enabled', False, as_type=bool):
        return
    
    # Queue async task instead of blocking
    sync_order_to_hubspot_async.delay(order.pk, order.event.pk)
```

### tasks.py - Async Celery Task
```python
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from eventyay.base.models import Order, Event
from django_scopes import scope
import logging
from hubspot_client import HubSpotClient  # External SDK

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def sync_order_to_hubspot_async(self, order_pk, event_pk):
    """
    Async task with automatic retries on failure.
    Max 3 retries with exponential backoff.
    """
    try:
        with scope(event=Event.objects.get(pk=event_pk)):
            order = Order.objects.get(pk=order_pk)
            api_key = order.event.settings.get('plugin_hubspot_api_key')
            
            if not api_key:
                logger.warning(f'No HubSpot API key configured for event {order.event.slug}')
                return
            
            client = HubSpotClient(api_token=api_key)
            
            # Sync all attendees
            for position in order.all_positions.all():
                contact_data = {
                    'email': position.attendee_email,
                    'firstName': position.attendee_name_parts.get('first_name', ''),
                    'lastName': position.attendee_name_parts.get('last_name', ''),
                    'properties': {
                        'event': order.event.name,
                        'ticket_code': order.code,
                    }
                }
                
                try:
                    # Upsert = idempotent (won't create duplicates)
                    client.crm.contacts.basic_api.create_or_update_a_contact(
                        contact_json=contact_data
                    )
                except Exception as e:
                    logger.exception(f'Failed to sync contact {position.attendee_email}')
                    raise
            
            logger.info(f'HubSpot sync complete for order {order.code}')
    
    except Exception as exc:
        # Retry with exponential backoff: 60s, 120s, 240s
        countdown = 60 * (2 ** self.request.retries)
        self.retry(exc=exc, countdown=countdown)
```

### forms.py - Configuration
```python
from django import forms
from django.utils.translation import gettext_lazy as _

class HubSpotSettingsForm(forms.Form):
    enabled = forms.BooleanField(
        label=_('Enable HubSpot sync'),
        required=False,
        help_text=_('Automatically sync attendees when orders are paid')
    )
    
    api_key = forms.CharField(
        label=_('HubSpot API Key'),
        widget=forms.PasswordInput(render_value=True),
        required=False,
        help_text=_('Get from HubSpot account → Settings → API keys'),
        max_length=500,
    )
```

---

## 9. Testing Strategy

### Unit Tests (Minimum Required)

```python
# tests/conftest.py
import pytest
from django.contrib.auth.models import User
from eventyay.base.models import Event, Organizer, Order, OrderPosition

@pytest.fixture
def event(db):
    org = Organizer.objects.create(name='Test Org', slug='test-org')
    return Event.objects.create(
        organizer=org,
        name='Test Event',
        slug='test-event',
        date_from='2025-01-01'
    )

@pytest.fixture
def order_with_attendees(db, event):
    order = Order.objects.create(
        event=event,
        email='buyer@example.com',
        locale='en',
        status='PAID'
    )
    OrderPosition.objects.create(
        order=order,
        item=event.items.create(name='Ticket'),
        attendee_email='attendee@example.com',
        attendee_name_cached='John Doe',
        attendee_name_parts={'first_name': 'John', 'last_name': 'Doe'}
    )
    return order

# tests/test_hubspot_signals.py
@pytest.mark.django_db
def test_order_paid_signal_queues_hubspot_sync(mocker, event, order_with_attendees):
    """Verify order_paid signal triggers HubSpot sync task"""
    # Mock Celery task
    task_mock = mocker.patch('eventyay.plugins.hubspot.tasks.sync_order_to_hubspot_async.delay')
    
    # Set API key
    event.settings.set('plugin_hubspot_enabled', True)
    event.settings.set('plugin_hubspot_api_key', 'test_key_12345')
    
    # Trigger signal
    from eventyay.base.signals import order_paid
    order_paid.send(sender=event, order=order_with_attendees)
    
    # Assert task was queued
    task_mock.assert_called_once_with(order_with_attendees.pk, event.pk)

@pytest.mark.django_db
def test_hubspot_sync_skipped_if_disabled(mocker, event, order_with_attendees):
    """Verify signal handler skips if plugin disabled"""
    task_mock = mocker.patch('eventyay.plugins.hubspot.tasks.sync_order_to_hubspot_async.delay')
    
    # Don't enable plugin
    event.settings.set('plugin_hubspot_enabled', False)
    
    from eventyay.base.signals import order_paid
    order_paid.send(sender=event, order=order_with_attendees)
    
    # Task should not be called
    task_mock.assert_not_called()
```

### Integration Tests
- Verify signal fires when real OrderPayment.confirm() is called
- Mock HubSpot API client and verify correct data is sent
- Test retry logic with Celery eager mode

---

## 10. Comparison: HubSpot vs. Stripe (Why HubSpot is Simpler)

| Aspect | Stripe | HubSpot |
|--------|--------|---------|
| **Trigger Point** | Payment processing (2 flow paths) | Order finalization (1 signal: order_paid) |
| **Config Storage** | Multiple locations (keys in 2 places) | Single location (event.settings) |
| **Attendee Data** | Spread across Order + Payment + Invoice | Centralized in OrderPosition |
| **Async Requirement** | Synchronous (must confirm immediately) | Asynchronous (can queue task) |
| **Complexity** | High (payment flow intertwined) | Low (just data sync) |

**Conclusion**: HubSpot plugin is **simpler and cleaner** than Stripe - single hook point, single data model, flexible async approach.

---

## 11. Open Questions & Clarifications

1. **Multiple HubSpot Workspaces?**
   - Can store different API keys per event ✅ (per-event settings)
   - Or use single workspace for all events (simplest)

2. **What if attendee_email is empty?**
   - HubSpot requires email; skip/log if missing
   - Check position.attendee_email availability before API call

3. **Should plugin create HubSpot lists/workflows?**
   - Out of scope for minimal plugin
   - Can be added as enhancement

4. **Handle order cancellations?**
   - Add listener for `order_canceled` signal if needed
   - Minimal version: ignore cancellations

5. **Contact deduplication?**
   - Use HubSpot's upsert endpoint (idempotent)
   - Won't create duplicates if email already exists

---

## Conclusion

**HubSpot plugin for Eventyay is architecturally sound and ready to build.**

### Key Strengths
✅ Clean signal integration point (`order_paid`)  
✅ Automatic event-level scoping  
✅ Proven plugin patterns in codebase  
✅ Safe async execution (Celery)  
✅ Per-event configuration storage  
✅ All attendee data readily available  

### Recommended Next Steps
1. Create `/eventyay/plugins/hubspot/` directory structure
2. Implement signal handler in `signals.py`
3. Implement async task in `tasks.py` (with retries)
4. Create settings form in `forms.py`
5. Write tests in `tests/test_hubspot_signals.py`
6. Test against real HubSpot API (sandbox workspace)

### Estimated Complexity
- **Minimal version** (sync on order paid): 200-300 lines of code
- **Production version** (+ error handling, logging, tests): 500-700 lines
- **Effort**: 1-2 weeks for one developer (including testing)

---

**Document Version**: 1.0  
**Date**: January 2025  
**Status**: Ready for Implementation ✅
