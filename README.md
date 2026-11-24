# AI Viral YouTube Shorts Idea Generator

A small, self-hosted dashboard that asks **Hacker AI** for original Hindi YouTube Shorts
ideas, validates every field, and turns the approved script into a **ElevenLabs** Hindi
voiceover you can preview and download.

Dark UI, live India clock, 12 categories, batches of 10 / 20 / 50, saved ideas, search,
copy, regenerate and full run history.

> This project intentionally contains **no** YouTube uploading, YouTube OAuth, Telegram bot,
> video rendering, publishing scheduler, deployment automation or Docker configuration.
> It generates ideas and audio only.

---

## 1. What it actually does

| Step | Behaviour |
| --- | --- |
| Ask | Sends a strict JSON-only prompt to an OpenAI-compatible `/chat/completions` endpoint. |
| Validate | Every idea must have all 12 fields. Hindi must be **Devanagari**. Missing scenes, subtitles or hashtags are rejected with a reason. |
| De-duplicate | Titles within a batch and against the last 200 saved titles are compared with Jaccard similarity; anything ≥ 0.8 is dropped. |
| Persist | Each 10-idea batch is committed as soon as it validates, so a long run makes progress even if a later batch fails. |
| Narrate | Sends the cleaned voiceover text to `POST /v1/text-to-speech/{voice_id}` with a speed and emotion preset, then stores the MP3. |

Nothing is templated and nothing is faked. If the model returns prose instead of JSON, the
run **fails with the model's own words quoted** instead of inventing ideas.

### The 12 fields per idea

Video title, viral hook, full Hindi script, scene-by-scene visuals, ElevenLabs voiceover
text, voice emotion, background music suggestion, subtitle lines, SEO description,
hashtags, estimated duration, audience engagement question.

### Categories

Amazing Facts · Psychology Facts · Mystery · Science · Technology & AI · Motivation ·
Horror Stories · History · Space & Universe · Human Behaviour · Interesting Discoveries ·
Emotional Stories — pick several, or switch on **Auto mode** to rotate through all twelve.

---

## 2. Quick start

```bash
git clone <your-repo-url> shorts-idea-generator
cd shorts-idea-generator
cp .env.example .env          # then edit .env
./run.sh                      # creates .venv, installs deps, starts on :8000
```

Open <http://127.0.0.1:8000>, sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`
(defaults `admin` / `change-this-password` — change them), then open **Config** and paste
your keys. Alternatively set them in `.env` before starting.

Manual start without the script:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Python 3.10+ is required (developed and tested on CPython 3.14).

---

## 3. Configuration

Keys can be entered in the UI (**Config** tab) or supplied as environment variables. Values
saved in the UI are encrypted and take priority over the environment. The browser is only
ever told *whether* a key exists, where it came from, and its last four characters.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HACKER_AI_API_KEY` | — | Inference key starting with `sk-`. Required to generate ideas. |
| `HACKER_AI_BASE_URL` | `https://api.hackerai.sh/v1` | OpenAI-compatible base URL. |
| `HACKER_AI_MODEL` | `auto` | Model name, or `auto` to let the gateway choose. |
| `ELEVENLABS_API_KEY` | — | Used only for speech synthesis and voice listing. |
| `ELEVENLABS_VOICE_ID` | `CwhRBWXzGAHq8TQ4Fs17` | Default voice (Roger, male, American). |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | Must be a multilingual model for Hindi. |
| `APP_SECRET_KEY` | auto-generated | Signs session cookies and derives the Fernet key. If unset, `data/secret.key` (0600) is created once. |
| `ADMIN_USERNAME` | `admin` | Login user. |
| `ADMIN_PASSWORD` | `change-this-password` | Login password — change it. |
| `SESSION_DAYS` | `7` | Cookie lifetime. |
| `COOKIE_SECURE` | `0` | Set to `1` when served over HTTPS. |
| `DATA_DIR` | `./data` | SQLite database, encryption key and MP3 files. |
| `DATABASE_URL` | `sqlite:///data/ideas.db` | Any SQLAlchemy URL. |
| `REQUEST_TIMEOUT` | `90` | Seconds for provider calls. |
| `ALLOW_ENV_SECRETS` | `1` | Allow falling back to environment keys. |

### Getting a working Hacker AI key

Buy a key at <https://hackerai.sh/pricing>; it is emailed to you and starts with `sk-`.
Then open **Config → Test Hacker AI**.

The test asks the model `2+2` and requires the digit `4`. This matters: the gateway has
been observed returning **HTTP 200 with an unrelated motivational quote** for a missing,
junk, or non-inference credential, so a `200` proves nothing on its own. An `hsb_` token
from `npx @hackerai/local` is a local-bridge credential and will fail this test.

### HackerAI local bridge (optional, separate from the API key)

There are two different HackerAI credentials and they are not interchangeable:

| Credential | Prefix | What it does | Used by |
| --- | --- | --- | --- |
| Inference API key | `sk-` | Generates ideas through `/chat/completions` | the app |
| Bridge token | `hsb_` | Lets HackerAI run commands on the machine running the bridge | `./bridge.sh` |

An `hsb_` token is **not** a model credential. It will not generate ideas, and the
inference endpoint answers unrelated prose when given one (or no token at all), so it
must never be used as `HACKER_AI_API_KEY`.

The bridge is useful when you want HackerAI to inspect or edit this project on your own
computer. Store the token in `.env` (git-ignored) and start it:

```bash
# .env
HACKERAI_BRIDGE_TOKEN=hsb_...
HACKERAI_BRIDGE_NAME="Home PC"   # optional, shown in the computer list
```

```bash
./bridge.sh
```

It prints `✓ Authenticated`, then `✓ Connected to command relay`, and stays connected
until you press Ctrl+C. In HackerAI, pick that computer from the list.

> The CLI's own warning: commands run directly on the host OS with **no isolation**.
> Only connect machines you control, and disconnect when you are done. The script
> refuses an `sk-` value by mistake, never echoes the token, and the repository has a
> test (`tests/test_no_credentials.py`) that fails if a real token is ever committed.

Run the bridge on the machine you want controlled. Starting it inside a container only
gives remote access to that container.

### Hindi voices on ElevenLabs

Any multilingual voice reads Hindi. Voice list and default ID come from your own library;
the dashboard also shows **plan, status and character usage**. If the subscription status
is not `active`/`trialing` (for example `past_due`), the key still authenticates but speech
generation is refused — the app surfaces that as a 402 with a plain-language message
instead of a generic failure.

---

## 4. How a run behaves

1. `POST /api/ideas/generate` creates a `queued` run and returns immediately. Only one run
   can be active at a time; a second request gets `409` naming the running run.
2. A worker thread generates `min(10, remaining)` ideas per API call, validates them,
   drops duplicates, commits, and updates the run counters.
3. The dashboard polls `GET /api/runs/{id}` every 1.5 s and shows real accepted/rejected
   counts — not a fake animation.
4. Runs stuck in `queued`/`running` for more than 20 minutes are reaped as failed on the
   next page load, so a server restart never blocks new work forever.
5. `generated` can be **lower** than `requested`. That is the honest outcome of rejection
   and de-duplication, and the UI says so.

### Validation rules

- Script must be ≥ 80 characters and ≥ 35 % Devanagari letters.
- At least 3 subtitle lines, 3 scenes and 3 hashtags.
- Hashtags are normalised to start with `#` and capped at 12.
- Duration is clamped to 15–90 seconds; `m:ss` is parsed.
- Emotion falls back to `energetic` when the model invents a label.

---

## 5. HTTP API

All endpoints except `/api/health`, `/login` and `/static/*` require the session cookie.
Errors are `{"detail": "..."}` and the dashboard prints that text verbatim.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Version, idea count, run count, database kind. |
| `POST` | `/api/ideas/generate` | `{"count": 10, "categories": ["Science"], "auto": false}` |
| `GET` | `/api/runs/{id}` | Run status and counters. |
| `GET` | `/api/ideas?q=&saved=&run=` | Filtered idea list. |
| `POST` | `/api/ideas/{id}/save` | Toggle saved. |
| `POST` | `/api/ideas/{id}/regenerate` | Replace one idea in the same category. |
| `GET` | `/api/voices` | Configured flag, voice list, default ID. |
| `POST` | `/api/ideas/{id}/voice` | `{"voice_id": "...", "emotion": "dramatic", "speed": 1.05}` |
| `GET` | `/voice/{id}.mp3` | Inline audio. |
| `GET` | `/voice/{id}/download` | Attachment download. |
| `POST` | `/api/test/hackerai` | 2+2 inference probe. |
| `POST` | `/api/test/elevenlabs` | Account status + voice count. |
| `GET` | `/api/meta` | Categories, emotions, defaults. |

A generated voiceover is stored with its voice ID, model, emotion, speed, character count
and byte size, so you can tell exactly what produced an MP3.

---

## 6. Tests

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest -q
```

The suite uses a temporary SQLite database and mocks every network call — no live keys are
needed. It covers encryption and hint leakage, Devanagari rejection, missing-field
rejection, hashtag/duration normalisation, duplicate similarity, the run lifecycle and
stale-run reaping, 401 behaviour, the ElevenLabs `payment_required` → `402` mapping, and
the probe refusing a quote reply.

---

## 7. Security notes

- API keys are encrypted with Fernet (key = SHA-256 of `APP_SECRET_KEY`, base64url encoded)
  before storage. The plaintext never leaves the server and is never rendered into HTML.
- Sessions are HMAC-SHA256 signed cookies (`HttpOnly`, `SameSite=Lax`); set
  `COOKIE_SECURE=1` behind HTTPS.
- Login is rate limited to 10 attempts per 5 minutes per IP.
- All model output is inserted with `textContent` / Jinja auto-escaping; no `|safe`.
- `data/` contains the database, the encryption key and generated MP3s. It is git-ignored
  and must not be published.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No Hacker AI key saved…` | Nothing stored and no env var. | Add an `sk-` key in Config. |
| `Hacker AI replied with text instead of JSON` | Key is not valid for inference (`hsb_`, revoked, wrong product). | Buy an `sk-` inference key; press **Test Hacker AI**. |
| `HTTP 402` / `billing is not active` | ElevenLabs subscription is `past_due`. | Pay the outstanding invoice; Config shows the exact status. |
| `Run #N is still generating` | One run at a time by design. | Wait for it, or let the 20-minute reaper clear a crashed run. |
| Voice list empty | ElevenLabs key missing or rejected. | Save the key, then reload Config. |
| `database is locked` | Multiple writers on SQLite. | The app sets WAL + an 8 s busy timeout; avoid running two servers on one file. |

---

## 9. Layout

```
app/
  main.py              FastAPI routes, auth, Jinja wiring
  config.py            environment settings + .env loading
  db.py  models.py     SQLAlchemy engine, Idea / Run / Voiceover / Secret / Setting
  security.py          Fernet encryption, signed cookies, password check
  store.py             encrypted secret resolution + app settings
  timeutil.py          IST conversion helpers
  services/
    hackerai.py        prompt, JSON parsing, per-field validation, 2+2 probe
    elevenlabs.py      voices, account, speech synthesis, error mapping
    ideas.py           batching, worker thread, duplicates, run lifecycle
  templates/           base, dashboard, history, config, login
  static/              app.css, app.js (no build step, no CDN)
tests/                 pytest suite with mocked providers
```
