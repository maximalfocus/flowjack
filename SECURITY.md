# Security policy

`flowjack` is an **intentionally vulnerable** educational project. Please read this before reporting
anything.

## The vulnerability that is supposed to be here

The **vulnerable** application has **no anti-automation on a sensitive business flow**. It
demonstrates — on purpose — `API6:2023` (unrestricted access to sensitive business flows), anchored
to `CWE-840`: a fictional 120-seat allocation drained by one automated operator, in four shapes.

- **no anti-automation** — the flow is unlimited and one identity takes all 120 seats;
- **abandoned-hold denial** — the allocation is denied with zero tickets confirmed and no payment;
- **the half-fixes** — a genuinely enforced per-source **rate limit**, a genuinely enforced
  per-patron **quota**, and a real single-use **verification gate**, each of which holds perfectly
  and *still* loses the allocation;
- **the negative controls** — the same automation at concurrency 1 paced under every limit still
  drains it, and legitimate power use still succeeds.

Every request in the demonstration is authenticated, authorised, well-formed, and individually
valid; each run reports that proportion, and it is 100%. **These behaviours are the subject of the
project, not bugs.** Please do not report them, and please do not open "fixes" that remove the
vulnerable variants or their demonstrated behaviour. The paired **secure** application already shows
the correct control: an outcome quota on the flow, governed identity supply, and flow-scoped
enforcement — all three, because no one of them suffices alone.

Everything is wholly fictional and runs only on your own machine, inside the demo's own container
network, which has **no egress**. No real venue, patron, performer, credential, or payment system
exists or is ever contacted. The vulnerable application requires two deliberate opt-in actions to
start — the `vulnerable` Compose profile *and* `ALLOW_VULNERABLE_DEMO=true` — and the secure
application is the default. No port is published to the host.

## Reporting an *unintended* problem

If you find a genuine, unintended security problem — something outside the deliberately demonstrated
business-flow abuse, for example an issue in the **secure** application, the containment, the
container setup, or the tooling — please report it **privately**:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** to open a private security advisory.

Please do not open a public issue for an unintended vulnerability until it has been addressed.

## Scope and expectations

This is a local, educational project with no hosted service. It makes no service-level, support,
compatibility, or production-readiness commitment, and provides no guaranteed response time. Reports
are reviewed on a best-effort basis.
