# Stripe Implementation - Key Code Locations

## File-by-File Credential Handling

### 1. Global Settings Configuration
**File**: [control/forms/global_settings.py](control/forms/global_settings.py)

**Lines 210-225: Production & Test Keys**
```python
# PRODUCTION KEYS
(
    'payment_stripe_secret_key',
    SecretKeySettingsField(required=False, label=_('Stripe Secret Key'))
),
(
    'payment_stripe_publishable_key',
    forms.CharField(required=False, label=_('Stripe Publishable Key'))
),

# TEST MODE KEYS
(
    'payment_stripe_test_secret_key',
    SecretKeySettingsField(required=False, label=_('Stripe Test Secret Key'))
),
(
    'payment_stripe_test_publishable_key',
    forms.CharField(required=False, label=_('Stripe Test Publishable Key'))
),
```

**Lines 240-290: Stripe Connect (Platform Fees)**
```python
(
    'payment_stripe_connect_secret_key',
    SecretKeySettingsField(required=False, label=_('Stripe Connect Secret Key'))
),
(
    'payment_stripe_connect_publishable_key',
    forms.CharField(required=False, label=_('Stripe Connect Publishable Key'))
),
(
    'payment_stripe_connect_client_id',
    forms.CharField(required=False, label=_('Stripe Connect Client ID'))
),
(
    'payment_stripe_connect_test_secret_key',
    SecretKeySettingsField(required=False)
),
(
    'payment_stripe_connect_test_publishable_key',
    forms.CharField(required=False)
),

# Fee Configuration
(
    'payment_stripe_connect_app_fee_percent',
    forms.DecimalField(required=False, label=_('App Fee Percent'))
),
(
    'payment_stripe_connect_app_fee_max',
    forms.DecimalField(required=False, label=_('App Fee Max'))
),
(
    'payment_stripe_connect_app_fee_min',
    forms.DecimalField(required=False, label=_('App Fee Min'))
),
```

**Lines 310-320: Webhook Security**
```python
(
    'stripe_webhook_secret_key',
    SecretKeySettingsField(
        required=False, 
        label=_('Stripe Webhook Secret Key')
    )
),
```

---

### 2. Stripe Utility Functions (Centralized Service)
**File**: [helpers/stripe_utils.py](helpers/stripe_utils.py)

**Lines 1-25: Module Setup**
```python
import stripe
from django.core.exceptions import ValidationError
from eventyay.base.models import BillingInvoice, Organizer
from eventyay.base.models.organizer import OrganizerBillingModel
from eventyay.base.settings import GlobalSettingsObject

logger = logging.getLogger(__name__)
```

**Lines 29-50: Webhook Secret Retrieval**
```python
def get_stripe_webhook_secret_key() -> str:
    """
    Retrieve the Stripe webhook secret key.
    @return: A string representing the Stripe webhook secret key.
    """
    gs = GlobalSettingsObject()
    stripe_webhook_secret_key = getattr(gs.settings, 'stripe_webhook_secret_key', None)
    if not stripe_webhook_secret_key:
        logger.error('Stripe webhook secret key not found')
        raise ValidationError('Stripe webhook secret key not found.')
    logger.info('Get successful Stripe webhook secret key')
    return stripe_webhook_secret_key
```

**Lines 51-85: Key Retrieval (Dynamic, Production/Test Fallback)**
```python
def get_stripe_key(key_type: str) -> str:
    """
    Retrieve the Stripe key.
    @param key_type: A string representing the key type.
    @return: A string representing the Stripe key.
    """
    gs = GlobalSettingsObject()

    try:
        prod_key = getattr(gs.settings, 'payment_stripe_{}_key'.format(key_type), None)
        test_key = getattr(gs.settings, 'payment_stripe_test_{}_key'.format(key_type), None)
    except AttributeError as e:
        logger.error('Missing attribute for Stripe %s key: %s', key_type, str(e))
        raise ValidationError(
            'Missing attribute for Stripe {} key: {}. Please contact the administrator to set the Stripe key.'.format(
                key_type, str(e)
            ),
        )

    if not prod_key and not test_key:
        logger.error('No Stripe %s key found', key_type)
        raise ValidationError('Please contact the administrator to set the Stripe {} key.'.format(key_type))

    logger.info('Get successful %s key', key_type)

    return prod_key or test_key  # <-- FALLBACK: test key if no prod key
```

**Lines 86-94: Secret & Publishable Key Getters**
```python
def get_stripe_secret_key() -> str:
    return get_stripe_key('secret')

def get_stripe_publishable_key() -> str:
    return get_stripe_key('publishable')
```

**Lines 67-122: Error Handling Decorator**
```python
def handle_stripe_errors(operation_name: str):
    """
    Handle the Stripe errors.
    @param operation_name: A string representing the operation name.
    @return: A decorator function.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except stripe.error.APIError as e:
                logger.error('Stripe API error during %s: %s', operation_name, str(e))
                raise ValidationError('Stripe service error.')
            except stripe.error.APIConnectionError as e:
                logger.error('API connection error during %s: %s', operation_name, str(e))
                raise ValidationError('Network communication error.')
            except stripe.error.AuthenticationError as e:
                logger.error('Authentication error during %s: %s', operation_name, str(e))
                raise ValidationError(
                    'Authentication failed. Please contact the administrator to check the configuration of the Stripe API key.'
                )
            # ... more exception handlers
```

**Lines 125-150: Create Setup Intent (with Key Usage)**
```python
@handle_stripe_errors('create_setup_intent')
def create_setup_intent(customer_id: str) -> str:
    """
    Create a setup intent for the customer.
    @param customer_id: A string representing the customer ID.
    @return: A string representing the client secret.
    """
    stripe.api_key = get_stripe_secret_key()  # <-- KEY USAGE
    stripe_setup_intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=['card'],
        usage='off_session',
    )
    logger.info('Created a successful setup intent.')
    billing_settings_updated = OrganizerBillingModel.objects.filter(stripe_customer_id=customer_id).update(
        stripe_setup_intent_id=stripe_setup_intent.id  # <-- STORE INTENT ID
    )
    if not billing_settings_updated:
        logger.error('No billing settings found for the customer %s', customer_id)
        raise ValidationError('No billing settings found for the customer.')
    return stripe_setup_intent.client_secret
```

**Lines 153-175: Get Stripe Customer ID**
```python
def get_stripe_customer_id(organizer_slug: str) -> str:
    """
    Retrieve the Stripe customer ID.
    @param organizer_slug: A string representing the organizer slug.
    @return: A string representing the Stripe customer ID.
    """
    organizer = Organizer.objects.get(slug=organizer_slug)
    if not organizer:
        logger.error('Organizer %s not found.', organizer_slug)
        raise ValidationError('Organizer {} not found.'.format(organizer_slug))
    billing_settings = OrganizerBillingModel.objects.filter(organizer_id=organizer.id).first()
    if billing_settings and billing_settings.stripe_customer_id:
        return billing_settings.stripe_customer_id  # <-- RETRIEVE FROM DB
    logger.error(
        'No billing settings or Stripe customer ID found for organizer %s',
        organizer_slug,
    )
    raise ValidationError('No stripe_customer_id found for organizer {}'.format(organizer_slug))
```

**Lines 176-195: Create Stripe Customer**
```python
@handle_stripe_errors('create_stripe_customer')
def create_stripe_customer(email: str, name: str):
    """
    Create a Stripe customer.
    @param email: A string representing the email address.
    @param name: A string representing the name.
    @return: A dictionary containing the customer information.
    """
    stripe.api_key = get_stripe_secret_key()  # <-- KEY USAGE
    customer = stripe.Customer.create(
        email=email,
        name=name,
    )
    logger.info('Created a successful customer.')
    return customer
```

**Lines 196-225: Update Payment Info**
```python
@handle_stripe_errors('update_payment_info')
def update_payment_info(setup_intent_id: str, customer_id: str):
    """
    Update the payment information.
    @param setup_intent_id: A string representing the setup intent ID.
    @param customer_id: A string representing the customer ID.
    @return: A dictionary containing the updated payment information.
    """
    stripe.api_key = get_stripe_secret_key()  # <-- KEY USAGE
    setup_intent = get_setup_intent(setup_intent_id)
    payment_method = setup_intent.payment_method
    if not payment_method:
        logger.error('No payment method found for the setup intent %s', setup_intent_id)
        raise ValidationError('No payment method found for the setup intent.')
    billing_setting_updated = OrganizerBillingModel.objects.filter(stripe_customer_id=customer_id).update(
        stripe_payment_method_id=payment_method  # <-- STORE METHOD ID
    )
    if not billing_setting_updated:
        logger.error('No billing settings found for the customer %s', customer_id)
        raise ValidationError('No billing settings found for the customer.')
    attach_payment_method_to_customer(payment_method, customer_id)
    customer_info_updated = stripe.Customer.modify(
        customer_id, invoice_settings={'default_payment_method': payment_method}
    )
    logger.info('Updated successful payment information.')
    return customer_info_updated
```

**Lines 247-275: Create Payment Intent (for Auto-Billing)**
```python
@handle_stripe_errors('create_payment_intent')
def create_payment_intent(
    amount: int,
    currency: str,
    customer_id: str,
    payment_method_id: str,
    metadata: dict,
    invoice_id: str,
):
    """
    Create a payment intent to process automatic billing charge.
    """
    stripe.api_key = get_stripe_secret_key()  # <-- KEY USAGE
    payment_intent = stripe.PaymentIntent.create(
        amount=int(amount * 100),
        currency=currency,
        customer=customer_id,
        payment_method=payment_method_id,
        automatic_payment_methods={'enabled': True, 'allow_redirects': 'never'},
        metadata=metadata,
    )
    billing_invoice_updated = BillingInvoice.objects.filter(id=invoice_id).update(
        stripe_payment_intent_id=payment_intent.id  # <-- STORE INTENT ID
    )
    if not billing_invoice_updated:
        logger.error('No billing invoice found for the invoice %s', invoice_id)
        raise ValidationError('No billing invoice found for the invoice.')
    logger.info('Created a successful payment intent.')
    return payment_intent
```

**Lines 316-340: End-to-End Auto-Billing Flow**
```python
def process_auto_billing_charge_stripe(
    organizer_slug: str, amount: int, currency: str, metadata: dict, invoice_id: str
):
    """
    Process the automatic billing charge using Stripe.
    """
    stripe.api_key = get_stripe_secret_key()  # <-- KEY USAGE
    customer_id = get_stripe_customer_id(organizer_slug)  # <-- GET CUSTOMER
    payment_method = get_payment_method_info(customer_id)  # <-- GET METHOD
    if not payment_method:
        logger.error('No payment method found for the customer %s', customer_id)
        raise ValidationError('No payment method found for the customer.')
    payment_intent = create_payment_intent(amount, currency, customer_id, payment_method.id, metadata, invoice_id)
    payment_intent_confirmation_info = confirm_payment_intent(payment_intent.id, payment_method.id)
    return payment_intent_confirmation_info
```

---

### 3. Organizer Billing Model
**File**: [base/models/organizer.py](base/models/organizer.py)

**Lines 737-751: Stripe Customer ID Storage**
```python
class OrganizerBillingModel(models.Model):
    """
    Billing model - support billing information for organizer
    """

    organizer = models.ForeignKey('Organizer', on_delete=models.CASCADE, related_name='billing')
    
    # ... other fields ...
    
    stripe_customer_id = models.CharField(
        max_length=255,
        verbose_name=_('Stripe Customer ID'),
        blank=True,
        null=True,
    )

    stripe_payment_method_id = models.CharField(
        max_length=255,
        verbose_name=_('Payment Method'),
        blank=True,
        null=True,
    )

    stripe_setup_intent_id = models.CharField(
        max_length=255,
        verbose_name=_('Setup Intent ID'),
        blank=True,
        null=True,
    )
```

---

### 4. Organizer Form Integration
**File**: [control/forms/organizer_forms/organizer_form.py](control/forms/organizer_forms/organizer_form.py)

**Lines 220-240: Auto-Create Stripe Customer on Organizer Save**
```python
from eventyay.helpers.stripe_utils import create_stripe_customer, update_customer_info

class OrganizerBillingForm(forms.ModelForm):
    def save(self, commit=True):
        def set_attribute(instance):
            for field in self.Meta.fields:
                setattr(instance, field, self.cleaned_data[field])

        instance = OrganizerBillingModel.objects.filter(organizer_id=self.organizer.id).first()

        if instance:
            set_attribute(instance)
            if commit:
                update_customer_info(
                    instance.stripe_customer_id,
                    email=self.cleaned_data.get('primary_contact_email'),
                    name=self.cleaned_data.get('primary_contact_name'),
                )
                instance.save()
        else:
            instance = OrganizerBillingModel(organizer_id=self.organizer.id)
            set_attribute(instance)
            if commit:
                stripe_customer = create_stripe_customer(  # <-- CREATE CUSTOMER
                    email=self.cleaned_data.get('primary_contact_email'),
                    name=self.cleaned_data.get('primary_contact_name'),
                )
                instance.stripe_customer_id = stripe_customer.id  # <-- STORE ID
                instance.save()
        return instance
```

---

### 5. Billing Invoice Model
**File**: [base/models/billing.py](base/models/billing.py)

**Line 67: Payment Intent ID Storage**
```python
class BillingInvoice(LoggedModel):
    STATUS_PENDING = 'n'
    STATUS_PAID = 'p'
    STATUS_EXPIRED = 'e'
    STATUS_CANCELED = 'c'

    STATUS_CHOICES = [
        (STATUS_PENDING, _('pending')),
        (STATUS_PAID, _('paid')),
        (STATUS_EXPIRED, _('expired')),
        (STATUS_CANCELED, _('canceled')),
    ]

    organizer = models.ForeignKey('Organizer', on_delete=models.CASCADE)
    event = models.ForeignKey('Event', on_delete=models.CASCADE)
    
    # ... other fields ...
    
    stripe_payment_intent_id = models.CharField(max_length=50, null=True, blank=True)
```

---

### 6. Event Settings Form
**File**: [control/forms/event.py](control/forms/event.py)

**Lines 1476-1513: Per-Event Stripe Toggle**
```python
class StripePaymentMethodsForm(ProviderForm):
    payment_stripe__enabled = forms.BooleanField(
        label=_('Enable Stripe for this event'),
        required=False,
    )
    
    # ... other fields ...

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        plugins_active = [...]  # Get active plugins
        
        # Only show Stripe toggle if:
        # 1. eventyay_stripe plugin is installed
        # 2. Global payment_stripe_client_id is configured
        if ('eventyay_stripe' not in plugins_active) or (not self.obj.settings.payment_stripe_client_id):
            del self.fields['payment_stripe__enabled']
```

**Key Logic**: Event-level toggle only shown if global configuration exists

---

### 7. Event Payment Provider Signal
**File**: [base/signals.py](base/signals.py)

**Line 281: Signal Registration**
```python
register_payment_providers = EventPluginSignal()
```

**Usage**: External plugins (including eventyay-stripe) register payment providers via this signal

---

### 8. Event Model Integration
**File**: [base/models/event.py](base/models/event.py)

**Lines 1689-1692: Payment Provider Discovery**
```python
@property
def payment_providers(self):
    """Returns list of available payment providers for this event"""
    from ..signals import register_payment_providers
    
    responses = register_payment_providers.send(self)
    return {
        provider_id: provider_instance
        for response in responses
        for provider_id, provider_instance in response[1].items()
    }
```

---

### 9. External Stripe Plugin
**File**: [pyproject.toml](pyproject.toml)

**Line 101: Dependency Declaration**
```toml
eventyay-stripe = { git = "https://github.com/fossasia/eventyay-tickets-stripe.git", rev = "a76e42f..." }
```

**Type**: External Django package that registers payment providers

---

## Search Results Summary

### Pattern: `stripe.api_key = get_stripe_secret_key()`

**Found in [helpers/stripe_utils.py](helpers/stripe_utils.py):**
- Line 139: `create_setup_intent()`
- Line 171: `create_stripe_customer()`
- Line 198: `update_payment_info()`
- Line 226: `get_payment_method_info()`
- Line 245: `update_customer_info()`
- Line 263: `attach_payment_method_to_customer()`
- Line 276: `get_setup_intent()`
- Line 298: `create_payment_intent()`
- Line 317: `confirm_payment_intent()`
- Line 328: `process_auto_billing_charge_stripe()`

**Pattern**: Consistent in ALL 10 functions

### Pattern: Key Retrieval

**All key retrieval goes through:**
- `get_stripe_secret_key()` → calls `get_stripe_key('secret')`
- `get_stripe_publishable_key()` → calls `get_stripe_key('publishable')`
- `get_stripe_webhook_secret_key()` → direct DB fetch

**Single source**: `GlobalSettingsObject()` in every function

---

## Conclusion

✅ **All Stripe operations follow unified pattern**
✅ **No hardcoded keys anywhere**
✅ **All keys fetched dynamically from database**
✅ **Centralized service layer in stripe_utils.py**
✅ **Consistent error handling**
✅ **Clear data storage locations**

