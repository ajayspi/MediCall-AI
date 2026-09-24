# SPEC: MediCall AI — Multi-Fit Healthcare Platform

## Goal
Build a **healthcare operating system** for India — not just another HMS. A microservices, FHIR-native, multi-tenant platform that starts as a Medical Call Center (voice-first) and expands into a modular healthcare OS supporting: Telemedicine, Revenue Cycle Management (RCM), FHIR Interoperability, with plugin architecture for Lab, Pharmacy, Analytics, Patient Portal.

**Core Differentiator**: Voice-first (call center roots) + FHIR-native + Microservices + India-first (ABDM/DPDP/Hindi+Regional) + Developer platform (APIs/SDKs for others to build on).

## Non-Goals
- No monolithic HMS clone (competitors have 10+ years head start)
- No Supabase (local PostgreSQL + pgvector only)
- No restaurant/order/Square/Stripe code
- No single-tenant deployment as default

## Market Context (from COMPETITOR_ANALYSIS.md)
- **Market**: $26.6B (2026) → $112B (2034), CAGR 20%
- **Competitors**: Monolithic HMS (MocDoc, eHospital, KareXpert), Consumer apps (Practo, 1mg, Apollo), Emerging FHIR (KareXpert, Adrine), **AI Voice Platforms (Hestur, Botsense, Interactly)**
- **Gaps**: Microservices, true FHIR API-first, native RCM/telemedicine, multi-tenant SaaS, multi-language Indian scripts, per-encounter pricing
- **Our Play**: Healthcare OS (platform), not product; Voice-first; FHIR-native; Microservices; India-first
- **Interactly Benchmark**: 3M+ patient interactions, 72% requests resolved without front-desk staff, 56% fewer missed appointments (15%→6.6%), 21.5% more preventive care completion, 150K+ calls/month, HIPAA-ready with BAAs, multilingual (English/Spanish), EHR integrations (Epic/Cerner/Athena), Call Center Automation + Virtual Receptionist product lines

## Architecture: Microservices (API-First, FHIR-Native)

### Framework Choices (Post-Research Integration)

Based on extensive market/framework research (Botsense, Hestur, Bolna, TEN, LiveKit Agents), the following framework decisions are made:

| Framework | Role | Key Reasoning |
|-----------|------|---------------|
| **LiveKit Agents** | **Primary voice agent framework** | 14.3k stars, 4k commits, production-ready, native SIP telephony integration, WebRTC, semantic turn detection, MCP support, Python+Go, active development. Best fit for call center core. |
| **TEN Framework** | **Multimodal alternative** | 11.1k stars, real-time multimodal (video+audio), 194+ examples, Agora video integration, Go+Python, ESP32 deployment. For video consults & future-proofing. |
| **Bolna** | **Open-source voice orchestrator** | 767 stars, Deepgram+OpenAI+ElevenLabs support, self-hostable, JSON-based agent definitions. Good fallback if needing full OSS control. |
| **Hestur** | **Compliance pattern reference** | HIPAA/BAA expertise: BAA signed before PHI flow, PHI isolation in customer infra, ZDR with LLM providers, audit logging (6yr retention), zero-data-retention API agreements. Informs our DPDP/BAA strategy. |
| **Botsense** | **India-market benchmark** | Per-minute pricing (₹5-9/min), 10+ Indian languages (Hindi/Tamil/Telugu/Kannada/Bengali), HM integration (Practo/HealthPlix), 24-72hr setup. Validates India pricing & language approach. |

### Service Boundaries (Domain-Driven)
```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway (Kong/Traefik)               │
│                    Auth | Rate Limit | Routing                   │
├─────────────────────────────────────────────────────────────────┤
│  Voice Gateway      │  Patient API    │  Clinical API           │
│  (Exotel/Knowlarity/ │  (Appointments, │  (Encounters,         │
│   Twilio India)     │   Records, PHR) │   Prescriptions)       │
├─────────────────────────────────────────────────────────────────┤
│  Telemedicine Svc   │  RCM Svc        │  FHIR Hub Svc          │
│  (Video/Voice/Async)│  (Claims, TPA,  │  (FHIR R4 Core,        │
│                     │   Denials, TPA) │   ABDM/NDHM,           │
│                     │                 │   Consent, HIE)        │
├─────────────────────────────────────────────────────────────────┤
│  EHR Adapter Svc    │  Analytics Svc  │  Notification Svc      │
│  (Petpooja/Posist/  │  (Clinical,     │  (SMS, WhatsApp,       │
│   Custom EHR)       │   Operational,  │   Email, Voice,        │
│                     │   Population)   │   Push)                │
├─────────────────────────────────────────────────────────────────┤
│                    Shared Kernel (Auth, Audit, Config, Events)  │
└─────────────────────────────────────────────────────────────────┘
```

### Service Contracts (FHIR R4 + Extensions)
- **Patient API**: `Patient`, `RelatedPerson`, `Coverage`, `Communication` (language)
- **Clinical API**: `Encounter`, `Condition`, `Procedure`, `MedicationRequest`, `ServiceRequest`, `DiagnosticReport`, `Observation`, `CarePlan`
- **Appointment API**: `Appointment`, `Schedule`, `Slot`, `AppointmentResponse`
- **RCM API**: `Claim`, `ClaimResponse`, `CoverageEligibilityRequest`, `PaymentNotice`, `Invoice`, `PaymentReconciliation`
- **FHIR Hub**: `Bundle`, `CapabilityStatement`, `OperationDefinition` (ABDM ops), `Consent`, `Provenance`
- **Telemedicine**: `VideoCall` (custom), `Media` (recording), `Endpoint` (LiveKit/WebRTC)

---

## Use Cases (Prioritized)

### Phase 1: Medical Call Center (Voice-First) — **Current**
- Inbound call → LiveKit Agents SIP trunk → Semantic turn detection → Deepgram STT (5 languages: Hindi, English, Tamil, Telugu, Bengali) → LiteLLM routing → GPT-4.1/medical LLM → ElevenLabs TTS → Triage → Appointment/Prescription/Escalation
- **Languages**: Hindi, English, Tamil, Telugu, Bengali (Deepgram Nova-3 models); extensible to 10+ Indian languages (Botsense benchmark: Kannada, Marathi, Malayalam, Punjabi via Deepgram model customization or ElevenLabs multilingual)
- **Telephony**: LiveKit Agents + SIP integration with Exotel + Knowlarity + Twilio India. LiveKit's telephony stack handles concurrent calls (1,000+), with fallback to Twilio Plivo if needed.
- **Agent Orchestration**: LiveKit Agents `AgentSession` with VAD → STT → LLM → TTS pipeline. Example: `stt=inference.STT("deepgram/nova-3", language="multi")`, `llm=inference.LLM("google/gemma-4-31b-it")`, `tts=inference.TTS("elevenlabs/sonic-3", voice="...)"`.
- **Turn Detection**: LiveKit semantic turn detection, `turn_detection=inference.TurnDetection(model="google/vad-fsmn-vad")`, reduces interruptions.
- **MCP Integration**: Native MCP support in LiveKit Agents for tool/function calling (appointment lookup, prescription check, EHR fetch).
- **Audio Quality**: 16kHz mono, Opus codec, AEC/AGC built into LiveKit media pipeline.
- **Call Recording**: Optional via LiveKit egress, stored in MinIO/S3, with DPDP consent flag per-call.
- **Fallback**: If LiveKit unavailable, Bolna orchestrator (Deepgram+OpenAI+ElevenLabs) as self-hosted alternative.

### Phase 2: Telemedicine/Video Consultations
- **Video Consultations**: LiveKit WebRTC, screen share, file share, recording
- **Async Consultations**: Store-and-forward (images, voice notes, forms)
- **E-Prescriptions**: FHIR `MedicationRequest` + digital signature + pharmacy integration
- **Remote Monitoring**: Vital signs via Bluetooth/IoT, alerts, trends
- **Group Consultations**: MDT, family conferences, group therapy

### Phase 3: Revenue Cycle Management (RCM)
- **Insurance Claims**: FHIR `Claim` submission, `ClaimResponse` tracking
- **TPA Integration**: Cashless/Reimbursement, pre-auth (`CoverageEligibilityRequest`)
- **Denial Management**: Denial codes, appeal workflow, resubmission automation
- **Patient Billing**: Estimates, payment links (Razorpay/PhonePe/Cashfree), payment plans
- **Denial Management**: CARC/RARC codes, root cause analysis, appeal letters

### Phase 4: FHIR Hub / Interoperability (ABDM/NDHM)
- **ABDM Integration**: ABHA creation/linking, HFR/HPR sync, consent artifacts (`Consent` resource)
- **FHIR R4 Core**: Full CRUD + search on all core resources
- **HIE/NHCX**: Health Information Exchange, NHCX gateway for claims
- **Consent Management**: Granular consent (`Consent` resource), audit trail (`Provenance`)
- **Terminology Services**: SNOMED CT, ICD-10, ICD-11, LOINC, RxNorm, ICD-10-CM/PCS

### Phase 5: Plugin Modules (Developer Platform)
| Module | Description | Integration |
|--------|-------------|-------------|
| **Lab/Radiology** | Orders, results, PACS, critical alerts | HL7 v2 / FHIR `ServiceRequest`/`DiagnosticReport` |
| **Pharmacy** | Inventory, dispensing, e-Rx, stock alerts | FHIR `MedicationRequest`/`MedicationDispense` |
| **Inpatient/ADT** | Admissions, beds, wards, ICU, OT, discharge | FHIR `Encounter`, `Location`, `Bed` |
| **OT/Scheduling** | OR booking, surgical checklists, anesthesia | `Procedure`, `Schedule`, `Slot` |
| **Analytics/BI** | Clinical outcomes, operational KPIs, population health | FHIR Bulk Export, OMOP CDM |
| **Patient Portal/PHR** | ABHA-linked PHR, appointments, records, telemedicine | ABHA-linked, ABDM consent |
| **RCM Advanced** | Denial analytics, contract mgmt, payer scorecards | Claims analytics, payer scorecards |

---

## Data Model (FHIR R4 Core + Indian Extensions)

### Core Resources (FHIR R4)
| Resource | Indian Extensions |
|----------|-------------------|
| `Patient` | `abhaId`, `abhaAddress`, `aadhaar` (encrypted), `communication.language` (hi/ta/te/bn/en), `casteCategory`, `rationCard` |
| `Practitioner` | `hprId`, `medicalCouncilRegistration`, `specialization` (NMC), `facilityAffiliation` |
| `Organization` | `hfrId`, `facilityType` (clinic/hospital/lab/pharmacy), `state`, `district`, `bedCount` |
| `Encounter` | `episodeOfCare`, `admissionType` (emergency/OPD/IPD), `dischargeDisposition`, `ayushmanBharatFlag` |
| `Coverage` | `scheme` (PMJAY/ESI/CGHS/State/Private), `beneficiaryId`, `preAuthRequired` |
| `Claim` | `pmjayClaimId`, `tpaId`, `hospitalClaimNumber`, `drgCode`, `packageRate` |

### Indian Code Systems
| System | Use Case |
|--------|----------|
| **ICD-10-CM/PCS** | Diagnosis/Procedure coding |
| **SNOMED CT** | Clinical terminology |
| **ICD-11** | WHO standard (future) |
| **LOINC** | Lab/Radiology observations |
| **RxNorm** | Medication coding |
| **ICD-10-CM/PCS (India)** | India-specific morbidity/mortality |
| **NMC Specialty Codes** | Practitioner specializations |
| **State/District Codes** | Geographic (Census 2011) |

---

## Deployment Model: Hybrid SaaS

| Tier | Target | Deployment | Pricing |
|------|---------|------------|---------|
| **SaaS Starter** | Small clinics (<10 doctors) | Shared multi-tenant | ₹500-800/dr/mo |
| **SaaS Growth** | Multi-specialty clinics (10-50 drs) | Shared multi-tenant + dedicated DB | ₹800-1,200/dr/mo |
| **SaaS Enterprise** | Hospitals (50-200 beds) | Dedicated VPC, dedicated DB | ₹1,200-1,500/dr/mo |
| **On-Premise** | Large hospitals (>200 beds), govt | Customer VPC/on-prem, air-gapped | Custom (₹50L-2Cr setup) |
| **Govt/ABDM** | State/National | GovCloud, air-gapped, ABDM sandbox | Tender-based |

**Pricing Model**: Hybrid — Per-encounter (₹10-15) + Per-provider (₹500-1,500/mo) + Per-bed (₹200-500) for inpatient

---

## Compliance Stack (India-First)

| Regulation | Implementation |
|------------|----------------|
| **ABDM/NDHM** | ABHA creation, HFR/HPR sync, FHIR R4, Consent artifacts, Health ID |
| **DPDP Act 2023** | Consent management, data minimization, breach notification (72hr), DPO, data localization |
| **HIPAA-equivalent** | AES-256 encryption, audit logs (immutable), access controls, BAA-ready |
| **Clinical Establishments Act** | Facility registration, standards, reporting |
| **MTP Act / PCPNDT** | Consent workflows, gestational age tracking, reporting |
| **Mental Healthcare Act** | Advance directives, nominated representative, consent |

---

## Technical Stack (Microservices + Framework Integration)

| Layer | Technology | Framework Choice |
|-------|------------|------------------|
| **API Gateway** | Kong / Traefik (OAuth2/OIDC, rate limiting, JWT) | — |
| **Voice Agent Framework** | **LiveKit Agents** (primary) / TEN Framework (multimodal fallback) / Bolna (OSS alternative) | **LiveKit Agents**: 14.3k stars, production-ready, SIP telephony, WebRTC, turn detection, MCP. **TEN**: 11.1k stars, real-time multimodal, video+audio, Agora. **Bolna**: 767 stars, self-voice orchestrator, Deepgram+OpenAI+ElevenLabs. |
| **Service Mesh** | Istio / Linkerd (mTLS, observability, traffic splitting) | — |
| **Orchestration** | Kubernetes (EKS/GKE/AKS) + Helm/ArgoCD | — |
| **Service Framework** | FastAPI (Python) / Go (high-perf services) | LiveKit Agents Python examples; Go for high-throughput services |
| **Database** | PostgreSQL 16 + pgvector (per-service), TimescaleDB (time-series) | pgvector for embeddings (STT/TTS metadata, clinical notes similarity) |
| **Event Bus** | Kafka (Confluent/Redpanda) — Event sourcing, CQRS | — |
| **Cache** | Redis Cluster (Valkey) | — |
| **Search** | OpenSearch (logs), Elasticsearch (clinical search) | — |
| **Message Queue** | RabbitMQ / NATS (async tasks) | — |
| **Object Storage** | MinIO (S3-compatible) — DICOM, recordings, documents | Call recordings, audio files |
| **Observability** | OpenTelemetry → Grafana/Prometheus/Loki/Tempo | — |
| **CI/CD** | GitHub Actions → ArgoCD → Argo Rollouts (canary) | — |
| **Secrets** | HashiCorp Vault / AWS Secrets Manager | — |
| **IaC** | Terraform + Terragrunt | — |

### Compliance & Security (Informed by Hestur Patterns)

| Regulation | Implementation Pattern (from Hestur) |
|------------|--------------------------------------|
| **DPDP Act 2023** | Consent management at agent level; data minimization in prompts; 72hr breach notification; designated DPO; data stored in India/region-controlled infra |
| **PHI Isolation** | Call transcripts with PHI stored only in customer-controlled infra (not shared SaaS); audio encrypted at rest (AES-256) and in transit (TLS 1.3); no LLM training on PHI (ZDR API agreements) |
| **Audit Logging** | Every call generates immutable log: caller verification, agent actions, data accessed/written to EHR, escalation decision; retained 6yr per DPDP/HIPAA-equivalent; `Provenance` resource tracking |
| **BAA-Ready** | Business Associate Agreement executed with LiveKit/Twilio/Exotel before any PHI flows; zero-data-retention API keys configured in writing; scoped data access at prompt/integration level |
| **Model Selection** | Conservative temperature (near 0) for clinical triage paths; system prompt explicitly states agent role & prohibits out-of-scope responses; escalation phrases hard-coded; red-teaming before go-live |

### Pricing Model (Informed by Botsense Market)

| Model | Rate | Rationale |
|-------|------|-----------|
| **Per-encounter** | ₹10-15/call | Validated by Botsense per-minute pricing (₹5-9/min); typical call 1-2 min |
| **Per-provider/Month** | ₹500-1,500/dr/mo | Standard clinic pricing; covers platform access, uptime, support |
| **Per-bed/Month** | ₹200-500/bd/mo | For inpatient/hospital tiers |
| **SaaS Tiers** | Starter: ₹500/dr/mo → Enterprise: ₹1,500/dr/mo | Hybrid: base subscription + per-encounter usage |
| **Setup Fee** | ₹0 (24-72hr self-serve) / Custom (enterprise) | Botsense model: no monthly commitment, per-minute billing |

---

## Design System (from spec-design-system.md)

### Tokens
- **Colors**: Medical teal primary (`#0d9488`), slate neutrals, semantic red/amber/green
- **Typography**: Inter (Latin) + **Noto Sans Devanagari/Tamil/Telugu/Bengali** (subset via `next/font`, `display: swap`); Indian language script support as CSS vars for `font-family`; `next/font` preload for all 5 scripts; `font-display: swap` for all Indic scripts; fallback chain: Noto Sans → system sans-serif; RTL support via `dir="rtl"` provider for Arabic/Urdu future
- **Spacing**: 4px base, 8px rhythm
- **Radius**: 8px base, 12px cards, 16px modals
- **Shadows**: Subtle, medical clean
- **Motion**: 150ms base, `prefers-reduced-motion`
- **Indian Language Support**: `font-display: swap` for all Indic scripts; fallback chain: Noto Sans → system sans-serif; RTL support via `dir="rtl"` provider for future Arabic/Urdu

### Components (Priority Order)
| Priority | Components |
|----------|------------|
| P0 | Button, Input, Card, Badge, Avatar, Badge, Tooltip, Dropdown, Modal, Drawer |
| P1 | Input, Select, Textarea, Checkbox, Radio, Switch, Table, Pagination, Tabs, Accordion |
| P2 | StatCard, KPICard, ProgressRing, Sparkline, Table, Pagination |
| P3 | CallCard, PatientAvatar, LanguageBadge, SeverityBadge, AudioPlayer, WaveformVisualizer |

### Medical Components (Unique)
- `CallCard` — Live call with waveform, language, duration, actions
- `PatientAvatar` — ABHA-linked, photo, language, critical alerts
- `LanguageBadge` — 5-language indicator with detection confidence
- `SeverityBadge` — Triage colors (red/amber/green/blue)
- `AudioPlayer` / `WaveformVisualizer` — Call recordings, voice notes
- `ABHABadge` — ABHA ID display with verification status

### Layout Primitives
`Box`, `Flex`, `Grid`, `Stack`, `Container`, `Section`, `Sidebar`, `Header`, `Footer`

---

## Website Pages (Marketing)

| Page | Key Sections |
|------|--------------|
| `/` | Hero (voice demo), Value props, Social proof (clinics/hospitals), CTA |
| `/features` | Multi-lang voice, Triage AI, Telemedicine, RCM, FHIR Hub, Security |
| `/integrations` | EHR (Petpooja/Posist/Custom), Payments (Razorpay/PhonePe/Cashfree), Telephony (Exotel/Knowlarity/Twilio), EHR (Petpooja/Posist/Epic/Cerner) |
| `/pricing` | 4 tiers, FAQ, ROI calculator |
| `/docs` | API reference, SDKs, Webhooks, FHIR profiles, ABDM guide |
| `/login` `/signup` | OTP + Password, SSO (Google/Microsoft/ABHA) |
| `/demo` | Live voice demo, simulated call, language selector |

---

## Dashboard Shells (Layouts Only — No Business Logic)

### Clinic Dashboard (7 Tabs)
| Tab | Key Widgets |
|-----|-------------|
| Overview | KPIs (calls, appointments, revenue), charts (volume, revenue, language) |
| Live Calls | Real-time cards (caller, language, duration, sentiment, actions) |
| Triage Queue | Severity-sorted, patient preview, assign doctor, escalate |
| Appointments | Pipeline (Requested→Confirmed→Completed→Cancelled), calendar |
| Prescriptions | Refill queue, doctor approval, pharmacy sync status |
| Patients | Directory (search, filter), ABHA, language, history, consent |
| Analytics | Volume trends, triage outcomes, language dist, no-show, revenue |
| Settings | Voice persona, languages, EHR sync, notifications, users |

### Admin Panel (9 Views)
| View | Key Widgets |
|------|-------------|
| Overview | System KPIs, platform health, MRR, clinic leaderboard |
| Live Monitor | Fleet calls, language filter, audio intercept, alerts |
| Clinics | 487+ directory, health score, EHR status, ABDM sync |
| Doctors | Directory, specialization, language, availability, performance |
| Patients | Directory, ABHA, language pref, consent status, history |
| Revenue | MRR breakdown, consultation fees, RCM COGS, payer mix |
| Billing | Subscription lifecycle, payment failures, Stripe/Razorpay sync |
| Infrastructure | 12 service health cards (telephony, STT, TTS, LLM, DB, FHIR, Payments, etc.) |
| Audit Log | Security trail (CALL, TRIAGE, APPT, RX, PAYMENT, ESCALATION, FHIR) |

---

## File Operations

### DELETE (22 files — Restaurant/Old Scope)
```
backend/supabase_schema.sql
backend/app/db/supabase.py
backend/app/api/orders.py
backend/app/api/restaurants.py
backend/app/api/payments.py
backend/app/api/admin.py
backend/app/models/order.py
backend/app/models/restaurant.py
backend/app/services/pos/base.py
backend/app/services/pos/square.py
backend/app/services/rag.py
backend/app/workers/__init__.py
backend/app/workers/celery_app.py
frontend/src/app/(restaurant)/
frontend/src/app/(admin)/
frontend/src/app/page.tsx
```

### KEEP & Adapt (9 files)
```
backend/main.py              → Medical API routes
backend/app/models/call.py   → Medical call state machine
backend/app/api/voice.py     → Multi-provider telephony
backend/app/services/livekit_agent.py → Medical agent logic
backend/app/services/llm.py  → Medical prompts
backend/app/services/stt.py  → Multi-language STT
backend/app/services/tts.py  → Multi-language TTS
backend/app/db/redis.py      → Keep as-is
```

### CREATE: Design System
```
frontend/src/design-system/
├── tokens/ (colors, typography, spacing, radius, shadows, motion)
├── components/
│   ├── primitives/ (Button, Input, Card, Badge, Avatar, Modal, Drawer, etc.)
│   ├── forms/ (Input, Select, Checkbox, Radio, Switch, Form)
│   ├── data-display/ (Table, StatCard, KPICard, ProgressRing, Sparkline, Table)
│   ├── feedback/ (Modal, Drawer, Toast, Tooltip, Progress, Spinner)
│   ├── navigation/ (Tabs, Breadcrumb, Pagination, Sidebar, Breadcrumb)
│   ├── medical/ (CallCard, PatientAvatar, LanguageBadge, SeverityBadge, AudioPlayer, Waveform)
│   └── index.ts
├── layout/ (Box, Flex, Grid, Container, Sidebar, Header, Footer)
├── hooks/ (useTheme, useMediaQuery, useReducedMotion)
├── providers/ (ThemeProvider, RTLProvider, AuthProvider)
├── utils/ (cn, format, i18n)
└── index.ts
```

### CREATE: Website Pages
```
frontend/src/app/
├── page.tsx                    # Home (hero, voice demo, social proof)
├── features/page.tsx           # Deep-dive features
├── integrations/page.tsx       # EHR, Payments, Telephony, EHR partners
├── pricing/page.tsx            # 4 tiers, FAQ, ROI calculator
├── docs/page.tsx               # API reference, SDKs, FHIR profiles
├── login/page.tsx              # OTP + Password, SSO
├── signup/page.tsx
├── demo/page.tsx               # Interactive voice demo
├── layout.tsx                  # Root layout with providers
├── globals.css                 # Design tokens as CSS vars
└── favicon.ico
```

### CREATE: Dashboard Shells
```
frontend/src/app/(clinic)/
├── layout.tsx                  # Sidebar + header
├── dashboard/page.tsx
├── live-calls/page.tsx
├── triage/page.tsx
├── appointments/page.tsx
├── prescriptions/page.tsx
├── patients/page.tsx
├── analytics/page.tsx
└── settings/page.tsx

frontend/src/app/(admin)/
├── layout.tsx
├── overview/page.tsx
├── live-monitor/page.tsx
├── clinics/page.tsx
├── doctors/page.tsx
├── patients/page.tsx
├── revenue/page.tsx
├── billing/page.tsx
├── infrastructure/page.tsx
├── audit/page.tsx
└── analytics/page.tsx
```

---

## Acceptance Criteria

### Cleanup
- [ ] All 22 restaurant files deleted
- [ ] No Supabase imports remain in codebase
- [ ] No restaurant/order/Square/Stripe references

### Design System
- [ ] Tokens defined as CSS variables in `globals.css`
- [ ] 15+ primitive components built with TypeScript interfaces
- [ ] Medical components: CallCard, PatientAvatar, LanguageBadge, SeverityBadge, AudioPlayer, WaveformVisualizer
- [ ] Dark/light theme via CSS `color-scheme`, RTLProvider for future RTL
- [ ] `next/font` with subset for 4 Indian scripts + Latin
- [ ] Storybook-ready exports, TypeScript strict mode

### Website
- [ ] 8 pages built: Home, Features, Integrations, Pricing, Docs, Login, Signup, Demo
- [ ] Home page: Hero with live voice demo, social proof, CTA
- [ ] Responsive: mobile-first, breakpoints 640/1024/1280
- [ ] WCAG AA, focus-visible, ARIA labels

### Dashboard Shells
- [ ] Clinic dashboard: 7-tab sidebar, responsive, mobile drawer
- [ ] Admin panel: 9-view sidebar, responsive, mobile drawer
- [ ] Both: Dark/light theme, RTLProvider, responsive (mobile drawer)

### Infrastructure
- [ ] `docker-compose.yml`: PostgreSQL + pgvector, Redis, backend, frontend
- [ ] `backend/postgres_schema.sql`: Medical FHIR tables + pgvector
- [ ] `backend/app/db/postgres.py`: Async SQLAlchemy + asyncpg
- [ ] `railway.toml`, `vercel.json`: Updated for MediCall AI

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep (22 files + 50+ new files) | High | Strict deletion first, then phased creation per spec |
| Font loading 4 Indian scripts | Medium | `next/font` subset, `display: swap`, preload |
| RTL readiness | Low | RTLProvider from day 1, test with `dir="rtl"` |
| Component API churn | Medium | Define TypeScript interfaces first, review before implement |
| Microservices complexity | High | Start with modular monolith, extract services incrementally |
| FHIR R4 complexity | High | Use `fhirclient`/`fhirpath` libraries, validate against spec |
| Multi-language voice quality | High | Test with native speakers, fallback chains |

---

## Spec Status
**Status**: READY FOR REVIEW — Awaiting sign-off before cleanup + implementation

**Next on approval**:
1. Delete 22 restaurant files
2. Create `backend/app/db/postgres.py` + `postgres_schema.sql`
3. Build design system tokens + primitives (P0 components)
4. Build marketing website pages
5. Build dashboard shells (clinic + admin)