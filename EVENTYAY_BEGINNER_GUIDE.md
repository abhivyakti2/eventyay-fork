# Eventyay: Complete Beginner's Guide
## Understanding Eventyay as Product & Codebase

**Target Audience**: New developers with no prior Eventyay knowledge  
**Prerequisites**: Django, REST APIs, basic Python knowledge  
**Time to Complete Full Guide**: ~4 hours  
**Time for Exploration Checklist**: ~2-3 hours hands-on

---

## Table of Contents
1. [Part 1: What is Eventyay?](#part-1-what-is-eventyay)
2. [Part 2: User Roles & Mental Model](#part-2-user-roles--mental-model)
3. [Part 3: End-to-End Product Workflow](#part-3-end-to-end-product-workflow)
4. [Part 4: Payments & Testing Locally](#part-4-payments--testing-locally)
5. [Part 5: Plugins & Integrations](#part-5-plugins--integrations)
6. [Part 6: Repository Structure](#part-6-repository-structure)
7. [Part 7: Signals & Background Tasks](#part-7-signals--background-tasks)
8. [Part 8: Code Exploration Techniques](#part-8-code-exploration-techniques)
9. [Part 9: Exploration Checklist](#part-9-exploration-checklist)

---

# Part 1: What is Eventyay?

## Product Overview

### Mission
**Eventyay is a unified event management platform** that handles everything an organizer needs to run events: ticketing, speaker management (Call for Papers), scheduling, and virtual event streaming.

### What Problems Does It Solve?

| Problem | Eventyay Solution |
|---------|-------------------|
| "I need to sell tickets online" | **Presale** component - public shop, inventory, payments |
| "I need to collect speaker submissions" | **Talk/CFP** component - Call for Papers, speaker workflow |
| "I need to schedule talks and manage speakers" | **Schedule/Orga** component - scheduling, speaker management |
| "I need to livestream my event" | **Video** component - virtual rooms, streaming, WebSockets |
| "I need custom functionality" | **Plugins** system - extend without modifying core |

### Key Insight: "Three Components, One Codebase"

Most event management platforms are separate tools. Eventyay is **unified**:
- All components share a **single Django database**
- All components share **authentication and user management**
- All components share **payment processing, plugins, and settings**
- One organizer account manages events across all components

**Example**: When a speaker buys a workshop ticket (Presale) and submits a talk proposal (Talk/CFP), it's the same Order, same Event, same User.

---

## Core Features at a Glance

### 1. **Events** (The Container)
- Think of an event as a "conference" or "concert"
- Each event belongs to one **Organizer** (a team/company)
- Contains: tickets, speakers, schedule, attendees, orders, payments

### 2. **Tickets/Products** (What You Sell)
- **Items**: Individual product types (e.g., "Early Bird Ticket", "VIP Pass", "Workshop")
- **Variations**: Options like "Size: Small/Medium/Large" or "Color: Blue/Red"
- **Quotas**: Limit how many of each product can be sold
- **Pricing**: Static or dynamic pricing, volume discounts, tax handling

### 3. **Orders** (Customer Purchases)
- When someone buys one or more tickets, an **Order** is created
- Contains multiple **OrderPositions** (one per ticket/attendee)
- Has lifecycle: PENDING → PAID → (COMPLETED/CANCELED)
- Links to **Attendees** (buyers and ticket holders can be different people)

### 4. **Payments** (Money Processing)
- Multiple payment providers: Stripe, PayPal, manual bank transfer, offsetting, etc.
- Order can have multiple payment attempts
- Order finalized only when **payment confirmed**
- Invoices generated on payment completion

### 5. **Attendees** (Ticket Holders)
- Can provide custom data: name, email, address, company, etc.
- Configurable per event: What questions to ask? (e.g., diet preferences)
- Can have **check-in status** (arrived at event or not)

### 6. **Plugins** (Extensibility)
- Payment providers (Stripe, PayPal, etc.)
- Integrations (email, webhooks, custom auth)
- Features (badges, check-in lists, reports, statistics)
- **No code modification needed** - register settings form and signal handlers

---

## Core Insight: The Order Lifecycle

This is **critical** to understanding Eventyay:

```
Customer Action          → Database State                    → Signals Fired
─────────────────────────────────────────────────────────────────────────
1. Add to cart           → Cart session stored              → (none yet)
2. Enter attendee data   → (still in cart session)          → (none yet)
3. Complete checkout     → Order created (PENDING)          → order_placed signal
4. Payment submitted     → OrderPayment created (PENDING)   → (none yet)
5. Payment confirmed     → Order → PAID, OrderPayment confirmed  → order_paid signal ⭐
6. Invoice generated     → Invoice created                  → (invoice-related signals)
7. Check-in at event     → OrderPosition.checkin_date set   → (attendee arrived)
```

**Most important**: Step 5 (order_paid signal) is when:
- ✅ Attendees are considered "confirmed"
- ✅ Emails are sent ("Thank you for your order")
- ✅ Invoices are generated (if configured)
- ✅ **Plugins hook in here** (HubSpot sync, badge generation, etc.)

---

# Part 2: User Roles & Mental Model

## Different User Types

### 1. **End User / Attendee**
**Who**: Person buying a ticket  
**Actions**: Browse events, buy tickets, provide attendee info, check in, download tickets  
**Website Section**: `/presale/` (public-facing shop)  
**Database Role**: Creates Order, OrderPosition with attendee data  

### 2. **Event Organizer**
**Who**: Person managing an event (selling tickets, managing speakers)  
**Actions**: 
- Create events
- Configure tickets/products
- Set pricing and quotas
- View orders and attendees
- Generate invoices and reports
- Enable plugins
**Website Section**: `/control/` (admin dashboard)  
**Database Role**: Creates Event, modifies Order states, configures settings  

### 3. **Super Admin / Staff**
**Who**: Eventyay platform administrator  
**Actions**: Manage users, create organizers, monitor system health, manage global settings  
**Website Section**: Django admin (`/admin/`)  
**Database Role**: Creates User, Organizer, manages system settings  

### 4. **Speaker / Submission Submitter** (Talk Component)
**Who**: Person submitting talk proposals to CFP  
**Actions**: Create speaker profile, submit talk proposals, edit submissions, view schedule  
**Website Section**: `/cfp/` (submitter), `/orga/` (organizer reviewing)  
**Database Role**: Creates Submission, Submission objects  

---

## Key Relationships

```
User (Authentication)
  ↓
Organizer (Team/Company that runs events)
  ├─→ Event 1
  │   ├─→ OrderPosition (1+ per attendee)
  │   ├─→ Order (1+ per purchase)
  │   ├─→ OrderPayment (1+ per order)
  │   ├─→ Item/Product (ticket types)
  │   ├─→ Submission (talks in CFP)
  │   └─→ Schedule (published lineup)
  │
  └─→ Event 2
      └─→ (same structure)
```

**Key**: A User can belong to multiple Organizers, so they can manage multiple events.

---

# Part 3: End-to-End Product Workflow

## Overview: What You'll Do

This section walks you through the **complete user journey** with both UI steps and code implications.

**Prerequisites**:
- Eventyay running locally: `cd app && ./manage.py runserver`
- Site accessible at `http://localhost:8000/`
- You have a superuser created: `./manage.py createsuperuser`

---

## 3.1 STEP 1: Create an Account

### UI Steps
1. Go to `http://localhost:8000/` (homepage)
2. Click "Sign up" (usually in top-right)
3. Enter email, password, name
4. Click "Create Account"
5. Check email for verification link (in development, check Django email backend output)

### Code Involved
- **Model**: `User` model ([app/eventyay/base/models/auth.py](app/eventyay/base/models/auth.py))
- **View**: Registration view (look in [app/eventyay/control/views/auth.py](app/eventyay/control/views/auth.py))
- **Database Created**:
  ```
  base_user (
    id, email, password_hash, first_name, last_name,
    is_active, date_joined
  )
  ```

### What to Search For
```bash
# Find registration form
grep -r "class.*RegistrationForm" app/eventyay/

# Find signup view
grep -r "def.*sign.*up\|class.*SignUp" app/eventyay/control/ --include="*.py"
```

---

## 3.2 STEP 2: Log In

### UI Steps
1. Go to `http://localhost:8000/control/` (control panel)
2. Enter email and password
3. Dashboard appears with "Organizers" and "Teams"

### Code Involved
- **Middleware**: Authentication via Django sessions
- **File**: [app/eventyay/control/views/auth.py](app/eventyay/control/views/auth.py)
- **Signals**: Post-login signals may fire (check [app/eventyay/base/signals.py](app/eventyay/base/signals.py) for `user_logged_in`)

### What to Search For
```bash
grep -r "class.*LoginView\|def.*login" app/eventyay/control/views/ --include="*.py"
```

---

## 3.3 STEP 3: Create an Organizer (Team)

### UI Steps
1. In control panel `/control/`, click "Create organizer"
2. Enter organizer name (e.g., "MyConf Inc")
3. Enter organizer slug (e.g., "myconf-inc") - used in URLs
4. Click "Create"
5. You are now owner of this organizer/team

### Code Involved
- **Model**: `Organizer` model ([app/eventyay/base/models/organizer.py](app/eventyay/base/models/organizer.py))
- **View**: Organizer creation view in [app/eventyay/control/views/organizer.py](app/eventyay/control/views/organizer.py)
- **Database Created**:
  ```
  base_organizer (
    id, name, slug, is_public, logo_image,
    created, updated
  )
  ```
- **Relationship Created**:
  ```
  auth_user_organizers (
    user_id → base_user,
    organizer_id → base_organizer
  )
  ```

### What to Search For
```bash
# Find Organizer model
grep -r "class Organizer" app/eventyay/base/models/

# Find organizer views
find app/eventyay/control -name "*.py" | xargs grep -l "Organizer"
```

---

## 3.4 STEP 4: Create an Event

### UI Steps
1. In control panel, click on your organizer name
2. Click "Create event" (or similar button)
3. Fill in:
   - **Event name**: e.g., "MyConf 2025"
   - **Event slug**: e.g., "myconf2025" (unique per organizer)
   - **Date from**: e.g., "2025-06-15"
   - **Date to**: e.g., "2025-06-17"
   - **Timezone**: Select your timezone
   - **Currency**: Select currency (e.g., USD)
4. Click "Create"
5. Dashboard shows your event

### Code Involved
- **Model**: `Event` model ([app/eventyay/base/models/event.py](app/eventyay/base/models/event.py))
- **Key Fields**:
  ```python
  Event (
    name, slug,
    organizer_id → Organizer,
    date_from, date_to, timezone, currency,
    is_public, settings (HierarkeyProxy for per-event config),
    created
  )
  ```
- **Database Created**: New `base_event` record
- **Settings Initialized**: `hierarkey` creates default settings namespace for this event

### What to Search For
```bash
# Find Event model
grep -r "class Event" app/eventyay/base/models/event.py

# Find event creation view
find app/eventyay/control -name "*.py" | xargs grep -l "EventCreate\|def.*create.*event"
```

---

## 3.5 STEP 5: Add Tickets/Products

### UI Steps
1. In control panel, go to your event
2. Click "Products" or "Tickets"
3. Click "Create product"
4. Fill in:
   - **Product name**: e.g., "Early Bird Ticket"
   - **Default price**: e.g., "50" (in your currency)
   - **Tax rate**: Select or create tax rule
   - **Quota**: e.g., "100" (how many can be sold)
5. Click "Create"
6. Repeat for other ticket types (VIP, Standard, etc.)

### Code Involved
- **Model**: `Item` model ([app/eventyay/base/models/items.py](app/eventyay/base/models/items.py))
- **Related Models**:
  - `ItemVariation`: If you add "Size: S/M/L" options
  - `Quota`: Limits per item, per variation, or across items
  - `TaxRule`: Tax calculation per item
- **Key Fields**:
  ```python
  Item (
    event_id → Event,
    name, description,
    default_price (Decimal),
    tax_rule_id → TaxRule,
    category (for grouping),
    created
  )
  ```

### Database Created
- `base_item` record(s)
- `base_quota` record(s) if quotas set
- `base_itemvariation` record(s) if variations added

### What to Search For
```bash
# Find Item model
grep -r "class Item" app/eventyay/base/models/items.py

# Find product views
find app/eventyay/control -name "*.py" | xargs grep -l "ItemCreate\|ProductCreate"
```

---

## 3.6 STEP 6: Configure Event Settings & Plugins

### UI Steps
1. In control panel event, click "Settings" → "General"
2. Configure event details (description, contact email, etc.)
3. Click "Settings" → "Plugins"
4. See list of available plugins (Badges, Email, Stripe, etc.)
5. Click "Enable" next to a plugin (e.g., "Stripe payment")
6. Fill in plugin settings (e.g., Stripe API keys)
7. Click "Save"

### Code Involved
- **Settings Storage**: `event.settings` (hierarkey-based)
- **Key Setting Names**:
  ```
  general_*_text (descriptions, contact info)
  payment_provider_enabled (which providers available)
  plugin_* (plugin-specific settings)
  ```
- **Models**:
  - `EventSetting` (stored in database via hierarkey)
  - `PluginAppConfig` (metadata about enabled plugins)
- **File**: [app/eventyay/base/settings.py](app/eventyay/base/settings.py) - Settings system

### How Plugins Are Enabled
**Plugins are stored per-event** via:
```python
event.settings.set('plugin_PLUGINNAME_enabled', True)
event.settings.set('plugin_PLUGINNAME_api_key', 'secret123')
```

When an event signal fires (like `order_paid`), only **enabled plugins' receivers** are called (automatic filtering).

### What to Search For
```bash
# Find settings model
grep -r "class.*Setting" app/eventyay/base/models/settings.py

# Find plugin list view
find app/eventyay/control -name "*.py" | xargs grep -l "plugin\|integration"
```

---

## 3.7 STEP 7: Publish the Event (Make Live)

### UI Steps
1. In control panel, event settings → "General"
2. Find "Event is public" or "Is live" checkbox
3. Click to make event visible
4. Public URL becomes: `http://localhost:8000/myconf-inc/myconf2025/`

### Code Involved
- **Model Field**: `Event.live` (boolean)
- **URLs**: Event is only accessible in `/presale/` if `is_live=True`
- **Middleware**: [app/eventyay/common/middleware.py](app/eventyay/common/middleware.py) may filter based on `is_live`

### What to Search For
```bash
# Find is_live or live field
grep -r "is_live\|\.live" app/eventyay/base/models/event.py
```

---

## 3.8 STEP 8: Buy a Ticket as an Attendee

### UI Steps (Open New Browser / Incognito)
1. Go to `http://localhost:8000/myconf-inc/myconf2025/` (public shop)
2. See products listed (Early Bird, VIP, Standard, etc.)
3. Click "Add to cart" on one product
4. See cart with item, quantity, price
5. Modify quantity if needed
6. Click "Checkout"

### Code Involved
- **View**: Presale shop view ([app/eventyay/presale/views/checkout.py](app/eventyay/presale/views/checkout.py))
- **Session Storage**: Cart items stored in Django session
- **Model**: No database record yet (just session)

### What to Search For
```bash
# Find presale views
find app/eventyay/presale -name "*.py" | xargs grep -l "cart\|checkout"

# Find cart session logic
grep -r "session\[.*cart" app/eventyay/presale/
```

---

## 3.9 STEP 9: Enter Attendee Information

### UI Steps (Continuing Checkout)
1. Checkout page asks: "Who is this ticket for?"
2. See form fields:
   - Email address
   - Full name (or First name + Last name depending on settings)
   - Custom fields (if event configured them)
   - Address (if invoice address enabled)
3. Fill in attendee information
4. Click "Continue"

### Code Involved
- **Model**: `OrderPosition` - Not yet created (still in checkout)
- **Form**: [app/eventyay/presale/forms.py](app/eventyay/presale/forms.py) builds attendee forms dynamically
- **Settings Determine Fields**: `Event.settings.get('attendee_names_asked')`, etc.
- **Custom Fields**: Stored in `OrderPosition.info_data` (JSONField)

### What to Search For
```bash
# Find attendee form building
grep -r "attendee.*form\|attendee.*field" app/eventyay/presale/forms.py

# Find OrderPosition model
grep -r "class OrderPosition\|class.*Position" app/eventyay/base/models/orders.py
```

---

## 3.10 STEP 10: Complete Checkout (NO REAL PAYMENT)

### UI Steps (Continuing Checkout)
1. Checkout page shows:
   - Items in order
   - Total price
   - Available payment methods (depends on settings)
2. For testing **without real payments**, select:
   - **"Free" method** (for free events)
   - **"Manual bank transfer"** (no real payment)
   - **"Box office"** (admin-only, allows manual payment)
3. Click "Pay now" or "Complete order"
4. Order is created in database with status **PENDING**

### Code Involved
- **Model**: `Order` created
- **Status**: Initially `STATUS_PENDING`
- **Related Records**:
  - `OrderPosition` created for each item (one per ticket/attendee)
  - `OrderPayment` created with payment provider set
- **Signal Fired**: `order_placed` signal ([app/eventyay/base/signals.py](app/eventyay/base/signals.py#L400))

### Database State After This Step
```
Order (
  code="ABCD1", event_id=X, email="attendee@example.com",
  status="PENDING", total=Decimal('50'),
  created=now(), payment_provider="banktransfer"
)

OrderPosition (
  order_id=Y, item_id=Z,
  attendee_email="attendee@example.com",
  attendee_name_cached="John Doe",
  attendee_name_parts={first_name: "John", last_name: "Doe"},
  info_data={...custom fields...}
)

OrderPayment (
  order_id=Y, state="PENDING",
  payment_date=null, amount=Decimal('50'),
  provider="banktransfer"
)
```

### What to Search For
```bash
# Find order creation logic
grep -r "Order.objects.create\|order_placed.send" app/eventyay/presale/ --include="*.py"

# Find OrderPosition model
grep -r "class OrderPosition" app/eventyay/base/models/orders.py

# Find payment handling
grep -r "class.*Payment" app/eventyay/base/models/orders.py
```

---

## 3.11 STEP 11: Confirm Payment (Mark Order as PAID)

### Scenario: Using Manual Bank Transfer
**In real life**: Customer sends bank payment, organizer checks bank account, manually confirms in admin.  
**For testing**: We simulate confirmation.

### UI Steps (As Organizer)
1. Go to control panel → Event → "Orders"
2. Find the order you just created (code "ABCD1")
3. Click on the order
4. See payment section: "Bank transfer" with status "PENDING"
5. Click "Mark as paid" (or similar button)
6. Order status changes to **PAID**

### Code Involved
- **Method**: `OrderPayment.confirm()` ([app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py#L1590))
- **What Happens**:
  1. `OrderPayment.state` → `PAYMENT_STATE_CONFIRMED`
  2. `Order.status` → `STATUS_PAID`
  3. `Order.payment_date` set to now
  4. **CRITICAL**: `order_paid` signal is **FIRED** 🔥
- **Signal Fire**: `order_paid.send(sender=order.event, order=order)`

### This Is The Critical Moment!
When `order_paid` signal fires:
- ✅ Attendees are "confirmed"
- ✅ Invoices generated (if configured)
- ✅ Confirmation emails sent
- ✅ **Plugins activated** (HubSpot sync, badge generation, webhooks, etc.)

### What to Search For
```bash
# Find OrderPayment.confirm() method
grep -n "def confirm" app/eventyay/base/models/orders.py

# Find order_paid signal definition
grep -r "order_paid.*=" app/eventyay/base/signals.py

# Find order_paid signal emitters
grep -r "order_paid.send" app/eventyay/ --include="*.py"
```

---

## 3.12 STEP 12: View Order & Attendee Details (As Organizer)

### UI Steps
1. Control panel → Event → "Orders"
2. Click on the order code
3. See:
   - Attendee details (name, email, custom fields)
   - Order status (PAID)
   - Payment info (amount, date)
   - Invitation to download ticket (if enabled)

### Code Involved
- **Models Displayed**:
  - `Order` (status, payment_date, total)
  - `OrderPosition` (attendee info - email, name, custom fields)
  - `OrderPayment` (payment details)
- **View**: Order detail view in [app/eventyay/control/views/orders.py](app/eventyay/control/views/orders.py)
- **Template**: Order detail template in [app/eventyay/control/templates/control/event/order/](app/eventyay/control/templates/control/event/order/)

### What to Search For
```bash
# Find order detail view
find app/eventyay/control/views -name "*.py" | xargs grep -l "OrderDetail\|class.*Order"

# Find order templates
find app/eventyay/control/templates -path "*order*" -name "*.html"
```

---

## 3.13 STEP 13: View Attendee List (As Organizer)

### UI Steps
1. Control panel → Event → "Attendees"
2. See table with all attendees from all orders:
   - Name, Email, Ticket type
   - Check-in status
   - Order code
3. Can export to CSV (if plugin enabled)
4. Can manually check in (mark as arrived)

### Code Involved
- **Model**: `OrderPosition` is the "attendee"
- **View**: Attendee list view in [app/eventyay/control/views/orders.py](app/eventyay/control/views/orders.py)
- **Query**:
  ```python
  OrderPosition.objects.filter(
    order__event=event,
    order__status='PAID'  # Only confirmed attendees
  )
  ```
- **Custom Fields**: Stored in `OrderPosition.info_data` (JSONField)

### What to Search For
```bash
# Find attendee list view
grep -r "attendee\|OrderPosition" app/eventyay/control/views/orders.py

# Find attendee template
find app/eventyay/control/templates -path "*attendee*" -name "*.html"
```

---

## 3.14 STEP 14: Generate & View Invoice

### UI Steps
1. Control panel → Event → "Orders" → Click order
2. See "Invoice" section
3. If invoice not yet generated:
   - Click "Generate invoice"
4. If already generated:
   - Click "Download" or "View" PDF

### Code Involved
- **Model**: `Invoice` ([app/eventyay/base/models/invoices.py](app/eventyay/base/models/invoices.py))
- **Trigger**: Usually generated when order payment confirmed
- **Stored**:
  - Database: `Invoice` record with number, date, amount
  - File: PDF in storage backend (S3, local filesystem, etc.)
- **PDF Generation**: Plugin/library handles rendering

### Database State
```
Invoice (
  order_id=Y, number="2025-00001",
  invoice_date=now(), due_date=...,
  amount=Decimal('50'),
  is_cancellation=False
)
```

### What to Search For
```bash
# Find Invoice model
grep -r "class Invoice" app/eventyay/base/models/invoices.py

# Find invoice generation logic
grep -r "Invoice.objects.create\|invoice.*generate" app/eventyay/ --include="*.py" | head -20
```

---

# Part 4: Payments & Testing Locally

## How Payments Work in Eventyay

### Payment Flow Conceptually

```
1. Customer initiates payment
   ↓
2. Payment provider selected (Stripe, PayPal, bank transfer, etc.)
   ↓
3. OrderPayment record created (state=PENDING)
   ↓
4. Customer completes payment (or organizer marks manual payment)
   ↓
5. Payment provider confirms (webhook or manual)
   ↓
6. OrderPayment.confirm() called
   ├─ Order.status → PAID
   ├─ order_paid signal fired 🔥
   └─ Attendees now "confirmed"
   ↓
7. Post-payment actions:
   - Invoices generated
   - Emails sent
   - Plugins activated
   - Attendee data available
```

### Key Concept: Multiple OrderPayments

An Order can have **multiple OrderPayment records**:
- Customer pays $30, order is $50 → partial payment (PENDING)
- Customer pays remaining $20 → now PAID (all payments confirmed)
- Or customer refunds partial amount → new payment with negative amount

### Payment Providers in Eventyay

| Provider | Type | For Local Testing? | Real Money? |
|----------|------|------------------|------------|
| **Manual (Bank Transfer)** | Manual | ✅ YES | ❌ NO |
| **Stripe** | Auto/Integration | ✅ YES (test mode) | ❌ NO (in test keys) |
| **PayPal** | Auto/Integration | ⚠️ Possible (sandbox) | ❌ NO (in sandbox) |
| **Manual Box Office** | Admin-only | ✅ YES | ❌ NO |
| **Offsetting** | Internal | ✅ YES | ❌ NO |

---

## Testing Locally: Recommended Approaches

### Approach 1: FREE TICKETS (Simplest)

**Best for**: Quick testing, no payment logic needed

**Steps**:
1. Create a product with price = **0**
2. Customer buys it
3. Order created with status **PAID** automatically (no payment needed)
4. order_paid signal fires immediately
5. Test order confirmation, invoices, attendees

**Code Impact**:
```python
# When order total is 0, payment is auto-confirmed
if order.total == Decimal('0'):
    order.status = Order.STATUS_PAID
    order.save()
    order_paid.send(sender=order.event, order=order)
```

### Approach 2: MANUAL BANK TRANSFER (Recommended for Full Testing)

**Best for**: Testing entire order flow including pending/paid transition

**Steps**:
1. Enable "Manual bank transfer" in event settings → Plugins
2. Customer buys ticket for $50
3. Order created with status **PENDING**, OrderPayment status **PENDING**
4. As organizer:
   - Go to control panel → Orders
   - Find the order
   - Click "Mark as paid" or similar
5. OrderPayment.confirm() called → order_paid signal fires

**Code Location**: [app/eventyay/plugins/banktransfer/payment.py](app/eventyay/plugins/banktransfer/payment.py)

**Testing Checklist**:
- [ ] Order in PENDING state after checkout
- [ ] Attendee data stored in OrderPosition
- [ ] Order changes to PAID when manually confirmed
- [ ] order_paid signal was fired
- [ ] Plugin signal handlers executed (check logs)
- [ ] Invoice generated (if configured)

### Approach 3: STRIPE TEST MODE (Most Realistic)

**Best for**: Testing real payment integration without real money

**Setup**:
1. Create Stripe account (free, automatic test mode)
2. Get test API keys from Stripe dashboard
3. In event settings → Plugins → Stripe:
   - Enable Stripe
   - Enter test **public key** and **secret key**
4. Customer buys ticket
5. Checkout shows Stripe payment form
6. Use Stripe test card: `4242 4242 4242 4242`
   - Expiry: Any future date
   - CVC: Any 3 digits
7. Payment succeeds → Order immediately PAID

**Stripe Test Cards**:
```
4242 4242 4242 4242    → Payment succeeds
4000 0000 0000 0002    → Payment declined
```

**Code Location**: [app/eventyay/plugins/stripe/](app/eventyay/plugins/stripe/) (Stripe plugin)

### Approach 4: OFFSETTING (Internal Testing)

**Best for**: Testing multiple orders between organizers

**Concept**: One organizer's payment is offset against another's debt (like internal accounting)

**How**: Less common, skip unless testing complex scenarios

---

## Which Flows Trigger order_paid Signal?

### ✅ Flows That TRIGGER order_paid:

1. **Free tickets** ($0 order):
   - Immediately marked PAID, signal fires

2. **Manual bank transfer** (marked paid by organizer):
   - Organizer clicks "Mark as paid"
   - OrderPayment.confirm() called
   - Signal fires

3. **Stripe payment** (card approved):
   - Stripe webhook confirms payment
   - OrderPayment.confirm() called
   - Signal fires

4. **Order import** (bulk upload by organizer):
   - Organizer bulk-imports orders as CSV
   - OrderPayment.confirm() called for each
   - Signal fires

### ❌ Flows That DO NOT trigger order_paid:

1. **Order in PENDING state** - not confirmed yet
2. **Partial payment** - only when ALL payments confirmed
3. **Order cancellation** - fires order_canceled instead
4. **Order modification** - fires order_changed instead

---

## What NOT to Test Locally

### ❌ DO NOT Test:
- Real card payments (use test mode instead)
- PayPal real payments (use sandbox instead)
- Production API keys (always use test/sandbox)
- Real payment webhooks from Stripe/PayPal (local environment can't receive them)

### ⚠️ Limitations:
- Bank transfer webhooks require manual marking (no automatic bank sync locally)
- PayPal sandbox requires PayPal account setup
- Some advanced features (subscription billing) may not work without real integration

---

# Part 5: Plugins & Integrations

## How the Plugin System Works

### Conceptually: Plugin = Signal Listener

A plugin in Eventyay is:
1. **Registered** in `/app/eventyay/plugins/{pluginname}/`
2. **Metadata** defined in `apps.py` (name, version, description)
3. **Signal subscriptions** defined in `signals.py` (what events to listen to)
4. **Configuration** form in `forms.py` (API keys, settings)
5. **Logic** in various files (tasks, models, views, etc.)

### Plugin Architecture

```
Plugin System
└─ /plugins/
   ├─ banktransfer/          (Payment provider)
   │  ├─ apps.py             (Plugin metadata)
   │  ├─ signals.py          (@receiver decorators)
   │  ├─ payment.py          (Payment logic)
   │  ├─ forms.py            (Config form)
   │  ├─ tasks.py            (Celery tasks)
   │  └─ ...
   ├─ stripe/                (Payment provider)
   ├─ badges/                (Feature: generate badges/tickets)
   ├─ sendmail/              (Feature: send custom emails)
   ├─ statistics/            (Feature: sales analytics)
   ├─ reports/               (Feature: generate reports)
   ├─ webcheckin/            (Feature: mobile check-in)
   └─ ...
```

### Key Signal Points Where Plugins Hook In

| Signal | When Fired | What It Means |
|--------|-----------|--------------|
| `order_placed` | Order created (PENDING) | Customer completed checkout |
| `order_paid` ⭐ | Order status → PAID | Payment confirmed, attendees ready |
| `order_canceled` | Order status → CANCELED | Customer cancels order |
| `order_expired` | Order not paid in time | Order deadline passed |
| `order_modified` | Order details changed | Customer edits attendee info |
| `register_ticket_outputs` | Ticket generation | Generate PDF badges, QR codes |
| `nav_event` | Sidebar built | Add plugin menu item |
| `nav_organizer` | Admin menu built | Add organizer-level menu |

### How Plugins Are Enabled Per Event

**Plugins are enabled per-event**, stored in `event.settings`:

```python
# Organizer enables Stripe for an event
event.settings.set('plugin_stripe_enabled', True)
event.settings.set('plugin_stripe_secret_key', 'sk_test_...')
event.settings.set('plugin_stripe_public_key', 'pk_test_...')

# When order_paid signal fires for THIS event:
# Only Stripe plugin's order_paid receiver is called
# (Other plugins not enabled for event are skipped)
```

**Signal System** (`EventPluginSignal`):
- Automatically filters receivers by enabled plugins
- Only calls signal handlers for enabled plugins
- No manual checking needed in handler code

### Example Plugin: Badges

**Purpose**: Generate ticket PDFs with barcodes/QR codes

**Location**: [app/eventyay/plugins/badges/](app/eventyay/plugins/badges/)

**Signal Subscriptions** ([app/eventyay/plugins/badges/signals.py](app/eventyay/plugins/badges/signals.py)):
```python
@receiver(register_ticket_outputs)
def register_badge_outputs(sender, **kwargs):
    """When organizer asks 'generate tickets', this fires"""
    return {
        'badges': {
            'name': 'Badges',
            'generator': BadgeGenerator,
        }
    }
```

**Workflow**:
1. Organizer clicks "Download tickets/badges"
2. `register_ticket_outputs` signal fires
3. Badges plugin returns its badge generator
4. Badges plugin generates PDF for each OrderPosition
5. PDF downloaded

### Example Plugin: Stripe

**Purpose**: Process credit card payments

**Location**: [app/eventyay/plugins/stripe/](app/eventyay/plugins/stripe/)

**Payment Provider Registration**:
```python
class StripeProvider(BasePaymentProvider):
    identifier = 'stripe'
    verbose_name = 'Credit card (Stripe)'
    
    def payment_form_fields(self):
        """Return Stripe payment form fields"""
        return {...}
    
    def checkout_confirm_render(self, request):
        """Render Stripe payment element"""
        return {...}
    
    def execute_payment(self, request, payment):
        """Process payment with Stripe API"""
        # Call Stripe API
        # If successful, call payment.confirm()
```

**Webhook Handling**:
- Stripe sends webhook: "payment successful"
- Eventyay receives webhook
- Plugin calls `OrderPayment.confirm()`
- order_paid signal fires
- Attendees confirmed

### Example: HubSpot Plugin (What You'd Build)

**Purpose**: Sync attendee data to HubSpot CRM when orders paid

**File Structure**:
```
plugins/hubspot/
├── apps.py                  (Register plugin)
├── signals.py               (Listen to order_paid)
├── tasks.py                 (Async sync to HubSpot API)
├── forms.py                 (API key config form)
└── models.py                (Optional: sync log, contact mapping)
```

**Signal Handler**:
```python
@receiver(order_paid, dispatch_uid='hubspot_sync')
def sync_to_hubspot(sender, order, **kwargs):
    """Fired when order paid - queue async sync"""
    sync_order_to_hubspot.delay(order.pk)

@shared_task
def sync_order_to_hubspot(order_pk):
    """Async task - call HubSpot API"""
    order = Order.objects.get(pk=order_pk)
    api_key = order.event.settings.get('plugin_hubspot_api_key')
    
    for position in order.all_positions.all():
        hubspot_client.create_contact({
            'email': position.attendee_email,
            'firstName': position.attendee_name_parts['first_name'],
            ...
        })
```

---

# Part 6: Repository Structure

## Top-Level Layout

```
eventyay-fork/
├── app/                          # Main Django application
│   ├── eventyay/                 # Django project directory
│   │   ├── base/                 # Shared models, services, utilities
│   │   ├── api/                  # REST API (DRF viewsets, serializers)
│   │   ├── control/              # Organizer web interface (/control/)
│   │   ├── presale/              # Public ticket shop (/presale/)
│   │   ├── plugins/              # All plugins
│   │   ├── config/               # Django settings
│   │   ├── common/               # Shared middleware, signals, utilities
│   │   ├── helpers/              # Helper functions
│   │   ├── static/               # CSS, JS, images
│   │   ├── jinja-templates/      # HTML templates
│   │   └── locale/               # Translations
│   ├── manage.py                 # Django management script
│   ├── pyproject.toml            # Dependencies (Django, DRF, Celery, etc.)
│   └── Makefile                  # Build commands
│
├── doc/                          # Documentation
│   ├── admin/                    # Administration guides
│   ├── development/              # Developer guides
│   │   ├── setup.rst             # Local setup
│   │   ├── structure.rst         # Project structure
│   │   └── concepts.rst          # Key concepts
│   ├── user/                     # End-user documentation
│   └── api/                      # API documentation
│
├── tests/                        # Test suite
│   ├── tickets/                  # Ticket/order tests
│   ├── talk/                     # Talk/CFP tests
│   ├── video/                    # Video/streaming tests
│   └── stable/                   # Stable/shared tests
│
├── deployment/                   # Docker, nginx configs
├── CONTRIBUTING.md               # Contribution guidelines
└── README.rst                    # Project README
```

---

## Key Directories Deep Dive

### 1. `/app/eventyay/base/` - Shared Core

**Purpose**: Database models, services, signals shared across all components

**Key Files**:
```
base/
├── models/
│   ├── __init__.py              (Import all models for convenience)
│   ├── organizer.py             (Organizer model)
│   ├── event.py                 (Event model)
│   ├── orders.py                (Order, OrderPosition, OrderPayment models)
│   ├── items.py                 (Item, ItemVariation, Quota models)
│   ├── invoices.py              (Invoice model)
│   ├── auth.py                  (User model)
│   └── room.py                  (Video room model - streaming)
├── services/
│   ├── orders.py                (Order processing logic)
│   ├── payments.py              (Payment processing)
│   └── invoices.py              (Invoice generation)
├── email.py                     (Email sending utilities)
├── signals.py                   (All signal definitions)
├── settings.py                  (Hierarkey settings system)
└── payment.py                   (BasePaymentProvider - for plugins)
```

### 2. `/app/eventyay/control/` - Organizer Dashboard

**Purpose**: Web UI for organizers to manage events

**What Lives Here**:
```
control/
├── views/
│   ├── event.py                 (Event detail, settings views)
│   ├── orders.py                (Orders, attendees list views)
│   ├── items.py                 (Products/items management)
│   ├── organizer.py             (Organizer settings)
│   └── ...
├── forms/
│   ├── event.py                 (Event configuration forms)
│   ├── orders.py                (Bulk actions on orders)
│   └── ...
├── templates/
│   └── control/
│       ├── event/
│       │   ├── orders/          (Order list, detail templates)
│       │   ├── items/           (Product templates)
│       │   └── settings/        (Event settings UI)
│       └── organizer/           (Organizer management)
└── urls.py                      (URL routing for /control/)
```

**Key Views to Know**:
- **EventDetail**: Show event overview
- **OrderList**: List all orders for event
- **OrderDetail**: Show single order and attendees
- **AttendeeList**: List all attendees
- **EventSettings**: Edit event configuration
- **PluginSettings**: Enable/disable plugins, configure API keys

### 3. `/app/eventyay/presale/` - Public Ticket Shop

**Purpose**: Customer-facing ticket purchasing

**What Lives Here**:
```
presale/
├── views/
│   ├── checkout.py              (Checkout flow - item selection, attendee forms, payment)
│   ├── event.py                 (Event shop landing page)
│   └── cart.py                  (Cart management)
├── forms.py                     (Attendee data forms, generated dynamically)
├── templates/
│   └── presale/
│       ├── event/               (Event shop template)
│       └── checkout/            (Checkout step templates)
└── urls.py                      (URL routing for /organizer/event/)
```

**Key Views to Know**:
- **EventDetail**: Event landing page (shows products, FAQs, schedule)
- **CheckoutFlow**: Multi-step checkout (cart → attendee forms → payment)
- **CartSummary**: Show cart and allow modifications
- **PaymentProcess**: Show payment form and process payment

### 4. `/app/eventyay/api/` - REST API

**Purpose**: JSON API for mobile apps, integrations, webhooks

**What Lives Here**:
```
api/
├── views/
│   ├── order.py                 (Order API endpoints)
│   ├── event.py                 (Event API endpoints)
│   ├── organizer.py             (Organizer API endpoints)
│   └── ...
├── serializers/
│   ├── order.py                 (OrderSerializer, OrderPositionSerializer)
│   ├── event.py                 (EventSerializer)
│   └── ...
├── auth/
│   └── api_auth.py              (API token authentication, permissions)
├── urls.py                      (URL routing for /api/v1/)
└── webhooks.py                  (Webhook registration, signal dispatch)
```

**API Endpoints**:
```
GET  /api/v1/organizers/{slug}/events/{slug}/orders/
GET  /api/v1/organizers/{slug}/events/{slug}/orders/{code}/
POST /api/v1/organizers/{slug}/events/{slug}/orders/
GET  /api/v1/organizers/{slug}/events/{slug}/attendees/
```

### 5. `/app/eventyay/plugins/` - Plugin Directory

**Purpose**: Extend Eventyay without modifying core

**Structure**:
```
plugins/
├── banktransfer/                (Manual bank transfer payment provider)
├── stripe/                      (Stripe payment provider)
├── badges/                      (Generate ticket PDFs)
├── sendmail/                    (Send custom emails)
├── statistics/                  (Sales analytics)
├── webcheckin/                  (Mobile check-in app)
└── ...
```

**Each plugin has**:
```
plugin-name/
├── apps.py                      (AppConfig + EventyayPluginMeta)
├── signals.py                   (@receiver decorators for hooks)
├── models.py                    (Optional: plugin-specific models)
├── forms.py                     (Configuration forms)
├── views.py                     (Optional: plugin pages)
├── tasks.py                     (Optional: Celery async tasks)
└── templates/                   (Optional: HTML templates)
```

### 6. `/app/eventyay/config/` - Django Settings

**Purpose**: Django configuration and initialization

**Key Files**:
```
config/
├── settings.py                  (Main Django settings - DATABASES, APPS, MIDDLEWARE)
├── urls.py                      (Main URL routing)
├── wsgi.py                      (Production deployment)
└── asgi.py                      (Async workers, WebSockets)
```

**To Know**:
- `INSTALLED_APPS`: Lists all Django apps (plugins auto-discovered here)
- `MIDDLEWARE`: Request/response pipeline
- `DATABASES`: PostgreSQL connection
- `CELERY_*`: Celery/Redis configuration
- `REST_FRAMEWORK`: DRF settings (pagination, auth, etc.)

### 7. `/app/eventyay/common/` - Shared Utilities

**Purpose**: Middleware, signals, helpers used across all components

**Key Files**:
```
common/
├── middleware.py                (Multi-tenant routing, event context, permissions)
├── signals.py                   (Shared signal definitions)
├── models.py                    (Shared abstract models)
└── utilities.py                 (Helper functions)
```

**Important Middleware**:
- **MultiDomainMiddleware**: Routes requests based on organizer/event URL
- **EventPermissionMiddleware**: Sets `request.event` context and checks permissions
- **PermissionMiddleware**: Requires login and event ownership for `/control/`

### 8. `/app/eventyay/helpers/` - Utility Functions

**Purpose**: Reusable helper functions across codebase

**Examples**:
```
helpers/
├── models.py                    (Abstract model mixins)
├── services.py                  (Service functions)
├── forms.py                     (Form helpers)
├── json.py                      (JSON serialization)
└── ...
```

---

## How to Trace a Feature Through the Codebase

### Example: "Order Paid → Attendee Created → Email Sent"

**Step 1: Find the Signal**
```bash
grep -r "order_paid" app/eventyay/base/signals.py
# Found: line ~460, definition of order_paid signal
```

**Step 2: Find Who Emits It**
```bash
grep -r "order_paid.send" app/eventyay/ --include="*.py"
# Results:
# - app/eventyay/base/models/orders.py:1590  (OrderPayment.confirm())
# - app/eventyay/base/services/orders.py:199
# - app/eventyay/plugins/banktransfer/payment.py:...
```

**Step 3: Find Who Listens (Signal Receivers)**
```bash
grep -r "@receiver(order_paid)" app/eventyay/ --include="*.py"
# Results:
# - app/eventyay/plugins/sendmail/signals.py:...
# - app/eventyay/plugins/badges/signals.py:...
# - Other plugins...
```

**Step 4: Examine a Receiver**
```bash
# Look at sendmail plugin
cat app/eventyay/plugins/sendmail/signals.py
# Find @receiver(order_paid) decorator
# See logic: send confirmation email to attendees
```

**Step 5: Find Attendee Creation**
```bash
grep -r "attendee_email" app/eventyay/presale/ --include="*.py"
# Look at checkout views - OrderPosition created here with attendee data
grep -r "OrderPosition.objects.create\|order_paid" app/eventyay/presale/views/checkout.py
```

---

# Part 7: Signals & Background Tasks

## What Are Signals?

Signals in Django are a **publish-subscribe messaging system**:
- A part of code **broadcasts** a signal: "Order was paid!"
- Other parts **listen** and respond: "Send email", "Generate invoice", "Sync to HubSpot"

### Why Signals Matter in Eventyay

Eventyay uses signals to **decouple plugins from core**:
- Core never directly calls plugin code
- Plugins register signal handlers and react to events
- Multiple plugins can listen to same signal (no conflicts)
- Plugins can be enabled/disabled per-event without core changes

---

## Important Signals in Eventyay

### Order Lifecycle Signals

```python
# From app/eventyay/base/signals.py

# When customer completes checkout (order created as PENDING)
order_placed = EventPluginSignal()
# Parameters: sender=Event, order=Order
# Used by: Email notifications, webhook integrations

# When order payment confirmed (THIS IS THE BIG ONE)
order_paid = EventPluginSignal()  ⭐⭐⭐
# Parameters: sender=Event, order=Order
# Used by: Invoice generation, email confirmations, HubSpot sync, badge generation
# THIS IS WHEN ATTENDEES ARE CONSIDERED "CONFIRMED"

# When order canceled by customer
order_canceled = EventPluginSignal()
# Parameters: sender=Event, order=Order
# Used by: Refund logic, notification emails

# When order modified (attendee info changed)
order_modified = EventPluginSignal()
# Parameters: sender=Event, order=Order
# Used by: Email notification, invoice updates

# When order expires (payment not made in time)
order_expired = EventPluginSignal()
# Parameters: sender=Event, order=Order
# Used by: Cleanup, notification emails
```

### Plugin System Signals

```python
# When organizer asks to download tickets
register_ticket_outputs = GlobalSignal()
# Used by: Badges plugin (return badge generator)
#          Reports plugin (return report generator)

# When building organizer sidebar navigation
nav_organizer = GlobalSignal()
# Used by: Plugins adding menu items

# When building event page sidebar
nav_event = GlobalSignal()
# Used by: Plugins adding event-specific menu items
```

### Payment System Signals

```python
# When payment provider is initialized
payment_provider_init = EventPluginSignal()
# Used by: Plugins adding new payment methods

# When payment method list is built
payment_methods_available = EventPluginSignal()
# Used by: Plugins filtering payment methods by event settings
```

---

## How EventPluginSignal Works (Event-Scoped)

### Standard Django Signal
```python
# Standard Django signal - ALL receivers called, no filtering
@receiver(post_save, sender=Order)
def notify_on_order_save(sender, instance, **kwargs):
    send_email(instance.email, 'Order saved')
```

### EventPluginSignal (Event-Aware)
```python
# EventPluginSignal - only receivers for ENABLED PLUGINS called
@receiver(order_paid, dispatch_uid='hubspot_sync')
def sync_to_hubspot(sender, order, **kwargs):
    # sender = Event instance
    # order = Order instance
    # This receiver ONLY called if:
    # 1. order.event.plugins has 'hubspot' enabled
    # 2. request.event matches order.event (multi-tenant safety)
    sync_attendees_to_hubspot(order)
```

### Code Location
[app/eventyay/base/signals.py](app/eventyay/base/signals.py) lines 116+:

```python
class EventPluginSignal(Signal):
    """
    A signal with automatic event-aware receiver filtering.
    Only receivers for enabled plugins are called.
    """
    def send(self, sender, **kwargs):
        # sender = Event instance
        # Filters to only enabled plugins for that event
        # Calls their receivers
```

---

## Celery & Background Tasks

### When & Why Use Background Tasks

**Synchronous (Immediate, in request)**:
```
Customer pays → order_paid signal fires → code runs → response sent
```
**Problem**: If code is slow (API call, email sending, PDF generation), customer waits.

**Asynchronous (Background, in Celery)**:
```
Customer pays → order_paid signal fires → queue task → response sent immediately
                    (task runs in background)
```
**Benefit**: Customer sees confirmation immediately, slow work happens in background.

### Celery in Eventyay

**Setup**: Celery + Redis queue (for background jobs)

**Configuration**: [app/eventyay/config/settings.py](app/eventyay/config/settings.py)
```python
CELERY_BROKER_URL = 'redis://localhost:6379/1'  # Job queue
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'  # Result storage
CELERY_TASK_ALWAYS_EAGER = True  # In development: run tasks immediately (synchronous)
```

**In development**: Tasks run immediately (synchronous), so you can test without Redis running.

### Writing a Background Task

**Example**: Generate PDF badge in background

```python
# In app/eventyay/plugins/badges/tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3)
def generate_badge_pdf(self, orderposition_id):
    """
    Generate badge PDF for attendee.
    If fails, automatically retry up to 3 times.
    """
    try:
        position = OrderPosition.objects.get(id=orderposition_id)
        pdf_content = render_badge_to_pdf(position)
        position.badge_pdf = pdf_content
        position.save()
    except Exception as e:
        # Retry with exponential backoff
        self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

**Using the Task**:
```python
# In signal handler
@receiver(order_paid)
def handle_order_paid(sender, order, **kwargs):
    for position in order.all_positions.all():
        # Queue task (doesn't block)
        generate_badge_pdf.delay(position.id)
```

### Task Discovery

Celery auto-discovers tasks in `{app}/tasks.py`:

```python
# app/eventyay/plugins/badges/apps.py
class BadgesConfig(AppConfig):
    name = 'eventyay.plugins.badges'
    
    def ready(self):
        from . import tasks  # Auto-load tasks.py for Celery
        from . import signals  # Auto-load signals.py for receivers
```

### Finding Tasks in Codebase

```bash
# Find all Celery tasks
grep -r "@shared_task\|@celery.task" app/eventyay/ --include="*.py"

# Find task files
find app/eventyay -name "tasks.py"

# Find specific task
grep -r "def my_task_name" app/eventyay/ --include="tasks.py"
```

---

# Part 8: Code Exploration Techniques

## How to Find Things in the Codebase

### Technique 1: Use grep for Specific Searches

```bash
# Find a model definition
grep -r "class Order" app/eventyay/base/models/

# Find where OrderPayment.confirm() is defined
grep -n "def confirm" app/eventyay/base/models/orders.py

# Find all usages of a function
grep -r "order_paid.send" app/eventyay/ --include="*.py"

# Find all signal receivers
grep -r "@receiver\|dispatch_uid" app/eventyay/ --include="*.py" | grep order

# Find all Celery tasks
grep -r "@shared_task" app/eventyay/ --include="*.py"

# Find where a setting is read
grep -r "event.settings.get.*payment" app/eventyay/control/ --include="*.py"
```

### Technique 2: Trace by URL Pattern

```bash
# Find what view handles /control/event/slug/orders/
grep -r "orders" app/eventyay/control/urls.py

# Find the view class
grep -r "class.*Order.*List\|class.*Order.*Detail" app/eventyay/control/views/ --include="*.py"

# Find the template
find app/eventyay/control/templates -path "*order*" -name "*.html"
```

### Technique 3: Follow the Database

```bash
# Find Order model
grep -r "class Order" app/eventyay/base/models/orders.py

# Read Order model
cat app/eventyay/base/models/orders.py | less

# Find where Order is created
grep -r "Order.objects.create" app/eventyay/ --include="*.py"

# Find where Order.status is changed
grep -r "\.status.*=" app/eventyay/base/models/orders.py | grep -v "self\._"
```

### Technique 4: Use IDE/Editor

**VS Code**:
- Right-click on class name → "Go to Definition"
- Right-click on function → "Find All References"
- Search: `Ctrl+Shift+F` for full codebase search
- Settings: Search `@query` to find all `query` usages

**Command Line**:
```bash
# Install ripgrep (faster than grep)
# brew install ripgrep  # macOS
# apt-get install ripgrep  # Linux

# Use ripgrep
rg "class Order" app/eventyay/
rg "order_paid.send" app/eventyay/
```

---

## Which Files to Keep Open While Exploring

### Essential Files (Open These First)

1. **Models** - Understand data structure
   - [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py) - Order, OrderPosition, OrderPayment
   - [app/eventyay/base/models/event.py](app/eventyay/base/models/event.py) - Event, Organizer
   - [app/eventyay/base/models/items.py](app/eventyay/base/models/items.py) - Item, Quota

2. **Signals** - Understand hooks
   - [app/eventyay/base/signals.py](app/eventyay/base/signals.py) - All signal definitions

3. **URLs** - Understand routing
   - [app/eventyay/control/urls.py](app/eventyay/control/urls.py) - Control panel routing
   - [app/eventyay/presale/urls.py](app/eventyay/presale/urls.py) - Public shop routing
   - [app/eventyay/api/urls.py](app/eventyay/api/urls.py) - API routing

4. **Views** - Understand logic
   - Depends on what you're exploring

5. **Settings** - Understand configuration
   - [app/eventyay/config/settings.py](app/eventyay/config/settings.py) - Django config

### Suggested Layout While Exploring

**Terminal**: Running `./manage.py runserver` or interacting with site

**Tab 1**: Models file (e.g., orders.py)
```bash
# Terminal 1: Keep your Django dev server running
cd app && ./manage.py runserver
```

**Tab 2**: Signals file + grep terminal
```bash
# Terminal 2: Dedicated to searching
cd app
grep -r "order_paid.send" eventyay/ --include="*.py"
```

**Editor**: Keep multiple files open
- Left pane: Current model/view
- Right pane: Related signals/forms

---

## Suggested Search Patterns

### Pattern 1: Tracing an Order

```bash
# 1. Find where Order is created
grep -r "Order.objects.create" app/eventyay/ --include="*.py" -n

# 2. Find where status changes
grep -r "order\.status\s*=" app/eventyay/base/models/ --include="*.py" -n

# 3. Find where signal is emitted
grep -r "order_paid.send" app/eventyay/ --include="*.py" -n

# 4. Find where signal is received
grep -r "@receiver(order_paid" app/eventyay/ --include="*.py" -n
```

### Pattern 2: Tracing Attendee Data

```bash
# 1. Find OrderPosition model
grep -r "class OrderPosition" app/eventyay/base/models/ -n

# 2. Find where attendee_email is set
grep -r "attendee_email\s*=" app/eventyay/ --include="*.py" -n

# 3. Find where attendee data is displayed
grep -r "attendee_email\|attendee_name" app/eventyay/control/templates/ -n

# 4. Find where attendee data is validated
grep -r "attendee" app/eventyay/presale/forms.py -n
```

### Pattern 3: Tracing a Plugin Hook

```bash
# 1. Find the signal definition
grep -r "^[a-z_]*\s*=\s*EventPluginSignal" app/eventyay/base/signals.py

# 2. Find where it's emitted
grep -r "your_signal.send" app/eventyay/ --include="*.py"

# 3. Find who listens
grep -r "@receiver(your_signal" app/eventyay/plugins/ --include="*.py"

# 4. Examine plugin handler
cat app/eventyay/plugins/PLUGINNAME/signals.py
```

### Pattern 4: Tracing Settings Storage

```bash
# 1. Find where a setting is written
grep -r "event.settings.set" app/eventyay/ --include="*.py" -B2 -A2

# 2. Find where it's read
grep -r "event.settings.get\|organizer.settings.get" app/eventyay/ --include="*.py"

# 3. Find form that provides UI for setting
grep -r "api_key\|secret" app/eventyay/plugins/*/forms.py
```

---

# Part 9: Exploration Checklist

## Quick Start (30 minutes)

- [ ] Setup Eventyay locally: [doc/development/setup.rst](doc/development/setup.rst)
- [ ] Run: `cd app && ./manage.py runserver`
- [ ] Access: `http://localhost:8000`
- [ ] Create superuser: `./manage.py createsuperuser`
- [ ] Login to `/admin/`
- [ ] Open [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py) in editor

## Beginner Level (2 hours)

### Understanding Product & Database

- [ ] **Create an organizer**
  - UI: Control panel → Create organizer
  - Files to check: 
    - [app/eventyay/base/models/organizer.py](app/eventyay/base/models/organizer.py) - Organizer model
    - [app/eventyay/control/views/organizer.py](app/eventyay/control/views/organizer.py) - Creation view
  - Database: `SELECT * FROM base_organizer;`

- [ ] **Create an event**
  - UI: Control panel → Your organizer → Create event
  - Files to check:
    - [app/eventyay/base/models/event.py](app/eventyay/base/models/event.py) - Event model
    - [app/eventyay/control/views/event.py](app/eventyay/control/views/event.py) - Event views
  - Database: `SELECT * FROM base_event;`

- [ ] **Create 2-3 ticket types (products)**
  - UI: Control panel → Event → Products → Create
  - Files to check:
    - [app/eventyay/base/models/items.py](app/eventyay/base/models/items.py) - Item model
  - Database: `SELECT * FROM base_item;`

- [ ] **Make event live (publish)**
  - UI: Control panel → Event settings → Toggle "Public"
  - Check database: `SELECT is_live FROM base_event;`

### Understanding Order Flow

- [ ] **Buy a ticket (as attendee)**
  - UI: Go to `http://localhost:8000/ORGANIZER/EVENT/`
  - Click "Add to cart"
  - Fill checkout form with attendee details
  - Select "Manual bank transfer" (or free tickets if price=0)
  - Click "Complete order"
  - Files to check:
    - [app/eventyay/presale/views/checkout.py](app/eventyay/presale/views/checkout.py) - Checkout logic
    - [app/eventyay/presale/forms.py](app/eventyay/presale/forms.py) - Attendee forms
  - Database: `SELECT * FROM base_order WHERE status='PENDING';`

- [ ] **View order in control panel**
  - UI: Control panel → Event → Orders → Click order code
  - See attendee data, payment status
  - Files to check:
    - [app/eventyay/control/views/orders.py](app/eventyay/control/views/orders.py) - Order detail view
    - [app/eventyay/control/templates/control/event/order/](app/eventyay/control/templates/control/event/order/) - Templates

- [ ] **Mark order as paid**
  - UI: Click order → "Mark as paid" button
  - Files to check:
    - [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py) - OrderPayment.confirm() method (line ~1590)
  - Database: `SELECT status FROM base_order;` - Should be 'PAID'

### Understanding Signals

- [ ] **Read signal definitions**
  - File: [app/eventyay/base/signals.py](app/eventyay/base/signals.py)
  - Find: `order_placed`, `order_paid`, `order_canceled` signals
  - Understand: When each fires, what parameters passed

- [ ] **Trace order_paid signal**
  - Where emitted: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py#L1590) in OrderPayment.confirm()
  - Who listens: `grep -r "@receiver(order_paid" app/eventyay/plugins/`
  - Example: [app/eventyay/plugins/sendmail/signals.py](app/eventyay/plugins/sendmail/signals.py) - Send email on order paid

- [ ] **Verify signal fired**
  - When you marked order as paid, check logs for signal receivers
  - Look for "order_paid" in server output
  - Check if emails were sent (if email logging enabled)

### Understanding Attendees

- [ ] **View attendee list**
  - UI: Control panel → Event → Attendees
  - See all attendees from all orders
  - Files to check:
    - [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py#L2136) - OrderPosition model
    - [app/eventyay/control/views/orders.py](app/eventyay/control/views/orders.py) - Attendee list view

- [ ] **Examine attendee data in database**
  - Query: `SELECT attendee_email, attendee_name_cached FROM base_orderposition;`
  - Note: attendee_name_parts is JSONField, check with: `SELECT attendee_name_parts::text FROM base_orderposition;` (PostgreSQL)

- [ ] **Understand OrderPosition model**
  - File: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py) line 2136
  - Fields: attendee_email, attendee_name_cached, attendee_name_parts, info_data
  - Understand: One OrderPosition per ticket, links to order.all_positions

---

## Intermediate Level (3-4 hours)

### Understanding Plugins

- [ ] **Enable a plugin for your event**
  - UI: Control panel → Event → Plugins
  - Enable "Sendmail" (Custom email plugin)
  - Files to check:
    - [app/eventyay/plugins/sendmail/apps.py](app/eventyay/plugins/sendmail/apps.py) - Plugin metadata
    - [app/eventyay/plugins/sendmail/signals.py](app/eventyay/plugins/sendmail/signals.py) - Signal receivers

- [ ] **Understand plugin registration**
  - File: [app/eventyay/plugins/sendmail/apps.py](app/eventyay/plugins/sendmail/apps.py)
  - See: EventyayPluginMeta class with plugin metadata
  - See: ready() method imports signals.py

- [ ] **Trace plugin signal receiver**
  - File: [app/eventyay/plugins/sendmail/signals.py](app/eventyay/plugins/sendmail/signals.py)
  - Find: @receiver decorators
  - Understand: How receiver listens to specific signal
  - See: What code runs when signal fires

- [ ] **Test plugin activation by order_paid**
  - Buy another ticket
  - Mark order as paid
  - Check plugin logic was executed (look at logs, side effects)
  - Example: Sendmail plugin should send email

### Understanding Payments

- [ ] **Look at available payment methods**
  - File: [app/eventyay/base/payment.py](app/eventyay/base/payment.py)
  - See: BasePaymentProvider class
  - See: Settings form fields for payment configuration

- [ ] **Enable Stripe plugin (optional, if you want real payment testing)**
  - Create free Stripe account
  - Get test API keys
  - UI: Event → Plugins → Enable Stripe
  - Enter test keys
  - Try buying ticket with test card: `4242 4242 4242 4242`

- [ ] **Understand payment flow**
  - File: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py) - OrderPayment model
  - See: Payment states (PENDING, CONFIRMED, REFUNDED)
  - See: confirm() method fires order_paid signal

### Understanding Settings Storage

- [ ] **Examine event settings**
  - File: [app/eventyay/base/settings.py](app/eventyay/base/settings.py)
  - Understand: SettingsSandbox class
  - Understand: event.settings.get/set pattern

- [ ] **Enable a plugin with API key**
  - UI: Event → Plugins → Enable plugin that needs API key (e.g., Stripe)
  - Fill in API key in form
  - Check database: `SELECT key, value FROM eventyay_hierarkey;`
  - See: Setting is stored as `plugin_PLUGINNAME_*`

- [ ] **Read plugin settings in code**
  - File: [app/eventyay/plugins/banktransfer/payment.py](app/eventyay/plugins/banktransfer/payment.py) line 201
  - See: `self.settings.get('public_name', as_type=LazyI18nString)`
  - Understand: How plugins read their configuration

### Understanding API

- [ ] **Access API documentation**
  - Go to: `http://localhost:8000/api/v1/`
  - API root with available endpoints

- [ ] **Get list of orders (via API)**
  - Endpoint: `/api/v1/organizers/{slug}/events/{slug}/orders/`
  - Files to check:
    - [app/eventyay/api/views/order.py](app/eventyay/api/views/order.py) - Order viewsets
    - [app/eventyay/api/serializers/order.py](app/eventyay/api/serializers/order.py) - Serializers

- [ ] **Understand API authentication**
  - File: [app/eventyay/api/auth/api_auth.py](app/eventyay/api/auth/api_auth.py)
  - See: Token-based authentication, permission classes

---

## Advanced Level (2-3 hours)

### Understanding Celery & Async

- [ ] **Find background tasks in codebase**
  - Command: `find app/eventyay -name "tasks.py" | xargs grep "@shared_task"`
  - Examples: Badge generation, email sending, etc.

- [ ] **Understand task definition**
  - File: [app/eventyay/plugins/badges/tasks.py](app/eventyay/plugins/badges/tasks.py) (if exists)
  - See: @shared_task decorator
  - See: bind=True, max_retries, retry() calls

- [ ] **Trace task execution**
  - Find: Signal handler queues task
  - File: Example in sendmail plugin signals
  - See: `task_name.delay()` call

- [ ] **Configure Celery locally**
  - File: [app/eventyay/config/settings.py](app/eventyay/config/settings.py)
  - Note: `CELERY_TASK_ALWAYS_EAGER = True` for development (runs synchronously)

### Understanding Multi-Tenancy

- [ ] **Understand how Eventyay handles multiple organizers/events**
  - File: [app/eventyay/common/middleware.py](app/eventyay/common/middleware.py)
  - See: MultiDomainMiddleware and EventPermissionMiddleware
  - Understand: request.organizer, request.event are set by middleware

- [ ] **Use django_scopes for queries**
  - File: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py)
  - Look for: `from django_scopes import scope`
  - See: `with scope(event=order.event):`

- [ ] **Test multi-tenancy**
  - Create 2 organizers with different events
  - Buy tickets for both
  - Verify: Orders/attendees are properly scoped per event

### Building Your Own Plugin

- [ ] **Create HubSpot plugin (mini version)**
  - Follow structure: [HUBSPOT_PLUGIN_FEASIBILITY.md](HUBSPOT_PLUGIN_FEASIBILITY.md) sections 8 & 11
  - Create: `/app/eventyay/plugins/hubspot/`
  - Create: `apps.py`, `signals.py`, `forms.py`
  - Register: @receiver(order_paid)
  - Test: Buy order, mark paid, verify signal handler ran

- [ ] **Add plugin to INSTALLED_APPS**
  - File: [app/eventyay/config/settings.py](app/eventyay/config/settings.py)
  - Add: `'eventyay.plugins.hubspot'` to INSTALLED_APPS
  - Restart: `./manage.py runserver`

- [ ] **Test plugin signal firing**
  - Buy ticket
  - Mark as paid
  - Check: Plugin signal handler was called
  - Verify: print() or logger.info() in handler output

---

## Expert Level (If Building Production Features)

### Code Architecture & Patterns

- [ ] **Understand DRF (Django REST Framework) patterns**
  - Files: [app/eventyay/api/views/](app/eventyay/api/views/) and [app/eventyay/api/serializers/](app/eventyay/api/serializers/)
  - See: ModelViewSet, Serializers, Permissions

- [ ] **Understand form generation patterns**
  - Files: [app/eventyay/presale/forms.py](app/eventyay/presale/forms.py), [app/eventyay/control/forms/](app/eventyay/control/forms/)
  - See: How forms are built dynamically based on settings

- [ ] **Understand invoice/PDF generation**
  - Files: [app/eventyay/base/models/invoices.py](app/eventyay/base/models/invoices.py)
  - Understand: How PDFs are generated and stored

### Tracing Complex Flows

- [ ] **Trace: Checkout → Order Created → Signal → Plugins Activated**
  - Start: [app/eventyay/presale/views/checkout.py](app/eventyay/presale/views/checkout.py)
  - Find: Order.objects.create()
  - Find: order_placed.send()
  - Find: Plugin receivers in [app/eventyay/plugins/*/signals.py](app/eventyay/plugins/*/signals.py)

- [ ] **Trace: Payment Confirmed → Attendee Confirmed → Emails Sent**
  - Start: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py) OrderPayment.confirm()
  - Find: order_paid.send()
  - Find: Plugin receivers (sendmail, badges, etc.)
  - Understand: What happens after payment

### Database Deep Dive

- [ ] **Query complex relationships**
  - Get all orders for an event with attendee details:
    ```sql
    SELECT o.code, op.attendee_email, op.attendee_name_cached
    FROM base_order o
    JOIN base_orderposition op ON o.id = op.order_id
    WHERE o.event_id = YOUREVENTID;
    ```

- [ ] **Understand transaction flow in code**
  - File: [app/eventyay/base/services/orders.py](app/eventyay/base/services/orders.py)
  - See: Order processing logic with proper transaction handling

---

## Exploration Tools & Commands

### Useful Django Commands

```bash
cd app

# Open Django shell to query database
./manage.py shell
# Then: from eventyay.base.models import *
# Then: Order.objects.all()

# Run tests
pytest tests/

# Run specific test
pytest tests/tickets/api/test_orders.py -v

# Check for errors
./manage.py check

# Create migrations after model changes
./manage.py makemigrations

# Apply migrations
./manage.py migrate

# Create superuser
./manage.py createsuperuser
```

### Useful Grep Commands

```bash
cd app

# Find all signal definitions
grep -r "^\s*[a-z_]*\s*=\s*.*Signal" eventyay/base/signals.py

# Find model fields
grep -r "^\s*[a-z_]*\s*=" eventyay/base/models/orders.py | head -30

# Find all views
grep -r "class.*View\|class.*ViewSet" eventyay/control/views/ --include="*.py"

# Find template usage
grep -r "{% for " eventyay/control/templates/ --include="*.html" | head -20

# Find settings usage
grep -r "event.settings" eventyay/ --include="*.py" | head -20
```

### Recommended Development Setup

```bash
# Terminal 1: Django dev server
cd app
./manage.py runserver

# Terminal 2: Celery worker (if testing async tasks)
cd app
celery -A eventyay worker -l info

# Terminal 3: Log monitoring
cd app
tail -f /var/log/django.log  # or check stdout from runserver

# Terminal 4: Database queries
cd app
./manage.py dbshell
# Then: SELECT * FROM base_order;
```

---

## Expected Learnings by Level

### After Beginner Checklist
- ✅ Understand basic product: Organizer → Event → Products → Orders
- ✅ Know database models: Order, OrderPosition, Item, Event
- ✅ Understand order lifecycle: PENDING → PAID
- ✅ Know where code lives (control, presale, api, plugins)
- ✅ Understand signal concept: When order_paid fires
- ✅ Can navigate codebase using grep and file exploration

### After Intermediate Checklist
- ✅ Understand how plugins hook into system
- ✅ Understand how settings are stored per-event
- ✅ Understand payment processing overview
- ✅ Can trace a feature through models → views → templates
- ✅ Understand API structure and serialization
- ✅ Can explain how organizer enables plugins

### After Advanced Checklist
- ✅ Understand async task execution (Celery)
- ✅ Understand multi-tenancy and scoping
- ✅ Can write a basic plugin from scratch
- ✅ Understand complete order flow with plugins
- ✅ Can query complex database relationships
- ✅ Ready to contribute production features

---

## Next Steps After Exploration

1. **Read the Code Comments**: Most models have detailed docstrings
   ```bash
   grep -A 10 "class Order\|class OrderPosition" app/eventyay/base/models/orders.py | less
   ```

2. **Study Existing Plugins**: Pick one and understand it completely
   - [app/eventyay/plugins/badges/](app/eventyay/plugins/badges/) - Simple example
   - [app/eventyay/plugins/sendmail/](app/eventyay/plugins/sendmail/) - Intermediate example
   - [app/eventyay/plugins/stripe/](app/eventyay/plugins/stripe/) - Complex example

3. **Run Tests**: Understanding tests teaches you how system works
   ```bash
   pytest tests/tickets/ -v -k "order"
   ```

4. **Read Documentation**: Official docs have good overviews
   ```bash
   cat doc/development/concepts.rst
   cat doc/development/structure.rst
   ```

5. **Build Something Small**:
   - Create a simple plugin (like HubSpot example)
   - Add a new field to Order
   - Add a new API endpoint
   - Create a new signal receiver

---

## Troubleshooting Common Issues

### Issue: "ModuleNotFoundError: No module named 'eventyay'"
**Solution**: Make sure you're in `app/` directory
```bash
cd app
./manage.py runserver
```

### Issue: "django.core.exceptions.ImproperlyConfigured: DATABASE"
**Solution**: Database not configured. Check setup in:
[doc/development/setup.rst](doc/development/setup.rst)

### Issue: "Signal handler not firing"
**Potential causes**:
- [ ] Plugin not enabled for event: Check `event.settings.get('plugin_NAME_enabled')`
- [ ] Wrong signal name: Check [app/eventyay/base/signals.py](app/eventyay/base/signals.py)
- [ ] Handler has typo in dispatch_uid: Check @receiver decorators
- [ ] Event context not set: Check middleware in [app/eventyay/common/middleware.py](app/eventyay/common/middleware.py)

### Issue: "Celery task not executing"
**For development**: Tasks run synchronously, should execute immediately
**Check**: [app/eventyay/config/settings.py](app/eventyay/config/settings.py) for `CELERY_TASK_ALWAYS_EAGER`

### Issue: "Can't find template"
**Solution**: Templates split across:
- Control panel: [app/eventyay/control/templates/](app/eventyay/control/templates/)
- Public shop: [app/eventyay/presale/templates/](app/eventyay/presale/templates/)
- Core: [app/eventyay/jinja-templates/](app/eventyay/jinja-templates/)

Use `grep -r "template_name" eventyay/control/views/ --include="*.py"` to find which template a view uses.

---

## Quick Reference Links

### Models
- Order, OrderPosition, OrderPayment: [app/eventyay/base/models/orders.py](app/eventyay/base/models/orders.py)
- Event, Organizer: [app/eventyay/base/models/event.py](app/eventyay/base/models/event.py)
- Item, Quota: [app/eventyay/base/models/items.py](app/eventyay/base/models/items.py)
- User, Team: [app/eventyay/base/models/auth.py](app/eventyay/base/models/auth.py)

### Views
- Control panel orders: [app/eventyay/control/views/orders.py](app/eventyay/control/views/orders.py)
- Presale checkout: [app/eventyay/presale/views/checkout.py](app/eventyay/presale/views/checkout.py)
- API orders: [app/eventyay/api/views/order.py](app/eventyay/api/views/order.py)

### Signals & Events
- All signals: [app/eventyay/base/signals.py](app/eventyay/base/signals.py)
- Plugin signals: [app/eventyay/plugins/PLUGINNAME/signals.py](app/eventyay/plugins/sendmail/signals.py)

### Settings & Configuration
- Django config: [app/eventyay/config/settings.py](app/eventyay/config/settings.py)
- Hierarkey settings system: [app/eventyay/base/settings.py](app/eventyay/base/settings.py)

### Plugins Reference
- Plugin structure example: [app/eventyay/plugins/badges/](app/eventyay/plugins/badges/)
- Payment providers: [app/eventyay/plugins/stripe/](app/eventyay/plugins/stripe/), [app/eventyay/plugins/banktransfer/](app/eventyay/plugins/banktransfer/)

---

## Final Notes

**Eventyay is a complex system, but follows Django/DRF best practices:**
- Models define data
- Views handle logic and routing
- Signals enable loose coupling for plugins
- Settings enable configuration without code changes
- Tests document how features work

**Start with small, contained explorations:**
1. Pick one model (Order)
2. Find where it's created (checkout views)
3. Find where it's displayed (control panel views)
4. Find what happens after (order_paid signal)
5. Build out from there

**Don't try to understand everything at once.** Eventyay has ~80k lines of code. Focus on the feature you're working on, and learn adjacent code as needed.

**The checklist is cumulative:** After completing all three levels (Beginner → Intermediate → Advanced), you'll have deep understanding of how Eventyay works as both a product and codebase.

Good luck exploring! 🚀

---

**Document Version**: 1.0  
**Last Updated**: January 2026  
**For**: Developers new to Eventyay  
**Time to Complete**: 6-8 hours (all checklists)
