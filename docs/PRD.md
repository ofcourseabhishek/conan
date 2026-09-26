# Conan: Product Requirements Document

| | |
|---|---|
| **Product** | Conan: AI contract obligation & risk intelligence (formerly "ClauseGuard") |
| **Context** | 24-hour hackathon, 2-person team, live 3-minute demo to judges |
| **Status** | Approved with conditions by the engineering council, 26 Sep 2026 |
| **Owners** | Person A (backend + AI), Person B (frontend + demo) |
| **Related** | [TRD.md](TRD.md) · [App-Flow.md](App-Flow.md) |

> Conan supports contract review and operational tracking. It does **not** give legal advice, judge enforceability, or decide which conflicting clause prevails.

---

## 1. Problem

Contractual duties hide in prose. They are spread across clauses, cross-references, conditions and relative deadlines ("within 30 days of invoice receipt"), so people miss payment dates, notice windows, certificate submissions and renewal conditions. The contract is never presented as an operational checklist. When one duty slips, nobody sees which other duties it puts at risk.

## 2. Vision and positioning

**"From clauses to consequences."** Conan turns a static contract into a traceable operational map: who must do what, by when, under which condition, and with what consequence. Every item links back to the exact clause and page it came from. Conan's differentiator is the **obligation dependency graph**, which shows how a blocked or late upstream duty may affect downstream ones.

Conan is **not** "chat with your PDF" and **not** an AI lawyer.

## 3. Target users

| Persona | Need | What Conan gives them |
|---|---|---|
| **Small business / startup operator** | Track vendor, client and partner duties without a contract-ops team | A checklist of obligations with due dates and reminders |
| **Operations / procurement lead** | Monitor deliveries, approvals, renewals and payment dependencies | A dependency graph and downstream-impact flags |
| **Freelancer / individual** | Understand their own action items and key dates | A plain list of "my obligations" with source quotes |
| **Legal / compliance reviewer** | Verify extraction fast, stay in control | Evidence and page for every item, confirm/edit/reject, and an audit trail |
| **Hackathon judge** (demo persona) | Understand the value in 3 minutes, try it unaided | A **Try sample contract** button that works end to end on the hosted URL |

## 4. Goals and non-goals

### Goals
1. Extract obligations from a text-based contract PDF, each linked to its source clause, page and quoted evidence.
2. Let a human confirm, edit or reject every extracted item, with an audit trail.
3. Never invent a calendar date. A relative deadline stays "unresolved" until the user supplies its trigger event.
4. Show an explainable, reproducible attention-priority score for every obligation.
5. Visualize dependencies and flag **potential downstream impact** when an upstream obligation is blocked, overdue or unresolved.
6. Deliver a demo that works reliably, even if the LLM or hosting is slow.

### Non-goals (hackathon)
- Legal advice, outcome prediction, enforceability, or deciding which clause prevails
- Training or fine-tuning models
- OCR for scanned PDFs
- User accounts, permissions, multi-tenancy, enterprise document management
- A free-form chatbot disconnected from structured obligations
- Production-grade integrations (calendar sync, scheduled messaging)

## 5. Scope

### 5.1 MVP (must work end to end)

| ID | Feature | Acceptance criteria |
|---|---|---|
| M1 | **PDF upload** | Accepts a text-based PDF ≤ 10 MB and ≤ 30 pages. Shows processing stages and progress. Rejects non-PDF, encrypted, oversized and scanned files with a specific, actionable message. |
| M2 | **Text extraction with provenance** | Text is page-indexed with section context. Hidden or invisible text is excluded. |
| M3 | **Clause segmentation & categories** | Clauses are split with section refs and page spans, and categorized as payment, renewal, termination, compliance, delivery, penalty, confidentiality or other. |
| M4 | **Obligation extraction** | Each obligation has actor, counterparty, modality (must / must not / may), action, object, trigger, deadline rule, amount, penalty, evidence quote, clause, page(s) and confidence. Mutual duties produce one obligation per party. |
| M5 | **Review & correction** | The user can confirm, edit or reject any obligation or dependency link. Each action is recorded with before/after values. |
| M6 | **Obligation list** | Searchable and filterable by category, party, status, due window, risk band and review state. |
| M7 | **Risk explanation** | Each obligation shows its attention-priority score (0–100), band, and a factor-by-factor breakdown. No unexplained scores. |
| M8 | **Source traceability** | Every obligation opens its clause text with the evidence quote highlighted and the page number shown. Unverified evidence is labelled as such. |
| M9 | **Timeline** | Dated deadlines sit on a timeline. Unresolved ones appear in a separate "Needs trigger date" lane. |
| M10 | **Obligation graph** (centerpiece) | Interactive nodes and edges. Clicking a node or edge shows its details and evidence. Nodes are coloured by risk band; AI-proposed edges are dashed and confirmed edges solid. |
| M11 | **Trigger events** | The user sets an event date such as "Invoice received = 3 Oct" once, and every dependent deadline resolves, each with a visible calculation trace. |
| M12 | **Disclaimer & delete** | A persistent "not legal advice" banner. The user can delete a contract and all its derived data. |

### 5.2 Differentiators (after MVP, in order)

| ID | Feature | Acceptance criteria |
|---|---|---|
| D1 | **Dependency risk propagation** | When an obligation is blocked, overdue or date-unresolved, downstream obligations get a "potential downstream impact" factor that shows the path, each edge's quote and its page. A "Reviewed links only" toggle limits propagation to human-confirmed links. A "Simulate blocked" action lets a user explore the effect. |
| D2 | **Potential conflict detection** | Flags inconsistent deadlines, amounts, day types or notice periods for the same duty across clauses. Both quotes are shown side by side with neutral wording. Conan never says which clause prevails. |

### 5.3 Stretch (only if the H13 checkpoint is green)

| ID | Feature | Plan |
|---|---|---|
| S1 | **ICS / CSV export** | ICS with reminders 7 days and 1 day before each resolved deadline; CSV of all obligations. |
| S2 | **Email reminder** | One real "Send test reminder" email to an address the user types in. Rate-limited, no scheduler. |
| S3 | **SMS reminder** | Preview of the SMS text, clearly labelled **"Simulated, not sent"**. Real SMS is post-hackathon. |
| S4 | **Version comparison** | Roadmap. Material obligation changes between two versions. |
| S5 | **Multi-contract overview** | Roadmap. Dashboard across contracts. |

## 6. User stories

1. *As an operations lead,* I upload a supply agreement and see every obligation with who, what and when, so I don't have to read 10 pages to find my action items.
2. *As a reviewer,* I click any obligation and see the exact quoted sentence highlighted on its page, so I can verify it in seconds.
3. *As a reviewer,* I correct a wrong field and confirm the obligation, and the change is logged, so the tracker stays trustworthy.
4. *As a user,* when a deadline depends on an event (invoice receipt), Conan asks me for that date instead of guessing, and resolves every dependent deadline once I enter it.
5. *As an operations lead,* I mark a delivery as blocked and immediately see which acceptance, invoice and payment obligations may be affected, and why.
6. *As a reviewer,* Conan flags that §6.3 says "30 days" while Schedule B says "Net 45", so I can raise it with counsel.
7. *As a user,* I see why an obligation is "High" priority as a list of factors and points, so I can agree or disagree with it.
8. *As a user,* I export my deadlines to my calendar so I get reminders.
9. *As a judge,* I click **Try sample contract** on the hosted site and reach the obligation graph without instructions.

## 7. Product principles

1. **Evidence first.** No obligation is shown without its source quote and page. Unverified items are visibly marked and routed to review.
2. **Never guess dates.** Unknown triggers mean "unresolved", never a fabricated date.
3. **Separate what was extracted, computed, AI-proposed and human-reviewed.** Each field carries a provenance chip.
4. **Explain every number.** Risk is an additive list of visible factors, labelled "attention priority, not a probability of breach".
5. **Humans stay in control.** AI-proposed links stay "proposed" until confirmed. Every edit is audited.
6. **Be honest about fallbacks.** Cached, sample and offline data are always labelled.

## 8. Success metrics

### Hackathon acceptance
| Metric | Target |
|---|---|
| Unaided judge flow | A judge reaches obligations and the graph on the hosted URL with no help |
| Obligation recall on the gold set (15–20 labelled obligations) | ≥ 80% |
| Page accuracy for verified obligations | 100% |
| Invented dates | 0 (enforced by a property test) |
| Risk reproducibility | Every score equals the sum of its visible factors |
| Graph | At least one evidence-backed chain with downstream highlighting |
| End-to-end analysis time (demo contract, live) | < 60–90 s with visible progress; < 3 s on a cache hit |
| Demo | 3-minute script rehearsed three times; offline fallback and backup video ready |

### Post-hackathon (directional)
Weekly active reviewers, share of obligations confirmed without edits (extraction quality proxy), deadlines exported per contract, and time-to-first-verified-obligation.

## 9. Constraints and assumptions

- **Time and team:** 24 wall-clock hours, including deploy, pitch and rehearsal. Two people.
- **Stack (fixed):** React + Vite + Tailwind + React Flow on Vercel; FastAPI + PyMuPDF + Pydantic on Render's free tier; Gemini structured output on the free tier; Neon Postgres.
- **LLM limits:** The Gemini free tier is rate-limited (about 15 RPM claimed, to be **verified at H0**). The design must stay inside that budget.
- **Data:** Fictional or public contracts only: a hand-written demo agreement plus a few CUAD contracts. Free-tier LLM inputs may be used by the provider, and the UI says so.

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| LLM invents an obligation or date | Wrong info shown to judges | Quotes verified against the source; unverified items flagged; dates resolved only from evidence or user input |
| Gemini quota or latency on stage | Stalled demo | Content-hash analysis cache, labelled "Try sample", offline fixture mode, backup video |
| Render cold start | 30–60 s wait | Landing page pre-warms `/health`; keep-warm pings; optional paid instance on demo day |
| Risk score read as legal judgment | Credibility | "Attention priority" label, factor breakdown, disclaimer |
| Messy PDF layouts (two-column, no numbering) | Poor segmentation | Paragraph-window fallback; demo contract is controlled |
| Prompt injection inside contract text | Manipulated output | Invisible-text filter, delimited untrusted input, strict schema, quote verification, "clauses with no obligations" count |
| Person A overloaded | Schedule slip | Person B takes over the conflicts module and exports if the H9 checkpoint slips |

## 11. Release plan (24 h)

| Gate | Time | Exit criterion |
|---|---|---|
| CP1 | H4 | A real PDF's clauses are visible in the hosted UI |
| CP2 | H9 | Hosted end to end: upload → obligations → set event date → deadlines resolve |
| CP3 | H13 | MVP + D1 on the hosted URL. **If red, stop feature work.** |
| Freeze | H16 | Feature freeze; only bug fixes and prompt tuning afterwards |
| Demo-safe | H21.5 | Tag `demo-safe`; fallbacks verified |

The full hour-by-hour plan is in [TRD §14](TRD.md#14-delivery-plan).

## 12. Demo narrative (3 minutes)

1. **Hook.** A supply agreement hides about 20 operational duties in prose.
2. Click **Try sample contract**. A cached analysis loads, and we say so. The overview shows parties, obligations and unresolved dates.
3. Open the payment obligation: the highlighted quote, p. 4, "Needs trigger date". Set *Invoice received* and six deadlines appear on the timeline.
4. In the graph, mark delivery **blocked**. Acceptance, invoice and payment light up with potential downstream impact. Open an edge to show its evidence, then confirm it.
5. Conflict flag: §6.3 says 30 days, Schedule B says Net 45. "Conan flags; it doesn't decide."
6. Correct a field and confirm it (audit trail), then export ICS.
7. Close with the pitch, the disclaimer and the roadmap.

**Pitch:** *"Conan turns contracts from static documents into a traceable map of obligations. It extracts who must do what and when, links every item to its source, and shows where one delay puts downstream commitments at risk, while people stay in control of verification."*

## 13. Roadmap (post-hackathon)

| Phase | Focus |
|---|---|
| 1. Stabilize | Accounts, persistent storage policy, stronger parsing, audit export |
| 2. Intelligence | Larger evaluation set, calibrated confidence, clause taxonomy, conflict review workflow |
| 3. Workflow | Scheduled email/SMS reminders, calendar sync, assignment and ownership, version comparison, multi-contract dashboard |
| 4. Scale & governance | Access control, encryption, retention policies, monitoring, tenant isolation, security review, OCR |

## 14. Open questions

1. What are the actual Gemini free-tier RPM/RPD limits, and which Flash model handles the flat schema reliably? (Resolve at H0.)
2. Do we pay about $7 for a Render instance that doesn't sleep on demo day?
3. If judges upload long CUAD contracts: reject above 30 pages, or analyze the first 30 with a warning?
4. Should offline mode be read-only or allow interactive recompute through a TypeScript port of the resolver and risk engine?
