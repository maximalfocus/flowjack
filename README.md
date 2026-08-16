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
application — the fictional venue, the two-step booking flow, self-service registration, and the
three flow limits that together constitute the fix — the **business-flow automation harness** that
runs the flow at volume and reconciles who ended up with the seats, the **vulnerable application**
in all four of its shapes, and both **negative controls**.

The comparison CLI and the educational walkthrough arrive in a later slice.

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

## The automation harness

No single request exposes this defect, so the unit of observation has to be the aggregate outcome
of the flow run many times. The harness runs it, records every request, and asks the venue what is
left. Against the secure application it reports:

```
  seats to the AUTOMATED actor : 6  (5.0% of the allocation)
    its documented ceiling     : 6
    identities it used         : 3

  seats to GENUINE patrons     : 80
    demand offered vs served   : 80 vs 80

  requests issued              : 238
    status distribution        : 201x175  409x63
    individually INVALID       : 0

  VERDICT                      : flow limit held
```

Read the last two numbers together, because that pairing *is* the lesson: sixty-three requests were
refused and **not one of them was invalid**. There is no malformed body, no failed signature, no
authorization error — nothing a scanner or a request-level rule could key on. What refused them was
a limit on the flow's outcome, which is the only thing that could have.

Volume, pace, and concurrency are run parameters, not the mechanism. Concurrency exists purely to
shorten the run: the same counts come out at concurrency 1, and the test suite asserts exactly that.

## The vulnerable application

Point the same harness at an application with no anti-automation and the same fixtures give a very
different answer:

| | secure | no anti-automation | abandoned holds |
|---|---|---|---|
| seats to the automated operator | 6 | **120** | **120** |
| identities it needed | 3 | **1** | **1** |
| seats confirmed | 86 | 120 | **0** |
| seats to genuine patrons | 80 | **0** | **0** |
| genuine demand served | 80 / 80 | **0 / 80** | **0 / 80** |
| individually invalid requests | 0 | **0** | **0** |
| verdict | flow limit held | flow limit absent | flow limit absent |

Two things are worth sitting with.

**One identity was enough.** Not a botnet, not stolen credentials — one registration, then the same
flow 120 times. Every response `201`.

**The third column never sold a ticket.** The operator holds every seat and simply never confirms,
re-holding as each hold lapses. The allocation is denied just as completely with no purchase, no
payment, and no transaction for a fraud control to look at. That is why the secure application's
quota counts *outstanding holds* and why expiry does not hand entitlement back indefinitely — a
limit that counted only confirmations would count the wrong event.

Across all three columns the invalid-request count is zero.

## Three controls that look like fixes

Each of these is a real, correctly implemented, genuinely enforced control. Each of them holds
perfectly. Each of them watches the allocation drain.

| control | did it hold? | the evidence | seats the operator got |
|---|---|---|---|
| **per-source rate limit** | yes, perfectly | **0** requests refused by it | **120 / 120** |
| **per-account quota** (2 seats) | yes, perfectly | **0** violations; most seats by any one identity: **2** | **120 / 120** |
| **verification gate** at the front door | yes, perfectly | **1** challenge passed, legitimately | **120 / 120** |

**The rate limit** was never once exceeded. The operator spread the identical flow across eight
source labels, each comfortably under the limit. The limiter counts *requests per source*; the
business cares about *outcomes per person*; and the attacker picks the source. (A separate test
hammers one source past the limit and watches it refuse, so the limiter is provably not a stub.)

**The quota** is the one to look hardest at, because it is *correct*. It is expressed in business
terms, it is enforced server-side, and no identity ever held more than its two seats. It was keyed
on an identity that cost nothing — so sixty were brought. A limit keyed on an identity is a limit on
how cheaply that identity can be obtained, and registration was itself an unprotected sensitive
flow. Fixing this is not a better quota; it is `governed_identity_supply`.

**The gate** was paid once. Nothing here defeats, solves, replays, or machine-answers a challenge —
and the finding does not depend on how hard the challenge is. Even one nobody could beat, paid once,
buys every unchallenged request behind it. A gate prices *entry*; it says nothing about how much
flow one entry may go on to consume.

## Two things this is not

**It is not a race.** Run the identical automation at concurrency **1**, one identity, one source,
paced deliberately *below* the enforced rate limit, and it still takes all 120 seats — just more
slowly. Nothing in this demo depends on simultaneity, interleaving, or scheduling. Throttling
changed how long the harm took and nothing else. The series' demonstration of the concurrency defect
this class is repeatedly mistaken for is [`racejack`](https://github.com/maximalfocus/racejack)
(CWE-367).

**It is not something a request-level control could have caught.** Every run ends by replaying its
captured requests through a per-request validity check — authentication, authorization, schema,
every per-request rule in force — and reports the proportion that pass. In all seven scenarios,
against every shape, the answer is the same:

```
request-level validity replay
-----------------------------
  requests replayed            : 321
  individually VALID           : 321  (100.0%)
  individually INVALID         : 0
  every request in this run was individually valid — a request-level control had nothing to key on
```

The check is deliberately conservative: a request refused for want of a verification token counts as
*invalid*, so the 100% is never reached by defining the problem away. And a control that stopped
this attack by refusing the household patron's legitimate four-seat booking would have failed twice
over — so that booking is asserted to keep succeeding.

### Running it takes two deliberate actions

The vulnerable application is not started by the default path. Reaching it requires **both**:

1. the opt-in Compose profile: `--profile vulnerable`
2. the explicit acknowledgement: `ALLOW_VULNERABLE_DEMO=true`

Which shape a vulnerable instance serves is chosen by `FLOWJACK_POLICY`; only a vulnerable shape may
be named there, and asking that entry point for the secure application is refused as a configuration
mistake.

With the profile but no acknowledgement, the container exits:

```
flowjack.vulnerable_app.VulnerableDemoNotAcknowledgedError: Refusing to start the
deliberately vulnerable flowjack application. ... It is local educational material with no
anti-automation on a sensitive business flow, and must never be deployed.
```

`scripts/verify.sh` takes both actions explicitly and visibly in its second phase. The gate sits on
the deployable entry point rather than on `create_app`, so the regression suite can still pin what
the vulnerable shapes do while the thing that can be *served* stays behind the acknowledgement.

## Run it

The host needs **Docker and nothing else** — no Python, no database, no configuration:

```sh
bash scripts/verify.sh
```

That brings up the secure application on a hermetic, egress-less network, runs the linters, the
type checker, and the test suite, then drives the HTTP walkthrough and the automation harness
against running services from *inside* that network, and tears everything down. GitHub Actions runs
the identical command.

Two identical secure instances run side by side so the walkthrough and the harness each get an
untouched 120-seat allocation. Same image, same code — only their state differs.

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
  policy.py       which flow limits are in force — the vulnerable variants are subsets
  ratelimit.py    a real per-source request limiter (not a flow limit, and not a stub)
  verification.py a single-use challenge token — never defeated, only paid
  app.py          the application factory
  secure_app.py   the secure ASGI entry point
  vulnerable_app.py  the gated vulnerable entry point (two opt-in actions)
  walkthrough.py  the HTTP walkthrough
  harness/
    fixtures.py   the fixed, checked-in identities and source labels
    records.py    one record per request, and what the application did with it
    engine.py     the flow run at volume — a callable, tested directly
    ledger.py     who ended up with the seats, and the flow-limit verdict
    scenarios.py  named runs shared by the CLI and the regression suite
    validity.py   the request-level validity replay
    transcript.py the run artifact
tests/            in-process tests over the real HTTP surface, on a controllable clock
```
