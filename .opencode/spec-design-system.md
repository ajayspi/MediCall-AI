# SPEC: MediCall AI — Design System & Website

## Goal
Create a complete, production-ready design system and marketing website for **MediCall AI** — an Indian Medical Call Center platform. Clean slate: remove all restaurant-specific code, build medical-first design system, marketing site, and dashboard shells.

## Non-Goals
- No backend business logic implementation (that's separate phases per spec-micc-india.md)
- No Supabase integration (local PostgreSQL only)
- No restaurant/order/Square/Stripe code

## Files to DELETE (Restaurant/old scope)
| File | Reason |
|------|--------|
| `backend/supabase_schema.sql` | Old restaurant schema |
| `backend/app/db/supabase.py` | Supabase client |
| `backend/app/api/orders.py` | Restaurant orders |
| `backend/app/api/restaurants.py` | Restaurant management |
| `backend/app/api/payments.py` | Stripe/Square (replace with Indian gateways) |
| `backend/app/api/admin.py` | Restaurant admin |
| `backend/app/models/order.py` | Restaurant order model |
| `backend/app/models/restaurant.py` | Restaurant model |
| `backend/app/services/pos/base.py` | POS abstraction |
| `backend/app/services/pos/square.py` | Square integration |
| `backend/app/services/rag.py` | Menu RAG |
| `backend/app/workers/__init__.py` | POS/payment tasks |
| `backend/app/workers/celery_app.py` | Restaurant Celery config |
| `frontend/src/app/(restaurant)/` | Restaurant dashboard |
| `frontend/src/app/(admin)/` | Restaurant admin |
| `frontend/src/app/page.tsx` | Restaurant landing page |

## Files to KEEP (Adapt for Medical)
| File | Adaptation |
|------|------------|
| `backend/main.py` | Medical API routes |
| `backend/app/models/call.py` | Medical call state machine |
| `backend/app/api/voice.py` | Multi-provider telephony |
| `backend/app/services/livekit_agent.py` | Medical agent logic |
| `backend/app/services/llm.py` | Medical prompts |
| `backend/app/services/stt.py` | Multi-language STT |
| `backend/app/services/tts.py` | Multi-language TTS |
| `backend/app/db/redis.py` | Keep as-is |
| `backend/app/db/redis.py` | Keep |
| `backend/app/db/redis.py` | Keep |

## New Design System (Fresh)
### Design Tokens
- **Colors**: Medical teal primary, slate neutrals, semantic red/amber/green
- **Typography**: Inter + Noto Sans Devanagari/Tamil/Telugu/Bengali
- **Spacing**: 4px base, 8px rhythm
- **Radius**: 8px base, 12px cards, 16px modals
- **Shadows**: Subtle depth, medical clean aesthetic
- **Motion**: 150ms base, respect prefers-reduced-motion

### Components (Atomic)
- Button (primary, secondary, ghost, danger, sizes)
- Input, Select, Textarea, Checkbox, Radio, Switch
- Card, Badge, Avatar, AvatarGroup, Tooltip, Dropdown
- Table, Pagination, Tabs, Accordion, Modal, Drawer
- StatCard, KPICard, ProgressRing, Sparkline
- CallCard, PatientAvatar, LanguageBadge, SeverityBadge
- AudioPlayer, WaveformVisualizer

### Layout Primitives
- Box, Flex, Grid, Stack, Container, Section, Sidebar, Header, Footer

## Website Pages (Marketing)
| Page | Purpose |
|------|---------|
| `/` | Hero, value props, social proof, CTA |
| `/features` | Deep-dive: multi-lang, triage, appointments, prescriptions, EHR |
| `/integrations` | EHR (Petpooja/Posist), Payments (Razorpay/PhonePe/Cashfree), Telephony |
| `/pricing` | Starter/Growth/Enterprise, FAQ |
| `/docs` | API reference, SDK, webhooks |
| `/login` / `/signup` | Auth pages |
| `/demo` | Interactive voice demo |

## Dashboard Shells (Layouts only)
### Clinic Dashboard (7 tabs)
- Overview, Live Calls, Triage Queue, Appointments, Prescriptions, Patients, Analytics, Settings

### Admin Panel (9 views)
- Overview, Live Monitor, Clinics, Doctors, Patients, Revenue, Billing, Infrastructure, Audit

## Affected Files
### DELETE (22 files)
See list above

### CREATE (Design System)
```
frontend/src/design-system/
├── tokens/
│   ├── colors.ts
│   ├── typography.ts
│   ├── spacing.ts
│   ├── radius.ts
│   ├── shadows.ts
│   ├── motion.ts
│   └── index.ts
├── components/
│   ├── primitives/
│   ├── forms/
│   ├── data-display/
│   ├── feedback/
│   ├── navigation/
│   ├── medical/
│   └── index.ts
├── layout/
│   ├── Box.tsx, Flex.tsx, Grid.tsx, Container.tsx
│   ├── Sidebar.tsx, Header.tsx, Footer.tsx
│   └── index.ts
├── hooks/
│   ├── useTheme.ts, useMediaQuery.ts, useReducedMotion.ts
├── providers/
│   ├── ThemeProvider.tsx, RTLProvider.tsx
├── utils/
│   ├── cn.ts, format.ts, i18n.ts
└── index.ts
```

### CREATE (Website Pages)
```
frontend/src/app/
├── page.tsx                    # Home
├── features/page.tsx
├── integrations/page.tsx
├── pricing/page.tsx
├── docs/page.tsx
├── login/page.tsx
├── signup/page.tsx
├── demo/page.tsx
├── layout.tsx                  # Root layout with providers
├── globals.css                 # Design tokens as CSS vars
└── favicon.ico
```

### CREATE (Dashboard Shells)
```
frontend/src/app/(clinic)/layout.tsx      # Clinic sidebar + header
frontend/src/app/(clinic)/dashboard/page.tsx
frontend/src/app/(clinic)/live-calls/page.tsx
... (6 more clinic tabs)

frontend/src/app/(admin)/layout.tsx       # Admin sidebar + header
frontend/src/app/(admin)/overview/page.tsx
... (8 more admin views)
```

## Acceptance Criteria
- [ ] All restaurant files deleted
- [ ] Design system tokens defined and exported as CSS vars
- [ ] 15+ primitive components built and documented
- [ ] Medical components (CallCard, LanguageBadge, SeverityBadge, PatientAvatar, AudioPlayer)
- [ ] Marketing site: Home, Features, Integrations, Pricing, Docs, Auth, Demo
- [ ] Clinic dashboard shell with 7-tab sidebar
- [ ] Admin panel shell with 9-view sidebar
- [ ] Dark/light theme, RTL support for Arabic/Urdu future
- [ ] CSS variables for all tokens, dark mode via `color-scheme`
- [ ] Responsive: mobile-first, breakpoints at 640/1024/1280
- [ ] Accessibility: WCAG AA, focus visible, ARIA labels
- [ ] Storybook-ready component exports

## Risks
| Risk | Mitigation |
|------|------------|
| Scope creep | Strict file deletion first, then only create what's in spec |
| Font loading for 4 Indian scripts | Use `next/font` with `display: swap`, subset fonts |
| RTL readiness | Build RTLProvider now, test with `dir="rtl"` |
| Component API churn | Define component props interface first, review before implement |

## Spec Status
**Status**: READY FOR REVIEW — Awaiting sign-off before cleanup + implementation