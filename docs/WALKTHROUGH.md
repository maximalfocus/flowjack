# flowjack — walkthrough

> Local educational material. The vulnerable service in this repository has **no anti-automation on
> a sensitive business flow** by design. It is fictional, it runs only on a container network with no
> egress, and it **must never be deployed**.

Run everything first, then read this alongside the output:

```sh
bash scripts/verify.sh
```

---

## 1. What a sensitive business flow is

A **business flow** is a sequence of steps that produces something the business cares about. In this
demo it is three steps long:

```
register  →  hold a seat  →  confirm the hold into a ticket
```

Nothing about those steps is unusual, and nothing about them is broken. Each is authenticated, each
is authorised, each does exactly what its documentation says.

A flow becomes **sensitive** when two things are true at once:

1. **it produces something scarce or valuable** — a seat, an appointment, a discount code, a review
   that moves a rating, an account that carries a signup bonus; and
2. **the business quietly assumed it would be paid for in human time** — that a person would sit
   there, one booking at a time, and that this was rate enough.

Assumption (2) is the whole vulnerability. It is not written down anywhere, no code enforces it, and
automation does not honour it.

Two questions identify a sensitive flow in a system you are reviewing:

> **What does the business lose if this runs ten thousand times?**
> **What stops it?**

If the second answer is "nothing in particular", you have found one.

## 2. What anti-automation is, and what it is not

**Anti-automation is not "detect the robot."** Every control in this demo that tries to identify or
slow the caller holds up perfectly and changes nothing about the outcome.

What actually works is a **flow limit**: a bound on *the outcome of the flow, per identity, over
time*, expressed in the units the business cares about. Not requests per second — **seats per
person**.

The distinction matters because these are different quantities and only one of them is the harm.

## 3. The taxonomy, stated carefully

| | |
|---|---|
| **OWASP API Security Top 10** | **API6:2023** — Unrestricted Access to Sensitive Business Flows |
| **Closest CWE anchor** | **CWE-840** — Business Logic Errors |
| **Also known as** | business-flow abuse, business-logic abuse, anti-automation failure; in its commercial forms scalping, inventory hoarding, bonus/referral farming |

**The caveat matters and is part of the lesson.** CWE-840 is a *class-level* entry, not a specific
weakness, and naming it here is an anchoring judgement rather than a claim of a published mapping.
This defect has no single canonical CWE precisely because **it is not an implementation bug**.

A demo of this class cannot point at one wrong line of code the way an injection demo can. There is
no unescaped quote, no missing check, no confused verifier. Everything works. That is the finding.

## 4. The fixture

**Alder Hall**, a fictional community concert venue. Show `SHOW-2026-11-07` — *the Meridian
Quartet* — **120 seats** on public sale.

- **40 genuine patrons**, entitled to **2** seats each: 80 seats of honest demand.
- **1 household patron**, carrying a documented entitlement of **4**.
- **1 automated operator**, running exactly the same flow the patrons run.

Everything is fictional. There is no real venue, performer, patron, or credential anywhere in this
project.

## 5. The ladder — five shapes, one flaw

Run `python -m flowjack.compare` to see all of these on one screen.

### Shape 1 — no anti-automation at all

One registration. Then the same flow, 120 times.

| | |
|---|---|
| seats to the operator | **120 / 120** |
| identities it needed | **1** |
| seats to genuine patrons | **0** |
| responses that were not `201` | **0** |

Note what it did *not* need: no botnet, no stolen credentials, no exploit. One account and a loop.

### Shape 2 — abandoned holds: harm with no transaction

The operator holds every seat and **never confirms one**, re-holding as each hold lapses.

| | |
|---|---|
| seats denied | **120 / 120** |
| **tickets sold** | **0** |
| payments taken | **0** |

There is no purchase, no payment, and no transaction for a fraud control to examine. The venue has
sold nothing and has nothing left to sell.

**Why it matters for the fix:** a limit that counted only *confirmed* outcomes would count the wrong
event. This is why the secure application charges an outstanding hold exactly as it charges a ticket,
and why expiry does not hand entitlement back indefinitely.

### Shape 3 — a per-source rate limit

A real, correctly implemented sliding-window limiter: N requests per source, genuinely enforced.
(The suite proves it is not a stub by pointing enough traffic at one source and watching it refuse.)

| | |
|---|---|
| requests it refused during the run | **0** — it was never once exceeded |
| seats to the operator | **120 / 120** |

The operator distributed the identical flow across eight source labels, each comfortably under the
limit.

**Why it fails:** the limiter counts *requests per source*. The business cares about *outcomes per
person*. Those are different quantities, and the attacker — not the venue — chooses the source.

### Shape 4 — a per-account quota

**This is the one to sit with, because the quota is correct.** Two seats per patron per show,
expressed in business terms, enforced server-side, checked at every step.

| | |
|---|---|
| quota violations | **0** — most seats held by any one identity: **2** |
| identities the operator used | **60** |
| seats to the operator | **120 / 120** |

Every single quota check passed. The allocation was drained by **compliant** requests.

**Why it fails:** the quota is keyed on an identity, and registration was itself an unprotected
sensitive flow — so identities cost nothing. The generalized rule:

> **A limit keyed on an identity is a limit on how cheaply that identity can be obtained.**

The fix is not a better quota. The quota was fine. The fix is to make the *key* cost something.

### Shape 5 — a verification gate at the front door

A human-verification challenge where a user interface would show one: at registration, as a new
visitor arrives. The flow behind it is ungated.

| | |
|---|---|
| challenges passed | **1** — legitimately |
| seats obtained afterwards | **120** |

**Nothing in this project defeats, solves, weakens, replays, or machine-answers a challenge**, and
the finding does not depend on how hard the challenge is. Even one nobody could beat, **paid once**,
buys every unchallenged request behind it. Tokens here are single-use, so "one challenge" needs no
qualification.

**Why it fails:** a gate prices **entry**. It says nothing about how much flow one entry may go on
to consume. The fix it points at is not a stronger challenge — it is a limit on what one verified
identity may then do, which is shapes 3 and 4's fix, not a fourth idea.

---

## 6. The two negative controls

A demo that only shows the flaw teaches half a lesson. These two mark its boundaries.

### It is not a race condition

Run the identical automation at **concurrency 1** — one identity, one source, one request at a time,
paced *deliberately below* the enforced rate limit — and it still takes all 120 seats. Just more
slowly.

Nothing in this demonstration depends on simultaneity, interleaving, or scheduling. Every count is
exactly reproducible on every machine, and the suite asserts the same numbers at concurrency 1 and 8.

> Throttling changed how long the harm took, and **nothing else**. Reducing the rate of a flow is not
> a limit on its outcome.

The defect this class is repeatedly mistaken for is the check-then-act race (`CWE-367` / `CWE-362`),
where simultaneity *is* the mechanism and serialising the requests is the fix — the subject of a
separate demonstration in this series, `racejack`. The two look similar in a summary and need
completely different fixes: here, serialising the requests changes nothing.

### There was no malicious request to find

Every run ends by replaying its captured requests through a per-request validity check —
authentication, authorization, schema, and every per-request rule in force:

```
request-level validity replay
-----------------------------
  requests replayed            : 321
  individually VALID           : 321  (100.0%)
  individually INVALID         : 0
  every request in this run was individually valid — a request-level control had nothing to key on
```

Across every shape, in every scenario, the answer is 100%.

The check is deliberately conservative: a request refused for want of a verification token counts as
**invalid**, so the figure is never reached by defining the problem away. And the suite proves the
replay is a real check, not a constant, by running a scenario that *does* produce invalid requests
and watching the number fall.

The other half of this control: the **household patron's legitimate four-seat booking must keep
succeeding**. A control that stopped the attack by refusing them would have failed twice over — once
at the attack, and once at the customer.

---

## 7. The fix — three flow limits, none sufficient alone

### A — an outcome quota on the flow

Count **seats per identity per show**, not requests per second. Count **outstanding holds together
with confirmed tickets**, because a hold is a claim on a seat nobody else can have and must cost its
holder exactly what a ticket costs. Return entitlement on expiry only within a bounded, documented
re-hold allowance — otherwise "hold, let it lapse, hold again" is an unlimited flow wearing a
limit's clothes.

*Closes shapes 1 and 2. Does nothing about shape 4.*

### B — governed identity supply

Treat registration as a sensitive business flow in its own right: an eligibility step and its own
limit, so obtaining an identity has a bounded, documented cost.

Be honest about what this buys. The operator is **limited, not eliminated** — in this demo it still
reaches its documented ceiling of 6 seats. That is the realistic outcome for this control class, and
a demo that claimed otherwise would be lying.

*Closes shape 4. Does nothing about shape 5.*

### C — flow-scoped enforcement

Keep **server-side flow state**: which flow was entered, by whom, and how far it has progressed.
Re-check it at every step. Entering the flow part-way through, presenting another identity's hold, or
replaying a finished flow are all refused.

*Closes the "control on an endpoint" mistake that shape 5 is the front-door version of.*

### Why all three

Each closes a different shape and leaves the others open. Shipping one and calling it done is how
each of the three half-fixes in section 5 came to exist.

### And: no oracle

Every refusal — sold out, entitlement used, flow not entered, identity supply reached — returns the
**same** status and the **same** body. A caller who could tell them apart would have an oracle for
the venue's remaining stock and for exactly where each limit sits. The audit event that records the
refusal is equally incurious.

---

## 8. Layers this demo names but does not build

Each is a real tool. None removes the need for a flow limit, and each costs somebody something.

| Layer | What it buys | What it costs |
|---|---|---|
| **Proof-of-work / human-verification challenges** | Raises the price of entry, and of each retry if applied per action | Friction for every legitimate user; accessibility harm; an arms race; and — as shape 5 shows — worth nothing at all if priced once |
| **Device and behavioural signals** | Correlates activity that separate accounts try to keep apart | Privacy exposure; false positives against unusual-but-honest users; needs data a local demo cannot honestly produce |
| **Waiting room / lottery allocation** | Decouples arrival speed from outcome entirely — a genuinely strong answer for scarce drops | Changes the product; only applies where a queue is acceptable |
| **Payment friction** (deposits, non-refundable holds) | Makes hoarding cost real money — directly answers shape 2 | Excludes people for whom the deposit is a barrier |
| **Aggregate anomaly detection** | Sees the pattern no single request contains — the right *altitude* | Detects after the fact; needs a baseline; tuning is a permanent job |

They are complements. The flow limit is the floor.

## 9. What this project deliberately does not contain

There is **no offensive or evasion capability anywhere in this repository**, and none is needed —
which is itself the point of the risk class.

Not built, not shipped, not required:

- credential guessing, wordlists, brute force, or stuffing;
- CAPTCHA or proof-of-work solving;
- browser-fingerprint spoofing, proxy rotation, or address rotation;
- headless-browser evasion or detection evasion of any kind;
- scraping.

Every request the harness issues is a well-formed, authenticated, authorised call the API is
**designed to accept**. The identities and source labels it distributes across are a fixed,
enumerated, checked-in set of fictional fixtures — nothing generated, discovered, or rotated at
scale.

This document explains *why naive controls fail*, which is knowledge a designer needs to choose
better ones. It does not explain how to get past a control in somebody else's system.

## 10. Where to look in the code

| | |
|---|---|
| `src/flowjack/policy.py` | which flow limits are in force; every vulnerable shape is a **subset** of `SECURE`, so the ladder is a diff |
| `src/flowjack/limits.py` | strategies A and B |
| `src/flowjack/flow.py` | the two-step flow and strategy C |
| `src/flowjack/ratelimit.py` | a real per-source limiter — not a flow limit, and not a stub |
| `src/flowjack/verification.py` | the challenge, and a long comment on what it is not |
| `src/flowjack/harness/` | the flow run at volume; the allocation ledger; the validity replay |
| `src/flowjack/compare/` | every scenario, side by side |

The most compressed statement of the whole demo is `policy.py`:

```python
SECURE = Policy(seat_quota=True, governed_identity_supply=True, flow_state=True)
VULNERABLE_PER_ACCOUNT_QUOTA = Policy(seat_quota=True)  # A without B
VULNERABLE_FRONT_DOOR_GATE = Policy(verification_gate_steps={"register"})
```

The second line is a correct quota with a free key. It is the shape that drains 120 seats without
violating a single limit.

## 11. What a learner should be able to do now

1. Identify a sensitive business flow in a system you are reviewing, using the two questions in §1.
2. Explain why a green test suite, a clean code review, and a passing scanner say nothing about it.
3. Explain why a per-source rate limit counts the wrong quantity.
4. Explain why a *correct* per-account quota is only as strong as the cost of an account.
5. Explain why a challenge paid once is not a limit on anything.
6. Explain that harm does not require a completed transaction.
7. Distinguish this from a race condition, and say why the fixes differ.
8. Name what to build instead: an outcome quota that counts holds, governed identity supply, and
   flow-scoped enforcement — and say why no one of them is enough.
