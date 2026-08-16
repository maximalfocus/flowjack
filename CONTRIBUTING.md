# Contributing to flowjack

Thanks for your interest. `flowjack` is a small, local, educational demonstration of unrestricted
access to a sensitive business flow — `API6:2023` / `CWE-840` — and the three flow limits that
together constitute the fix. Contributions are welcome within that purpose.

## Ground rules

- **The vulnerability stays.** The vulnerable application and all four of its shapes, the half-fixes,
  and both negative controls are intentionally insecure and are the whole point. Please do not "fix"
  them or remove their demonstrated behaviour; improvements to the *demonstration* — clarity, tests,
  documentation — are what help here. The secure application already shows the correct control.
- **Every request stays individually valid.** The defining property of this class is that the attack
  is made entirely of successful, correct requests. Nothing here may become a malformed request, an
  authorization bypass, or a defeated challenge — the request-level validity replay asserts this, and
  it must keep reporting 100%.
- **No evasion capability.** No credential guessing, wordlist, brute force, CAPTCHA solving,
  fingerprint spoofing, proxy rotation, or scraping. None is needed: every request in the
  demonstration is one the API is designed to accept.
- **Everything stays fictional and local.** The venue, show, performers, patrons, source labels, and
  demo tokens are invented. Do not add real data, real credentials, or anything that reaches a real
  system. The network has no egress.
- **Keep the containment.** The secure application stays the default; the vulnerable application
  keeps its two deliberate opt-in actions; no port is published to the host; containers stay non-root
  with capabilities dropped, `no-new-privileges`, and a read-only root filesystem.
- **Keep it exactly reproducible.** Every asserted count is identical across machines and CI. Do not
  introduce an assertion expressed as a rate, probability, or tolerance, and do not make an outcome
  depend on timing or interleaving.
- **No deployment or hosting.** This project is run locally with Docker Compose only. Do not add
  cloud deployment, hosting, or published-image configuration.

## Developing

Everything runs in containers; the host needs only Docker with Compose — no Python, no database, no
configuration.

```sh
bash scripts/verify.sh
```

That is the whole boundary: Ruff, mypy, the full test suite, the HTTP walkthrough, the automation
harness, and the side-by-side comparison of every scenario, all inside the hermetic network, torn
down afterwards. GitHub Actions runs the identical command.

Please make sure it is green before opening a pull request, keep changes focused, and add or update
tests at the behaviour boundary you are changing.

## Reporting problems

For an *unintended* security issue, follow [`SECURITY.md`](SECURITY.md) and report it privately. For
everything else — a bug in the demonstration, a documentation gap, an idea — open a normal issue.
