# BayBot Dynamics - Modern Website Redesign

A polished, professional, and fully responsive redesign of the BayBot Dynamics website, preserving the original brand identity while enhancing user experience and modern web standards.

## Features

### Design & UX
- **Modern, Clean Interface**: Premium design with improved typography, spacing, and visual hierarchy
- **Fully Responsive**: Optimized for all devices (desktop, tablet, mobile)
- **Smooth Animations**: Subtle, professional animations that enhance without distracting
- **Intuitive Navigation**: Clear menu structure with dropdown support
- **Accessibility**: WCAG-compliant with semantic HTML, ARIA labels, and keyboard navigation

### Technical Highlights
- **Pure HTML/CSS/JavaScript**: No frameworks required, fast loading times
- **Original Media Preserved**: All images and videos from the original site are maintained in their exact form
- **SEO Optimized**: Proper meta tags, structured data, semantic markup
- **Performance**: Optimized images, lazy loading, debounced scroll events
- **Cross-browser Compatible**: Works on all modern browsers

### Sections
1. **Hero Section**: Engaging opening with clear value proposition and CTAs
2. **About Section**: Company overview with visual storytelling
3. **Industries Section**: Service offerings across 6 key sectors
4. **Why Choose Us**: Feature highlights with benefits
5. **FAQ Section**: Common questions with accordion interface
6. **Contact Form**: Integrated contact form with validation
7. **Footer**: Complete site navigation and contact information

## File Structure

```
baybotdynamics-redesign/
├── index.html          # Home page
├── about.html          # About page
├── industries.html     # Six industry sections (#healthcare, #warehouse, ...)
├── products.html       # 14 models in 4 sections (#cleaning, #delivery, ...)
├── product-*.html      # One generated page per model (video + details)
├── contact.html        # Contact details + enquiry form
├── schedule-demo.html  # Demo request form (online or in-person)
├── parts-store.html    # Part categories + quote request form
├── blog.html           # Empty state until posts exist
├── sustainability.html # Efficiency and environmental approach
├── terms.html          # DRAFT outline only - needs legal review, noindex
├── 404.html            # Error page (self-contained, no external assets)
├── styles.css          # Complete CSS with responsive design
├── script.js           # Interactive JavaScript functionality
├── robots.txt          # Crawler directives
├── .htaccess           # Apache config (GoDaddy Linux/cPanel + generic Apache)
├── web.config          # IIS config (GoDaddy Windows/Plesk)
├── assets/
│   ├── favicon.ico
│   └── images/         # All brand imagery, served from this site
└── README.md           # This file
```

## Usage

### Local Development
Use a local server rather than opening the file directly. Under `file://`
some browsers restrict requests, and the extensionless URLs below don't apply.

```bash
python3 -m http.server 8000
# Then visit http://localhost:8000
```

## Deployment

The site is a static bundle with no build step and no hardcoded domain, so the
same files work on any host and any domain. Upload the folder contents and the
site works — including `.htaccess`, `web.config`, and the `assets/` directory.

### Domain portability

Nothing in the markup points at a specific hostname:

- **Images, CSS, JS, favicon** use document-relative paths (`assets/images/…`),
  so they resolve against whatever domain serves the page, including a
  subfolder deploy such as `example.com/baybot/`.
- **Canonical tags** are relative (`href="./"`), which the HTML spec and Google
  both resolve against the page's own URL. No per-domain edit needed.
- **`og:url` is intentionally omitted.** Social scrapers fall back to the URL
  they fetched, which is always correct. A hardcoded value would be wrong on
  every domain but one.
- **`.htaccess` and `web.config`** derive the hostname from `%{HTTP_HOST}`
  rather than naming a domain, so HTTPS redirects follow the site.

### GoDaddy Linux hosting (cPanel) — most common

1. cPanel → **File Manager** → open `public_html`.
2. Upload the contents of this folder — not the folder itself — into
   `public_html`, so `index.html` sits at the root.
3. Enable **Show Hidden Files** in File Manager settings, and confirm
   `.htaccess` uploaded. It is easy to miss and it carries the HTTPS redirect
   and the extensionless URLs.
4. Turn on the free SSL certificate under **Security → SSL**.

### GoDaddy Windows hosting (Plesk)

Upload to `httpdocs` instead. `web.config` applies and `.htaccess` is ignored;
leaving both in place is harmless.

### GoDaddy Website Builder / Airo

This one will not work. That product does not accept uploaded HTML, so the site
needs a hosting plan (Linux or Windows above) rather than the site builder.

### Other hosts

Netlify, Vercel, Cloudflare Pages, GitHub Pages, S3 and any generic Apache or
nginx host serve this as-is by pointing them at this directory. On those hosts
`.htaccess` and `web.config` are ignored; the `.html` URLs still work, and
most of these platforms strip `.html` automatically.

nginx has no per-directory config file, so the extensionless URLs need a
server-block entry:

```nginx
location / {
    try_files $uri $uri.html $uri/ /404.html;
}
```

### Robot models and product pages

Models live in `data/models.json`. `tools/build_models.py` turns them into
the cards on `products.html` and one page per model, `product-<id>.html`,
with the YouTube video, overview, features, functions and specifications.
Everything is plain HTML, so it needs no JavaScript and is indexed by search
engines. Clicking a robot's name or photo on the products page opens its page.

**Adding a model that's already in the live CMS** (the fastest route):

```bash
python3 tools/import_from_cms.py --list                      # see what's there
python3 tools/import_from_cms.py --add "PUDU X1" --category cleaning
python3 tools/build_models.py
```

**Refreshing every model from the CMS** (after content changes there):

```bash
python3 tools/import_from_cms.py
python3 tools/build_models.py
```

The importer reads the same public API the live site uses
(`/api/cms/bot-list`, `/api/cms/bot-details/<slug>`). It copies the video,
title, summary, overview, features, functions (images downloaded unmodified
into `assets/images/models/functions/`), genuine specifications and industries.
It never changes `name`, `category`, `description`, `image`, `badge`,
`tagline`, `specs` or `brochure`, so hand edits to those survive a refresh.
It filters out and reports:

- the CMS's placeholder paragraph ("committed to revolutionizing the
  facilities, EVS, and janitorial fields"), which fills several description
  and specification fields, including one copy naming another company;
- stray editor text such as a trailing "test";
- any humanoid robot (below).

**Adding a model by hand** (not in the CMS): put the photo in
`assets/images/models/`, add an entry to `data/models.json`, then run
`python3 tools/build_models.py`. Only `id` (lowercase-with-hyphens, unique),
`name`, `category` and `description` are required. `category` must be one of
`cleaning`, `delivery`, `industrial` or `quadruped`. Optional fields:

| Field | Shown on | Format |
|---|---|---|
| `image`, `image_alt` | card and page | path under `assets/images/models/` |
| `badge`, `tagline` | card | short text |
| `video` | page | YouTube ID or any YouTube URL |
| `title` | page | subtitle under the name |
| `summary_html`, `overview_html` | page | HTML (sanitised on build) |
| `industries` | page | list of names |
| `features` | page | strings, or `{name, html}` |
| `functions` | page | `{title, html, image}` |
| `spec_sections`, `details` | page | `{title, html}` |
| `specs` | page | `[["Runtime", "6 h"], ...]` table |
| `brochure` | page | PDF path, adds a download button |

HTML fields are reduced to `p`, `ul`, `ol`, `li`, `strong`, `em` and `br`
with every attribute removed, so CMS content can't inject scripts or break
the layout. Videos use a click-to-load player: only a thumbnail loads until
the visitor presses play, then YouTube's privacy-enhanced (no-cookie) player.

The build validates everything and writes nothing if there's a problem: a
missing field, duplicate id, unknown category, bad video link or missing
image. `--check` reports whether the pages are current without changing
them. Don't hand-edit `product-*.html` or the `MODELS:…` blocks in
`products.html`; they're regenerated on every build, and pages for removed
models are deleted automatically.

#### Excluded: humanoid robots

Humanoid robots are not approved for sale in the USA, so both scripts refuse
any model described as humanoid, checked across every text field, not only
the name. Currently excluded: **PUDU D7** (semi-humanoid), **PUDU D9**
(humanoid) and **FlashBot Arm**, whose CMS overview classifies it as a
semi-humanoid. The Lovable project and the live CMS still list all three.

`data/` and `tools/` are build inputs, not site content. They're safe to
upload, and `.htaccess` / `web.config` hide them from visitors, but you can
also leave them out of the upload entirely.

### Forms

The contact, demo, parts and homepage forms all share one handler in
`script.js`. With no configuration, a submission opens the visitor's email
app with the message pre-filled to `info@baybotdynamics.com`. That keeps
enquiries from being lost, but some visitors won't have a mail app set up.

To have forms submit in the page instead, create a form endpoint (Formspree,
Web3Forms or similar; all work on any host, including GoDaddy) and set it at
the top of `script.js`:

```js
const FORM_ENDPOINT = 'https://formspree.io/f/your-id';
```

### Before going live

- **`terms.html` is an outline, not a legal agreement.** Have counsel draft
  every section, delete the yellow draft notice, and change the page's
  `robots` meta from `noindex` to `index`.
- **Social icons in the footer link to `#`.** Replace them with the real
  profile URLs, or remove them.
- **Most models have no real specifications in the CMS.** Only the T150, D5
  Series and BG1 Pro do; the rest have placeholder text there, which is
  filtered out. Add specs per model (the `specs` table field works well) as
  they're confirmed, or fix them in the CMS and re-import.
- **Two CMS video choices worth reviewing:** the T600 and T600 Underride
  share one video, and KettyBot Pro's is a general "10 Years of Pudu" video
  rather than a KettyBot one.

### URL style

Both `/about.html` and `/about` resolve on Apache and IIS. Links in the markup
use the `.html` form so the site still works on hosts with no rewrite support
at all, while the extensionless rewrite keeps the URL style the live site
currently uses, so existing inbound links don't break.

## Browser Support
- Chrome/Edge (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Original Brand Assets Preserved
Every image is the original file from baybotdynamics.com, downloaded
byte-for-byte into `assets/images/` — not recompressed, resized, recolored or
regenerated:
- Logo and branding
- Hero section background shapes
- About section images (robots in field)
- Industry section imagery
- Footer decorative elements

They are served from this site rather than hotlinked from the original domain.
Hotlinking would have made the redesign break the moment the old site changed,
moved or went offline, and it cannot survive a move to a new domain.

Filenames keep their original capitalization (`pro/Bots-in-Field1.webp`).
Linux hosting is case-sensitive, so renaming them breaks the references even
though it works fine on macOS or Windows.

## Customization

### Colors
Colors are defined as CSS variables in `styles.css`:
```css
--primary-color: #0066cc;
--secondary-color: #00cc88;
--dark-bg: #0a0e1a;
```

### Typography
Uses Inter font family for modern, professional appearance. Can be changed in the `:root` section.

### Spacing
Responsive spacing system using CSS custom properties for consistency.

## Performance Optimizations
- Lazy loading for images
- Debounced scroll events
- Efficient CSS selectors
- Minimal JavaScript
- Optimized animations using CSS transforms

## Accessibility Features
- Semantic HTML5 elements
- ARIA labels and roles
- Keyboard navigation support
- Focus management for mobile menu
- Color contrast compliance
- Screen reader friendly

## Mobile Responsiveness
- Hamburger menu for mobile devices
- Touch-friendly interactive elements
- Optimized layouts for all screen sizes
- Fluid typography with clamp()

## Future Enhancements
- Add backend API integration for contact form
- Implement actual video/image loading
- Add analytics tracking
- Create additional subpages (About, Industries detail pages)
- Add blog integration
- Implement live chat widget

## Credits
Redesign preserves the original BayBot Dynamics brand identity while modernizing the user experience and technical implementation.

## License
© 2026 BayBot Dynamics LLC. All rights reserved.