# DEFER — Anonymizer multi-machine / shared-work topology

**Status:** DEFER
**Written:** 2026-06-14
**Workstream:** Contract Management Tools (Catalog + Anonymizer)
**Decision owner:** USER (originates) — network/hosting decision, not a build decision.

---

## Why this marker exists

A later session may propose making the anonymizer (and scanner) reachable from
the other machines, or "fixing" the localhost-only bind. **Read this before
doing that.** The decision was deliberately deferred on 2026-06-14, not
overlooked.

---

## What was settled on 2026-06-14

- The anonymizer is **three routes inside the existing `server.py`**
  (`/api/list-in-process`, `/api/anonymize`, `/anonymize` page), **not a
  separate service.** It runs under the existing `DCS-Contract-Scanner`
  scheduled task. No second task, no second port.
- The four build pieces are **complete and verified** (endpoints + page in
  `server.py`, syntax OK; `install-anonymizer.ps1` built). They work as-is for
  the single-machine case today.
- Usage confirmed as **shared work**: ~<10 machines, multiple users acting on
  the **same** contracts in `05-In-Process`.

## The deferred decision

Making one server reachable by the other machines' browsers requires changing
`server.py` to bind `0.0.0.0` (not just `127.0.0.1`) plus a firewall rule for
inbound `:5000`. That widens network exposure on an **authless** service —
anyone who can reach the host on `:5000` can run anonymization and read output.
That is a security-relevant decision (USER's 93% gate) and was **not** made.

**Current state: `server.py` bind is UNCHANGED (localhost-only). Do not flip
it without a deliberate decision.**

## Why the "10 servers, one synced tree" path is WRONG (do not build it)

Shared work + each machine running its own `server.py` against the **synced**
`05-In-Process` tree produces two silent, machine-count-scaling failure modes:

1. **OneDrive write-back conflicts** — multiple servers writing `.anon.txt` /
   `.audit.json` into the synced folder generates `file-MACHINENAME.ext`
   conflict copies. (Same class as the prior iCloud-stub bug.)
2. **Per-machine dehydration** — Files-On-Demand stubs cause anonymization to
   fail on one machine while succeeding on another; intermittent and invisible
   because the service is unattended (auto-start, no terminal, no one watching
   the error).

This is the "Parallel Work Without Coordination" anti-pattern
(OPERATING_PRINCIPLES) realized as <10 background servers with no handoff.

## The recommended shape when this is picked up

**One server, many browsers** (for shared work):

- ONE machine runs `server.py` (single Python env, single spaCy model, single
  writer). `install-anonymizer.ps1` is run on **that machine only** — not all ten.
- The other ~9 users install nothing; they open
  `http://<server-machine>:5000/anonymize` in a browser. Pieces 1–3 are plain
  HTTP and already work this way unchanged.
- **Split runtime data off the synced tree:** the running server's working data
  (catalog CSV, scan queue, anonymizer output) should live in a **plain local
  folder outside OneDrive** on the host (e.g. `C:\DCS-Runtime\`). SharePoint
  syncs *code* (good) and is the *publish target* for finished artifacts — it is
  NOT the live working directory. Single writer ⇒ the conflict class disappears
  rather than being mitigated.
- Decide separately: which machine hosts; whether `:5000` LAN-visible is
  acceptable; whether an **auth story** is required before exposing an authless
  endpoint even on the LAN (recommended: yes). Never internet-facing.

## What NOT to do

- Do NOT run `install-anonymizer.ps1` on all <10 machines.
- Do NOT flip `server.py` to `0.0.0.0` as a quiet sub-decision of a build session.
- Do NOT point multiple servers at the synced `05-In-Process` working tree.
- Do NOT expose `:5000` without first deciding the auth + hosting question.

---

*Marker authored 2026-06-14. Build is shippable single-machine today; the
multi-machine topology is its own scoped decision with whoever owns the network.*
