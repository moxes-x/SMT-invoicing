# Invoicing

Invoices, quotes, repeating invoices, payment tracking, reminders and WhatsApp/email sending for Zambian small businesses that are **not
VAT-registered**: turnover-tax payers, freelancers, small traders and service providers who today
send invoices as photos, Word files or WhatsApp texts and lose track of who has paid.

> Documents from this app are titled **"Invoice"**, never "Tax Invoice". VAT-registered businesses
> must issue tax invoices through ZRA Smart Invoice; onboarding tells them so.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5 + Django REST Framework, drf-spectacular (OpenAPI), PostgreSQL, WeasyPrint (PDF), django-anymail |
| Jobs | Celery + Redis (sending, PDFs), Celery beat (recurring invoices, reminders) |
| Frontend | React 19 + TypeScript (strict), Vite, React Router, TanStack Query, React Hook Form + Zod |
| UI | Tailwind CSS v4 with shadcn/ui tokens, so components from [21st.dev](https://21st.dev) / shadcn drop straight in (`components.json` is configured) |
| Tests | pytest + factory_boy, Vitest + Testing Library, Playwright (mobile viewport) |

```
React SPA (Vite + TS) ──HTTPS──► Django + DRF ──► PostgreSQL
                                     ├──► Celery + Redis
                                     ├──► Object storage (R2/S3)
                                     ├──► Email (django-anymail)
                                     └──► WhatsApp Cloud API (optional)
```

## Key decisions

- **Sessions + CSRF, not JWT.** The SPA and API share one site (`/api/` is proxied in dev), so the
  browser holds an HttpOnly session cookie and nothing token-like lives in JavaScript. Signup and
  login enforce CSRF too (DRF skips it for anonymous users by default), blocking login-CSRF.
- **Multi-tenant from day one.** Every business-owned row has a `business` FK. `request.business` is
  resolved from the session and *always* re-checked against the user's memberships;
  `apps.core.tenancy.BusinessScopedMixin` filters every queryset by it. Another business's objects
  return **404**, never 403, so ids don't leak. Tests prove this per endpoint.
- **Money in ngwee integers** (K12.50 → `1250`); totals computed server-side only.
- **Sent invoices are locked**; changes after sending are void + reissue.
- **Typed API contract.** `backend/openapi.yml` is generated from DRF; `frontend/src/api/schema.d.ts`
  is generated from it. CI fails if either drifts.
- Phone numbers are stored in E.164 (`+260971234567`) via `phonenumbers`; users can type `097…`.

## Running locally

**Docker:** `docker compose up`, then open http://localhost:5173.

If a port is already taken on your machine, put the ones you want in a `.env` file next to
`docker-compose.yml` (it's git-ignored) instead of editing the compose file:

```
DB_PORT=5433
BACKEND_PORT=8001
FRONTEND_PORT=5174
```

Emails print to the backend console in development. PDFs are written to `backend/media/`.
The `beat` service runs the daily jobs (repeating invoices at 06:00, reminders at 09:00, Lusaka
time); without it nothing is generated or chased automatically. Without Docker, run
`uv run celery -A config worker -l info` and `uv run celery -A config beat -l info` as well.

**Without Docker** (needs Postgres and Redis running):

```bash
cd backend
cp .env.example .env
uv sync
uv run python manage.py migrate
uv run python manage.py runserver        # http://localhost:8000/api/docs/

cd ../frontend
pnpm install
pnpm dev                                 # http://localhost:5173
```

## Checks

```bash
# backend
uv run pytest && uv run ruff check . && uv run mypy .
# frontend
pnpm test && pnpm lint && pnpm typecheck
# end to end (with both servers running)
cd e2e && pnpm install && pnpm exec playwright test
# after changing the API
cd backend && uv run python manage.py spectacular --file openapi.yml && cd ../frontend && pnpm gen:api
```

Install hooks once with `uv run --directory backend pre-commit install`.

## How invoices work

- **Numbers** are `INV-<year>-<nnnn>` per business, allocated inside `SELECT … FOR UPDATE` on a
  per-business, per-year counter. A test fires 50 concurrent creations and checks for 50
  consecutive, unique numbers.
- **Totals** are computed on the server from the lines (`quantity × unit_price − discount`), summed
  exactly and rounded half-up **once** at the end. The frontend preview uses the same maths with
  BigInt, but the server's numbers are what gets stored.
- **Status** is stored lifecycle (`draft → sent`, or `void`) plus payment state derived from
  payments (`unpaid`, `partial`, `paid`). `overdue` means sent, not fully paid, and past the due
  date *in Lusaka time*. The badge shown is one of draft, sent, viewed, partly paid, paid, overdue,
  void.
- **Sent invoices are locked.** To change one, "Change" voids it and opens a corrected draft with a
  new number; both link to each other, and the customer's old link says it was replaced. Invoices
  are never deleted. An invoice with payments can't be voided until the payments are removed.
- **Payments** can't exceed the balance, can only be recorded on sent invoices, and can be deleted
  to fix mistakes (logged on the timeline).
- **Public link** `/i/<uuid4>/` is server-rendered Django (no JS, small, works in WhatsApp's
  in-app browser). The first view by someone who isn't a member of the business sets *viewed*.
  Drafts 404 for the public; owners see a preview banner.
- **PDF** is WeasyPrint from the same template, cached in storage under a fingerprint of everything
  printed on it, so it's rebuilt only when something changes. A Celery task pre-builds it on send.
- **WhatsApp (click-to-chat):** "Send on WhatsApp" marks the invoice sent and opens
  `wa.me/<number>?text=…` with the message and link. Free, no Meta approval. Logged as a *shared*
  Delivery; the *viewed* event confirms the customer opened it.
- **Email** goes through Django's email API (console in dev; set `EMAIL_BACKEND` to an anymail
  backend such as `anymail.backends.resend.EmailBackend` in production). A Celery task sends it
  with the PDF attached, retries up to 3 times, and records the Delivery as sent or failed.
- Every change writes an **ActivityLog** row, shown as the invoice timeline.

## Phase 2: automation

- **One Send button, three channels.** *WhatsApp from my phone* (wa.me, free, no setup),
  *WhatsApp, sent for me* (Cloud API, only shown when configured) and *Email*. Every send is a
  `Delivery` row with a status that only moves forward: queued → sent → delivered → read, or
  failed. The invoice shows them under "Sending".
- **WhatsApp Cloud API.** One platform-owned business number sends Meta-approved *utility*
  templates with the PDF as the document header; the business name is a template parameter. Set
  `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET` and
  `WHATSAPP_VERIFY_TOKEN`, and create the three templates listed at the top of
  `backend/apps/messaging/whatsapp.py` (`invoice_new`, `invoice_reminder`, `quote_new`). Failed
  sends retry up to 3 times unless Meta says retrying won't help (bad number, template problem).
- **Delivery webhooks.**
  - WhatsApp: point the app's webhook at `https://<your-domain>/api/webhooks/whatsapp/` with the
    same verify token and subscribe to `messages`. Every POST is checked against
    `X-Hub-Signature-256` (HMAC with the app secret); each status event is applied once.
  - Email: `https://<your-domain>/api/webhooks/email/<esp>/tracking/` (anymail; e.g. `resend`).
    Protect it with `ANYMAIL_WEBHOOK_SECRET`.
- **Reminders.** "Send reminder" on any sent invoice with a balance chases it now. Automatic
  reminders are off by default; in Settings an owner turns them on and picks the gap (default 7
  days) and the most per invoice (default 3). Each morning at 09:00 the beat job sends one to
  every overdue invoice that is due for one, by Cloud WhatsApp if set up, else email. Reminders
  can be paused per invoice. Customers who can't be reached automatically (no email, and Cloud
  WhatsApp not set up) are skipped; chase them with *Send reminder*, which uses wa.me.
- **Repeating invoices** (`/recurring`): weekly or monthly every *n*, with optional end date,
  payment terms and what to do with each invoice (keep as draft, email, or WhatsApp). Monthly
  dates stay anchored to the start day (31 Jan → 28 Feb → 31 Mar). Generation is idempotent (one
  invoice per schedule per date, enforced by a unique constraint), catches up after downtime (up
  to 12, only the newest is sent), and a paused schedule that's resumed skips the missed dates.
- **Quotes** (`QUO-<year>-<nnnn>`, numbered separately): draft → sent → accepted / declined, plus
  *expired* after the valid-until date. The customer's link `/q/<uuid>/` has Accept and Decline
  buttons (CSRF-protected form, no JS). "Make invoice" copies the lines into a new draft invoice
  and links the two.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health/` | Liveness + DB check (public) |
| GET | `/api/auth/csrf/` | Sets the `csrftoken` cookie |
| POST | `/api/auth/signup/` · `login/` · `logout/` | Email + password (rate limited) |
| GET | `/api/auth/me/` | User, current business, all businesses |
| GET/POST/PATCH | `/api/businesses/…` | Profile, payment details; `POST {id}/switch/` |
| CRUD | `/api/customers/` · `/api/items/` | `?search=` |
| GET/POST/PATCH | `/api/invoices/` | `?status=draft\|unpaid\|partial\|paid\|overdue\|void`, `?customer=`, `?search=` |
| POST | `/api/invoices/{id}/send/` · `void/` · `reissue/` | Lifecycle |
| POST | `/api/invoices/{id}/payments/` | Record a payment |
| POST | `/api/invoices/{id}/deliver/` · `remind/` | Send or chase: `{channel: whatsapp_link\|whatsapp\|email, to?, message?}` |
| POST | `/api/invoices/{id}/reminders/` | `{paused: bool}` for automatic reminders |
| POST | `/api/invoices/{id}/whatsapp/` · `email/` | Phase 1 send endpoints (still work) |
| GET | `/api/invoices/{id}/pdf/` | Owner download |
| GET/DELETE | `/api/payments/{id}/` | Undo a payment |
| GET | `/api/dashboard/` | Owed, overdue, paid this month, top debtors |
| CRUD | `/api/quotes/` | `?status=draft\|open\|sent\|accepted\|declined\|expired\|converted` |
| POST | `/api/quotes/{id}/deliver/` · `respond/` · `convert/` | Send, record answer, make invoice |
| CRUD | `/api/recurring/` | Repeating invoice schedules, with the next few dates |
| GET | `/api/config/` | Which optional integrations are switched on |
| GET/POST | `/api/webhooks/whatsapp/` · `/api/webhooks/email/…` | Delivery status callbacks (public, signed) |
| GET | `/i/{token}/` · `/i/{token}/pdf/` | Customer-facing invoice and PDF |
| GET/POST | `/q/{token}/` · `respond/` · `pdf/` | Customer-facing quote, accept/decline, PDF |

All amounts are integers in ngwee (or cents for USD). Full schema: `/api/docs/`.

## Roadmap

| Phase | Scope |
|---|---|
| **0 – Setup** ✅ | Repo, Docker, CI, email auth, Business/Membership tenancy, hello world |
| **1 – MVP** ✅ | Customers, items, invoices (draft/send/void), PDF, public link + viewed, WhatsApp click-to-chat, email, manual payments, dashboard |
| **2 – Automation** ✅ | WhatsApp Cloud API, delivery webhooks, reminders, recurring invoices, quotes |
| 3 – Get paid | Mobile-money/card "Pay now", webhook reconciliation, receipts, statements |
| 4 – Grow | ZRA Smart Invoice integration, team roles, PWA, Bemba/Nyanja labels |

Customer phone numbers and emails are personal data, handled in line with Zambia's Data Protection
Act.
