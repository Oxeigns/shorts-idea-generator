# AI Viral YouTube Shorts Idea Generator

A small, self-hosted studio for original Hindi YouTube Shorts ideas. **Hacker AI** writes
them, every field is validated, and **ElevenLabs** turns an approved script into a Hindi
voiceover you can preview and download.

The dashboard has a light, dark and system theme, a live India clock, 12 categories,
batches of 10 / 20 / 50, saved ideas, full-text search, copy, delete, regenerate and run
history. It is plain HTML, CSS and JavaScript served by FastAPI — no CDN, no build step,
no frontend framework.

> This project intentionally contains **no** YouTube uploading, YouTube OAuth, Telegram bot,
> video rendering, publishing scheduler, deployment automation or Docker configuration.
> It generates ideas and audio only.

`SKILL.md` is the agent-facing manifest for this project. Its YAML frontmatter
(`name`, `description`, `version`, `license`, `author`, `allowed-tools`, and
`metadata.category` / `tags` / `languages` / `requires`) is the source for auto-populated
skill fields; the Markdown body documents the real operating contract.

---

## 1. What it actually does

| Step | Behaviour |
| --- | --- |
| Ask | Sends a strict JSON-only prompt to an OpenAI-compatible `/chat/completions` endpoint, with retries and backoff. |
| Validate | Every idea must have all 12 fields. Hindi must be **Devanagari**. Missing scenes, subtitles or hashtags are rejected with a reason. |
| De-duplicate | Titles within a batch and against the last 200 saved titles are compared with Jaccard similarity; anything ≥ 0.8 is dropped. |
| Persist | Each 10-idea batch is committed as soon as it validates, so a long run makes progress even if a later batch fails. |
| Search | Case-insensitive SQL search across title, hook, Hindi script, category, hashtags and SEO description — over **all** saved ideas, not just the most recent page. |
| Narrate | Sends the cleaned voiceover text to `POST /v1/text-to-speech/{voice_id}` with a speed and emotion preset, then stores the MP3. |
| Delete | Removes an idea from every list and deletes its stored MP3s. The row is soft-deleted (`status = deleted`) so run history stays intact. |

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

## 2. Interface

- **Themes** — dark (default), light and system, chosen from the top bar or the mobile
  tab bar. The choice is stored in a `theme` cookie and applied **server-side**, so the
  first paint already has the right colours and there is no flash. `meta[theme-color]`
  follows the active theme for mobile browser chrome.
- **Live clock** — Asia/Kolkata, `DD-MM-YYYY · HH:MM:SS`, ticking every second in the
  browser from a server-rendered starting value.
- **Studio** — segmented count control (10 / 20 / 50), category chips, Auto switch,
  Generate button with a real progress bar driven by the run counters, and live totals.
- **Idea cards** — title, category / duration / number chips, star and delete, the hook,
  and a collapsible full breakdown (script, scenes, subtitles, SEO, hashtags, music).
- **Voice panel** — voice picker, emotion preset, speed slider from 0.8× to 1.2×, preview
  player and download link. If no ElevenLabs key is configured, the button is genuinely
  disabled and says why instead of failing after a click.
- **History** — every run with requested / generated / rejected counts, status and timing.
- **Config** — encrypted key entry, masked hints (last four characters only), provider
  test buttons, model and voice settings.
- **Mobile** — bottom tab bar (Studio / History / Config / Theme), safe-area padding,
  bottom-sheet delete confirmation, and one-handed 390 px layout.
- **Keyboard** — `/` focuses search, `Esc` clears it.
- **Accessibility** — semantic landmarks, visible focus rings, `aria-live` toasts,
  labelled controls, and reduced-motion support.

All icons are inline SVG and all fonts are the system UI stack, so the app works offline
and behind a strict Content-Security-Policy.

---

## 3. Quick start

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

To make it reachable from another machine, put a TLS reverse proxy in front of it and set
`COOKIE_SECURE=1`, then send `X-Forwarded-Proto: https` so HSTS is emitted. The repo
deliberately does not ship hosting automation.

---

## 4. Configuration

Keys can be entered in the UI (**Config** tab) or supplied as environment variables. Values
saved in the UI are encrypted and take priority over the environment. The browser is only
ever told *whether* a key exists, where it came from, and its last four characters.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HACKER_AI_API_KEY` | — | Inference key starting with `sk-`. Required to generate ideas. |
| `HACKER_AI_BASE_URL` | `https://api.hackerai.sh/v1` | OpenAI-compatible base URL. Must be HTTPS and public. |
| `HACKER_AI_MODEL` | `auto` | Model name, or `auto` to let the gateway choose. |
| `HACKER_AI_ALLOW_INSECURE_BASE_URL` | `0` | Opt-in escape hatch for a local compatible gateway: allows `http://` and private hostnames. Never enable it on a public server. |
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
| `SECURITY_HEADERS` | `1` | Emit CSP, `nosniff`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`. |
| `HSTS` | `1` | Emit HSTS on HTTPS requests only. Set `0` if a proxy already does it. |

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

## 5. How a run behaves

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

### Provider resilience

- Idea generation retries up to **3 attempts** on 408, 409, 425, 429 and 5xx. It honours
  `Retry-After` (capped at 10 s), otherwise backs off exponentially with jitter (capped
  at 6 s). A 400/401/403 is not retried.
- ElevenLabs retries once on 429, 5xx and transport errors.
- Both clients have explicit timeouts; a hung provider cannot pin a worker forever.

### Validation rules

- Script must be ≥ 80 characters and ≥ 35 % Devanagari letters.
- At least 3 subtitle lines, 3 scenes and 3 hashtags.
- Hashtags are normalised to start with `#` and capped at 12.
- Duration is clamped to 15–90 seconds; `m:ss` is parsed.
- Emotion falls back to `energetic` when the model invents a label.

---

## 6. HTTP API

All endpoints except `/api/health`, `/login` and `/static/*` require the session cookie.
Errors are `{"detail": "..."}` and the dashboard prints that text verbatim.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Version, idea count, run count, database kind. |
| `POST` | `/api/ideas/generate` | `{"count": 10, "categories": ["Science"], "auto": false}` |
| `GET` | `/api/runs/{id}` | Run status and counters. |
| `GET` | `/api/ideas?q=&saved=&run=` | Filtered idea list. `q` searches every text field. |
| `POST` | `/api/ideas/{id}/save` | Toggle saved. |
| `DELETE` | `/api/ideas/{id}` | Soft-delete an idea and remove its MP3 files. |
| `POST` | `/api/ideas/{id}/regenerate` | Replace one idea in the same category. |
| `GET` | `/api/voices` | Configured flag, voice list, default ID. |
| `POST` | `/api/ideas/{id}/voice` | `{"voice_id": "...", "emotion": "dramatic", "speed": 1.05}` |
| `GET` | `/voice/{id}.mp3` | Inline audio. |
| `GET` | `/voice/{id}/download` | Attachment download. |
| `POST` | `/api/test/hackerai` | 2+2 inference probe. |
| `POST` | `/api/test/elevenlabs` | Account status + voice count. |
| `GET` | `/api/meta` | Categories, emotions, defaults. |

Rate-limited routes answer `429` with a `Retry-After` header and a readable message.
Limits are per signed-in user **and** IP:

| Route | Limit |
| --- | --- |
| Generate | 6 requests / 5 minutes |
| Voice | 20 requests / 10 minutes |
| Regenerate | 20 requests / 10 minutes |
| Provider probe | 12 requests / minute |

A generated voiceover is stored with its voice ID, model, emotion, speed, character count
and byte size, so you can tell exactly what produced an MP3.

---

## 7. Tests

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check app tests
./.venv/bin/python -m mypy app
```

The suite uses a temporary SQLite database and mocks every network call — no live keys are
needed. 107 tests cover encryption and hint leakage, Devanagari rejection, missing-field
rejection, hashtag/duration normalisation, duplicate similarity, the run lifecycle and
stale-run reaping, 401 behaviour, the ElevenLabs `payment_required` → `402` mapping, the
probe refusing a quote reply, and the hardening work:

- search results beyond the first 200 rows and case-insensitive multi-field matching;
- voiceover totals counting voiceovers, not ideas;
- deterministic latest-voiceover selection;
- generation retry/backoff/`Retry-After` behaviour and no-retry on 400;
- base-URL validation rejecting private, loopback and non-HTTPS targets;
- generate rate limiting returning `429` with `Retry-After`;
- the strict CSP and security headers;
- a guard that templates contain no inline `style`, event handler or `<script>`;
- the theme cookie being applied server-side.

---

## 8. Security notes

- API keys are encrypted with Fernet (key = SHA-256 of `APP_SECRET_KEY`, base64url encoded)
  before storage. The plaintext never leaves the server and is never rendered into HTML.
- Sessions are HMAC-SHA256 signed cookies (`HttpOnly`, `SameSite=Lax`); set
  `COOKIE_SECURE=1` behind HTTPS.
- Login is rate limited to 10 attempts per 5 minutes per IP, and generation / voice /
  regenerate / probes have their own sliding-window limits (see above).
- The CSP is strict: `default-src 'self'`, no inline scripts or styles, `object-src
  'none'`, `base-uri 'none'`, `frame-ancestors 'none'`. Templates are covered by a test
  that fails if an inline style, handler or script is reintroduced.
- Provider base URLs are validated before use: HTTPS only, no userinfo/query/fragment, and
  the hostname must resolve to a public address. This blocks SSRF through the Config form.
  `HACKER_AI_ALLOW_INSECURE_BASE_URL=1` is the explicit, documented exception for local
  gateways.
- All model output is inserted with `textContent` / Jinja auto-escaping; no `|safe`.
- `data/` contains the database, the encryption key and generated MP3s. It is git-ignored
  and must not be published.
- Delete is a soft delete of the idea plus hard deletion of its audio files; foreign keys
  are enforced, so no orphan voiceover rows remain.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No Hacker AI key saved…` | Nothing stored and no env var. | Add an `sk-` key in Config. |
| `Hacker AI replied with text instead of JSON` | Key is not valid for inference (`hsb_`, revoked, wrong product). | Buy an `sk-` inference key; press **Test Hacker AI**. |
| `HTTP 402` / `billing is not active` | ElevenLabs subscription is `past_due`. | Pay the outstanding invoice; Config shows the exact status. |
| `Too many requests…` / `429` | Sliding-window limit hit. | Wait for the `Retry-After` seconds; the limit exists to protect paid quota. |
| `base URL must use https` on Config | The configured base URL is not HTTPS or points at a private host. | Use `https://api.hackerai.sh/v1`; for a local gateway set `HACKER_AI_ALLOW_INSECURE_BASE_URL=1`. |
| `Run #N is still generating` | One run at a time by design. | Wait for it, or let the 20-minute reaper clear a crashed run. |
| Voice list empty | ElevenLabs key missing or rejected. | Save the key, then reload Config. |
| `database is locked` | Multiple writers on SQLite. | The app sets WAL + an 8 s busy timeout; avoid running two servers on one file. |

### Honest limits

- Generation requires a valid `sk-` inference key. Without one the app says so; it never
  falls back to canned ideas.
- Speech generation requires an ElevenLabs plan whose status is `active` or `trialing`.
- The app has no built-in TLS or process supervisor. Run it behind a reverse proxy and a
  service manager, or use `run.sh` for a single foreground process.

---

## 10. Layout

```
app/
  main.py              FastAPI routes, auth, themes, security headers, rate limits
  config.py            environment settings + .env loading
  db.py  models.py     SQLAlchemy engine, Idea / Run / Voiceover / Secret / Setting
  security.py          Fernet encryption, signed cookies, password check
  store.py             encrypted secret resolution + app settings
  netguard.py          base-URL validation / private-address blocking
  ratelimit.py         in-process sliding-window limiter
  timeutil.py          IST conversion helpers
  services/
    hackerai.py        prompt, JSON parsing, per-field validation, retries, 2+2 probe
    elevenlabs.py      voices, account, speech synthesis, retry, error mapping
    ideas.py           batching, worker thread, duplicates, run lifecycle, delete
  templates/           base, dashboard, history, config, login, error
  static/              app.css, app.js (no build step, no CDN)
tests/                 pytest suite with mocked providers
```
