# Stripe Implementation Documentation Index

This folder contains comprehensive documentation about Stripe integration in Eventyay, clarifying the two distinct use cases and explaining the storage architecture.

## Documents Overview

### 1. **STRIPE_USE_CASES_CLARIFICATION.md** (Most Comprehensive)
**Read this first for the full picture**

- **Purpose**: Detailed explanation of why Stripe keys are stored in multiple places
- **Contents**:
  - Executive summary with comparison table
  - Complete breakdown of USE CASE 1 (Organizer Payments)
  - Complete breakdown of USE CASE 2 (Platform Fee Collection)
  - Detailed rationale for each storage location
  - Storage breakdown by use case
  - Identification of current problems (webhook ambiguity, naming confusion)
  - Recommendations for streamlining
  - Summary tables and architectural diagrams
  - Links to relevant code files

- **Best For**: Architects, code reviewers, anyone wanting complete understanding

---

### 2. **STRIPE_USE_CASES_FLOWS.md** (Developer Reference)
**Read this for code-level implementation details**

- **Purpose**: Show actual code flows for each use case
- **Contents**:
  - Quick reference for the two use cases
  - Complete storage architecture breakdown
  - Code flow diagrams for USE CASE 1 (Organizer Payments)
  - Code flow diagrams for USE CASE 2 (Platform Fee Collection)
  - Key functions and their use cases
  - Explanation of why confusion exists
  - Verification questions for clarification

- **Best For**: Developers implementing features, debugging, integrating with Stripe

---

### 3. **STRIPE_STORAGE_LOCATIONS.md** (Quick Reference)
**Read this for a quick answer**

- **Purpose**: Concise explanation of storage locations
- **Contents**:
  - Quick reference table of all storage locations
  - Explanation of both use cases in simple terms
  - Why separate locations are needed
  - Naming/confusion issues
  - Streamlining recommendations

- **Best For**: Quick lookup, onboarding new team members, discussing with non-technical stakeholders

---

### 4. **STRIPE_CODE_LOCATIONS.md** (Implementation Map)
**Read this for code references and examples**

- **Purpose**: Point to actual code locations for each Stripe feature
- **Contents**:
  - Code file locations with line numbers
  - Database models with field definitions
  - Service functions with signatures
  - Task definitions
  - Configuration locations
  - Real code examples from the codebase

- **Best For**: Navigating the codebase, understanding how features are implemented

---

### 5. **STRIPE_CREDENTIALS_QUICK_REFERENCE.md** (Cheat Sheet)
**Read this when you need a quick lookup**

- **Purpose**: One-page credential reference
- **Contents**:
  - All credential types at a glance
  - Where each credential is stored
  - When each credential is used
  - What happens if a credential is missing
  - Example error messages

- **Best For**: Quick reference during development, troubleshooting credentials

---

### 6. **STRIPE_IMPLEMENTATION_ANALYSIS.md** (Original Deep Dive)
**Read this for detailed technical analysis**

- **Purpose**: Original comprehensive analysis of Stripe implementation
- **Contents**:
  - Architecture overview
  - Level-by-level breakdown (platform, organizer, invoice)
  - Complete list of services and utilities
  - Function mappings and relationships
  - Detailed credential flow diagrams
  - State lifecycle documentation
  - Full file/line references

- **Best For**: Code review, architectural decisions, complete picture

---

## Key Findings Summary

### Two Use Cases
1. **USE CASE 1: Organizer-Direct Payments**
   - Organizer connects their own Stripe account
   - Customers pay organizer directly
   - Via external `eventyay-stripe` plugin
   - **Key Settings**: `payment_stripe_*_key`, `OrganizerBillingModel`, Event toggle

2. **USE CASE 2: Platform Fee Collection**
   - Platform charges organizers for service fees
   - Via Stripe Connect automatic billing
   - Built-in feature (not external plugin)
   - **Key Settings**: `payment_stripe_connect_*_key`, `BillingInvoice`

### Storage Architecture is Correct
✅ Global Settings → Platform-level configuration (admin sets once)  
✅ OrganizerBillingModel → Per-organizer data (each organizer is independent)  
✅ BillingInvoice → Per-invoice tracking (audit trail)  
✅ Event Settings → Per-event toggle (organizer controls per event)  

### Main Issues (Not Architectural)
⚠️ **Naming Confusion**: `payment_stripe_*` vs `payment_stripe_connect_*` not clearly labeled  
⚠️ **Webhook Ambiguity**: Unclear which Stripe account webhook secret belongs to  
⚠️ **Missing Documentation**: No clear separation of concerns in code  

### Recommendations
1. Add section comments to `control/forms/global_settings.py`
2. Create dedicated getter functions for Connect keys
3. Clarify webhook configuration
4. Add architecture documentation to `/doc/development/`

---

## Quick Navigation

| I want to... | Read this | Line Count |
|---|---|---|
| Understand everything about Stripe | `STRIPE_USE_CASES_CLARIFICATION.md` | 350+ |
| See code flows and implementations | `STRIPE_USE_CASES_FLOWS.md` | 300+ |
| Quick reference about storage | `STRIPE_STORAGE_LOCATIONS.md` | 250+ |
| Find specific code locations | `STRIPE_CODE_LOCATIONS.md` | 600+ |
| Look up credentials quickly | `STRIPE_CREDENTIALS_QUICK_REFERENCE.md` | 250+ |
| Deep technical analysis | `STRIPE_IMPLEMENTATION_ANALYSIS.md` | 550+ |

---

## Key Code Files Referenced

| File | Purpose | Use Cases |
|------|---------|-----------|
| `control/forms/global_settings.py` (315-328) | Configuration form | Both |
| `helpers/stripe_utils.py` | Utility functions | Both |
| `base/models/organizer.py` (737-751) | Organizer customer storage | USE CASE 1 & 2 |
| `base/models/billing.py` (67) | Invoice payment tracking | USE CASE 2 |
| `eventyay_common/tasks.py` (300+) | Auto-billing Celery task | USE CASE 2 |
| `plugins/stripe/` | Frontend integration (if exists) | USE CASE 1 |
| `pyproject.toml` (101) | External plugin dependency | USE CASE 1 |

---

## Answer to Original Question

> "Stripe is used in two different ways on eventyay. We have several different areas where the keys to connect to Stripe are stored. It is unclear why there are different places in the DB. Clarify this and streamline the implementation where necessary."

**Answer**: 

The two different uses of Stripe require different storage locations because they serve different purposes:

- **USE CASE 1** (Organizer payments) needs:
  - Platform's credentials (global) for initiating organizer connections
  - Per-organizer customer IDs (in OrganizerBillingModel)
  - Per-event toggles (in event settings)

- **USE CASE 2** (Platform fees) needs:
  - Platform's Stripe Connect credentials (global) for auto-billing
  - Per-organizer customer IDs (shared with USE CASE 1)
  - Per-invoice payment tracking (in BillingInvoice)

**The current implementation is architecturally correct.** The confusion comes from:
1. Unclear naming in global settings (both key types stored together)
2. Missing documentation explaining the separation
3. Potential webhook configuration ambiguity

**Recommended streamlining** (non-breaking):
1. Add code comments to global settings form
2. Create dedicated getter functions
3. Document architecture in codebase
4. Clarify webhook setup

See `STRIPE_USE_CASES_CLARIFICATION.md` for detailed recommendations.

---

## Document Generation Date
Generated as part of Stripe implementation analysis and clarification task.

For questions or updates to this documentation, refer to the individual documents and the source code files they reference.

