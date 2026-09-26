# 🔗 Conan — AI-Powered Contract Obligation Intelligence

<div align="center">

![Conan Banner](https://img.shields.io/badge/Contract-Intelligence-blue?style=for-the-badge&logo=script&logoColor=white)
![Status](https://img.shields.io/badge/Status-Hackathon%202026-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**Transform complex contracts into actionable obligation graphs, dependency maps, and explainable risk signals.**

[🚀 Live Demo](#-live-demo) • [📖 Documentation](#-documentation) • [🏗️ Architecture](#%EF%B8%8F-architecture) • [⚡ Quick Start](#-quick-start)

</div>

> ⚖️ **Conan is a review and tracking aid, not legal advice.** It never judges enforceability or decides which conflicting clause prevails, and every extracted item needs human verification.

---

## 🎯 The Problem

Contracts are complex. Obligations are scattered across clauses, conditions, dates, and interdependencies. Teams struggle to maintain an actionable view of:

- ❌ What must happen
- ❌ When it must happen
- ❌ Who is responsible
- ❌ What depends on what
- ❌ What the consequences are if something is missed

**Result:** Missed deadlines, compliance failures, and financial penalties.

---

## 💡 The Solution

Conan converts contractual complexity into **traceable, actionable intelligence**.

```
PDF Contract
    ↓
Page-indexed text (hidden text filtered out)
    ↓
Clause segmentation
    ↓
Obligation extraction (Gemini, pass 1)
    ↓
Evidence verification → page derived from the quote's position in the PDF text
    ↓
Date resolution (only from contract text or dates you supply)
    ↓
Dependency graph (rule-based links + Gemini proposals, pass 2)
    ↓
Explainable attention priority + potential downstream impact
    ↓
Human review ← (You stay in control)
```

Instead of:

```
"The contract contains payment, renewal, and compliance provisions."
```

Conan produces:

```
CONTRACT HEALTH
├── 18 Obligations Detected
│   ├── 6 Needs review
│   ├── 5 Waiting on a trigger date ("Invoice received" not set)
│   ├── 3 High / Critical priority
│   └── 1 Potential conflict (§6.3 "30 days" vs Schedule B "Net 45")
├── Next Critical Action: Pay undisputed invoice amounts (§6.3 · p. 4)
├── Due: 2 November (invoice received 3 Oct, set by you, + 30 calendar days)
├── Attention priority: 69 · HIGH
└── Why:
    • +20 due within 7 days
    • +15 explicit penalty: "interest at 1.5% per month"
    • +12 part of a flagged conflict
    • +7  potential downstream impact: delivery (§3.1) is blocked
```

---

## 🌟 Key Features

### Core Features ✅

| Feature | Description |
|---------|------------|
| **📄 PDF Upload** | Text-based PDFs up to 10 MB / 30 pages, with page-level tracking (no OCR) |
| **🔍 Clause Classification** | Payment, renewal, termination, compliance, delivery, penalty, confidentiality, other |
| **📋 Obligation Extraction** | Actor, action, object, trigger, deadline rule, amount, penalty, quoted evidence |
| **⏰ Temporal Intelligence** | "Within 30 days of invoice receipt" becomes a real date **only once you enter the invoice date**. Conan never guesses dates. |
| **🕸️ Obligation Graph** | Interactive dependency map with React Flow (dashed = AI-proposed link, solid = confirmed) |
| **⚠️ Explainable Priority** | Additive factors you can see, labelled *attention priority*, not a probability of breach |
| **📊 Workspace** | Overview, obligations, graph, timeline, conflicts |
| **🔗 Source Traceability** | Every item opens its clause with the evidence quote highlighted and the page number shown |

### Innovation Differentiators 🚀

| Differentiator | Impact |
|---------------|--------|
| **Obligation Graph + Risk Propagation** | "Delivery is blocked, so acceptance, invoicing and payment may be affected." Every link shows its evidence. |
| **Potential Conflict Detection** | Flags inconsistent deadlines, amounts or notice periods side by side. Conan flags; it doesn't decide. |
| **Explainable Priority** | A "Why?" breakdown whose factors add up to the score |
| **Human-in-the-Loop Verification** | Confirm, edit or reject any extraction or link, with an audit trail |
| **Evidence-First Extraction** | A quote that can't be found in the source is marked *unverified* and sent to review |

### Stretch Features 🎁

- 📅 Calendar export: ICS with reminders 7 days and 1 day before, plus CSV
- 📧 One real "send test reminder" email (no scheduler during the hackathon)
- 💬 SMS reminder preview, clearly labelled *simulated, not sent*
- 🔄 Version comparison and 📊 multi-contract dashboard, on the roadmap unless there's spare time

---

## 🏗️ Architecture

### System Flow

```
                         USER
                          │
                          ↓
                 ┌─────────────────────┐
                 │  React UI (Vercel)  │
                 │ • Overview          │
                 │ • Obligations       │
                 │ • Graph (React Flow)│
                 │ • Timeline          │
                 └──────────┬──────────┘
                            │ HTTPS JSON · job polling
                            ↓
                 ┌─────────────────────┐        ┌──────────────┐
                 │ FastAPI (Render)    │◄──────►│ Neon         │
                 │ • Upload validation │        │ Postgres     │
                 │ • Async job runner  │        │ • Contracts  │
                 │ • Pipeline stages   │        │ • Clauses    │
                 │ • Recompute on edit │        │ • Obligations│
                 └──────────┬──────────┘        │ • Edges      │
                            │                   │ • Events     │
          ┌─────────────────┼─────────────────┐ │ • LLM cache  │
          ↓                 ↓                 ↓ └──────────────┘
      PyMuPDF          Gemini API        Deterministic
   (text + offsets)   (P1 obligations,   engines: evidence,
                       P2 dependency     dates, edges,
                       proposals)        conflicts, risk
```

**One backend, no API gateway.** A single FastAPI service runs the pipeline as an in-process async job. Gemini is used only where language understanding is needed. Everything after extraction is deterministic code, so editing a field recomputes dates, the graph and risk instantly, without calling the LLM.

### Where AI is used (and where it isn't)

| Task | Approach |
|------|----------|
| PDF extraction | Deterministic (PyMuPDF), with invisible-text filtering |
| Clause segmentation | Heading and font heuristics, with a paragraph fallback |
| Clause classification | Gemini (in pass 1), with a keyword fallback |
| Obligation extraction | Gemini structured output (flat schema), pass 1 |
| Evidence and page reference | Deterministic: fuzzy quote match against the PDF text; page = position of the match |
| Date resolution | Deterministic rules plus trigger events you set; the LLM never computes dates |
| Dependency detection | Rule-based links (cross-references, event chains, penalties) plus Gemini proposals (pass 2) |
| Conflict detection | Deterministic attribute comparison |
| Risk scoring | Transparent additive points; no ML model |
| Explanations | Templates over visible factors; no LLM prose |

---

## 🛠️ Tech Stack

### Frontend
```
React 18
├── Vite (build)
├── Tailwind CSS (styling)
├── @xyflow/react + dagre (obligation graph + auto-layout)
├── TanStack Query (data fetching, job polling)
├── React Router (navigation)
└── date-fns (dates)
```

### Backend (single service)
```
Python 3.11 + FastAPI + uvicorn
├── PyMuPDF (PDF text with page offsets)
├── Pydantic v2 (API + LLM schemas)
├── google-genai (Gemini structured output)
├── rapidfuzz (evidence verification)
├── python-dateutil (date arithmetic)
└── SQLModel + psycopg 3 (Postgres)
```

### Database
```
Neon Postgres (free tier)
└── Tables: contracts, jobs, pages, clauses, obligations, edges,
            events, conflicts, review_actions, llm_cache, analysis_cache
```

### Deployment
```
Frontend: Vercel
Backend:  Render (1 web service)
Database: Neon
```

Deliberately left out for the hackathon: a Node/Express gateway, MongoDB, spaCy, sentence-transformers, ML risk models, queues (Redis/Celery), user accounts, and OCR.

---

## ⚡ Quick Start

> 🚧 Code lands during the hackathon. These commands follow the planned layout in [docs/TRD.md](./docs/TRD.md).

### Prerequisites

- Node.js 18+
- Python 3.11+
- A Postgres database (e.g. a free [Neon](https://neon.tech) project)
- A Gemini API key
- Git

### 1️⃣ Clone Repository

```bash
git clone https://github.com/ofcourseabhishek/conan.git
cd conan
```

### 2️⃣ Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# DATABASE_URL=postgresql://...        (Neon, sslmode=require)
# GEMINI_API_KEY=your-key
# GEMINI_RPM=...                        (from your quota page)
# ALLOWED_ORIGINS=http://localhost:5173

uvicorn app.main:app --reload
```

The API runs on `http://localhost:8000`. Tables are created on startup. Load the demo contract with:

```bash
python scripts/seed_demo.py
```

### 3️⃣ Frontend Setup

```bash
cd frontend
npm install
echo "VITE_API_BASE=http://localhost:8000" > .env.local
npm run dev
```

The app runs on `http://localhost:5173`.

### 4️⃣ Try It

1. Open `http://localhost:5173`
2. Click **Try sample contract**, or drop a text-based PDF
3. Watch the processing stages
4. Explore the overview, obligations, graph, timeline, and conflicts
5. Set a trigger date (e.g. *Invoice received*) and watch deadlines resolve

The full list of environment variables is in [TRD §15](./docs/TRD.md#15-deployment-and-configuration).

---

## 📚 Project Structure

```
conan/
├── backend/                     # Python + FastAPI (single service)
│   ├── app/
│   │   ├── main.py              # App, CORS, startup (create tables, requeue stale jobs)
│   │   ├── models.py            # SQLModel tables
│   │   ├── schemas.py           # Pydantic API + LLM schemas
│   │   ├── api/                 # contracts, jobs, obligations, edges, events, exports
│   │   └── pipeline/            # ingest, segment, gemini, extract, verify, dedupe,
│   │                            # temporal, edges, conflicts, risk, runner
│   ├── prompts/                 # P1 / P2 system prompts
│   ├── fixtures/                # demo contract, known-good analysis, gold set
│   ├── scripts/seed_demo.py
│   └── tests/                   # unit, invariant, injection, eval_score.py
│
├── frontend/                    # React + Vite + Tailwind
│   ├── public/offline_fixture.json
│   └── src/
│       ├── api/  types/
│       ├── pages/               # Upload, Workspace
│       └── components/          # ObligationTable, SourcePanel, ReviewDrawer,
│                                # GraphView, Timeline, EventsPanel, ConflictsPanel, …
│
├── docs/                        # PRD, TRD, App Flow
├── LICENSE                      # MIT
└── README.md                    # This file
```

---

## 🚀 Live Demo

**[Deployed Instance](https://conan-demo.vercel.app)** (Coming Soon)

**Demo Video:** (Coming Soon)

**Sample Contract:** a fictional *Master Supply & Services Agreement* between Tarnwick Robotics Pvt. Ltd. and Velloran Components LLP. Both companies are invented. It is written during the hackathon and loaded through the **Try sample contract** button.

### Demo Flow (3 minutes)

1. **Try sample contract** → a cached analysis loads in about 3 s (clearly labelled)
2. **Overview** → parties, 18 obligations, 5 dates waiting on a trigger event
3. **Open the payment obligation** → quote highlighted on p. 4, "Needs trigger date"
4. **Set "Invoice received"** → six deadlines resolve on the timeline, each with its calculation shown
5. **Graph** → mark delivery *blocked*; acceptance, invoice and payment show potential downstream impact; open a link to see its evidence
6. **Conflicts** → §6.3 "30 days" vs Schedule B "Net 45", shown side by side
7. **Edit + confirm** a field (audit trail) → **export ICS**

The screen-by-screen flow is in [docs/App-Flow.md](./docs/App-Flow.md).

---

## 📊 Data Model

| Table | Key contents |
|-------|--------------|
| `contracts` | name, parties, page count, content hash, pipeline version, sample flag |
| `jobs` | state, stage, progress, warnings, error code |
| `clauses` | section ref, heading, category, text, char offsets, page span |
| `obligations` | actor, modality, action, object, trigger/produced event, deadline rule, amount, penalty, evidence quote + span, page(s), confidence, due date + provenance, review state, status |
| `edges` | upstream → downstream, relation, source (rule/AI), status (proposed/confirmed/rejected), evidence |
| `events` | trigger events (invoice receipt, delivery, …) with dates set by you or by completion |
| `conflicts` | kind, the two clauses, both quotes, status |
| `review_actions` | audit trail (before/after) |
| `llm_cache` · `analysis_cache` | Gemini call memoization, known-good analyses |

Full DDL: [TRD §6](./docs/TRD.md#6-data-model).

---

## 🤖 Gemini API Integration

### Two-Pass Processing

**Pass 1: Obligation extraction** (batches of whole clauses, about 8k characters each)
```python
# Input:  <clause id="C07" ref="6.3">…</clause>  (untrusted data, delimited)
# Output: flat JSON: category per clause; per obligation: actor, modality, action, object,
#         trigger_event, deadline fields, amount, penalty, verbatim evidence_quote, confidence
# Never: page numbers, IDs, or computed dates
```

**Pass 2: Dependency proposals** (one call over a compact obligation list)
```python
# Output: [{ upstream_id, downstream_id, relation, evidence_quote, confidence }]
# relation ∈ must_precede | condition_for | depends_on | may_trigger
# Every proposed link is verified against the source and stays "proposed" until a person confirms it
```

Calls are rate-limited to the free-tier quota and cached in Postgres, so a restarted job replays finished calls for free. The prompts and schemas are in [TRD §8](./docs/TRD.md#8-llm-integration).

### Attention Priority (0–100)

```
Additive points; each factor is shown with its source:
  overdue +35 · due ≤7d +20 · due 8–30d +10 · blocked +30
  penalty +15 · amount stated +5 · category +7/+10
  unresolved date +8 · unspecified day type +5 · unverified evidence +10
  low confidence +7 · in a conflict +12
  potential downstream impact 0–30:
      30 × source strength × Π link weight × 0.6^(hop−1), max over paths, ≤3 hops

Bands: Low 0–24 · Medium 25–49 · High 50–74 · Critical 75–100
```

It is a prioritization aid, not a probability of breach.

---

## 🔐 Security & Privacy

- ✅ API keys only on the server (Render env vars); nothing secret in the frontend bundle
- ✅ CORS locked to the deployed frontend
- ✅ Uploads validated before parsing: size, PDF magic bytes, page cap, encryption, text layer
- ✅ Prompt-injection defenses: hidden-text filtering, delimited untrusted input, strict schemas, server-assigned IDs and pages, quote verification
- ✅ No contract text, quotes, or prompts in logs
- ✅ PDF bytes discarded after ingest; hard delete of a contract and all derived data
- ⚠️ No user accounts in the hackathon build. Use **fictional or public contracts only**: free-tier LLM inputs may be used by the provider.

---

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| [PRD.md](./docs/PRD.md) | Product requirements: problem, users, scope, acceptance criteria, metrics |
| [TRD.md](./docs/TRD.md) | Technical requirements: architecture, data model, API, prompts, algorithms, plan |
| [App-Flow.md](./docs/App-Flow.md) | Screens, user flows, demo flow, states, and copy |

---

## 🧪 Testing

```bash
cd backend
pytest                        # unit, invariant and injection tests (LLM replay mode, no network)
python tests/eval_score.py    # precision/recall against the hand-labelled gold set (target recall ≥ 80%)
```

Key guarantees under test:
- **Zero invented dates:** every due date traces back to contract text, a date you entered, or a completion
- **Correct pages:** every verified obligation's page contains its quote
- **Reproducible risk:** scores equal the sum of visible factors; propagation never compounds

---

## 📦 MVP Checklist

- [ ] PDF upload + validation + page-indexed text extraction
- [ ] Clause segmentation + classification
- [ ] Obligation extraction (actor, action, trigger, deadline rule, amount, penalty, evidence)
- [ ] Evidence verification + derived page references
- [ ] Trigger events + date resolution (no invented dates)
- [ ] Review workflow (confirm / edit / reject + audit trail)
- [ ] Obligation list with filters
- [ ] Explainable attention priority
- [ ] Timeline (dated + "needs trigger date")
- [ ] Obligation graph (React Flow)
- [ ] D1: dependency risk propagation
- [ ] D2: potential conflict detection

---

## 🚀 Roadmap

### Phase 1: Hackathon (24 h)
- MVP + dependency risk propagation + conflict detection
- ICS/CSV export, test email, simulated SMS preview (stretch)

### Phase 2: Stabilize
- User accounts, storage and retention policy, stronger parsing, audit export

### Phase 3: Intelligence & Workflow
- Larger evaluation set, calibrated confidence, conflict review workflow
- Scheduled email/SMS reminders, calendar sync, assignment and ownership
- Contract version comparison, multi-contract dashboard

### Phase 4: Scale & Governance
- Access control, encryption, monitoring, tenant isolation, security review, OCR

---

## 👥 Team

| Role | Responsibility |
|------|----------------|
| **Person A: Backend + AI** | PDF ingest, Gemini extraction, verification, dates, dependency edges, risk engine, API |
| **Person B: Frontend + Demo** | React workspace, React Flow graph, timeline, demo contract, gold-set labels, pitch |

**24-hour plan with checkpoints** (details in [TRD §14](./docs/TRD.md#14-delivery-plan)):
- **H0–1:** Scaffold, API contract, hello-world deploys, verify the Gemini quota
- **H1–4:** Ingest + segmentation · demo contract + UI shell → **CP1 (H4): real clauses in the hosted UI**
- **H4–9:** Extraction, verification, dates · table, source panel, review, timeline → **CP2 (H9): end to end on the hosted URL**
- **H9–13:** Edges, risk, propagation · graph + risk breakdown → **CP3 (H13): MVP + D1 live (if red, stop features)**
- **H13–16:** Conflicts, cache, exports, fallbacks → **Feature freeze (H16)**
- **H16–21.5:** Prompt tuning to ≥ 80% recall, unaided user test, pitch, backup video (staggered sleep)
- **H21.5–24:** Blocker fixes, `demo-safe` tag, rehearse three times

---

## 📄 License

MIT License — see [LICENSE](./LICENSE) file

---

## 🙏 Contributing

This is a hackathon project. For future enhancements:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 💬 Support

- 📧 Email: [your-email@example.com]
- 💻 GitHub Issues: [Report bugs here](https://github.com/ofcourseabhishek/conan/issues)
- 📚 Documentation: [docs/](./docs)

---

## 🎓 Inspirations & References

- **Problem:** Contract obligation complexity & missed deadlines
- **Solution Approach:** Evidence-first obligation extraction + graph-based dependency mapping + explainable priority
- **Innovation:** Dependency propagation + conflict detection + human verification
- **Stack:** One FastAPI service, a structured-output LLM used narrowly, and deterministic code everywhere correctness matters

---

<div align="center">

### Built with ❤️ for the Hackathon

**From Clauses to Consequences** 🔗

[⬆ Back to top](#-conan--ai-powered-contract-obligation-intelligence)

</div>
