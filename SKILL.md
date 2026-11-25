---
name: shorts-idea-generator
description: Generate original Hindi YouTube Shorts ideas with Hacker AI, validate them field by field, and narrate them as Hindi voiceovers with ElevenLabs. Use when asked for Shorts ideas, viral hooks, Hindi scripts, scene-by-scene visuals, subtitles, hashtags, SEO descriptions, or Hindi TTS audio, or when running, configuring or debugging this FastAPI dashboard.
version: 1.1.0
license: MIT
author: Yash Samrat
allowed-tools: Bash(./run.sh:*) Bash(./bridge.sh:*) Bash(./.venv/bin/python:*) Bash(./.venv/bin/pip install:*) Bash(./.venv/bin/python -m pytest:*) Bash(curl:*) Read Write Edit
metadata:
  category: content-generation
  tags:
    - youtube-shorts
    - hindi
    - hacker-ai
    - elevenlabs
    - tts
    - fastapi
  languages:
    - hi
    - en
  requires:
    - "python>=3.10"
    - "HACKER_AI_API_KEY (sk- inference key) for idea generation"
    - "ELEVENLABS_API_KEY (active plan) for voiceovers"
---

# Shorts Idea Generator

A self-hosted FastAPI dashboard that turns **Hacker AI** into a Hindi YouTube Shorts
strategist, then turns the approved script into a **ElevenLabs** Hindi voiceover.

It generates ideas and audio only. There is deliberately no YouTube upload, no OAuth, no
Telegram bot, no video rendering and no scheduler.

## The one mistake to avoid

There are two different HackerAI credentials and they are **not** interchangeable:

| Credential | Prefix | What it does | Where it goes |
| --- | --- | --- | --- |
| Inference key | `sk-` | Generates ideas via `/chat/completions` | Config page or `HACKER_AI_API_KEY` |
| Bridge token | `hsb_` | Lets HackerAI run commands on your machine | `HACKERAI_BRIDGE_TOKEN`, used by `./bridge.sh` |

An `hsb_` token **cannot generate ideas**. The inference endpoint returns `200` with an
unrelated sentence even when **no** token is sent, so a `200` response proves nothing. That
is why the app's connectivity test asks the model `2+2` and requires the digit `4` — a real
key answers, a bridge token or junk key does not.

Get an `sk-` key at <https://hackerai.sh/pricing>.

## Quick start

```bash
cp .env.example .env     # add keys, set a real ADMIN_PASSWORD
./run.sh                 # creates .venv, installs deps, serves on :8000
```

Sign in, open **Config**, paste the keys, press **Test Hacker AI** and **Test ElevenLabs**,
then **Generate ideas** on the dashboard.

## Generating ideas

1. Choose **10**, **20** or **50** ideas.
2. Pick categories, or enable **Auto mode** to rotate all twelve.
3. Press **Generate ideas**. The request returns immediately; a worker thread generates in
   batches of ten and the dashboard polls progress.

Only one run may be active at a time — a second request returns `409` naming the running
run. Runs stuck in `queued`/`running` for over 20 minutes are reaped as failed so a restart
never blocks new work.

**`generated` can be lower than `requested`.** That is the honest result of validation and
de-duplication, not a bug. Never pad the count to match.

## What every idea contains

Video title · viral hook · full Hindi script · scene-by-scene visuals · ElevenLabs
voiceover text · voice emotion · background music suggestion · subtitle lines · SEO
description · hashtags · estimated duration · audience engagement question.

## Rules the validator enforces

An idea is rejected, not repaired, when it fails these:

- Script ≥ 80 characters and **≥ 35% Devanagari** (`[\u0900-\u097F]`). Romanised "Hindi" is
  rejected because the channel publishes Devanagari.
- At least **3 scenes**, **3 subtitle lines**, **3 hashtags**.
- Hashtags normalised to start with `#`, capped at 12.
- Duration clamped to 15–90 seconds; `m:ss` is parsed.
- Unknown emotion falls back to `energetic`.

Duplicate titles are dropped with Jaccard token similarity **≥ 0.8**, both within the batch
and against the newest 200 active titles.

If the model replies with prose instead of JSON, the run **fails and quotes the reply**.
Never convert prose into ideas or invent content to fill a batch.

## Making a Hindi voiceover

Open an idea → **Hindi voice**, then choose voice, emotion and speed.

- Model: `eleven_multilingual_v2` (multilingual voices read Hindi).
- Speed is clamped to **0.7–1.2** by the app.
- Emotion presets map to ElevenLabs `voice_settings` (stability / style / similarity_boost).
- Text is cleaned before synthesis: markdown, emoji and stage directions removed.

Each MP3 is stored with voice id, model, emotion, speed, character count and byte size, so
output is auditable. **Voice generation spends ElevenLabs characters** — check the Config
page, which shows plan, status and usage.

A `past_due` or otherwise inactive subscription still authenticates but is refused by
ElevenLabs. The app maps that to **HTTP 402** with the provider's sentence verbatim:

> ElevenLabs billing is not active, so voice generation is blocked: Your subscription has a
> failed or incomplete payment. Complete the latest invoice to continue usage.

That is a billing problem, not a bad key. Do not rotate the key over it.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Version, counts, database kind (public). |
| `POST` | `/api/ideas/generate` | `{"count": 10, "categories": ["Science"], "auto": false}` |
| `GET` | `/api/runs/{id}` | Run status and real counters. |
| `GET` | `/api/ideas?q=&saved=&run=` | Filtered ideas; `q` searches all text fields. |
| `POST` | `/api/ideas/{id}/save` | Toggle saved. |
| `DELETE` | `/api/ideas/{id}` | Soft-delete the idea and remove its MP3s. |
| `POST` | `/api/ideas/{id}/regenerate` | Replace one idea in the same category. |
| `GET` | `/api/voices` | Configured flag, voices, default. |
| `POST` | `/api/ideas/{id}/voice` | `{"voice_id": "...", "emotion": "dramatic", "speed": 1.05}` |
| `GET` | `/voice/{id}.mp3` · `/voice/{id}/download` | Inline / attachment. |
| `POST` | `/api/test/hackerai` · `/api/test/elevenlabs` | Connection probes. |

Everything except `/api/health`, `/login` and `/static/*` requires the session cookie.

## Security rules

- API keys are encrypted with Fernet before storage. The browser only receives
  `configured` / `source` / last-4 hint — **never** the value. Do not add an endpoint that
  returns a stored key.
- Sessions are HMAC-signed `HttpOnly` cookies. Login is limited to 10 attempts per 5
  minutes per IP; generation, voice, regenerate and provider probes have their own
  sliding-window limits and answer `429` with `Retry-After`.
- Responses carry a strict CSP (no inline script or style) plus `nosniff`,
  `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy` and HSTS on HTTPS.
- Provider base URLs must be HTTPS and resolve to a public address, blocking SSRF via the
  Config form. `HACKER_AI_ALLOW_INSECURE_BASE_URL=1` is a local-gateway-only exception.
- Never put a real key in the repository, a README, a screenshot or a chat message.
  `tests/test_no_credentials.py` fails the suite if an `sk-`, `hsb_` or ElevenLabs key is
  ever committed.
- Set `COOKIE_SECURE=1` behind HTTPS and change `ADMIN_PASSWORD` before exposing the app.

## Verify the project

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest -q
```

Tests use a temporary SQLite database and mock every network call, so no live keys are
needed. They cover encryption and hint leakage, Devanagari rejection, missing-field
rejection, hashtag and duration normalisation, duplicate similarity, the run lifecycle,
stale-run reaping, 401 behaviour, the `payment_required` → `402` mapping, the probe
rejecting a quote reply, and the credential guard. Hardening tests additionally cover
search past 200 rows, voiceover counts, deterministic voiceover ordering, retry and
`Retry-After` behaviour, SSRF base-URL rejection, rate limiting, security headers, and a
guard against inline styles/handlers/scripts in templates.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No Hacker AI key saved…` | Nothing stored and no env var. | Add an `sk-` key in Config. |
| `replied with text instead of JSON` | Key is not valid for inference (`hsb_`, revoked, wrong product). | Buy an `sk-` key; press **Test Hacker AI**. |
| `HTTP 402` / `billing is not active` | ElevenLabs subscription is `past_due`. | Pay the invoice; Config shows the exact status. |
| `Run #N is still generating` | One run at a time by design. | Wait, or let the 20-minute reaper clear it. |
| Voice list empty | ElevenLabs key missing or rejected. | Save the key, reload Config. |
| `database is locked` | Two servers on one SQLite file. | Run one; WAL and an 8 s busy timeout are already set. |

## Local bridge (optional)

To let HackerAI inspect or edit this project on your own computer, put the bridge token in
`.env` and run `./bridge.sh`. It authenticates and connects to the command relay, then
appears in HackerAI's computer list.

The CLI warns that commands run **directly on the host OS with no isolation**. Only connect
machines you control, and disconnect when finished. Running the bridge inside a container
only exposes that container.
