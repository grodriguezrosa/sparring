# Sparring roadmap

## Phase 0: Prototype for personal use

Goal: be able to do a voice Python interview with myself as soon as possible, even if it's ugly.

- [ ] Backend repository (FastAPI, this one) and a separate frontend repository (Next.js), each with its own `CLAUDE.md`.
- [x] Verify how to call Jev from Python. Yes: `POST /v1/decisions` on Vercel AI Gateway with httpx (`docs/decisions/0001-score-answers-with-jev.md`).
- [x] Endpoint that receives job offer + CV text and returns a structured profile (DeepSeek). `POST /profile`. Tested against real DeepSeek (`deepseek-flash`): correct result with the sample job offer and CV.
- [x] Endpoint that generates the interview plan from the profile. `POST /interview-plan`. Tested end to end against real DeepSeek (job offer + CV → profile → plan, ~25 s for both calls).
- [x] Endpoint that returns the signed URL for ElevenLabs. `POST /voice-session`. Tested against real ElevenLabs (restricted key, agent with auth enabled).
- [ ] Minimal page: paste the job offer, upload the CV, start-interview button.
- [x] Make the voice signed URL single-use (`include_conversation_id=true`): a plain signed URL can open several conversations for one quota unit (found in the ADR 0002 spike).
- [ ] End-to-end voice interview working with DeepSeek as the model, via a custom LLM endpoint in FastAPI (`docs/decisions/0002-deliver-plan-through-custom-llm.md`):
  - [x] `POST /voice-session` receives the plan and stores `conversation_id -> plan`.
  - [x] Streaming in the `LLMClient` port (DeepSeek). Live: first text chunk after 0.7-1.2 s with `deepseek-flash`.
  - [x] `POST /v1/chat/completions` for the agent: bearer auth, conversation lookup, interviewer prompt, SSE. Live with real DeepSeek: opens with the plan intro and the first question in Spanish (~1.4-1.7 s).
  - [x] Configure the real agent (custom LLM URL, secret, stub prompt) with a script (`make agent-config`). Verified end to end with a typed interview through the real agent (`make interview`).
  - [ ] Measure latency with real DeepSeek and voice.

Exit criterion: I complete a full Python interview with my own job offer and CV.

## Phase 1: MVP

Goal: someone else can use it without me being there.

- [ ] Rubric derived from the job offer and scoring of each answer (Jev or alternative).
- [ ] Decide whether to follow up or move on based on the score.
- [ ] Final report: scores per criterion, fit with the offer, mistakes and model answers.
- [ ] Text extraction from PDF and Word CVs.
- [ ] Protection against instructions injected in the CV and the job offer.
- [ ] Choose the cloud for the database (AWS RDS or Google Cloud SQL, free offers; see open decisions in `CLAUDE.md`), in an EU region, with a budget alert.
- [ ] Persistence of sessions and reports in Postgres (repository port + Postgres adapter; Postgres in Docker for local development).
- [ ] Data deletion at the end of the session and privacy notice (GDPR).
- [x] Protect the paid endpoints: ElevenLabs agent limits, access codes (`X-Access-Code`) and a per-code daily voice quota.
- [ ] Move the voice quota from memory to Postgres (needed before running more than one backend instance).
- [ ] Deployment: frontend on Vercel, backend in a container (preferably on the same cloud as the database).
- [ ] Tests for the main endpoints.

Exit criterion: 3 or 4 different people complete an interview and find the report useful.

## Phase 2: Next milestone

- [ ] Multiple job offers and CVs per user, to prepare several processes in parallel.
- [ ] User accounts.
- [ ] Live code editor during the interview (Python exercises).
- [ ] Session history and progress.

## Phase 3: Growth

- [ ] Detection of recurring gaps and suggested review sessions.
- [ ] English and other languages.
- [ ] Pricing model and usage limits.
- [ ] Possible offering for academies and companies.

## Risks to watch

- **Voice latency:** the response must arrive within 1-2 seconds or it stops feeling like an interview.
- **Cost per minute:** voice is the most expensive part; calculate it before setting prices.
- **Score reliability:** compare scores with human judgement before presenting them as final.
- **Privacy:** CVs and transcripts are personal data.
- **Name:** check the domain and trademark (EUIPO) for "Sparring" before investing in branding.
