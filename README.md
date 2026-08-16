# flowjack

A small, local, **educational** demonstration of **unrestricted access to sensitive business
flows** — `API6:2023` in the OWASP API Security Top 10, anchored to `CWE-840` (business logic
errors).

Everything here is fictional. It runs entirely in containers on a network with no egress, contacts
no real system, and is not a production pattern.

## The idea

Most vulnerability demos have a bad request in them somewhere — a quote that escapes a query, a
token that should not verify, a path that climbs out of a directory. This one does not.

Every request in the attack this project demonstrates is authenticated, authorised, well-formed,
and individually correct. The server is right to answer each of them. The harm is their **sum**: a
business flow with a value the business assumed would be paid for in human time, run at machine
volume until the thing being allocated is gone.

That is why the defect has no single canonical CWE, why a scanner does not find it, and why a
green test suite says nothing about it.

## What is here today

This repository is being delivered slice by slice. Right now it contains the **secure**
application: the fictional venue, the two-step booking flow, self-service registration, and the
three flow limits that together constitute the fix.

The vulnerable variants — the ladder of controls that *look* like fixes and are not — and the
automation harness that drives them arrive in later slices.

## The fixture

**Alder Hall** is a fictional community concert venue. Show `SHOW-2026-11-07` — *the Meridian
Quartet* — has a public allocation of **120 seats**. Forty fictional patrons are entitled to two
seats each; one household patron carries a documented entitlement of four.

Seats are acquired in two steps, because a flow is the unit that matters here:

| Method | Path | |
|---|---|---|
| `POST` | `/patrons` | self-service registration; issues a demo bearer token |
| `POST` | `/shows/{show_id}/holds` | place a time-limited hold on one seat — **flow step 1** |
| `POST` | `/holds/{hold_id}/confirm` | confirm that hold into a ticket — **flow step 2** |
| `GET`  | `/shows/{show_id}` | the venue's own view of its allocation |
| `GET`  | `/shows/{show_id}/allocation` | who holds what — the reconciliation surface |

## The three flow limits

No one of these is sufficient alone. That is the point of shipping all three.

**A — an outcome quota on the flow.** The limit counts *seats per identity per show*, not requests
per second. It counts **outstanding holds together with confirmed tickets**, because a hold is a
claim on a seat nobody else can have and must cost the holder exactly what a ticket costs. Expiry
returns entitlement only within a bounded, documented re-hold allowance — otherwise "hold, let it
lapse, hold again" is an unlimited flow wearing a limit's clothes.

**B — governed identity supply.** A quota keyed on an identity is only as strong as the cost of
obtaining that identity. Registration is therefore a sensitive flow in its own right: it consumes a
single-use eligibility reference and counts against a documented cap. The ceiling is deliberately
modest — an operator is **limited, not eliminated**, which is the honest outcome for this control.

**C — flow-scoped enforcement.** The server records that a flow was entered, by whom, and how far
it has progressed. Every step re-reads that record. A caller that arrives directly at the
confirmation step has no flow state to present; a caller presenting someone else's hold fails the
identity check; a caller replaying a finished flow fails the ordering check. A control placed on
the endpoint a user interface happens to call first is not a control on the flow.

Every refusal — sold out, entitlement used, flow not entered, identity supply reached — returns the
**same** status and the **same** body. A caller who could tell them apart would have an oracle for
the venue's remaining stock and for exactly where each limit sits.

## Run it

The host needs **Docker and nothing else** — no Python, no database, no configuration:

```sh
bash scripts/verify.sh
```

That brings up the secure application on a hermetic, egress-less network, runs the linters, the
type checker, and the test suite, then drives the HTTP walkthrough against the running service from
*inside* that network, and tears everything down. GitHub Actions runs the identical command.

No port is published to the host. Nothing persists between runs: fixtures are recreated from
scratch every time and the database is in memory.

### A note on the hold window

The hold window is configured to **3 seconds** for the demo (`FLOWJACK_HOLD_TTL_SECONDS`), so the
walkthrough can observe a genuine expiry inside its time budget rather than waiting out a
venue-realistic ten minutes. The default in code is 600 seconds.

## What this is not

- Not a concurrency demo. Nothing here depends on simultaneity, interleaving, or isolation; the
  walkthrough is strictly sequential and every count is exactly reproducible. The demo of the
  check-then-act race this class is repeatedly mistaken for is
  [`racejack`](https://github.com/maximalfocus/racejack).
- Not an attack tool. There is no credential guessing, wordlist, brute force, CAPTCHA solving,
  fingerprint spoofing, proxy rotation, or scraping capability here, and none is needed — every
  request in the demonstration is one the API is designed to accept.
- Not a guide to evading anti-automation controls. It explains why naive controls fail so that
  designers pick better ones.
- Not deployable. The services are local educational material and make no production-readiness,
  support, or compatibility claim.

## Layout

```
src/flowjack/
  config.py       every documented ceiling, in one place
  db.py           schema and deterministic fixtures (plain sqlite3, explicit SQL)
  auth.py         demo bearer tokens; one generic 401
  errors.py       the single refusal type and the single refusal response
  audit.py        the generic rejection event
  limits.py       strategy A (outcome quota) and strategy B (identity supply)
  flow.py         the two-step flow and strategy C (flow-scoped enforcement)
  app.py          the application factory
  secure_app.py   the secure ASGI entry point
  walkthrough.py  the HTTP walkthrough
tests/            in-process tests over the real HTTP surface, on a controllable clock
```
