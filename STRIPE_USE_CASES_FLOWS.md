# Stripe: Two Use Cases & Implementation Flows

## Quick Reference: The Two Use Cases

### USE CASE 1: Organizer Receives Ticket Payments (External Plugin)
```
Customer buys ticket → Platform accepts payment → Money goes to Organizer's Stripe
```
- **External Plugin**: eventyay-stripe (GitHub dependency)
- **Organizer Setup**: Clicks button to connect their Stripe account
- **Who controls funds**: Organizer (gets money directly)
- **Charges**: Organizer's customer → Organizer's Stripe account

### USE CASE 2: Platform Collects Recurring Fees (Built-In)
```
Organizer's billing cycle → Platform auto-charges organizer → Money to Platform's Stripe
```
- **Implementation**: Built-in Django code + Celery tasks
- **Setup**: Admin configures platform's Stripe Connect keys
- **Who controls funds**: Platform (collects service fees)
- **Charges**: Organizer → Platform's account (via Stripe Connect)

---

## Storage Architecture

### 1. GLOBAL SETTINGS (One-time admin config)
**File**: `control/forms/global_settings.py` lines 315-328

```python
# USE CASE 1: Platform's credential for initiating organizer connections
'payment_stripe_secret_key',           # For OAuth during organizer setup
'payment_stripe_publishable_key',      # For frontend payment forms
'payment_stripe_test_secret_key',      # Test environment
'payment_stripe_test_publishable_key',

# USE CASE 2: Platform's Stripe Connect credentials for auto-billing
'payment_stripe_connect_client_id',           # OAuth client for Connect
'payment_stripe_connect_secret_key',          # For charging organizers
'payment_stripe_connect_publishable_key',    # For frontend fee display
'payment_stripe_connect_test_secret_key',    # Test mode
'payment_stripe_connect_test_publishable_key',
'payment_stripe_connect_app_fee_percent',    # Fee configuration
'payment_stripe_connect_app_fee_max',
'payment_stripe_connect_app_fee_min',

# Webhooks
'stripe_webhook_secret_key',           # Webhook secret (clarification needed)
```

**Retrieved by**:
- `stripe_utils.get_stripe_secret_key()` → returns `payment_stripe_secret_key`
- `stripe_utils.get_stripe_publishable_key()` → returns `payment_stripe_publishable_key`
- (No dedicated getter for Connect keys found - used directly)

---

### 2. PER-ORGANIZER DATA (OrganizerBillingModel)
**File**: `base/models/organizer.py` lines 737-751

```python
class OrganizerBillingModel(models.Model):
    organizer = models.OneToOneField(Organizer, on_delete=models.CASCADE, related_name='billing')
    
    # USE CASE 1 only
    stripe_customer_id = models.CharField(...)           # Org's Stripe customer ID
    stripe_payment_method_id = models.CharField(...)    # Org's saved payment method
    stripe_setup_intent_id = models.CharField(...)      # In-progress Stripe setup
```

**Created/Updated by**:
- `stripe_utils.create_stripe_customer(organizer)` → on organizer creation
- `stripe_utils.update_stripe_customer_from_webhook(customer_id)` → on webhook
- `stripe_utils.update_payment_method(stripe_customer_id, payment_method_id)` → when organizer adds payment method

**Used by**:
- External eventyay-stripe plugin (via global settings keys)
- Ticket payment processing

---

### 3. PER-INVOICE DATA (BillingInvoice)
**File**: `base/models/billing.py` line 67

```python
class BillingInvoice(models.Model):
    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE)
    ...
    stripe_payment_intent_id = models.CharField(...)    # Payment intent ID
```

**Used by**:
- **USE CASE 2**: Auto-billing task stores payment intent here
- **USE CASE 1**: Possibly for invoice tracking (verify)

**Populated by**:
- `stripe_utils.process_auto_billing_charge_stripe(invoice)` → creates payment intent

---

### 4. PER-EVENT TOGGLE (Event Settings)
**File**: `control/forms/event.py` lines 1476-1513

```
Event Settings namespace:
└─ payment_stripe__enabled: True/False
```

**Used by**:
- External plugin to enable/disable Stripe per event
- Checked when rendering payment options

**Set by**:
- PaymentProviderSettings view in control panel

---

## Code Flow: USE CASE 1 (Organizer Payments)

### Step 1: Organizer Connects Stripe Account
**Triggered by**: Organizer clicks "Connect Stripe" button in organizers menu

```
┌─ control/views/organizer_views.py
│  └─ StripeConnectSetup (TBD: search for exact view)
│     ├─ Uses: payment_stripe_secret_key (from Global Settings)
│     ├─ Initiates: Stripe OAuth flow with organizer
│     └─ Receives: organizer's Stripe access token
│
├─ External plugin: eventyay-stripe
│  └─ Exchanges token for organizer's Stripe customer ID
│
└─ stripe_utils.create_stripe_customer()
   ├─ Stores: stripe_customer_id in OrganizerBillingModel
   └─ Logs: Organizer now connected to Stripe
```

### Step 2: Customer Purchases Ticket
**Triggered by**: Ticket purchase flow

```
┌─ presale/views.py (or custom checkout)
│  └─ PaymentProcess
│     ├─ Gets: event.settings.payment_stripe__enabled (enabled per-event)
│     ├─ Checks: organizer.billing.stripe_customer_id exists
│     └─ If yes: Show Stripe payment form
│
├─ Frontend (JavaScript)
│  ├─ Uses: payment_stripe_publishable_key (from Global Settings)
│  └─ Creates: Payment Intent on platform side
│
└─ External plugin: eventyay-stripe
   ├─ Gets: organizer.billing.stripe_customer_id
   ├─ Gets: organizer.billing.stripe_payment_method_id
   └─ Charges: Customer → Organizer's Stripe account
```

### Step 3: Payment Confirmation
```
Stripe Webhook
├─ Event: payment_intent.succeeded
├─ Verified: Using stripe_webhook_secret_key (from Global Settings)
└─ Updates: BillingInvoice.stripe_payment_intent_id + status
```

---

## Code Flow: USE CASE 2 (Platform Fee Collection)

### Step 1: Billing Cycle Triggers
**Triggered by**: Celery task on schedule

```python
# File: eventyay_common/tasks.py
@periodic_task(run_every=crontab(hour=0, minute=0))  # Daily at midnight
def process_monthly_billing():
    for organizer in Organizer.objects.filter(billing__active=True):
        process_auto_billing_charge_stripe(organizer)
```

### Step 2: Create & Charge Invoice
```
┌─ stripe_utils.process_auto_billing_charge_stripe()
│  ├─ Gets: payment_stripe_connect_secret_key (from Global Settings)
│  ├─ Gets: organizer.billing.stripe_customer_id
│  ├─ Gets: organizer.billing.stripe_payment_method_id
│  │
│  ├─ Step A: Calculate fee amount (app_fee_percent, app_fee_max, app_fee_min)
│  │
│  ├─ Step B: Create Stripe PaymentIntent
│  │  └─ stripe.PaymentIntent.create(
│  │       customer=stripe_customer_id,
│  │       payment_method=stripe_payment_method_id,
│  │       amount=fee_amount,
│  │       currency='usd',
│  │       on_behalf_of=platform_stripe_account,  # ← Stripe Connect
│  │       application_fee_amount=app_fee_amount
│  │     )
│  │
│  ├─ Step C: Confirm payment
│  │  └─ stripe.PaymentIntent.confirm(intent_id)
│  │
│  └─ Step D: Save payment intent
│     └─ BillingInvoice.stripe_payment_intent_id = intent_id
│
└─ Result: Organizer charged, platform receives fee
```

---

## Key Functions & Their Use Cases

### Global Settings Getters (stripe_utils.py)

```python
def get_stripe_secret_key() -> str:
    """USE CASE 1: For organizer payment processing"""
    # Gets: payment_stripe_secret_key
    
def get_stripe_publishable_key() -> str:
    """USE CASE 1: For frontend payment form"""
    # Gets: payment_stripe_publishable_key

def get_stripe_webhook_secret_key() -> str:
    """USE CASE 1 or 2?: Webhook verification"""
    # Gets: stripe_webhook_secret_key
    # TODO: Clarify which account this belongs to
```

### Per-Organizer Functions (stripe_utils.py)

```python
def create_stripe_customer(organizer: Organizer) -> str:
    """USE CASE 1: Create organizer's customer ID on platform"""
    # Stores in: OrganizerBillingModel.stripe_customer_id
    
def get_stripe_customer_id(organizer_slug: str) -> str:
    """USE CASE 1 & 2: Retrieve organizer's customer ID"""
    # Reads from: OrganizerBillingModel.stripe_customer_id
    
def update_payment_method(stripe_customer_id: str, payment_method_id: str) -> None:
    """USE CASE 1: Save organizer's payment method"""
    # Stores in: OrganizerBillingModel.stripe_payment_method_id
```

### Auto-Billing Functions (stripe_utils.py)

```python
def process_auto_billing_charge_stripe(invoice: BillingInvoice) -> dict:
    """USE CASE 2: Charge organizer for service fees"""
    # Uses: payment_stripe_connect_secret_key
    # Reads: OrganizerBillingModel.stripe_customer_id, stripe_payment_method_id
    # Stores: BillingInvoice.stripe_payment_intent_id
```

---

## Why the Confusion Exists

The global settings file mixes both use cases:

```python
# Same place, different purposes:
'payment_stripe_secret_key'              # USE CASE 1
'payment_stripe_connect_secret_key'      # USE CASE 2
```

### This is Actually OK Because:
✅ Both are platform-level configuration  
✅ Both set by admin once  
✅ Both used at runtime  
✅ Makes sense to group all payment config together  

### But Could Be Improved By:
📝 Adding section comments to explain each group  
📝 Creating separate getter functions for Connect keys  
📝 Documenting which use case each key supports  

---

## Verification Questions (For Developer Clarification)

1. **Webhook Secret**: Is `stripe_webhook_secret_key` for:
   - Organizer's webhook (USE CASE 1)?
   - Platform's webhook (USE CASE 2)?
   - Both (need two separate secrets)?

2. **Platform Fees in USE CASE 1**: When USE CASE 1 charge happens, is there a:
   - Platform fee deducted from organizer's payment?
   - If yes, does it use `payment_stripe_connect_*` keys?
   - Or does external plugin handle it?

3. **BillingInvoice Usage**:
   - Used only for USE CASE 2 (platform fees)?
   - Or also for USE CASE 1 (ticket sales tracking)?

4. **External Plugin Integration**:
   - Does eventyay-stripe read `payment_stripe_secret_key` directly?
   - Or does it call `stripe_utils.get_stripe_secret_key()`?
   - How is it installed/configured?

