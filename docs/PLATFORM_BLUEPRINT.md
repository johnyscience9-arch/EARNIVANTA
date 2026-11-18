# Earnivanta platform blueprint

This document is the implementation contract for the next build stages. It is intentionally specific so the web, Android and Windows clients share one set of rules.

## Product boundaries

Earnivanta has three connected services:

1. **Work exchange** — approved research, usability testing, product feedback, data tasks and other legitimate work. Every task has instructions, eligibility, reward, evidence rules, a cap and a review status.
2. **Promotion exchange** — advertiser-funded campaigns for genuine awareness, voluntary participation and consent-based leads. No purchased likes, follows, subscribers, fake views, fabricated reviews or undisclosed engagement.
3. **Digital studio** — scoped requests for websites, Android applications/APKs and Windows desktop software, with quotes, milestones, delivery and maintenance.

The same person may use more than one role. Role switching must not create duplicate accounts.

## Roles and permissions

| Role | Allowed actions | Restricted actions |
|---|---|---|
| Member / worker | Browse eligible tasks, submit evidence, view own ledger, request withdrawal, contact support | Approve own evidence, edit ledger entries, view another member's private data |
| Advertiser | Create campaign drafts, fund campaign by recorded manual payment, view own campaign and lead reports | Approve own campaign, approve own payment, access worker identity documents |
| Maintenance staff | View assigned support/project tickets, update permitted ticket status, communicate with assigned users | Access KYC documents, change balances, approve withdrawals unless separately authorised |
| Reviewer | Review assigned task evidence and campaign submissions | Change wallet balances or approve own work |
| KYC reviewer | Review identity submissions and record a decision | Download or disclose documents outside the review purpose |
| Finance reviewer | Reconcile manual deposits and withdrawals, add reasoned ledger adjustments | Review identity documents unless separately authorised |
| Administrator | Manage roles, staff assignments, policy settings and audit review | No silent edits: sensitive actions must be logged and attributable |

Maintenance staff may have a separately disclosed compensation schedule and onboarding requirements. Any joining or verification charge must pay for a clearly described service; it must never be represented as an investment or used to fund other members' earnings.

## Core records

Use UUID primary keys, UTC timestamps, explicit status fields and immutable audit events.

- `users`: id, normalized_email, normalized_phone, password_hash, account_status, created_at, updated_at
- `user_roles`: user_id, role, granted_by, granted_at, revoked_at
- `profiles`: user_id, display_name, preferred_language, country, contact_preferences
- `kyc_submissions`: id, user_id, document_type, encrypted_object_key, masked_identifier, review_status, consent_at, retention_until, reviewer_id, reviewed_at, decision_reason
- `campaigns`: id, advertiser_id, title, objective, campaign_type, audience, budget_minor, currency, status, policy_review_status, starts_at, ends_at
- `campaign_payments`: id, campaign_id, payer_id, method, reference, amount_minor, currency, proof_object_key, status, reviewed_by, reviewed_at
- `tasks`: id, campaign_id, title, instructions, eligibility_json, reward_minor, currency, capacity, evidence_schema_json, status
- `task_submissions`: id, task_id, worker_id, evidence_object_key, status, reviewer_id, review_note, submitted_at, reviewed_at
- `wallet_accounts`: id, user_id, currency, status
- `ledger_entries`: id, wallet_account_id, direction, amount_minor, entry_type, reference_type, reference_id, idempotency_key, created_by, created_at
- `withdrawal_requests`: id, user_id, amount_minor, currency, payout_method, masked_destination, status, reviewer_id, reviewed_at
- `projects`: id, requester_id, service_type, brief, quoted_amount_minor, currency, status, assigned_staff_id
- `project_milestones`: id, project_id, title, amount_minor, due_at, status, delivery_reference
- `support_threads`: id, requester_id, assigned_staff_id, status, priority, created_at, updated_at
- `support_messages`: id, thread_id, sender_id, body, attachment_key, created_at
- `notifications`: id, user_id, event_type, payload_json, read_at, created_at
- `audit_events`: id, actor_id, action, target_type, target_id, reason, before_json, after_json, created_at

Money is stored as integer minor units (for BDT, poisha), never floating-point. Ledger entries are append-only. Corrections use compensating entries, not edits or deletes. Every financial operation must be idempotent.

## Required state transitions

- Account: `pending → active → suspended/closed`
- KYC: `not_submitted → pending → approved/rejected → resubmission_required`
- Campaign: `draft → submitted → under_review → approved/rejected → active → paused/completed`
- Manual deposit: `submitted → under_review → approved/rejected`
- Task submission: `submitted → under_review → approved/rejected`
- Withdrawal: `requested → under_review → approved → paid` or `rejected/cancelled`
- Project: `inquiry → quoted → accepted → in_progress → review → delivered → closed`
- Support thread: `open → assigned → waiting_on_user/staff → resolved → closed`

A status change must validate the actor's permission and append an audit event.

## Manual payment rules

The first release records human-reviewed payments only. It does not connect to or impersonate bKash, Nagad, banks or card networks. Show the exact amount, recipient instructions, reference field, proof upload, review status and support route. Staff must reconcile against the merchant's own transaction records before approval. Never credit a wallet merely because a screenshot was uploaded.

## Identity and privacy rules

Do not launch real NID/passport collection until a Bangladesh-qualified legal/privacy review and secure storage/access controls are in place. Collect the minimum required data, obtain clear consent, encrypt documents, restrict access to named reviewers, log every access, mask identifiers in ordinary screens and set a deletion/retention schedule. Never claim a match is certain based only on phone, device or IP. Do not connect to unofficial identity databases.

## Backend/API boundary

GitHub Pages can serve the static site only. It cannot safely host authentication, private identity files, wallet records or live chat. Those features require a separately deployed backend and database with HTTPS, backups, access controls and monitoring.

Suggested first backend contract (versioned under `/api/v1`):

- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /me`
- `GET /tasks`, `POST /tasks/{id}/submissions`
- `GET /campaigns`, `POST /campaigns`, `POST /campaigns/{id}/payment-submissions`
- `GET /wallet/ledger`, `POST /wallet/withdrawals`
- `POST /projects`, `GET /projects/{id}`
- `GET /support/threads`, `POST /support/threads`, `POST /support/threads/{id}/messages`
- Restricted staff endpoints for review queues, role assignment and audit search.

All private endpoints require authentication, role authorization, input validation, rate limiting and CSRF protection where cookie sessions are used. Uploads need file-type/size checks, malware scanning and private object storage.

## Client strategy

Build one responsive web client and one shared API. Android and Windows clients should consume the same API and permission rules. A WebView/PWA wrapper is a packaging shortcut, not a native implementation; it must be described honestly. Do not ship clients that contain server secrets.

## Launch gates

Before accepting real money or identity documents, complete:
- legal review of business model, fees, consumer disclosures and privacy notices;
- verified payout and refund procedures;
- secure backend, encrypted backups and tested restore;
- role/permission and abuse tests;
- audit trail and dispute handling;
- accessibility, Bangla/English content and mobile-device tests;
- clear public terms, privacy, prohibited-campaign and complaint policies.

## Current implementation status

The repository currently contains a static landing-page prototype. This blueprint is a design contract, not a claim that the backend, account system, wallet, KYC, chat or mobile/desktop clients already exist.
