# Stripe Storage Locations: Quick Reference

## The Question
> "We have several different areas where the keys to connect to Stripe are stored. It is unclear why there are different places in the DB."

## The Answer
**The separation is intentional and correct.** Eventyay uses Stripe for two different purposes, requiring different storage:

---

## Storage Locations Explained

| **Storage Location** | **What It Stores** | **Purpose** | **Use Case** |
|---|---|---|---|
| **Global Settings** `payment_stripe_*_key` | Platform's Stripe credentials | Authenticate organizers; process their payments | USE CASE 1 |
| **Global Settings** `payment_stripe_connect_*` | Platform's Stripe Connect credentials | Charge organizers for service fees | USE CASE 2 |
| **OrganizerBillingModel** `stripe_customer_id` | Each organizer's Stripe customer ID | Track which organizer is which in Stripe | USE CASE 1 |
| **OrganizerBillingModel** `stripe_payment_method_id` | Each organizer's saved payment method | Charge organizer's saved card for fees | USE CASE 2 |
| **BillingInvoice** `stripe_payment_intent_id` | Payment intent for each fee invoice | Track which invoice was charged to Stripe | USE CASE 2 |
| **Event Settings** `payment_stripe__enabled` | Boolean toggle | Enable/disable Stripe per event | USE CASE 1 |

---

## Two Use Cases Explained

### USE CASE 1: Ticket Payments → Organizer's Stripe Account
```
Customer → Platform → Organizer's Stripe (organizer receives money)
```

**External Plugin**: `eventyay-stripe`

**Keys Used**:
- `payment_stripe_secret_key` ← Platform's credentials to initiate organizer connection
- `payment_stripe_publishable_key` ← Platform's credentials for payment forms
- `stripe_webhook_secret_key` ← Verify webhooks from organizer's Stripe

**Per-Organizer Storage** (`OrganizerBillingModel`):
- `stripe_customer_id` ← Which Stripe account is this organizer?
- `stripe_payment_method_id` ← What's their payment method?
- `stripe_setup_intent_id` ← In-progress setup?

**Flow**:
```
1. Organizer clicks "Connect Stripe" button
   ↓ uses payment_stripe_secret_key for OAuth
   ↓
2. System stores organizer's stripe_customer_id
   ↓
3. Customer buys ticket
   ↓ uses organizer's stripe_customer_id + payment_method_id
   ↓ payment goes to organizer's Stripe account
   ↓
4. BillingInvoice records the payment_intent_id (for tracking)
```

---

### USE CASE 2: Service Fees → Platform's Stripe Account
```
Organizer (scheduled billing) → Platform's Stripe (platform collects fees)
```

**Built-In Feature** (Celery task + Django code)

**Keys Used**:
- `payment_stripe_connect_secret_key` ← Platform's Stripe Connect credentials
- `payment_stripe_connect_publishable_key` ← For fee display
- `payment_stripe_connect_app_fee_percent` ← Fee calculation
- `payment_stripe_connect_app_fee_max` ← Fee caps
- `payment_stripe_connect_app_fee_min`

**Per-Organizer Storage** (used from `OrganizerBillingModel`):
- `stripe_customer_id` ← Which organizer to charge?
- `stripe_payment_method_id` ← What card to charge?

**Per-Invoice Storage** (`BillingInvoice`):
- `stripe_payment_intent_id` ← Which Stripe payment for this fee invoice?

**Flow**:
```
1. Scheduled billing task runs daily
   ↓
2. For each organizer:
   - Get stripe_customer_id + stripe_payment_method_id from OrganizerBillingModel
   - Use payment_stripe_connect_secret_key to charge
   ↓
3. Create payment on platform's Stripe account
   ↓
4. Store payment_intent_id in BillingInvoice
```

---

## Why Separate Locations?

### **Global Settings**
- **Purpose**: Admin-level configuration (read once, used everywhere)
- **Scope**: Platform-wide (not organizer-specific)
- **Content**: Both USE CASE 1 and USE CASE 2 keys (mixed together)

### **OrganizerBillingModel**
- **Purpose**: Each organizer's Stripe identifiers (they can enable/disable independently)
- **Scope**: Per-organizer (different organizers = different IDs)
- **Content**: USE CASE 1 and USE CASE 2 data (same organizer, different purposes)

### **BillingInvoice**
- **Purpose**: Track payment for each fee invoice (audit trail)
- **Scope**: Per-invoice (each invoice gets one payment)
- **Content**: Payment intent ID (links invoice to Stripe transaction)

### **Event Settings**
- **Purpose**: Control which events accept Stripe (organizer choice)
- **Scope**: Per-event (organizer can enable for Event A but not Event B)
- **Content**: Boolean toggle for USE CASE 1

---

## The "Confusion" Is Naming, Not Architecture

### Problem: Global Settings Mix Both Use Cases
```python
# control/forms/global_settings.py lines 315-328
'payment_stripe_secret_key',                    # ← What is this for?
'payment_stripe_connect_secret_key',            # ← What is this for?
'stripe_webhook_secret_key',                    # ← What account is this?
```

### Solution: Add Documentation
```python
# Stripe - ORGANIZER PAYMENTS (via external eventyay-stripe plugin)
# These are the platform's Stripe API keys used to authenticate the plugin
'payment_stripe_secret_key',           # USE CASE 1: Initiate organizer connections
'payment_stripe_publishable_key',      # USE CASE 1: Payment form frontend
'payment_stripe_test_secret_key',      # USE CASE 1: Test mode
'payment_stripe_test_publishable_key', # USE CASE 1: Test mode

# Stripe Connect - PLATFORM FEE COLLECTION (via built-in Celery tasks)
# These are the platform's Stripe Connect credentials for auto-billing organizers
'payment_stripe_connect_client_id',              # USE CASE 2: OAuth client
'payment_stripe_connect_secret_key',             # USE CASE 2: Charge organizers
'payment_stripe_connect_publishable_key',        # USE CASE 2: Fee display
'payment_stripe_connect_app_fee_percent',        # USE CASE 2: Fee config
'payment_stripe_connect_app_fee_max',            # USE CASE 2: Fee config
'payment_stripe_connect_app_fee_min',            # USE CASE 2: Fee config

# Webhooks
'stripe_webhook_secret_key',           # TODO: Clarify which account/use case
```

---

## Streamlining Recommendations

### 1. **Add Code Comments** (Easiest, Non-Breaking)
✅ Document which keys are for which use case in `control/forms/global_settings.py`

### 2. **Create Dedicated Getters** (Recommended)
✅ Instead of accessing keys directly, create helper functions:
```python
def get_organizer_stripe_keys():
    """Returns keys for USE CASE 1 (organizer payments)"""
    
def get_platform_stripe_connect_keys():
    """Returns keys for USE CASE 2 (fee collection)"""
```

### 3. **Clarify Webhook Setup**
⚠️ **ACTION NEEDED**: Determine if `stripe_webhook_secret_key` is for:
- Organizer's webhook (USE CASE 1) → Rename to clarify
- Platform's webhook (USE CASE 2) → Add separate setting
- Both → Create two separate settings

### 4. **Write Architecture Documentation**
✅ Document in `/doc/development/` explaining:
- Two use cases and their flows
- Which keys are used where
- How data flows through the system
- Which external plugins are involved

---

## Summary

**Is the current separation necessary?**  
✅ **YES** — Different scopes require different storage locations.

**Are keys stored in confusing places?**  
⚠️ **SOMEWHAT** — Both use cases are in global settings, but that's intentional.

**How to improve?**  
📝 Add documentation and section comments.

**Conclusion**:  
The implementation is sound. The confusion comes from **unclear naming and lack of documentation**, not architectural problems. No major refactoring needed.

