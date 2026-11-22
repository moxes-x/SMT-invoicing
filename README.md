# Invoicing

Invoices, quotes, repeating invoices, online payments, receipts, reminders and WhatsApp/email sending for Zambian small businesses that are **not
VAT-registered**: turnover-tax payers, freelancers, small traders and service providers who today
send invoices as photos, Word files or WhatsApp texts and lose track of who has paid.

> Documents from this app are titled **"Invoice"**. Only a VAT-registered business that has switched
> on ZRA Smart Invoice (Phase 4e) gets **"Tax Invoice"**, and only on invoices ZRA has signed.

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
                                     ├──► WhatsApp Cloud API (optional)
                                     └──► Lenco (each business's own account, optional)
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
# end to end (with both servers running, the fakes started, and Django pointed at the fake Lenco:
#   node e2e/fake-lenco.mjs &  node e2e/fake-vsdc.mjs &
#   AUTH_THROTTLE_RATE=1000/min LENCO_SANDBOX_API_URL=http://localhost:8090/access/v2)
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

## Phase 3: getting paid

- **Pay now.** A business connects its **own** Lenco (BroadPay) merchant account in Settings
  (public key + secret key; the secret is write-only and stored encrypted with
  `FIELD_ENCRYPTION_KEY`). Money goes straight to the business, so this app never holds customer
  funds. Sent, unpaid **Kwacha** invoices then show *Pay now* on the customer link:
  - **Mobile money** (MTN, Airtel, Zamtel): no JavaScript. The customer confirms their number,
    Lenco pushes a PIN prompt to the phone, and a waiting page refreshes itself until Lenco says
    successful or failed.
  - **Card**: Lenco's own popup widget (`inline.js`), so card numbers never touch this server.
    The result is always verified server-side with Lenco's status API.
- **Confirmation, three ways, applied once.** The webhook
  (`/api/webhooks/lenco/<per-business id>/`, shown in Settings to paste into Lenco's dashboard),
  the waiting page polling (at most every 4 s), and a Celery beat job every 10 minutes that
  re-checks anything still open (webhooks can be missed). Each webhook is checked against
  `X-Lenco-Signature` (HMAC-SHA512 of the raw body, keyed with the hex SHA-256 of the business's
  secret key), de-duplicated, and the payment attempt row is locked, so a payment is recorded
  exactly once whichever arrives first.
- **What happens on success:** a `Payment` (source *online*, method MTN/Airtel/Zamtel/card, Lenco
  reference) for the amount Lenco reports, the invoice moves to paid/partly paid, the timeline
  says *Paid online*, the owner gets an email and the customer gets their receipt by email.
  Online payments can't be deleted (refund in Lenco instead). If a customer pays twice, both are
  recorded and the timeline flags the overpayment.
- **Receipts** for every payment, online or recorded by hand: `RCT-<year>-<nnnn>`, a public page
  `/r/<uuid>/` and PDF, listed on the invoice link, and one-tap "send receipt on WhatsApp" in the
  app. Existing payments got receipt numbers in the migration.
- **Statements** per customer and currency for any date range: opening balance, invoices and
  payments with a running balance, closing balance, unpaid invoices. In the app and as a PDF.
- **CSV exports** of invoices (honours the list filters) and payments (date range), amounts in
  Kwacha, UTF-8 with BOM so Excel opens them cleanly. Under More → Export.

**Testing with Lenco's sandbox:** create a Lenco account, copy the sandbox public and secret keys
into Settings → Online payments, choose *Sandbox*, press *Test connection*, and paste the webhook
URL into Lenco. Sandbox numbers: MTN `0961111111` and Airtel `0971111111` succeed;
`0962222222` fails (not enough funds). Lenco's docs don't publish the sandbox **API** host, so it's
`LENCO_SANDBOX_API_URL` (default `https://sandbox.lenco.co/access/v2`): confirm it with Lenco. The
webhook can't reach `localhost`; use a tunnel (e.g. `cloudflared`) or rely on polling locally.
End-to-end tests use `e2e/fake-lenco.mjs` instead of the real sandbox.

## Phase 4a: team roles

Every business member has one role. The API enforces it (`HasBusiness` in `apps/core/tenancy.py`);
the app just hides what you can't do.

| Role | Can |
|---|---|
| Owner | Everything, including making others owner. A business always keeps at least one owner. |
| Admin | Everything except creating, changing or removing owners |
| Staff | Customers, items, invoices, quotes, payments, sending. Not void/reissue, deletes, settings or the team |
| Accountant | Sees everything and exports CSV/statements. Changes nothing |

Invites (More → Team) are emailed and can also be shared on WhatsApp. The `/join/<token>` link
works for 7 days, and works logged out: the person signs up or logs in with the invited email and
comes back to accept. Existing "member" memberships became **staff** in the migration.

## Phase 4b: reports in more than one currency

More → Reports, for any period (this month, last month, quarter, year, last 12 months or custom):

- **Per currency, never mixed:** invoiced (sent, not void, by issue date), collected (payments by
  date received, split by method), owed and overdue right now with an aging breakdown
  (not due, 1–30, 31–60, 61–90, 90+ days late), month-by-month invoiced vs collected (chart or
  table), and top customers.
- **Everything in Kwacha:** each foreign-currency invoice can carry an **exchange rate** (Kwacha
  per 1 unit) set in the editor or added later on the invoice (it doesn't change what the
  customer owes). The Kwacha view converts each invoice, its payments and its balance at its own
  rate. Invoices without a rate are counted and left out, never guessed. The invoice PDF shows the
  Kwacha total when a rate is set.
- **CSV:** `/api/reports/export/` (month, currency, invoiced, collected, plus the Kwacha rows).
  The invoices CSV gained *Kwacha rate* and *Total in Kwacha* columns at the end.

## Phase 4c: works with a weak or no connection

- **Installable.** A web app manifest and icons, so phones offer *Add to home screen* (also under
  More on Android/Chrome). It opens full-screen like an app.
- **Opens offline.** A small hand-written service worker (`frontend/public/sw.js`, production
  builds only) keeps the app itself on the phone: pages fall back to the saved app when there's
  no network; hashed `/assets/` files are cache-first. The API, customer pages (`/i/`, `/q/`,
  `/r/`), `/admin`, `/static` and `/media` always go to the network.
- **Shows the last data it loaded.** The query cache is saved to the phone (`localStorage`,
  successful reads only, max 7 days, about 3 MB) and restored on start. A banner says when you're
  offline. Saved data is wiped on log out, on log in as someone else, and when the session ends.
- **Changes wait for the connection.** Saving while offline (a customer, a payment, an invoice)
  is paused rather than failing and is sent automatically when the connection returns, while the
  app stays open; the banner counts what's waiting.

**Hosting:** serve `frontend/dist` with an SPA fallback to `index.html`, and serve `/sw.js` with
`Cache-Control: no-cache` so updates are picked up. Bump `VERSION` in `sw.js` to clear old saved
files after big releases. Try it locally with `pnpm build && pnpm preview` (port 4173, proxies
the API like `pnpm dev`), load a few pages, then switch the browser to offline and reload.

## Phase 4d: Bemba and Nyanja

- **The app:** More → Language switches the app's main labels (navigation, page titles, main
  buttons, statuses, the offline banner) between English, Icibemba and Chinyanja. Saved on the
  user (`PATCH /api/auth/me/ {language}`), so it follows them to other phones.
- **Customers:** each customer has a language. Their WhatsApp/email message (invoice, reminder,
  quote), the receipt WhatsApp text, and the invoice, quote and receipt pages and PDFs use it.
  The document names stay in English (*Invoice*, *Quote*, *Receipt*), and so do the WhatsApp
  Cloud API templates, which Meta approves per language (add Bemba/Nyanja templates there first).
- **Where the words live:** `backend/apps/core/i18n.py` (customer-facing) and
  `frontend/src/i18n/{en,bem,ny}.ts` (the app). Missing words fall back to English; tests check
  every key has all three languages with the same `{placeholders}`. **The translations need a
  check by native speakers before launch.**

## Phase 4e: ZRA Smart Invoice

For VAT-registered businesses. Built to ZRA's *VSDC API Specification* (updated 02-10-2026).

- **The VSDC:** ZRA gives each approved taxpayer a VSDC (a Java service, WAR/JAR) to run on a server
  they control. It holds ZRA's keys, so our requests carry no credentials. Each business enters
  its own details in **Settings → ZRA Smart Invoice**: VSDC address, branch ID, device serial,
  item class code, what they sell (goods or services), usual VAT category and payment type. The
  TPIN and "We are VAT-registered" come from the business details above it. **Test connection**
  runs device initialisation (`selectInitInfo`) and keeps the SDC ID and MRC number.
- **Sending:** when it's on, *Mark as sent* (and every send) reports the sale to the VSDC
  (`saveSales`) inside the same transaction, after saving any new item codes (`saveItem`, ZRA's
  `ZM<type>NTU<0000001>` format). If ZRA says no, the invoice stays a draft and the reason is shown.
  If ZRA already has the number (code 924, e.g. after a timeout) the signed receipt is fetched with
  `selectInvoice` instead.
- **Amounts:** line prices include VAT, as in ZRA's examples: K116 at 16% is taxable K100 and VAT
  K16 (4 decimal places). Each line's VAT category is the item's, else the business's usual one,
  and is stored on the line once reported. Non-Kwacha invoices need an exchange rate first, and it
  can't change afterwards.
- **The document:** signed invoices are titled **Tax Invoice** and show both TPINs, a VAT summary,
  ZRA's SDC ID, receipt number, MRC, internal data, signature and a verification QR code
  (`segno`). The fiscal block stays in English: those are ZRA's terms.
- **Voiding** a tax invoice (or *Change*, which voids and copies) sends ZRA a credit note
  (`rcptTyCd R`, reason code 07 with your reason) numbered `CN-<year>-<nnnn>`, referring to the
  original receipt. If ZRA refuses it, the invoice is not voided.
- **Not yet:** stock reports (`saveStockItems`/`saveStockMaster`), which ZRA expects from
  businesses selling goods from stock; debit notes; MTV (category B), export and tourism fields.
- **Testing:** `e2e/fake-vsdc.mjs` (port 8091) answers like the spec's samples. Set the VSDC
  address to `http://localhost:8091/zrasandboxvsdc`.

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
| GET/DELETE | `/api/payments/{id}/` | Undo a payment (not online ones) |
| GET | `/api/payments/export/` · `/api/invoices/export/` | CSV; `?start=&end=` for payments |
| GET/PUT | `/api/online-payments/` | This business's Lenco keys; `POST …/test/` checks them |
| GET | `/api/customers/{id}/statement/` · `statement/pdf/` | `?start=&end=&currency=` |
| POST | `/api/webhooks/lenco/{id}/` | Lenco collection events (signed) |
| GET | `/api/team/` | Members and open invites |
| POST/DELETE | `/api/team/invites/` · `invites/{id}/` | Invite by email + role; cancel |
| PATCH/DELETE | `/api/team/members/{id}/` | Change role; remove (or leave) |
| GET/POST | `/api/auth/invites/{token}/` · `accept/` | Invite details (public); accept |
| GET | `/api/reports/` · `/api/reports/export/` | `?start=&end=` (default this month, max 3 years) |
| POST | `/api/invoices/{id}/exchange-rate/` | `{exchange_rate}` for a non-Kwacha invoice, also after sending |
| GET/PUT | `/api/zra/` | This business's ZRA VSDC settings; `POST …/test/` initialises the device |
| GET | `/api/dashboard/` | Owed, overdue, paid this month, top debtors |
| CRUD | `/api/quotes/` | `?status=draft\|open\|sent\|accepted\|declined\|expired\|converted` |
| POST | `/api/quotes/{id}/deliver/` · `respond/` · `convert/` | Send, record answer, make invoice |
| CRUD | `/api/recurring/` | Repeating invoice schedules, with the next few dates |
| GET | `/api/config/` | Which optional integrations are switched on |
| GET/POST | `/api/webhooks/whatsapp/` · `/api/webhooks/email/…` | Delivery status callbacks (public, signed) |
| GET | `/i/{token}/` · `/i/{token}/pdf/` | Customer-facing invoice and PDF |
| GET/POST | `/q/{token}/` · `respond/` · `pdf/` | Customer-facing quote, accept/decline, PDF |
| POST/GET | `/i/{token}/pay/` · `pay/{reference}/` | Pay now and the waiting page |
| GET | `/r/{token}/` · `/r/{token}/pdf/` | Customer-facing receipt and PDF |

All amounts are integers in ngwee (or cents for USD). Full schema: `/api/docs/`.

## Roadmap

| Phase | Scope |
|---|---|
| **0 – Setup** ✅ | Repo, Docker, CI, email auth, Business/Membership tenancy, hello world |
| **1 – MVP** ✅ | Customers, items, invoices (draft/send/void), PDF, public link + viewed, WhatsApp click-to-chat, email, manual payments, dashboard |
| **2 – Automation** ✅ | WhatsApp Cloud API, delivery webhooks, reminders, recurring invoices, quotes |
| **3 – Get paid** ✅ | Mobile-money/card "Pay now", webhook reconciliation, receipts, statements, CSV export |
| 4 – Grow | Team roles ✅, multi-currency reports ✅, offline PWA ✅, Bemba/Nyanja ✅, ZRA Smart Invoice ✅ |

Customer phone numbers and emails are personal data, handled in line with Zambia's Data Protection
Act.
