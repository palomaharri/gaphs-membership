# GAPHS membership site (first draft)

The members' platform for the Global Association of Professional Home Stagers. It is built from the
Home Staging Association replica of 14 November 2026 (same code, same features), rebranded to the GAPHS
brand identity, Option 05 (The Roofmark, Sans), and filled with the GAPHS Library.

**This is a draft for the board.** Prices, the Accredited tier, the Terms, Code of Ethics and Privacy Policy
are placeholders until the board decides them (see "Decisions for the board" below).

## Try it on a computer first (optional)
1. Install Python 3.11 or newer.
2. In this folder run: `pip install -r requirements.txt`
3. Run: `ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=choose-a-password python app.py`
4. Open http://localhost:5000
Payments are simulated until Stripe keys are added. Emails are only logged until SMTP is set.

## Put it online (Render)
1. Upload this folder to a new private GitHub repository.
2. In Render choose New > Web Service, pick the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --workers 2 --threads 4 --timeout 120`
5. Add a Disk: mount path `/data`, 1 GB is enough for a test (the five video guides are about 110 MB); 5 GB for the real site.
6. Environment variables:
   - `DATA_DIR` = `/data`
   - `SITE_URL` = the site address (for a test, the onrender.com address Render gives you)
   - `SECRET_KEY` = a long random string
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD` = first admin login (first start only)
   - Leave `EDU_HOST` unset: GAPHS has no second brand.
   - Do not add Stripe or email settings for a test: payments stay simulated and no email is sent.
7. Deploy, log in at /login, open Admin.

### A temporary test on someone else's Render or GitHub account
Use a **new** repository and a **new** web service with its **own** disk and environment variables. Never
point it at another site's repository, disk, database or keys. When the test is over, delete the web service
(and its disk) in Render and the repository in GitHub; nothing else is touched.

## Copy the Library files from Google Drive (once)
The Library is filled in on first start: the course Home Staging for Real Estate Agents (five lessons with
the full course text, the slides and the twelve downloads), the six Atelier Series guides and five video guides.
Covers are in `seed/`; the PDFs and videos stay in Google Drive until you copy them in:
1. In Google Drive, open the GAPHS content folder, Share > General access: *Anyone with the link, Viewer*.
2. Admin > Content > **Import files from Google Drive**. Refresh to see progress (a few minutes).
3. Set the Drive folder back to *Restricted*. The site keeps its own copies and shows them to members and buyers only.

## Connect Stripe (real payments)
1. Stripe > Developers > API keys: copy the Secret key.
2. Developers > Webhooks > Add endpoint: `https://YOUR-SITE/stripe/webhook`; events `checkout.session.completed`,
   `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.paid`.
3. Settings > Billing > Customer portal: turn it on.
4. In Render add `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` (courses can use a second account:
   `STRIPE_COURSES_SECRET_KEY`, `STRIPE_COURSES_WEBHOOK_SECRET`, webhook `/stripe/webhook-courses`). Currency is EUR.
5. Test with keys starting `sk_test_` first.

## Email
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` (e.g. info@gaphs.org). Form notifications go to
`CONTACT_EMAIL`, `ACCREDITATION_NOTIFY_EMAIL`, `ENQUIRY_COPY_EMAIL` (all default to info@gaphs.org).

## Membership
- **Member** (plan key `professional`): trained home stagers. Training course asked at sign-up; a page in the global directory; the GAPHS member logo.
- **Associate** (plan key `member`): industry partners such as real estate agents, developers and photographers. Library and community, no directory page.
- The founding rate and the Accredited tier from the replica are switched off (the code stays, unused).
- The directory is searched by country first (the visitor's country is suggested from their browser language), then by city, name or service.

## Library
- GAPHS content, free for members: the Agents course, the six Atelier Series guides, five video guides and two Entre2portes lessons
  (files copied from Google Drive, see above). Non-members can buy the course and guides (draft prices).
- Introduction to Home Staging, The Home Staging Business Course and Design Elements & Styling are shown as offered by the
  Home Staging Education Centre; their Buy buttons open the course on homestagingeducationcentre.co.uk (`courses_data.py`).

## Decisions for the board (placeholders in this draft)
- **Prices** (Admin > Prices): Member €200 and Associate €160 a year (no monthly option). Shop prices for non-members:
  guides €9.99, the agents course €247 (Admin > Content).
- **Legal texts**: paste the GAPHS Terms, Code of Ethics and Conduct and Privacy Policy in Admin > Terms and wording.
- **Board on the home page**: Sanja and Paloma use the photos from the HSA files, Verena is cropped from the GAPHS Drive (small, a better portrait would help) (`templates/home.html`, "The Board").

## What changed from the HSA replica
- GAPHS brand, Option 05: noir, burnished gold, parchment; Montserrat 200 for headings, Cormorant Garamond 300 italic for supporting lines; the Roofmark logo and app icons.
- GAPHS wording everywhere, emails signed by the GAPHS Board, euros instead of pounds.
- The GAPHS Library replaces the HSA seed content; lessons can now carry text (shown under the video or PDF).
- Admin > Content > Import files from Google Drive (`drive_import.py`).
- Removed: reviews (as the brief intended), the podcast and coaching pages, the Evidence Report, the second brand, the founding rate and the Accredited tier.

## How the site is built
Flask 3, Jinja2, SQLite (one file in `DATA_DIR`), Pillow. See the replica brief for the file map. GAPHS additions:
`drive_import.py` (Drive import), `seed_data.py` and `seed/` (the first Library), `covers.py` and `tools/make_cards.py`
(cover cards), `tools/make_brand.py` (logo and icon files, needs `fonttools` and `cairosvg`).
Rules from the replica still apply: the add-on imports at the end of `admin_views.py` stay last; email bodies passed to
`helpers.email_html` are plain text.
