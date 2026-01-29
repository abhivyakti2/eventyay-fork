# Stripe Implementation Analysis for Eventyay

## Executive Summary

**Status**: Stripe credential handling is **PARTIALLY UNIFIED** with clear separation of concerns, but has some **opportunities for consolidation**.

- **Global Platform Keys**: All Stripe API credentials centralized in global settings (`control/forms/global_settings.py`)
- **Organizer-Level Customer Management**: Per-organizer Stripe customers stored in `OrganizerBillingModel` via `stripe_utils.py`
- **Dynamic Key Retrieval**: Keys are fetched dynamically from global settings at runtime (NOT hardcoded)
- **No Duplication**: Credential handling is unified in `stripe_utils.py` service layer
- **External Plugin**: Stripe payment provider implementation is in external GitHub package (`eventyay-stripe`)

---

## Architecture Overview

### 1. **Stripe Credential Storage (Three Levels)**

#### Level 1: Global Platform Configuration
**File**: [control/forms/global_settings.py](control/forms/global_settings.py#L210-L329)

All Stripe API keys are centralized at the platform level:

```python
# Production Keys
- payment_stripe_secret_key
- payment_stripe_publishable_key

# Test Mode Keys  
- payment_stripe_test_secret_key
- payment_stripe_test_publishable_key

# Stripe Connect (Platform Fees)
- payment_stripe_connect_secret_key
- payment_stripe_connect_publishable_key
- payment_stripe_connect_client_id
- payment_stripe_connect_test_secret_key
- payment_stripe_connect_test_publishable_key

# Webhook Security
- stripe_webhook_secret_key

# Fee Configuration
- payment_stripe_connect_app_fee_percent
- payment_stripe_connect_app_fee_max
- payment_stripe_connect_app_fee_min
```

**Storage**: Django `event.settings` (database settings object via `GlobalSettingsObject`)

**Access Pattern**: 
```python
from eventyay.base.settings import GlobalSettingsObject
gs = GlobalSettingsObject()
stripe_key = getattr(gs.settings, 'payment_stripe_secret_key', None)
```

#### Level 2: Organizer-Level Stripe Customer
**File**: [base/models/organizer.py#L737-L751](base/models/organizer.py#L737-L751)

`OrganizerBillingModel` stores per-organizer Stripe identifiers:

```python
class OrganizerBillingModel(models.Model):
    organizer = ForeignKey('Organizer')
    
    # Stripe Customer IDs
    stripe_customer_id = CharField(max_length=255, null=True, blank=True)
    stripe_payment_method_id = CharField(max_length=255, null=True, blank=True)
    stripe_setup_intent_id = CharField(max_length=255, null=True, blank=True)
    
    # Billing Information
    primary_contact_name
    primary_contact_email
    company_or_organization_name
    address_line_1, address_line_2
    city, zip_code, country
    tax_id
```

**Relationship**: One-to-one (organizer → OrganizerBillingModel)

#### Level 3: Invoice-Level Payment Intent
**File**: [base/models/billing.py#L67](base/models/billing.py#L67)

```python
class BillingInvoice(LoggedModel):
    organizer = ForeignKey('Organizer')
    event = ForeignKey('Event')
    
    stripe_payment_intent_id = CharField(max_length=50, null=True, blank=True)
    # Per-invoice payment intent reference
```

**Purpose**: Track individual payment processing attempts per invoice

---

### 2. **Centralized Stripe Service Layer**

**File**: [helpers/stripe_utils.py](helpers/stripe_utils.py) (340 lines)

This is the **unified API gateway** for all Stripe operations. Key characteristics:

#### Credential Retrieval (Dynamic, NOT Hardcoded)

```python
def get_stripe_key(key_type: str) -> str:
    """Fetches from GlobalSettings dynamically"""
    gs = GlobalSettingsObject()
    
    # Try prod key first, fall back to test key
    prod_key = getattr(gs.settings, f'payment_stripe_{key_type}_key', None)
    test_key = getattr(gs.settings, f'payment_stripe_test_{key_type}_key', None)
    
    if not prod_key and not test_key:
        raise ValidationError('No Stripe key found')
    
    return prod_key or test_key

def get_stripe_secret_key() -> str:
    return get_stripe_key('secret')

def get_stripe_publishable_key() -> str:
    return get_stripe_key('publishable')
```

**✅ No Hardcoding**: Keys are always fetched from `GlobalSettingsObject()` at runtime

**✅ Fallback Logic**: Test mode keys used if production keys not available

#### Customer Management Functions

| Function | Purpose | Database Access |
|----------|---------|-----------------|
| `create_stripe_customer(email, name)` | Create new Stripe customer | Stores `stripe_customer_id` in `OrganizerBillingModel` |
| `get_stripe_customer_id(organizer_slug)` | Retrieve customer ID | Reads from `OrganizerBillingModel.stripe_customer_id` |
| `create_setup_intent(customer_id)` | Create intent for adding payment method | Stores `stripe_setup_intent_id` in `OrganizerBillingModel` |
| `update_payment_info(setup_intent_id, customer_id)` | Save verified payment method | Stores `stripe_payment_method_id` in `OrganizerBillingModel` |
| `get_payment_method_info(customer_id)` | Retrieve saved payment method | Reads from `OrganizerBillingModel` |

#### Billing Charge Functions

```python
def create_payment_intent(
    amount: int,
    currency: str,
    customer_id: str,
    payment_method_id: str,
    metadata: dict,
    invoice_id: str
) -> PaymentIntent:
    """Create payment intent and store ID in BillingInvoice"""
    stripe.api_key = get_stripe_secret_key()
    
    payment_intent = stripe.PaymentIntent.create(
        amount=int(amount * 100),
        currency=currency,
        customer=customer_id,
        payment_method=payment_method_id,
    )
    
    # Store reference for tracking
    BillingInvoice.objects.filter(id=invoice_id).update(
        stripe_payment_intent_id=payment_intent.id
    )
    
    return payment_intent

def process_auto_billing_charge_stripe(
    organizer_slug: str,
    amount: int,
    currency: str,
    metadata: dict,
    invoice_id: str
):
    """End-to-end billing flow"""
    stripe.api_key = get_stripe_secret_key()
    customer_id = get_stripe_customer_id(organizer_slug)
    payment_method = get_payment_method_info(customer_id)
    payment_intent = create_payment_intent(...)
    payment_intent_confirmation_info = confirm_payment_intent(...)
    return payment_intent_confirmation_info
```

#### Error Handling
Comprehensive decorator `@handle_stripe_errors(operation_name)` catches and logs:
- API errors
- Authentication errors
- Card errors
- Rate limit errors
- Invalid request errors
- Signature verification failures
- Permission errors
- Stripe SDK exceptions

**All errors converted to Django `ValidationError` for consistent handling**

---

### 3. **Integration Points**

#### Entry Point 1: Organizer Creation/Update
**File**: [control/forms/organizer_forms/organizer_form.py#L222-L226](control/forms/organizer_forms/organizer_form.py#L222-L226)

```python
class OrganizerBillingForm(forms.ModelForm):
    def save(self, commit=True):
        instance = OrganizerBillingModel.objects.filter(organizer_id=...).first()
        
        if not instance:
            # NEW ORGANIZER: Create Stripe customer
            stripe_customer = create_stripe_customer(
                email=self.cleaned_data.get('primary_contact_email'),
                name=self.cleaned_data.get('primary_contact_name'),
            )
            instance.stripe_customer_id = stripe_customer.id
        else:
            # EXISTING ORGANIZER: Update customer info
            update_customer_info(
                instance.stripe_customer_id,
                email=self.cleaned_data.get('primary_contact_email'),
                name=self.cleaned_data.get('primary_contact_name'),
            )
        
        instance.save()
        return instance
```

**Flow**: 
1. Organizer created → Stripe customer auto-created
2. Customer ID stored in `OrganizerBillingModel.stripe_customer_id`
3. Form imports from `stripe_utils` (via `from eventyay.helpers.stripe_utils import ...`)

#### Entry Point 2: Payment Method Setup (Billing UI)
**File**: [control/views/organizer_views/organizer_view.py#L40-L472]

```python
def get_organizer_payment_view(request, organizer):
    organizer = request.organizer
    
    # Step 1: Get customer ID
    stripe_customer_id = get_stripe_customer_id(organizer.slug)
    
    # Step 2: Retrieve saved payment method
    payment_method_info = get_payment_method_info(stripe_customer_id)
    
    # Step 3: Create SetupIntent for adding new payment method
    client_secret = create_setup_intent(stripe_customer_id)
    
    # Step 4: Get Stripe public key for frontend
    stripe_public_key = get_stripe_publishable_key()
    
    context = {
        'stripe_public_key': stripe_public_key,
        'client_secret': client_secret,
        'payment_method_info': payment_method_info,
    }
    return render(request, 'organizer/billing.html', context)
```

**Frontend** ([static/billing/js/billing.js]):
```javascript
const stripe = Stripe(stripePublishKey);  // From context
const elements = stripe.elements();
const cardElement = elements.create('card');
cardElement.mount('#card-element');

// User adds payment method
const {setupIntent} = await stripe.confirmCardSetup(clientSecret, {
    payment_method: {card: cardElement}
});

// POST to backend with setupIntent.id
fetch('/api/billing/confirm', {
    method: 'POST',
    body: JSON.stringify({setup_intent_id: setupIntent.id})
});
```

**Backend Confirmation** (organizer_form.py):
```python
# Called when user submits setup intent
update_payment_info(setup_intent_id, stripe_customer_id)
# Stores payment_method_id in OrganizerBillingModel
```

#### Entry Point 3: Event Payment Settings
**File**: [control/forms/event.py#L1476-L1513](control/forms/event.py#L1476-L1513)

```python
class EventSettingsForm(SettingsForm):
    
    payment_stripe__enabled = forms.BooleanField(
        label=_('Enable Stripe for this event'),
        required=False,
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Only show if external stripe plugin is active
        plugins_active = [...]  # get from plugin registry
        has_client_id = self.obj.settings.payment_stripe_client_id
        
        if ('eventyay_stripe' not in plugins_active) or (not has_client_id):
            # Plugin not installed or global keys not configured
            del self.fields['payment_stripe__enabled']
```

**Conditional Logic**:
- Stripe plugin (external) must be installed
- Global `payment_stripe_client_id` must be configured
- If both true: show per-event toggle `payment_stripe__enabled`

**Implication**: 
- Event-level: `payment_stripe__enabled` is a boolean toggle
- Global-level: All actual keys are in `global_settings.py`
- **Events share platform-level credentials** (no per-event API keys)

---

### 4. **Payment Provider Plugin Architecture**

#### Signal-Based Registration
**File**: [base/signals.py#L281](base/signals.py#L281)

```python
register_payment_providers = EventPluginSignal()
```

**File**: [base/models/event.py#L1689-L1692](base/models/event.py#L1689-L1692)

```python
@property
def payment_providers(self):
    """Returns list of available payment providers for this event"""
    responses = register_payment_providers.send(self)  # Signal dispatch
    return {
        provider_id: provider_instance
        for response in responses
        for provider_id, provider_instance in response[1].items()
    }
```

#### Built-In Free Provider
**File**: [base/payment.py#L1435+](base/payment.py#L1435)

```python
@receiver(register_payment_providers, dispatch_uid='payment_free')
def register_free_payment(sender, **kwargs):
    return {
        'free': FreeOrderProvider(sender)
    }
```

#### External Stripe Provider
**Plugin**: `eventyay-stripe` (external GitHub package)

- Located at: `fossasia/eventyay-tickets-stripe` (referenced in [pyproject.toml](pyproject.toml#L101))
- Registered via: Signal receiver in plugin's `signals.py`
- Provides: `StripePaymentProvider` class (BasePaymentProvider subclass)
- Handles: Payment processing, webhooks, Stripe Connect

**NOT in main codebase** (intentional plugin architecture)

---

## Credential Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PLATFORM CONFIGURATION (Global)                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  GlobalSettingsObject → django.settings object (DB)                 │
│  ├── payment_stripe_secret_key         (Production)                 │
│  ├── payment_stripe_publishable_key    (Production)                 │
│  ├── payment_stripe_test_secret_key    (Test Mode)                  │
│  ├── payment_stripe_test_publishable_key (Test Mode)                │
│  ├── stripe_webhook_secret_key         (Webhook Verification)       │
│  └── payment_stripe_connect_* (6 keys for platform fees)            │
│                                                                       │
│  Accessed by: stripe_utils.get_stripe_secret_key()                  │
│               stripe_utils.get_stripe_publishable_key()             │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ Dynamic fetch at runtime
                                  │ (every Stripe API call)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STRIPE API CLIENT (stripe.Stripe)                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  stripe.api_key = get_stripe_secret_key()                           │
│  stripe.Customer.create(email, name)   → customer.id                │
│  stripe.SetupIntent.create(customer_id) → setup_intent              │
│  stripe.PaymentIntent.create(...) → payment_intent                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                    │                        │
                    │ Organizer ID           │ Payment Intent ID
                    ▼                        ▼
        ┌──────────────────────┐  ┌──────────────────────┐
        │ OrganizerBillingModel │  │  BillingInvoice      │
        ├──────────────────────┤  ├──────────────────────┤
        │ organizer (FK)       │  │ organizer (FK)       │
        │ stripe_customer_id   │  │ event (FK)           │
        │ stripe_payment_..._id│  │ stripe_payment_..._id│
        │ stripe_setup_intent  │  │ amount, currency     │
        │ billing_info         │  │ status, paid_date    │
        └──────────────────────┘  └──────────────────────┘
```

---

## Key Findings

### ✅ **Unified Credential Handling**

1. **Single Source of Truth**: All Stripe API keys stored in global settings (`GlobalSettingsObject`)
2. **Dynamic Retrieval**: Keys fetched from database at runtime (not hardcoded)
3. **Centralized Service Layer**: All Stripe operations go through `stripe_utils.py`
4. **No Duplication**: Functions like `create_stripe_customer()`, `get_stripe_customer_id()` used consistently everywhere

**Evidence**:
```python
# ALL stripe.api_key assignments in stripe_utils.py:
stripe.api_key = get_stripe_secret_key()  # Single source

# Same pattern in ALL functions:
@handle_stripe_errors('create_setup_intent')
def create_setup_intent(customer_id: str) -> str:
    stripe.api_key = get_stripe_secret_key()  # Fetched fresh each time
    stripe_setup_intent = stripe.SetupIntent.create(...)
```

### ⚠️ **Minor Architectural Observations**

1. **API Key Re-fetched Per-Operation**: Each Stripe API call re-fetches the key from database
   - **Not inefficient** (minimal DB query), but could cache in memory
   - Current approach ensures always uses latest configuration

2. **Stripe Connect Configuration Incomplete**:
   - Platform has Stripe Connect keys defined
   - **Unknown**: Whether payments use these for platform fees or if organizers use own accounts
   - External plugin likely handles this logic

3. **Event-Level vs Organizer-Level Separation**:
   - Events have `payment_stripe__enabled` toggle (feature flag)
   - All events share platform credentials (no per-event keys)
   - **Acceptable design**: Simplifies multi-tenant architecture

4. **Error Handling Homogenization**:
   - All Stripe SDK errors converted to Django `ValidationError`
   - Makes error messages user-friendly but loses exception type information
   - **Logging available**: All operations logged with `logger.error()` and `logger.info()`

---

## Credential Lifecycle

### New Organizer Registration
```
1. User creates organizer (OrganizerForm)
   ↓
2. OrganizerBillingForm.__init__() called
   ↓
3. Form.save() triggers:
   stripe_customer = create_stripe_customer(name, email)
   ↓ [Uses get_stripe_secret_key() to authenticate]
   ↓
4. Result stored: OrganizerBillingModel.stripe_customer_id
   ↓
5. Database persists organizer ↔ Stripe customer relationship
```

### Payment Method Addition (Organizer Billing Panel)
```
1. Organizer visits /billing/
   ↓
2. View calls: get_stripe_customer_id(organizer.slug)
   ↓ [Retrieves from OrganizerBillingModel]
   ↓
3. View calls: create_setup_intent(customer_id)
   ↓ [Uses get_stripe_secret_key()]
   ↓
4. SetupIntent ID sent to frontend (JavaScript)
   ↓
5. Frontend calls Stripe.js with setup intent
   ↓ [User enters card details]
   ↓
6. Frontend confirms with Stripe, receives setupIntent ID
   ↓
7. POST back to backend: update_payment_info(setup_intent_id, customer_id)
   ↓ [Uses get_stripe_secret_key()]
   ↓
8. Payment method ID stored: OrganizerBillingModel.stripe_payment_method_id
```

### Automatic Billing (Invoice Processing)
```
1. Celery task or signal triggers: process_auto_billing_charge_stripe()
   ↓
2. Function retrieves:
   - customer_id: get_stripe_customer_id(organizer_slug)
   - payment_method: get_payment_method_info(customer_id)
   ↓ [Uses get_stripe_secret_key()]
   ↓
3. Creates payment intent: create_payment_intent(amount, ...)
   ↓ [Stores stripe_payment_intent_id in BillingInvoice]
   ↓
4. Confirms payment: confirm_payment_intent(intent_id, method_id)
   ↓ [Uses get_stripe_secret_key()]
   ↓
5. Database updated: BillingInvoice.stripe_payment_intent_id = intent_id
```

---

## Security Observations

### ✅ **Secure Practices**

1. **No Hardcoded Keys**: All credentials fetched from database
2. **Webhook Signature Verification**: `stripe_webhook_secret_key` validated
3. **Error Information Sanitization**: Exception details logged but not exposed to users
4. **Database-Backed Configuration**: Admin only access to global settings

### ⚠️ **Potential Improvements**

1. **API Key Rotation**: Consider keyringless Stripe API key versioning
2. **Rate Limiting**: No built-in rate limit handling beyond Stripe SDK
3. **Webhook Verification**: Should verify webhook signature before processing
4. **Test/Prod Key Fallback**: Current fallback (test key if no prod key) could cause unexpected behavior

---

## External Plugin Integration

### eventyay-stripe Package
**Repository**: `fossasia/eventyay-tickets-stripe`
**Type**: External Django plugin (Git dependency)
**Location in codebase**: `eventyay/plugins/stripe/` (mounted via plugin system)

**Provides**:
- `StripePaymentProvider` class (registers via signal)
- Payment processing logic for checkout flow
- Webhook handlers
- Stripe Connect integration for platform fees

**Integration Point**:
```python
# In eventyay/plugins/stripe/signals.py (external):
@receiver(register_payment_providers, dispatch_uid='payment_stripe')
def register_stripe_payment(sender, **kwargs):
    return {
        'stripe': StripePaymentProvider(sender),
        'stripe_giropay': StripeGiropayProvider(sender),
        # ... other Stripe payment methods
    }
```

**Communication**: Plugin likely calls functions from `stripe_utils.py` or implements own Stripe integration

---

## Recommendations

### Priority: LOW (Current Design is Sound)

1. **Cache API Keys in Memory** (Optional optimization)
   - Reduce database queries for frequently accessed keys
   - Invalidate cache on settings change
   ```python
   def get_stripe_secret_key_cached():
       cache_key = 'stripe_secret_key'
       key = cache.get(cache_key)
       if not key:
           key = get_stripe_key('secret')
           cache.set(cache_key, key, timeout=3600)  # 1 hour
       return key
   ```

2. **Document Stripe Connect Flow**
   - Currently unclear if platform collects fees
   - Document expected behavior in code comments
   - Add tests covering fee distribution

3. **Add API Key Validation**
   - Validate keys are correct format when saved
   - Test Stripe API authentication on settings save
   ```python
   def validate_stripe_credentials(secret_key, publishable_key):
       stripe.api_key = secret_key
       try:
           stripe.Account.retrieve()  # Validates authentication
           return True
       except stripe.AuthenticationError:
           return False
   ```

4. **Enhance Webhook Signature Verification**
   - Ensure all webhooks use `get_stripe_webhook_secret_key()`
   - Add webhook endpoint verification endpoint
   ```python
   def verify_stripe_webhook(request):
       sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
       body = request.body
       try:
           event = stripe.Webhook.construct_event(
               body, 
               sig_header, 
               get_stripe_webhook_secret_key()
           )
       except stripe.error.SignatureVerificationError:
           return HttpResponse(status=400)
   ```

---

## Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| [helpers/stripe_utils.py](helpers/stripe_utils.py) | 340 | Stripe API wrapper (centralized) |
| [control/forms/global_settings.py](control/forms/global_settings.py) | 210-329 | Platform credential configuration |
| [base/models/organizer.py](base/models/organizer.py) | 737-751 | OrganizerBillingModel (customer IDs) |
| [base/models/billing.py](base/models/billing.py) | 67 | BillingInvoice.stripe_payment_intent_id |
| [control/forms/organizer_forms/organizer_form.py](control/forms/organizer_forms/organizer_form.py) | 222-226 | Organizer creation (calls create_stripe_customer) |
| [control/views/organizer_views/organizer_view.py](control/views/organizer_views/organizer_view.py) | 40-472 | Billing UI (payment method setup) |
| [control/forms/event.py](control/forms/event.py) | 1476-1513 | Event-level Stripe toggle |
| [base/payment.py](base/payment.py) | 60-150 | BasePaymentProvider class |
| [base/signals.py](base/signals.py) | 281 | register_payment_providers signal |
| [pyproject.toml](pyproject.toml) | 101 | eventyay-stripe external dependency |

---

## Conclusion

**Stripe credential handling in Eventyay IS UNIFIED and WELL-DESIGNED**:

✅ Single global credential source (GlobalSettingsObject)  
✅ Centralized service layer (stripe_utils.py)  
✅ Dynamic key retrieval (no hardcoding)  
✅ Consistent error handling  
✅ Clear separation: platform keys ↔ organizer customers ↔ invoice payments  
✅ External plugin architecture allows for future flexibility  

**Minor Opportunities**:
- Optional: In-memory caching of API keys (trivial performance gain)
- Documentation: Clarify Stripe Connect fee collection flow
- Testing: Enhanced webhook verification

**Overall Assessment**: No unification work urgently needed. Code is maintainable and secure as-is.

