# Invoicing

Invoices, payment tracking and WhatsApp/email sending for Zambian small businesses that are **not
VAT-registered**: turnover-tax payers, freelancers, small traders and service providers who today
send invoices as photos, Word files or WhatsApp texts and lose track of who has paid.

> Documents from this app are titled **"Invoice"**, never "Tax Invoice". VAT-registered businesses
> must issue tax invoices through ZRA Smart Invoice; onboarding tells them so.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5 + Django REST Framework, drf-spectacular (OpenAPI), PostgreSQL |
| Jobs | Celery + Redis (sending, PDFs, reminders) |
| Frontend | React 19 + TypeScript (strict), Vite, React Router, TanStack Query, React Hook Form + Zod |
| UI | Tailwind CSS v4 with shadcn/ui tokens, so components from [21st.dev](https://21st.dev) / shadcn drop straight in (`components.json` is configured) |
| Tests | pytest + factory_boy, Vitest + Testing Library, Playwright (mobile viewport) |

```
React SPA (Vite + TS) ──HTTPS──► Django + DRF ──► PostgreSQL
                                     ├──► Celery + Redis
                                     ├──► Object storage (R2/S3)
                                     ├──► Email (django-anymail)
                                     └──► WhatsApp Cloud API (Phase 2)
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

## API (Phase 0)

| Method | Path | |
|---|---|---|
| GET | `/api/health/` | Liveness + DB check (public) |
| GET | `/api/auth/csrf/` | Sets the `csrftoken` cookie |
| POST | `/api/auth/signup/` · `/api/auth/login/` · `/api/auth/logout/` | Email + password |
| GET | `/api/auth/me/` | User, current business, all businesses |
| GET/POST | `/api/businesses/` | List mine / create (creator becomes owner) |
| GET/PATCH | `/api/businesses/{id}/` | Owners and admins can edit |
| POST | `/api/businesses/{id}/switch/` | Change the current business |

Full schema: `/api/docs/` (Swagger UI).

## Roadmap

| Phase | Scope |
|---|---|
| **0 – Setup** ✅ | Repo, Docker, CI, email auth, Business/Membership tenancy, hello world |
| 1 – MVP | Customers, items, invoices (draft/send/void), PDF, public link + viewed, WhatsApp click-to-chat, email, manual payments, dashboard |
| 2 – Automation | WhatsApp Cloud API, delivery webhooks, reminders, recurring invoices, quotes |
| 3 – Get paid | Mobile-money/card "Pay now", webhook reconciliation, receipts, statements |
| 4 – Grow | ZRA Smart Invoice integration, team roles, PWA, Bemba/Nyanja labels |

Customer phone numbers and emails are personal data, handled in line with Zambia's Data Protection
Act.
