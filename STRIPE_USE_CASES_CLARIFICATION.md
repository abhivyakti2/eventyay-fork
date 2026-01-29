# Stripe Implementation: Two Use Cases Explained

## Executive Summary

Eventyay uses Stripe in **TWO COMPLETELY DIFFERENT WAYS** that serve different business purposes. The current implementation correctly separates them by storage location and purpose:

| **Use Case** | **Purpose** | **Direction** | **Storage** | **Keys** | **Setup** |
|---|---|---|---|---|---|
| **USE CASE 1** | Organizer receives payments from ticket buyers | Buyer → Organizer's Stripe | Per-organizer | `OrganizerBillingModel` (IDs) + Global `payment_stripe_*` (credentials) | External plugin |
| **USE CASE 2** | Platform collects fees from organizers | Organizer → Platform | Platform-wide | Global `payment_stripe_connect_*` | Built-in feature |

---

## USE CASE 1: Organizer-Direct Payments (Organizer Connected to Stripe)

### Business Flow
```
Ticket Buyer → Platform → Organizer's Stripe Account
                         (payment goes directly to organizer)
```

### Purpose
- Organizers can accept payments **directly to their own Stripe account**
- The platform facilitates the payment but doesn't hold funds
- Organizer has full control over their transactions and payouts
- Implemented via **external `eventyay-stripe` plugin**

### How It Works
1. **Organizer Setup**:
   - Admin/organizer clicks button on "Payment Settings" page in organizers menu
   - Opens Stripe onboarding flow
   - Organizer grants eventyay access to their Stripe account

2. **Payment Flow**:
   - Ticket buyer enters payment info on platform's checkout
   - Platform uses organizer's Stripe API keys to create a payment intent
   - Customer charges money to organizer's Stripe account
   - Money stays in organizer's account (with platform's app fee deducted)

3. **After Payment**:
   - Organizer's Stripe customer ID stored in `OrganizerBillingModel.stripe_customer_id`
   - Payment method ID stored in `OrganizerBillingModel.stripe_payment_method_id`
   - Payment intent ID stored in `BillingInvoice.stripe_payment_intent_id` (for tracking)

### Storage Breakdown for USE CASE 1

#### Location 1: Global Settings - `payment_stripe_*_key` (4 keys)
```
payment_stripe_secret_key          ← Platform's Stripe account (for connecting organizers)
payment_stripe_publishable_key
payment_stripe_test_secret_key
payment_stripe_test_publishable_key
```

**Purpose**: These are the **PLATFORM'S OWN STRIPE KEYS** used to:
- Authenticate the external `eventyay-stripe` plugin
- Allow organizers to connect their Stripe accounts via OAuth
- These are needed when organizers go through the "Connect Stripe" flow

**Why Platform's Keys?**: The external plugin uses these keys to:
1. Call Stripe OAuth endpoints to initiate organizer connection
2. Request organizer's consent to manage their account
3. Exchange OAuth code for organizer's access token

#### Location 2: Per-Organizer - `OrganizerBillingModel`
```python
stripe_customer_id          ← Organizer's Stripe customer ID
stripe_payment_method_id    ← Organizer's saved payment method
stripe_setup_intent_id      ← In-progress setup intent for adding payment method
```

**Purpose**: Store **EACH ORGANIZER'S STRIPE IDENTIFIERS**

**Why Separate?**:
- Each organizer has their own Stripe customer ID in the platform system
- Different organizers = different Stripe IDs
- Per-organizer because organizers can enable/disable this feature independently
- Created automatically when organizer is created

#### Location 3: Per-Invoice - `BillingInvoice`
```python
stripe_payment_intent_id    ← Reference to Stripe payment intent for this invoice
```

**Purpose**: Track payment for billing purposes

#### Location 4: Per-Event - Event Settings
```
payment_stripe__enabled     ← Boolean toggle to enable/disable Stripe for this event
```

**Purpose**: Organizers can choose which events accept Stripe payments

---

## USE CASE 2: Platform Fee Collection (Auto-Billing)

### Business Flow
```
Organizer's Stripe Account → Platform's Stripe Account
                            (platform collects recurring fees)
```

### Purpose
- Platform automatically charges organizers for hosting/subscription fees
- Uses Stripe Connect for **split payments** and **app fees**
- Completely separate from ticket buyer payments
- Built-in feature (NOT external plugin)

### How It Works
1. **Setup** (Admin configures once):
   - Admin enters platform's Stripe Connect keys in global settings
   - Platform's Stripe Connect app is registered with Stripe

2. **Fee Collection** (Celery task triggers):
   - Monthly/yearly billing cycle runs
   - For each organizer with active billing:
     - Create a `BillingInvoice` record
     - Call Stripe to create a payment intent
     - Charge organizer using their saved payment method

3. **Payment Processing**:
   - Money flows to platform's Stripe account
   - Stripe automatically deducts fees (app fee, processing fee)
   - Remaining amount either goes to platform or back to organizer (depends on Split Payments setup)

### Storage Breakdown for USE CASE 2

#### Location: Global Settings - `payment_stripe_connect_*` (7 keys)
```
payment_stripe_connect_client_id              ← Platform's OAuth client ID
payment_stripe_connect_secret_key             ← Platform's Stripe Connect secret
payment_stripe_connect_publishable_key        ← Platform's Stripe Connect publishable
payment_stripe_connect_test_secret_key        ← Test mode equivalents
payment_stripe_connect_test_publishable_key
payment_stripe_connect_app_fee_percent        ← Fee configuration
payment_stripe_connect_app_fee_max
payment_stripe_connect_app_fee_min
```

**Purpose**: **PLATFORM'S OWN STRIPE CONNECT ACCOUNT CREDENTIALS**

**Why Global?**:
- Only the platform collects fees (not per-organizer)
- Platform-wide configuration
- Same keys used for all organizers' fee collection

#### Location: Per-Invoice - `BillingInvoice`
```python
stripe_payment_intent_id    ← Payment intent for THIS fee invoice
```

**Purpose**: Track which payment intent corresponds to which invoice

---

## Why Multiple Storage Locations? The Rationale

The confusion arises because the codebase correctly separates **scope** from **purpose**, but doesn't make it clear in the configuration:

### 1. **Scope Separation**
| Data Type | Scope | Storage Location |
|-----------|-------|-----------------|
| Platform credentials | Global (platform-wide) | Global Settings |
| Organizer customer IDs | Per-organizer | `OrganizerBillingModel` |
| Invoice payment tracking | Per-invoice | `BillingInvoice` |
| Event toggle | Per-event | Event Settings |

### 2. **Purpose Confusion in Global Settings**
The problem: **Both USE CASE 1 and USE CASE 2 keys are stored in the same place** (`control/forms/global_settings.py` lines 315-328):

```python
'payment_stripe_connect_client_id',              # USE CASE 2 (platform fees)
'payment_stripe_connect_secret_key',             # USE CASE 2
'payment_stripe_connect_publishable_key',        # USE CASE 2
...
'payment_stripe_secret_key',                     # USE CASE 1 (organizer payments)
'payment_stripe_publishable_key',                # USE CASE 1
'stripe_webhook_secret_key',                     # ??? (unclear which use case)
```

**This Mixing Is Actually Correct** because:
- Both need to be configured globally by admin
- Both are read at startup/configuration time
- It's convenient to have all payment-related config in one place
- BUT: The naming should be clearer

### 3. **Current Code Patterns**

**USE CASE 1 Code Flow**:
```
External Plugin (eventyay-stripe)
    ↓
uses: payment_stripe_secret_key (platform's credentials to initiate OAuth)
    ↓
Organizer connects their Stripe account
    ↓
Stores: stripe_customer_id in OrganizerBillingModel (per-organizer)
    ↓
When charging tickets:
    - Use organizer's customer ID + saved payment method
    - Store payment intent in BillingInvoice
```

**USE CASE 2 Code Flow**:
```
Celery Task: process_auto_billing_charge_stripe()
    ↓
uses: payment_stripe_connect_secret_key (platform's Connect credentials)
    ↓
For each organizer:
    - Create payment intent for their fee
    - Store payment_intent_id in BillingInvoice.stripe_payment_intent_id
    - Charge organizer's saved payment method
```

---

## Current Implementation Problems (If Any)

### 1. **Webhook Secret Ambiguity** ⚠️
The `stripe_webhook_secret_key` in global settings is **unclear**:
- Which Stripe account does it belong to?
- Platform's account or organizer's account?
- Should there be TWO webhook secrets (one for each use case)?

**Current behavior** (based on code): Appears to be for **organizer's webhook** (USE CASE 1), but should be verified.

### 2. **Naming Confusion**
- `payment_stripe_*` could mean "payment provider Stripe" or "Stripe for organizer payments"
- `payment_stripe_connect_*` clearly means "Stripe Connect" but it's for platform fees, not organizer connections
- Better names would be:
  - `payment_stripe_organizer_*` → for USE CASE 1 (organizer payments)
  - `payment_stripe_connect_*` → for USE CASE 2 (platform fee collection) ← already done

### 3. **No Clear Separation in UI**
The global settings form groups them all together without distinction:
```
[Payment Gateways]
  ├─ PayPal settings
  ├─ Stripe (for organizer payments)    ← Not labeled clearly
  ├─ Stripe Connect (for platform fees) ← Not labeled clearly
```

---

## Recommendations for Streamlining

### 1. **Clarify Naming (Non-Breaking)**
In `control/forms/global_settings.py`, add comments:

```python
('payment_gateways', _('Payment Gateways'), [
    # PayPal
    'payment_paypal_connect_client_id',
    ...
    
    # Stripe - ORGANIZE PAYMENTS (via eventyay-stripe plugin)
    # These are the platform's Stripe credentials used for initiating organizer connections
    'payment_stripe_secret_key',
    'payment_stripe_publishable_key',
    'payment_stripe_test_secret_key',
    'payment_stripe_test_publishable_key',
    
    # Stripe Connect - PLATFORM FEE COLLECTION (built-in)
    # These are the platform's Stripe Connect credentials for auto-billing organizers
    'payment_stripe_connect_client_id',
    'payment_stripe_connect_secret_key',
    ...
    
    # Webhooks
    'stripe_webhook_secret_key',  # TODO: Clarify which account this belongs to
]),
```

### 2. **Separate UI Sections (Breaking Change - Not Recommended)**
Reorganize global settings form to show:
```
[Payment Gateways]
  ├─ PayPal Settings
  ├─ Stripe Settings (Organizer Direct Payments)
  │   ├─ payment_stripe_secret_key
  │   ├─ payment_stripe_publishable_key
  │   └─ ...
  └─ Stripe Connect Settings (Platform Fee Collection)
      ├─ payment_stripe_connect_secret_key
      ├─ payment_stripe_connect_publishable_key
      └─ ...
```

**Not recommended** because:
- Breaking change to settings form
- Both sections need to be configured together
- Current approach works fine

### 3. **Fix Webhook Secret Ambiguity** (Recommended)
Create a clear function like:

```python
def get_organizer_stripe_webhook_secret() -> str:
    """Get webhook secret for organizer's Stripe account (USE CASE 1)"""
    return GlobalSettingsObject().settings.stripe_webhook_secret_key

def get_platform_stripe_webhook_secret() -> str:
    """Get webhook secret for platform's Stripe Connect (USE CASE 2)"""
    # Currently missing - should be added if platform fees have webhooks
    return GlobalSettingsObject().settings.stripe_connect_webhook_secret_key
```

### 4. **Document Storage Architecture**
Create a diagram in codebase:

```
Global Settings
├─ payment_stripe_*_key           ← USE CASE 1: Platform's credentials for organizer connections
├─ payment_stripe_connect_*       ← USE CASE 2: Platform's credentials for fee collection
└─ stripe_webhook_secret_key      ← USE CASE 1: Webhook for organizer's payments

OrganizerBillingModel (per-organizer)
├─ stripe_customer_id             ← USE CASE 1: Organizer's Stripe customer in platform
├─ stripe_payment_method_id       ← USE CASE 1: Organizer's payment method (setup intent)
└─ stripe_setup_intent_id         ← USE CASE 1: In-progress Stripe setup intent

BillingInvoice (per-invoice)
├─ stripe_payment_intent_id       ← USE CASE 2: Payment intent for fee invoice
└─ (possibly also for USE CASE 1 invoice tracking)

Event Settings (per-event)
└─ payment_stripe__enabled        ← USE CASE 1: Enable/disable Stripe for event
```

---

## Answer to "Why Different Places?"

**The separation is CORRECT and INTENTIONAL**:

1. **Global Settings**: Store credentials that are **read-only by admin**, used to **configure payment behavior**
   - Both use cases need admin-level credentials
   - Both are platform-wide configuration
   - Makes sense to have them together

2. **OrganizerBillingModel**: Store **per-organizer identifiers** for USE CASE 1
   - Organizer A's Stripe customer ID ≠ Organizer B's
   - Must be per-organizer
   - Separate from credentials because it's data, not config

3. **BillingInvoice**: Store **per-invoice payment tracking**
   - Different invoices have different payment intents
   - Must be per-invoice
   - Links invoice to actual Stripe transaction

4. **Event Settings**: Store **per-event feature toggle** for USE CASE 1
   - Organizer can enable Stripe for Event 1 but not Event 2
   - Must be per-event

---

## Summary Table: Storage by Use Case

| **Component** | **USE CASE 1** | **USE CASE 2** | **Storage Location** |
|---|---|---|---|
| Platform's Stripe secret key | ✅ Used for OAuth | ❌ | Global Settings |
| Platform's Stripe publishable key | ✅ For frontend | ❌ | Global Settings |
| Platform's Stripe Connect secret | ❌ | ✅ For auto-billing | Global Settings |
| Platform's Stripe Connect publishable | ❌ | ✅ For app fees | Global Settings |
| Organizer's Stripe customer ID | ✅ Per-organizer | ❌ | `OrganizerBillingModel` |
| Organizer's payment method ID | ✅ Per-organizer | ❌ | `OrganizerBillingModel` |
| Invoice payment intent ID | ✅ Per-invoice | ✅ Per-invoice | `BillingInvoice` |
| Event toggle | ✅ Per-event | ❌ | Event Settings |
| Webhook secret | ✅ Organizer account | ❌ | Global Settings |

**Conclusion**: The current implementation is **logically sound**. The confusion comes from **unclear naming** and **lack of documentation**, not architectural problems.

