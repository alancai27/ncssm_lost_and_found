# NCSSM Lost & Found

A lost and found for campus. Two things it does:

1. **Post what you find.** Upload a photo. A vision model looks at it and
   writes down what it is — object, color, brand, stickers, wear, damage —
   so the item is searchable even though nobody typed any of that in.
2. **Find what you lost.** Describe it from memory in plain English. The
   search matches your description against everything in the bin and shows
   you what's probably yours, with the finder's contact info.

The UI is the same design language as [ncssmtime.com](https://ncssmtime.com):
same fonts, tokens, toggle switches, and page structure.

## Run it

```bash
pip install -r requirements.txt
```

```bash
python3 app.py
```

Then open <http://127.0.0.1:5000>.

Browsing and searching work immediately. **Posting requires signing in with
an `@ncssm.edu` Google account**, which needs an OAuth client — see
[Google sign-in](#google-sign-in) below. Until that is set up, posting is
disabled and the app says so.

It runs with no Gemini key — search falls back to keyword matching, and
uploads keep whatever title and note you type.

## Google sign-in

Google is the only sign-in method. Only `@ncssm.edu` accounts can post an item
or mark one returned; browsing and searching stay open unless you set
`REQUIRE_LOGIN_TO_VIEW=1`.

Nothing works until you create an OAuth client, because the client ID and
secret cannot be checked into a repo. It takes about five minutes.

### 1. Create the project

Go to [console.cloud.google.com](https://console.cloud.google.com) and sign
in. **Any Google account works** — personal Gmail is fine; see step 2 for what
that does and does not change. Create a new project, named something like
`ncssm-lost-and-found`.

### 2. Fill in Branding first

**Google Auth Platform → Branding.** Only three fields are actually required:

- **App name** — what students see on the consent screen. "NCSSM Lost & Found".
- **User support email**
- **Developer contact information → Email addresses** — this sits in its own
  section at the *bottom* of the page, separate from the support email, and
  is the field most often left blank. The Audience page stays locked until it
  has a value.

**Do not upload an App logo.** Google's own note on that field: *"After you
upload a logo, you will need to submit your app for verification unless the
app is configured for internal use only or has a publishing status of
Testing."* A logo is the one thing on this page that drags an External app
into the verification queue the moment you publish it — which is exactly the
wait we are avoiding. If you already uploaded one, remove it before
publishing. The consent screen works fine without it.

**Application home page and Application privacy policy link are required to
publish**, even though this app needs no verification. Google's words when you
try:

> Valid app name, support email, homepage url, and privacy policy url are
> required for switching the app to external production mode.

They must be publicly reachable URLs, which means **the app has to be deployed
somewhere before you can publish** — `localhost` will not do. See
[Deploying](#deploying). While you are still on `localhost` and in Testing
status, leave them blank; they only gate the move to production.

Leave these blank regardless:

| Field | Leave empty because |
|---|---|
| Application terms of service link | Not required to publish, and this app has no separate terms. |
| Authorized domains | Only needed once you reference a real domain. `localhost` and `127.0.0.1` are supported for OAuth without being registered, and Google will not accept them here anyway. |
| App logo | Uploading one forces verification when you publish. See above. |

Click **Save** before moving on. The Audience page stays locked until this one
is complete — if it says *"Your app's OAuth configuration is incomplete"*, it
means Branding has not been saved yet.

On a brand-new project Google may show this as a **Get started** wizard that
asks for the app name, support email, audience type, and developer contact in
one flow. Same fields; finish it and both pages are done.

### 3. Set the audience and publish

In the left nav open **Google Auth Platform → Audience**.

**You do not need an @ncssm.edu account to do any of this.** Whoever owns the
Cloud project is unrelated to who is allowed to sign in — the project is just
where the credentials live. A personal Gmail account works fine, and the
`@ncssm.edu` restriction is unaffected, because it is enforced by this app's
own code against the email Google returns, not by Google.

What owning the project from a personal account does cost you is the
**Internal** user type, which is only offered to projects inside the school's
Workspace organization. So:

| | Available from a personal account | 100-user cap | Re-consent every 7 days |
|---|---|---|---|
| Internal | no — needs an @ncssm.edu project | no | no |
| External, **Testing** | yes | **yes, hard cap of 100** | **yes** |
| External, **In production** | yes | no | no |

**Choose External, then press "Publish app" to move it out of Testing.**

Testing status is the trap: it caps you at 100 manually-listed test users and
expires every authorization after seven days. Publishing removes both.

Publishing normally implies Google's verification review, but **this app is
exempt**. Verification is driven by which scopes you request, and this app
only ever asks for `openid email profile` — Google classifies those as
*non-sensitive*, and its help centre states plainly that an app using only
non-sensitive scopes is not required to complete verification. There is
nothing to submit and nothing to wait for. That exemption holds only as long
as the app does not start asking for Gmail, Drive, or Calendar access; it has
no reason to.

One cosmetic caveat: showing a custom app name and logo on Google's consent
screen requires a separate lightweight "brand verification". Skip it and the
consent screen still works, it just looks plainer.

#### If "Publish app" refuses

Read the message carefully; there are two different failures here.

**"Valid app name, support email, homepage url, and privacy policy url are
required..."** — this one is real and actionable. Deploy the app, then put its
public URL and its `/privacy` URL on the Branding page and add the domain under
Authorized domains. See [Deploying](#deploying).

**"Your app's OAuth configuration is incomplete. Please visit the Branding
page..."** with every field already filled — this vaguer one is a known Google
Cloud console bug, reported by many people on freshly created projects, with no
confirmed fix. Do not burn an evening on it.

**It does not block you.** Testing status works completely — add your own
address under **Audience → Test users** and carry on to step 4. Everything in
this app works signed in as a test user. Publishing only matters when you want
the whole school on it, and you can retry it any time.

Cheap things worth one attempt each, in order:

1. Hard-reload the console, or open it in a private window. Stale console
   state causes a share of these.
2. Re-save the Branding page even though it looks complete — some reports say
   the save silently fails to persist.
3. Add the scopes explicitly under **Data Access**: `openid`, `email`,
   `profile`. All three are non-sensitive.
4. Create a fresh project and redo Branding before touching anything else.

If none work, the clean escape is to stop fighting it and go **Internal**
instead: an Internal app has no publishing step at all — it is available to
everyone in the Workspace org immediately, with no cap and no 7-day
re-consent. That needs the project to live inside NCSSM's Google Workspace,
so it means asking whoever administers it. Given this bug, that ask is worth
making sooner rather than later.

### 4. Create the OAuth client

**Google Auth Platform → Clients → Create client.**

- Application type: **Web application**
- Authorized redirect URIs — add **both** of these:

```
http://localhost:5000/auth/callback
http://127.0.0.1:5000/auth/callback
```

Google matches redirect URIs byte for byte, and `localhost` is not the same
string as `127.0.0.1`. Registering both means it works whichever one you type
in the address bar. The app prints these at startup so you can copy them.

Leave *Authorized JavaScript origins* empty — this app never calls Google from
the browser.

When you deploy, come back and add `https://your-domain/auth/callback` too.

### 5. Paste the credentials in

Copy the client ID and client secret into `.env`:

```
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
```

Restart the server. The banner should now read
`Sign-in: Google, @ncssm.edu only`.

### 6. Try it

Open the site, click **Post an item**, and you should land on a page with a
*Continue with Google* button. Signing in with a personal Gmail account is
refused with a message; an `@ncssm.edu` account goes straight through and back
to whatever you were doing.

### How the restriction is actually enforced

The `hd=ncssm.edu` parameter in the authorization URL only pre-filters
Google's account chooser — it is a convenience, and it can be bypassed by
editing the URL. The real check is in `auth.py`, server-side, against the
verified email Google returns in the token exchange, and it also rejects any
account whose `email_verified` claim is false. Nothing trusts the browser.

Sessions are signed cookies, so **`SECRET_KEY` must be a fixed value in
production** — otherwise every restart signs everyone out. If you don't set
one, the app generates one and stores it in a gitignored `.secret_key` file
so local development isn't annoying.

### If it doesn't work

- **`redirect_uri_mismatch`** — the callback URL is not registered on the
  OAuth client. In order of how often each is the culprit:
  1. It was pasted into **Authorized JavaScript origins** instead of
     **Authorized redirect URIs**. Different fields, adjacent on the page.
     Origins take no path; redirect URIs need the full `/auth/callback`.
  2. Only one of `localhost` / `127.0.0.1` was registered and the browser is
     on the other. They are different strings to Google. Register both.
  3. A trailing slash, the wrong port, or `https` instead of `http`.

  Google's error page has a **"see error details"** link that prints the exact
  URI the app sent — compare it character by character with what is
  registered. The app prints the same two URIs every time it starts.

  Changes to an OAuth client can take a few minutes to propagate, so if it
  looks right, wait a moment and retry before changing anything else.
- **"Google rejected the token exchange"** — usually a wrong or rotated
  client secret.
- **"Access blocked: app has not completed verification"** — your app is
  still in **Testing** and that address is not a listed test user. Either add
  it under **Audience → Test users**, or (better) press **Publish app** to
  move to In production, which this app needs no verification for.

## Turn on AI matching

Get a free key from [Google AI Studio](https://aistudio.google.com/apikey),
then:

```bash
export GEMINI_API_KEY="your-key-here"
```

Check that the key and model work before relying on them:

```bash
python3 scripts/check_ai.py
```

That lists the models your key can call and makes one live test request.

Google retires older models, and `ListModels` keeps showing them after they
stop accepting requests — so trust the live test, not the listing. When a
model is retired the error names its replacement; put that in `GEMINI_MODEL`.
Avoid the `-latest` aliases: they drift, and they get overloaded (503) more
often than a pinned version.

**Free-tier cost.** One vision call per uploaded photo, and one text call per
search. Nothing runs on a timer. Gemini's free tier is rate-limited per
minute, so a rush of uploads may need a moment between them — the app tells
you when it hits that limit and still saves the item.

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *(unset)* | OAuth client credentials. Without them, posting is disabled. |
| `ALLOWED_EMAIL_DOMAIN` | `ncssm.edu` | The only domain allowed to post. |
| `OAUTH_REDIRECT_URI` | *(derived)* | Override when the callback URL Flask builds is wrong. |
| `REQUIRE_LOGIN_TO_VIEW` | *(unset)* | `1` also requires sign-in to browse and search. |
| `HTTPS_ONLY` | `0` | `1` marks session cookies Secure. Set this when serving over TLS. |
| `GEMINI_API_KEY` | *(unset)* | Turns on vision + AI matching. Without it, keyword search. |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Which model to call. |
| `SECRET_KEY` | generated into `.secret_key` | **Set a fixed value in production** — this signs session cookies. |
| `DATABASE_URL` | *(unset → SQLite)* | Postgres connection string. Required in production. |
| `S3_BUCKET` / `S3_ENDPOINT_URL` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | *(unset → local disk)* | Object storage for photos. Required in production. |
| `S3_PREFIX` | `uploads/` | Key prefix inside the bucket. |
| `PORT` | `5000` | Port to serve on. |
| `LNF_DB` | `./lostfound.db` | SQLite file location. |
| `FLASK_DEBUG` | *(unset)* | `1` for auto-reload while developing. Never in production. |

These can be exported in your shell, or put in a `.env` file next to
`app.py` — the app reads it on startup. Start from `.env.example`. `.env` is
gitignored; keep it that way, it holds your API key and OAuth secret.

## The campus background

Each campus has its own full-bleed photo. Install one with:

```bash
python3 scripts/set_background.py durham source-images/durham-aerial-snow.jpg
```

```bash
python3 scripts/set_background.py morganton source-images/morganton-aerial.webp
```

`--latest` picks the newest image in `~/Downloads` instead, if you just saved
one out of a browser.

The script resamples to 2400px wide with Lanczos, applies a light unsharp mask,
and writes `static/assets/<campus>-bg.webp`. That matters: a source narrower
than the display gets upscaled by the browser with cheap bilinear filtering,
which reads as blur. Doing it properly ourselves measures about 54% more edge
energy. It cannot invent detail — if you get the full-resolution originals,
replace the files in `source-images/` and re-run, and it will downscale
instead, which is strictly better. The script tells you which it did.

Originals live in `source-images/` so backgrounds can be regenerated later.

### Readability over the photo

White Montserrat over a photograph only works if the photo underneath stays
dark, so each background carries a two-part scrim in `static/main.css` — a
horizontal gradient weighted to the left where all the text sits, plus a
vertical one covering the top and bottom corners where the account bar and nav
links land. Weighting it left means the right side of the photo keeps its
detail instead of being flattened uniformly.

The values are per campus, because photos differ enormously: the Durham snow
aerial is close to the same white as the text and needs far more scrim than the
Morganton dusk shot. They were set by measuring, not by eye — compositing the
scrim over the photo and computing WCAG contrast for white text against the
brightest 2% of each text region. Everything currently sits above 4.5:1; the
Morganton heading was at 2.3:1 before this and was genuinely unreadable.

`scripts/set_background.py` prints the brightness of the region behind the
heading when you install a photo, and says whether the existing scrim is
enough. If it flags a photo as bright, raise the `rgba(...)` alphas on
`.bg-durham` or `.bg-morganton`.

## Deploying

The app needs a host that runs Python. GitHub Pages cannot serve it — it is
static-file only, so there is nowhere to run Flask, keep the database, accept
uploads, or hold the API key and OAuth secret. (Enabling Pages on this repo
just publishes this README as a web page.)

The target is Render's free plan, which runs Python and deploys from GitHub.
**Its filesystem is wiped on every deploy and restart**, so nothing written at
runtime can live on it — hence managed Postgres for the database and object
storage for photos. Both have free tiers that comfortably fit a campus lost
and found.

Locally none of this applies: with no `DATABASE_URL` and no `S3_*` set, the app
uses SQLite and `static/uploads/` exactly as before, and neither `psycopg` nor
`boto3` is even imported.

### 1. Database — Neon

[neon.tech](https://neon.tech) → new project → copy the connection string. It
looks like `postgresql://user:pass@ep-something.neon.tech/dbname`. The free
tier is 0.5 GB, which is far more than this schema will ever need — photos do
not go here.

### 2. Photos — Cloudflare R2

[Cloudflare dashboard](https://dash.cloudflare.com) → R2 → create a bucket.
Then **Manage R2 API Tokens** → create one with read and write. You need four
values:

| Variable | Where it comes from |
|---|---|
| `S3_BUCKET` | the bucket name |
| `S3_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
| `S3_ACCESS_KEY_ID` | from the API token |
| `S3_SECRET_ACCESS_KEY` | from the API token |

R2's free tier is 10 GB, roughly 25,000 photos at the size this app stores.
The bucket can stay **private** — photos are streamed back through the app at
`/uploads/<name>`, so no public bucket or custom domain is needed.

Any S3-compatible service works instead: Backblaze B2, Supabase Storage, MinIO,
or S3 itself. Only the endpoint changes.

### 3. Check the credentials before deploying

```bash
DATABASE_URL='postgresql://...' S3_BUCKET=... S3_ENDPOINT_URL=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... python3 scripts/check_deploy.py
```

This writes a throwaway row and a throwaway object, reads both back, and
deletes them. It is much easier to debug a connection string here than in
Render's build logs.

### 4. Deploy

Render → **New → Blueprint** → pick this repository. It reads `render.yaml`
and creates the service. Then set every `sync: false` variable in the
dashboard: the two above plus `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET`.

The app prints which backends it is using at startup, so check the logs:

```
Database: Postgres (ep-something.neon.tech)
Photos:   object storage (my-bucket at https://....r2.cloudflarestorage.com)
```

If storage is misconfigured the app refuses to start rather than failing on a
student's first upload.

### 5. Point Google at it

You now have a public URL, which is what publishing the OAuth app was waiting
for:

| Google Cloud Console field | Value |
|---|---|
| Branding → Application home page | `https://your-app.onrender.com/` |
| Branding → Application privacy policy link | `https://your-app.onrender.com/privacy` |
| Branding → Authorized domains | `onrender.com` |
| Clients → Authorized redirect URIs | `https://your-app.onrender.com/auth/callback` |

*Add* the redirect URI rather than replacing the localhost ones, so local
development keeps working.

### Remaining free-tier caveat

Free instances sleep after 15 minutes idle, so the first request after a quiet
spell takes 30–60 seconds. Data is no longer at risk — that was the part worth
fixing — but if the delay bothers people, Render's paid tier removes it.

## Demo data

To see the UI populated before anyone has posted anything real:

```bash
python3 scripts/seed_demo.py
```

Those are drawn placeholders, not photos. Remove them with
`python3 scripts/seed_demo.py --clear`.

## How matching works

Vision runs **once per item, at upload time** — never per search. The
description it produces is stored in SQLite as ordinary text.

A search then:

1. Scores every unclaimed item lexically (with a small synonym table, so
   "thermos" finds a flask and "navy" finds dark blue).
2. Sends the top ~30 plus the newest few to the model with the user's
   description, and asks which ones could plausibly be it — each with a
   0-100 score and a one-line reason.
3. Falls back to the keyword ranking if the model is unavailable, rate
   limited, or finds nothing it's confident about.

That keeps the cost at one cheap text call per search regardless of how many
items are in the database, and keeps the whole thing working with no key at
all.

## Layout

```
app.py                  routes
auth.py                 Google sign-in and the @ncssm.edu restriction
db.py                   schema + queries; SQLite locally, Postgres in production
storage.py              photos; local disk locally, S3-compatible in production
ai.py                   vision, ranking, and the keyword fallback
static/main.css         the ncssmtime.com design language, extended
static/app.js           toggles, drag-and-drop, submit states
static/uploads/         posted photos (gitignored)
templates/              Jinja templates
render.yaml             Render deployment blueprint
source-images/          original photos, for regenerating backgrounds
scripts/check_ai.py     verify the API key and list usable models
scripts/check_deploy.py verify Postgres + object storage before deploying
scripts/set_background.py  install a campus photo
scripts/seed_demo.py    placeholder items for development
```

## Before you put this on the internet

It's built to be simple, which means a few things are deliberately missing:

- **Anyone with an @ncssm.edu account can post, and there is no moderation
  queue.** The gate is "is at this school", not "is trusted". Nothing reviews
  uploads before they appear.
- **Browsing is open by default, and contact info is public on the item
  page.** That means a school email address is visible to anyone who opens
  the site, signed in or not. If that's not what you want, either set
  `REQUIRE_LOGIN_TO_VIEW=1`, or tell people to put "front desk" in the
  contact field instead of their email.
- **Claiming is on the honor system.** Any signed-in user can mark any item
  returned; the app records who did it but does not verify ownership. The
  item page tells claimants to describe something the photo doesn't show —
  that check happens between two humans, not in this app.
- **Uploaded photos are served without an access check** at
  `/uploads/<name>`. The names are unguessable random hex, but anyone with a
  URL can open the photo without going through the item page.
- **`/privacy` describes all of the above to users.** If you change what the
  app stores or who can see it, update that page too — it is the thing Google
  and your users are being pointed at.
- **Rotate any key that has been pasted into a chat, screenshot, or commit.**
  Gemini keys are revoked and reissued at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
- Serve it over HTTPS with `HTTPS_ONLY=1`, run it behind a real WSGI server
  (gunicorn, waitress) rather than `app.py` directly, and set a fixed
  `SECRET_KEY`, and add the deployed callback URL to the OAuth client.

Not affiliated with NCSSM.
