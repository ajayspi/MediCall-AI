# RESEARCH: The Medical Information Call Centre (MICC) Process — Global + India

**Purpose** — Ground-truth the real-world MICC process (Medical Information / pharmacovigilance
contact centre) so the PV module spec (`spec-micc-pv-module.md`) reflects regulator and industry
practice, not folklore. Everything cited; PDF URLs are links to the source documents.

**Scope chosen by user**: both artifacts (this research doc + the implementation spec), research net =
Global + India.

**One-line verdict (carries over from the earlier session)**: MediCall-AI already covers the
voice-intake half of an MICC; the pharmacovigilance layer is an incremental sprint (data model +
validation/triage functions + export), **not a rewrite**. This document proves that claim with sources.

---

## 1. What an MICC is

A **Medical Information Call Centre** (also "Medical Information Contact Center", "MI Call Center")
is the pharma-industry function that receives and answers unsolicited enquiries about a company's
medicines from **healthcare professionals (HCPs) and patients/consumers**. Its charter is
three-fold and every call must be classified into one of these buckets on arrival:

| Bucket | What it is | Who owns it inside the company |
|---|---|---|
| **MI** (Medical Information) | Answer factual product questions from **approved content** (SmPC/PI/PIL, standard responses, literature) — dosing, indication, interactions, storage, pregnancy info. Never personal medical advice. | Medical Affairs / Medical Information dept |
| **PQC** (Product Quality Complaint) | Defect, appearance, labelling, packaging, taste/odour, batch problem, suspected contamination. | GMP Quality / QA (complaint file, e.g. US 21 CFR 820.198) |
| **AE/ADR** (Adverse Event/Reaction) | Any untoward medical occurrence suspected of being caused by the product — including special situations: pregnancy/breastfeeding, overdose, misuse/abuse, medication error, off-label use, occupational exposure, lack of efficacy. | Pharmacovigilance / Drug Safety |

The critical process rule: **the call centre is a *collector*, never the *assessor*.** An MI centre
that identifies a possible AE must hand it to PV — with the call source data — within an internal
deadline, and must **not** give the caller a causality judgement or medical advice.

Sources: [PIPA UK MI Guidelines 2022](https://pipaonline.org/wp-content/uploads/2022/02/Pipa-MI-Guideline-Document_Jan-2022_final.pdf);
[ABPI Guidance on collection of drug safety information](https://www.abpi.org.uk/media/vaiiqlzd/guidance-on-collection-drug-safety-information-by-pharmaceutical-companies.pdf);
[HUTCHMED Drug Safety information reporting policy (24-h rule example)](https://www.hutch-med.com/wp-content/uploads/2023/02/Drug-Safety-Information-Reporting_230208.pdf);
[EFPIA HCP Code (2014), sect. 8.01 — no personal medical advice to the public](https://www.efpia.eu/media/25597/hcp-prima-code-amended-25th-august-2014-2.pdf).

---

## 2. Global regulatory & institutional framework (the rules)

### 2.1 ICH guidelines (the harmonised baseline everyone follows)

| Guideline | Role | Key facts |
|---|---|---|
| **ICH E2A** (1995) | Pre-approval definitions + expedited reporting | Seriousness criteria (death, life-threatening, hospitalisation, disability/incapacity, congenital anomaly, important medical event); **7 calendar days** for fatal/life-threatening unexpected ADRs (+8-day complete report), **15 days** for other serious unexpected; minimum criteria (identifiable patient + suspect product + identifiable reporter + event). |
| **ICH E2B(R3)** | Electronic ICSR transmission standard | The E2B(R3) message format with batch/message wrappers (N.1, N.2.r), case-safety-report section (C.1.*), ~130 data elements; **minimum information** for a valid report; code sets/terminologies; retransmission rules. Regulators' gateways (EudraVigilance, FDA ESG, PvPI) ingest this XML. |
| **ICH E2D** (2003) | Post-approval definitions + standards | Seriousness per E2A; **expedited = serious AND unexpected**; minimum data elements = identifiable reporter, identifiable patient, adverse reaction, suspect product; solicited reports treated as "report from study" with causality; general clock **≤15 calendar days**. |
| **ICH E2D(R1)** (Step 4 final **15 Sep 2025**; EU effective 18 Mar 2026) | Revises E2D for modern sources | New definitions: **digital platform, organized data collection system (ODCS), patient support program (PSP), market research program (MRP)**; screening expectations for MAH-owned digital platforms; **day-zero** = receipt of info sufficient to meet minimum criteria; new "important safety findings" section; new E2B(R3) values (C.5.4 study type). |
| **ICH E2C / E2E** | PSUR / PV planning + RMP | Periodic reports; risk management plans (used as guide rails, not needed for the module). |

Sources: [ICH E2A (FDA copy)](https://www.fda.gov/downloads/Drugs/Guidances/ucm073087.pdf);
[ICH E2B(R3) ICSR Implementation Guide (FDA copy)](https://www.fda.gov/media/81904/download);
[ICH E2D 2003](https://database.ich.org/sites/default/files/E2D_Guideline.pdf);
[ICH E2D(R1) Step 4 final 2025](https://database.ich.org/sites/default/files/ICH_E2D(R1)_Step4_FinalGuideline_2025_0819.pdf);
[E2D(R1) FDA guidance](https://www.fda.gov/media/176977/download);
[EMA E2D(R1) page + EU implementation strategy](https://www.ema.europa.eu/en/ich-e2d-post-approval-safety-data-management-scientific-guideline).

### 2.2 EU — EMA GVP Module VI (Rev 2)

- **VI.B.1.1 Unsolicited vs solicited sources**: spontaneous reports, literature, **internet/digital
  media**, PSP/MRP reports, non-interventional studies. MAHs must screen digital platforms **under
  their responsibility** (E2D(R1) refines this obligation).
- **VI.B.2 Validation** (E2B minimum criteria); **VI.B.3 Follow-up** (incl. VI.App.1: follow-up
  process and effectiveness); **VI.B.4 data management**; **VI.B.5 quality management**.
- **VI.B.7.1 Reporting time frames (global section)**: serious valid ICSRs "as soon as possible,
  but in no case later than **15 calendar days**" after initial receipt by any MAH personnel
  (incl. medical reps and **contractors** — that clause is what makes an outsourced call centre an
  in-scope collector). **Day zero** is the day anyone in the company first has the minimum criteria
  — weekends/holidays included; timelines count calendar days.
- **VI.C EU specifics**: EudraVigilance electronic reporting; EU serious = 15 days (no separate EU
  7-day post-marketing clock — the 7-day exists only pre-approval via E2A/SUSAR); important medical
  event (IME) list; specific 15-day reporting for certain **lack-of-therapeutic-efficacy** cases
  (critical conditions, vaccines, contraceptives).
- QPPV (Module I) is the EU accountability holder; MI/PV/QC interactions are part of the PSMF.

Sources: [GVP Module VI Rev 2 (EMA)](https://www.ema.europa.eu/en/documents/regulatory-procedural-guideline/guideline-good-pharmacovigilance-practices-gvp-module-vi-collection-management-submission-reports-suspected-adverse-reactions-medicinal-products-rev-2_en.pdf);
[GVP VI Rev 1 (superseded, incl. VI.C.2.2.7 excerpts)](https://www.ema.europa.eu/en/documents/scientific-guideline/guideline-good-pharmacovigilance-practices-module-vi-management-and-reporting-adverse-reactions-medicinal-products-rev-1-superseded_en.pdf);
[EudraVigilance electronic reporting](https://www.ema.europa.eu/en/human-regulatory-overview/research-development/pharmacovigilance-research-development/eudravigilance/eudravigilance-electronic-reporting).

### 2.3 US — FDA

- **21 CFR 314.80** (post-marketing, NDA holders): **15-day Alert reports** for serious + unexpected
  ADEs, regardless of origin (foreign/domestic), ≤15 calendar days from initial receipt by the
  applicant; follow-ups ≤15 days of new info; non-applicant labelers must forward to the applicant
  ≤5 days; periodic reports 3-monthly ×3y then annually. Electronic submission via FDA ESG.
- **21 CFR 312.32** (IND, pre-approval): SUSARs — unexpected fatal/life-threatening **7 days** + 8-day
  follow-up; all other SUSARs 15 days.
- **Field Alert Reports (FAR)**: certain quality defects (fatal/serious unexpected spread, contamination)
  go to FDA within **3 working days** (see FDA "Report a Product Quality Issue" page).
- MedWatch + FAERS = the collection/surveillance system; MedWatch is the consumer/HCP reporting route.
- Device complaint files (21 CFR 820.198) + nonconforming product/CAPA (820.90/820.100) model the
  PQC side; serious-injury reports 30 days.

Sources: [21 CFR 314.80 (eCFR)](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-D/part-314/section-314.80);
[FDA IND safety reporting (312.32)](https://www.fda.gov/drugs/investigational-new-drug-ind-application/ind-application-reporting-ind-safety-reports);
[FDA Report a Product Quality Issue / FAR](https://www.fda.gov/drugs/surveillance/report-product-quality-issue);
[MedWatch](https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program);
[FDA Nonconforming Product / CAPA slides (820.90/820.198/820.100)](https://www.fda.gov/files/about%20fda/published/Nonconforming-Product---Printable-Slides.pdf).

### 2.4 WHO / UMC (the global data layer)

- **VigiBase** (global ICSR database, >30M cases), **VigiFlow** (national-centre/MAH ICSR capture
  & management, used by India's NRA programme), **VigiLyze** (signal detection; drug-event
  combinations = DECs).
- **WHO-UMC causality categories**: Certain / Probable(Likely) / Possible / Unlikely /
  Conditional(Unclassified) / Unassessable — the standard case-level causality scheme used by
  MAHs and NRAs (and the one the module should model).
- MedDRA (ICH MSSO) is the mandatory AE/indication coding dictionary for regulatory exchange;
  WHODrug for company-agnostic drug coding.

Sources: [WHO-UMC causality assessment](https://www.who.int/docs/default-source/medicines/pharmacovigilance/whocausality-assessment.pdf);
[WHO RMP assessment guidelines (VigiFlow/VigiBase/VigiLyze, DECs, ICSR → PSUR flow)](https://cdn.who.int/media/docs/default-source/medicines/pharmacovigilance/who-rmp-assessment-guidelines-final.pdf);
[MedDRA coding tutorial (MSSO)](https://admin.new.meddra.org/sites/default/files/page/documents_insert/coding_with_meddra_tutorial_tomas_moraleda_2011.pdf).

### 2.5 Industry self-regulation — the MI-collector rules

- **ABPI (UK) guidance on collection of drug safety information**: "Safety information should
  normally be reported **immediately or at least within one business day** of awareness." Minimum
  to forward = **a company product + an AE / special safety situation**; additionally collect
  identifiable patient (age/sex/initials…), event course/outcome. "Safety information **must** be
  sent to the company's PV department — this **may be via the Medical Information department**."
  Source notes (hand-written, AE collection forms) go to PV too; a caller who refuses to give more
  info is documented and notified to PV.
- **HUTCHMED corporate policy (sector example of the same rule)**: all employees report AEs /
  special situations to Drug Safety & PV **within 24 hours of first awareness**; minimum = reporter
  + patient + suspect company product + at least one AE/special situation; no causality
  pre-screening by the collector.
- **PIPA UK MI Guidelines 2022**: out-of-hours process (answerphone, QPPV contact in the message),
  daily reconciliation of the out-of-hours call log **to prevent delayed reporting of AEs and
  PQCs**, QPPV always contactable, contingency plans.
- **EFPIA HCP Code 8.01**: for public callers asking personal medical advice → **advise them to
  consult an HCP** (the "never give personal medical advice" rule).

Sources: [ABPI guidance](https://www.abpi.org.uk/media/vaiiqlzd/guidance-on-collection-drug-safety-information-by-pharmaceutical-companies.pdf);
[HUTCHMED policy](https://www.hutch-med.com/wp-content/uploads/2023/02/Drug-Safety-Information-Reporting_230208.pdf);
[PIPA UK MI Guidelines 2022](https://pipaonline.org/wp-content/uploads/2022/02/Pipa-MI-Guideline-Document_Jan-2022_final.pdf);
[EFPIA HCP Code](https://www.efpia.eu/media/25597/hcp-prima-code-amended-25th-august-2014-2.pdf).

---

## 3. India layer (the jurisdiction MediCall-AI operates in)

### 3.1 Legal base

- **Drugs and Cosmetics Act, 1940 + Rules, 1945** (incl. **Schedule Y** — new drug approval &
  clinical trial data; **Schedule M** — GMP incl. serious-ADR reporting obligation).
- **New Drugs and Clinical Trials (NDCT) Rules, 2019** (GSR 227(E), amended 2022): defines
  "pharmacovigilance"; SAE reporting for clinical trials (14 days per Third Schedule Table 5); the
  post-marketing expectation of a MAH PV system.
- **CDSCO** = national regulator; **NCC-PvPI** (National Coordination Centre — Pharmacovigilance
  Programme of India) at the Indian Pharmacopoeia Commission (IPC), Ghaziabad = the safety hub.

### 3.2 PvPI today (facts from PvPI newsletter)

- 1,200 AMC/**ADR Monitoring Centres**; **1.09 million ICSRs** processed by PvPI up to 31 Mar 2026.
- MAHs submit safety data to PvPI as **E2B-XML** (90+ MAHs monthly); AMCs use **VigiFlow**.
- Consumers/HCPs report directly via toll-free **1800-180-3024** (Mon–Fri 09:00–17:30, English+Hindi)
  or `icsr.nccpvpi@gmail.com`; PvPI runs completeness-scoring of MAH submissions in interactive meetings.

### 3.3 MAH obligations — CDSCO Guidance Document + IPC PV Guidance v2.0 (18 Jan 2024)

- **ICSR reporting**: "All **serious** adverse events must be reported by the MAH within
  **15 calendar days** of receipt of information from any source" to CDSCO via `sae@cdsco.nic.in`.
  Non-serious AEs: **90 calendar days** (CDSCO Guidance Doc 29). Timelines are calendar-day clocks.
- **Minimum criteria for a valid ICSR** (India): identifiable reporter (source), identifiable
  patient, suspect pharmaceutical product, an AE/ADR — i.e. E2B minimum criteria verbatim.
- **Validation before reporting**: all AEs/ADRs must be validated before being reported to
  NCC-PvPI; digital-media screening frequency must permit valid-ICSR reporting within the clock.
- **MedDRA coding** required for AE + indication on ICSRs (both expedited and periodic).
- **PSUR**: every **6 months for the first 2 years**, then **annually for the next 2 years** from
  approval (D&C Act/Rules + NDCT 2019). PSUR submission is a condition for importing new drugs.
- **PVOIC (Pharmacovigilance Officer-in-Charge)** — the MAH-side accountable person, with a
  named alternate; PV system must cover ICSR collection/collation/processing/assessment/reporting/
  follow-up + PSURs + signal detection; QMS chapter + audits & inspections chapter in the guidance.
- Clinical-trial SAEs: 14 days (NDCT Third Schedule) — **out of scope for the voice module**.

### 3.4 Data protection

- **DPDP Act 2023** + rules: consent, purpose limitation, breach notification (72 h).
  MediCall-AI already has G6-Q2 DPDP consent/audit/retention (privacy maintained for the PV layer —
  AE records are health data: minimize PII per E2B practice, honor per-call recording_consent).

Sources: [CDSCO Guidance Document for MAHs (PV)](https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/PSUR_PV_AEFI/Guidance-Document-for-Marketing-Authorization-Holders.pdf);
[IPC PV Guidance for MAHs v2.0 (18.01.2024)](https://www.ipc.gov.in/images/PV_Guidance_Docs_for_MAH_Version_2_as_on_18.01.2024.pdf);
[CDSCO Guidance Doc 29 (non-serious 90 days)](https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/PSUR_PV_AEFI/Guidance_Documentpsur2.pdf);
[NDCT Rules 2019](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/new_DC_rules/NEW%20DRUGS%20AND%20ctrS%20RULE,%202019.pdf);
[PvPI Newsletter Vol.16-1 (2026)](https://ipc.gov.in/images/pvpi/PvPI-Newsletter-Vol.-16-Issue-1-2026-January-to-March-2026.pdf);
[PMC: PvPI overview (helpline, VigiFlow, MAH E2B-XML)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8265409).

---

## 4. The MICC operational process, end-to-end

### 4.1 Intake channels & classification (the front door)

Channels: inbound phone/IVR, email, web forms, fax, letter, **out-of-hours recorded line**,
MAH-owned app/inbox — plus (post E2D(R1)) organised programs (PSP/MRP) and MAH-owned digital
platforms. Every contact is **classified at intake** into MI / PQC / AE / other and routed:

- Suspected AE → PV path (collect minimum info, hand off, no analysis).
- Quality complaint → QA path (product + batch + defect).
- MI question → Medical Affairs path (approved content only).
- The EU/FDA PQC rules explicitly say: complaints that are actually suspected AEs must be routed
  to PV (**EU GMP Ch. 8.7**: "complaints which do not indicate a potential quality defect …
  communicated to the relevant group … such as suspected adverse events").

### 4.2 MI inquiry handling (the approved-content discipline)

- Respond from **approved content**: SmPC / package leaflet / PI, company standard responses,
  published literature, medical-affairs escalation for anything off-label. Responses must be
  substantiated (EFPIA HCP Code 3.02: promotional claims about side-effects must be substantiated).
- **Never give personal medical advice** (EFPIA 8.01; PIPA) — advise consulting an HCP.
- Document the enquiry + response; keep standard-response versions controlled (audit trail).
- Response-time SLAs (see §6); follow-up if incomplete or safety-relevant.

### 4.3 AE handling from an MI/MICC call (the critical handoff)

1. **Recognise**: AE trigger language in the transcript (symptom + product suspicion, special
   situations: pregnancy, overdose, medication error, off-label use, lack of effect…).
2. **Collect minimum information** (E2B/India minimum criteria): identifiable reporter, identifiable
   patient (age/sex/initials suffice), suspect product, event description + onset. Don't
   interrogate beyond what the caller volunteers; if they decline, record and forward anyway
   (ABPI).
3. **Instant internal notification**: ABPI one business day / industry 24-hour norm. The MI desk
   sends the case + raw source data (transcript, notes, AE form) to PV. **No causality statement,
   no diagnosis, no medical advice to the caller.**
4. **Day zero** = when the company (incl. call-centre contractor) first has minimum criteria —
   that's what the India/EU 15-day clock counts from.

### 4.4 PQC handling (quality-complaint path)

Capture: product, **batch/lot number**, expiry, defect description, photos/returns, retain/label
conditions. Investigation: batch record + release testing review, retain-sample inspection,
initial assessment **within 24–48 h** (industry practice), then **CAPA** + batch **disposition**
(use/release, hold, reject, recall per risk). EU GMP Ch. 8 requires documented complaint
procedures, batch-record review for AE investigations, and competent-authority notification of
quality defects. Complaint files satisfy e.g. 21 CFR 820.198; serious safety overlap → FAR if US.

### 4.5 PV case-processing lifecycle (what happens after the handoff)

Per the operational reference ["A day in the life of a pharmacovigilance case processor" (PMC)]:

1. **Receipt & registration** (book-in) with a sender case id;
2. **Duplicate search** (link follow-up to existing case vs create new);
3. **Validation** — E2B minimum criteria (patient, reporter, product, AE) → valid ICSR clock starts;
4. **Triage/priority** — seriousness + expectedness + causality determine expedited vs periodic;
5. **Coding** — AE/indication to **MedDRA**, company drugs to company dictionary, others to WHODrug (WHO DD);
6. **Assessment** — seriousness (E2A criteria), expectedness (vs label), **causality** (WHO-UMC;
   record reporter assessment + company assessment separately);
7. **Narrative** — structured case narrative (templates);
8. **QC / peer review → medical review**;
9. **Submission** — **E2B(R3) XML** to the regulator gateway (India: PvPI/NCC; EU: EudraVigilance;
   US: FDA ESG) within the clock (serious 15 days; India non-serious 90 days; US 15-day alert; EU 15 days);
10. **Follow-up** (GVP VI.App.1) and **closure**; archive (company-defined, e.g. 15 years;
    MediCall retention service governs the call records).

### 4.6 Roles & organisation

MI specialist (approved-content answers) · PV case processor (receipt→submission) · PVOIC (India,
accountable, with alternate) / QPPV (EU) · safety physician (medical review) · QC reviewer ·
QA complaint investigator (PQC/CAPA) · compliance/audit (GVP Module I QMS; India guidance Ch.5
audits & inspections).

---

## 5. Technology stack (what a production MICC/PV operation runs)

- **Voice/telephony layer**: IVR/ACD, CTI screen-pop, recording, multi-language (MediCall's G4
  stack — Exotel/Knowlarity/Twilio + Deepgram/ElevenLabs + LiveKit — maps 1:1 here).
- **MI layer**: CRM + knowledge management holding **approved content** (SmPC/PI, standard
  responses), enquiry-log database, response-version control.
- **Safety layer**: a **safety database** — ArisGlobal **LifeSphere Safety / MultiVigilance**
  (case receipt & AE triage, case management, E2B R3 import/export, signal detection, central
  coding; ReporterX front-end for AE/MI/PQC intake; claims "up to 65% faster PV case intake" via
  GenAI extraction, touchless case processing), **Veeva Safety** (intake→submission, built-in
  gateway connections, semi-annual MedDRA/WHODrug/EDQM dictionary automation, AI narrative
  enhancement), or WHO **VigiFlow** (+VigiBase/VigiLyze) — the pragmatic NRA-side standard India uses.
- **Gateways**: EudraVigilance, FDA ESG, PvPI E2B-XML endpoint; distributions to partners.

---

## 6. KPIs & benchmarks (call-centre + PV)

**Call-centre (industry + US Medicare/government standards):**

| Metric | Typical target / standard | Source |
|---|---|---|
| Average Speed of Answer (ASA) | ~20–30 s (general), ~28 s observed | IBM sample targets; vcc.live; 8x8 |
| Service Level | 80/20 ("80% answered ≤20 s") | IBM, gov standards |
| Abandonment | ≤5% (CMS pass: disconnect rate ≤5%, avg hold ≤2 min) | CMS Part C/D monitoring |
| Average Handle Time (AHT) | ~20 min (ATT ~15 + ACW ~5); measure what's *measured* | IBM sample targets |
| FCR / Quality / CSAT | FCR ~80%, Quality ~90%, CSAT ~85% | IBM sample targets |
| What centres actually measure (ICMI 2024) | abandonment 85%, AHT 84%, quality 77%, ASA 76%, agent productivity 74%; deflection 14%, self-service 13% (least) | ICMI |

**PV-specific (the ones that matter for an MICC):**

- **Internal handoff compliance** — % of AE-bearing (M)IC(C) calls sent to PV within the internal
  SLA (24 h / one business day) — the legal clock starts at the company, so this is the control.
- **Regulatory clock compliance** — % of valid serious ICSRs submitted ≤15 calendar days (India/EU/US
  post-marketing), non-serious ≤90 days (India); 7-day + 8-day follow-up only for pre-approval SUSARs.
- **Completeness score** — E2B minimum criteria + follow-up closure rate (PvPI scores MAHs on this).
- **PQC closure** — investigation initiated ≤24–48 h; CAPA effectiveness; batch disposition recorded.
- **MI quality** — standard-response adherence, response SLA, audit scores, first-contact resolution.

---

## 7. AI/automation in MICC/PV (2025–26 landscape)

- **Intake automation**: GenAI extraction from unstructured sources (ArisGlobal claims ≤65% faster
  PV case intake; "touchless case processing" in production), AI-assisted AE/MI/PQC collection
  front-ends (ReporterX).
- **Processing**: AI narrative drafting/polish (Veeva), MedDRA auto-coding (Burna etc.), AI
  translation for multilingual case processing (LifeSphere).
- **Voice AI**: conversational AE/quality capture on inbound calls is the emerging pattern — exactly
  MediCall-AI's slot (fast, structured intake from natural speech, then hand to a safety database).
- **Caution flags (documented)**: UMC's own 2022 exercise showed **ChatGPT mis-coding MedDRA
  terms**; Roche withdrew the Naranjo algorithm for triage after 2001–2009. Lesson: **keep
  human-in-the-loop for coding/causality/expedited decisions**; use AI for classification +
  extraction + clocks, not for regulatory judgement.
- **E2D(R1) 2025/2026**: regulators codified digital-platform/PSP/MRP sourcing — AI intake must
  treat solicited vs unsolicited distinctly (causality required for solicited ("study") reports).

Sources: [ArisGlobal LifeSphere Safety / MultiVigilance](https://www.arisglobal.com/lifesphere/safety);
[Veeva Safety](https://www.veeva.com/products/safety);
[PubMed review: generative AI for PV](https://pubmed.ncbi.nlm.nih.gov/39238375);
[UMC conference report (Naranjo, case processing)](https://who-umc.org/media/164840/umc-conference-report_2012.pdf);
[UMC workshop report (ChatGPT MedDRA coding test)](https://cdn.who.int/media/docs/default-source/medicines/pharmacovigilance/who-umc-workshop-report_sep-20.pdf).

---

## 8. Regulatory clock cheat-sheet (what the module must compute)

| Jurisdiction | Report type | Clock | Begins |
|---|---|---|---|
| **India** | Serious AE (post-marketing, MAH) | **15 calendar days** | Day zero = company first has minimum criteria (any source, incl. call centre) |
| **India** | Non-serious AE | **90 calendar days** | Same day-zero rule |
| **India** | PSUR | 6-monthly ×2y, annual ×2y | From approval |
| **India** | Clinical-trial SAE | 14 days | (out of module scope) |
| **EU** | Valid serious ICSR (post-marketing) | **15 calendar days** | Day zero (GVP VI.B.7.1 / VI.App.2.7) |
| **EU** | Pre-approval SUSAR fatal/life-threat. | 7 days + 8-day report | First knowledge |
| **US** | Post-marketing 15-day Alert (serious+unexpected) | **15 calendar days** | Initial receipt by applicant (314.80) |
| **US** | Non-applicant labeler → applicant | 5 days | Initial receipt (314.80) |
| **US** | Field Alert Report (quality) | **3 working days** | Quality defect discovery |
| **Internal** | MI/voice collector → PV handoff (industry) | **24 h / 1 business day** | Collector awareness (ABPI; company policy) |

---

## 9. Gap analysis vs MediCall-AI (what exists / what's missing)

**Already built (the voice-intake half of an MICC):** multi-provider India telephony + multi-language
voice agent (G4), triage severity + `escalate` intent + RED/CRITICAL auto-escalation (maps to MI
"urgent → human" and to PQC/AE routing), deterministic clinical guardrails (no diagnosis/dosage
claims — aligns with "no medical advice from the desk"), DPDP consent + compliance-event audit +
retention (G6-Q2), notifications layer (G6-Q8), payments, call/transcript persistence with RLS.

**Missing (the PV layer — the incremental sprint):** no AE/PQC/MI data model (no `adverse_events`,
`quality_complaints`, `medical_inquiries`, `products`, `batches` tables); no E2B minimum-criteria
validator; no ICH E2A/E2D seriousness triage; no **15/90-day** deadline computation for India;
no WHO-UMC causality or MedDRA coding (Phase 2, licensed dictionary); no PSUR help; no E2B(R3) XML
submission (Phase 2; needs PvPI gateway credentials + a validated system); no approved-content MI
knowledge base (Phase 2); no PVOIC/dashboard workflows.

**Phase-1 recommendation (this research supports the spec)**: 3 data tables (AE, PQC, MI) +
4 stdlib service functions (classify, validate-minimum-criteria, seriousness, deadline) + 1 export
route — everything unit-testable with the existing stdlib-only pattern, zero new PyPI deps, no
requirements.txt churn (the livekit/openai Docker blocker stays untouched), India-clock correct,
and Phase 2 (E2B(R3) XML, MedDRA/WHO-UMC, approved-content KB, agent intents) designed in.

---

## 10. Full source list

**Regulatory/guidelines**: ICH E2A · E2B(R3) implementation guide · E2D (2003) · E2D(R1) Step 4 (2025)
(+ FDA copy, EMA page) · EMA GVP VI Rev 2 (Rev 1 superseded) · EudraVigilance e-reporting ·
21 CFR 314.80 (eCFR) · FDA IND 312.32 · FDA FAR page · MedWatch · FDA nonconforming/CAPA slides ·
WHO-UMC causality · WHO RMP assessment guidelines · MedDRA MSSO tutorial · CDSCO PV Guidance ·
IPC PV Guidance v2.0 · CDSCO Doc 29 · NDCT Rules 2019 · PvPI Newsletter Vol.16-1 · PMC PvPI overview.
**Industry**: PIPA UK MI Guidelines 2022 · ABPI safety-info collection guidance · EFPIA HCP Code ·
HUTCHMED safety reporting policy · EU GMP Ch. 8 (complaints/quality defects) · PMC case-processor
lifecycle · ICMI 2025 measurement survey · CMS Part C/D call-center monitoring (2022) · IBM call-
center KPI samples · 8x8 ASA · vcc.live KPIs · ArisGlobal LifeSphere/MultiVigilance · Veeva Safety ·
PubMed gen-AI-in-PV review · UMC conference + workshop reports (AI caution flags).
**Prior-session MICC context (reference)**: globalvigipub.com MICC interview-questions article;
clinevotech.com ICSR-processing blog; Wipro 24/7 MICC case study.

Every URL is embedded inline above under each section.