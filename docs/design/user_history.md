# User accounts and saved request history

Status: agreed design, 15 Nov 2026. Academic project: kept deliberately simple.

## Goal

After a patient selects a hospital, they can save the request, the questions asked and their
answers (the "thread"), and the hospitals they chose, so that the next time they log in they see
their history. The **My history** tab is shown only to a logged-in user.

## Decisions

| Topic | Decision |
|---|---|
| When to log in | **Optional.** Search, results and hospital pages work without an account. On the hospital page, "Save to my history" opens a Log in / Sign up dialog if needed; "Skip, don't save" is always possible. A "Log in" link is in the header of every page. |
| What is saved | Request text (only if "Save my description" is ticked, on by default), city, language, the thread (each question and answer), suggested speciality and reason, a **shortlist of up to 3 hospitals** (snapshot of name, city, specialities, website), the trace request id. **No PDF and no report text.** |
| Where | SQLite, `data/app/mediroute.db` (folder ignored by git; set `MEDIROUTE_APP_DB` to move it). The Fargate demo image uses writable task storage at `/var/lib/mediroute/mediroute.db`. Accounts and saved searches reset when the task is replaced. Not in the trace file: that is admin/debug data, pruned to 100 requests. |
| Login method | Email + password. No email verification, no password reset (an admin can reset), no Google sign-in (possible later). |
| Sign-up fields | **Required:** email, password (8+ characters), country of residence, consent tick. **Optional:** name, preferred language. **Not collected:** phone, age, sex, passport, address. |
| Passwords | Salted hash with Python's built-in `hashlib.scrypt`; never stored or logged as text. |
| Session | Random token in an **HttpOnly** cookie (`SameSite=Lax`), valid 7 days; logout deletes it. Only a hash of the token is stored. |
| CSRF | State-changing account calls accept only JSON with the header `X-MediRoute: 1` (a cross-site form cannot send it). |
| Login attempts | At most 5 failed logins per email per 15 minutes. |
| Isolation | Every history call reads the user from the session; one user can never read or delete another user's entry (tested). |
| Retention | Entries older than **90 days** are deleted automatically; Delete entry and Delete account buttons. |
| Admin page | Unchanged (trace only). Saved histories are not shown there. |

## Flow

```
patient page -> results -> hospital page --"Save to my history"--> logged in? --no--> Log in / Sign up dialog
                                                                       |yes                     |
                                                                       v                        v
                                                         POST /api/history (request, thread, shortlist)
header "My history" (logged in only) -> history.html: list, newest first -> entry: thread + hospitals
```

The pending save is kept in the browser's session storage while the dialog is open, so the search
is never lost; after login the save completes on the same page.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup` | email, password, country, consent, name?, language? -> logged in (cookie) |
| POST | `/api/auth/login` | email, password -> logged in (cookie) |
| POST | `/api/auth/logout` | ends the session |
| GET | `/api/auth/me` | the logged-in user, or 401 |
| DELETE | `/api/auth/me` | deletes the account and all its saved entries |
| POST | `/api/history` | save one request (adds hospitals to an existing entry for the same search) |
| GET | `/api/history` | the user's entries, newest first (summary) |
| GET | `/api/history/{id}` | one entry with the thread and hospitals |
| DELETE | `/api/history/{id}` | delete one entry |

## Tables

- `users`: id, email (unique, lower case), password_hash, name, country, language, consent_at, created_at
- `sessions`: token_hash, user_id, expires_at
- `login_failures`: email, at
- `saved_requests`: id, user_id, created_at, updated_at, workflow_id, trace_request_id, request_text,
  city, language, specialty, specialty_reason, thread (JSON), hospitals (JSON, up to 3)

## Later (not in this version)

- "Search again with today's data" on an entry (rerun Step 2, mark new / gone hospitals).
- One feedback question on an entry ("Was this the right kind of specialist?") for the evaluation.
- Google sign-in; email verification; password reset by email.

## Privacy note (for the patient page)

"If you log in and save, MediRoute stores your request, your answers and the hospitals you chose
so you can see them later. Reports are never stored. Entries are deleted after 90 days, or when you
delete them or your account. This is an academic project: please use test data only."
