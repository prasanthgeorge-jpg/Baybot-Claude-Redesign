#!/usr/bin/env python3
"""Build robot model cards and per-model detail pages from data/models.json.

1. products.html: each category section contains a marked slot,

       <!-- MODELS:cleaning:START ... -->
       <!-- MODELS:cleaning:END -->

   which is replaced with a card per model in that category. Each card's name
   and photo link to the model's own page.

2. product-<id>.html: one page per model, with the YouTube video, overview,
   features, functions, specifications and related models. The navigation
   and footer are copied from products.html, so the site chrome stays
   identical without a separate template to maintain. Detail pages live at
   the site root so every relative asset path keeps working.

Detail pages for models that have been removed from the data are deleted,
but only files carrying this script's generated-page marker are ever touched.

Output is plain static HTML: no JavaScript is needed to show a model, it
works on any host, and every page is indexable.

Usage (from the site folder):
    python3 tools/build_models.py            # validate and rebuild
    python3 tools/build_models.py --check    # validate only; exit 1 if the
                                             # pages are out of date

Uses only the Python standard library.
"""
import argparse
import glob
import html
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "models.json")
PAGE = os.path.join(ROOT, "products.html")

GENERATED_MARKER = "<!-- GENERATED:product-page by tools/build_models.py - edit data/models.json, not this file -->"

REQUIRED = ("id", "name", "category", "description")
OPTIONAL = (
    "tagline", "image", "image_alt", "badge", "brochure",
    # detail page
    "title", "summary_html", "overview_html", "video", "industries",
    "features", "functions", "spec_sections", "details", "specs",
    # provenance, not rendered
    "cms_slug",
)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Humanoid robots are not approved for sale in the USA, so the site must never
# list one. Enforced here as well as in the importer so hand-edited data can't
# slip one through either.
HUMANOID = re.compile(r"humanoid", re.I)

CATEGORY_LABELS = {
    "cleaning": "Cleaning Robots",
    "delivery": "Delivery & Reception Robots",
    "industrial": "Industrial Transport Robots",
    "quadruped": "Quadruped Robots",
}


# --------------------------------------------------------------------------
# HTML sanitising
# CMS rich text arrives full of editor debris: inline styles, data-*
# attributes, wrapper divs, and in places an entire HTML document escaped
# inside a <p>. Everything is reduced to a small allowlist of tags with no
# attributes, so nothing from the CMS can inject script or break layout.
# --------------------------------------------------------------------------
ALLOWED = {"p", "ul", "ol", "li", "strong", "em", "br"}
RENAME = {"b": "strong", "i": "em"}
BLOCK = {"p", "ul", "ol", "li"}
DROP_CONTENT = {"script", "style", "head", "title", "iframe", "object", "noscript"}


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []
        self.skip = 0

    def _close_to(self, tag):
        while self.stack:
            top = self.stack.pop()
            self.out.append("</%s>" % top)
            if top == tag:
                return

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self.skip += 1
            return
        if self.skip:
            return
        tag = RENAME.get(tag, tag)
        if tag not in ALLOWED:
            return
        if tag == "br":
            self.out.append("<br>")
            return
        # A block element can't sit inside <p>: close the paragraph first.
        if tag in BLOCK and "p" in self.stack:
            self._close_to("p")
        if tag == "li" and self.stack and self.stack[-1] == "li":
            self._close_to("li")
        self.out.append("<%s>" % tag)
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if RENAME.get(tag, tag) not in ("br",) and RENAME.get(tag, tag) in self.stack:
            self._close_to(RENAME.get(tag, tag))

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        tag = RENAME.get(tag, tag)
        if tag in self.stack:
            self._close_to(tag)

    def handle_data(self, data):
        if self.skip:
            return
        self.out.append(html.escape(data.replace("\xa0", " "), quote=False))

    def result(self):
        while self.stack:
            self.out.append("</%s>" % self.stack.pop())
        s = "".join(self.out)
        s = re.sub(r"\s+", " ", s)
        # Drop elements left empty once attributes and wrappers are gone.
        for _ in range(3):
            s = re.sub(r"<(p|strong|em|li|ul|ol)>\s*</\1>", "", s)
        s = re.sub(r"\s*(</?(?:p|ul|ol|li)>)\s*", r"\1", s)
        # Trailing line breaks inside a block just add blank space.
        s = re.sub(r"(?:\s*<br>)+\s*(</(?:p|li)>)", r"\1", s)
        s = re.sub(r"(?:<br>\s*)+$", "", s)
        return s.strip()


def sanitize_html(raw):
    """Reduce CMS rich text to allowlisted tags with no attributes."""
    if not raw:
        return ""
    raw = str(raw)
    # Some CMS fields hold a whole HTML document escaped as text. Unescape it
    # once so its list structure survives instead of printing literal tags.
    if re.search(r"&lt;/?(?:p|ul|ol|li|b|strong|span|div|html|body)\b", raw):
        raw = html.unescape(raw)
    p = _Sanitizer()
    p.feed(raw)
    p.close()
    return p.result()


def plain_text(raw):
    text = re.sub(r"<[^>]+>", " ", sanitize_html(raw))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def youtube_id(value):
    """Accept a bare 11-character ID or any common YouTube URL form."""
    if not value:
        return ""
    value = str(value).strip()
    if YOUTUBE_ID.match(value):
        return value
    m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})", value)
    return m.group(1) if m else ""


def esc(value):
    return html.escape(str(value), quote=True)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def slot_pattern(category):
    return re.compile(
        r"(<!-- MODELS:%s:START[^>]*-->\n)(.*?)([ \t]*<!-- MODELS:%s:END -->)"
        % (re.escape(category), re.escape(category)),
        re.S,
    )


def page_categories(page):
    return re.findall(r"<!-- MODELS:([a-z0-9-]+):START", page)


def _check_path(where, key, path, errors):
    if not path:
        return
    if path.startswith(("/", "http:", "https:")):
        errors.append("%s: %s must be a relative path inside the site, e.g. assets/images/models/x.png" % (where, key))
    elif not os.path.exists(os.path.join(ROOT, path)):
        errors.append("%s: %s file not found: %s" % (where, key, path))


def validate(models, categories):
    errors = []
    seen = set()
    for n, m in enumerate(models, start=1):
        if not isinstance(m, dict):
            errors.append("model #%d: must be an object" % n)
            continue
        where = "model #%d (%s)" % (n, m.get("name") or m.get("id") or "unnamed")
        for key in REQUIRED:
            if not str(m.get(key, "")).strip():
                errors.append("%s: missing required field '%s'" % (where, key))
        unknown = set(m) - set(REQUIRED) - set(OPTIONAL)
        if unknown:
            errors.append("%s: unknown field(s) %s" % (where, ", ".join(sorted(unknown))))

        mid = m.get("id", "")
        if mid and not SLUG.match(mid):
            errors.append("%s: id '%s' must be lowercase letters, digits and hyphens" % (where, mid))
        if mid in seen:
            errors.append("%s: duplicate id '%s'" % (where, mid))
        seen.add(mid)

        if m.get("category") and m["category"] not in categories:
            errors.append("%s: category '%s' has no section on products.html (valid: %s)"
                          % (where, m["category"], ", ".join(categories)))

        # Scan every text field, not just the name: the FlashBot Arm's
        # classification as semi-humanoid only appeared in its overview.
        if HUMANOID.search(json.dumps({k: v for k, v in m.items() if k != "cms_slug"})):
            errors.append("%s: humanoid robots are excluded from the site (not approved for sale in the USA)" % where)

        if m.get("video") and not youtube_id(m["video"]):
            errors.append("%s: video '%s' is not a recognisable YouTube ID or URL" % (where, m["video"]))

        specs = m.get("specs", [])
        if not isinstance(specs, list) or not all(isinstance(r, list) and len(r) == 2 for r in specs):
            errors.append("%s: specs must be a list of [label, value] pairs" % where)

        for key in ("industries",):
            if not isinstance(m.get(key, []), list) or not all(isinstance(x, str) for x in m.get(key, [])):
                errors.append("%s: %s must be a list of strings" % (where, key))

        feats = m.get("features", [])
        if not isinstance(feats, list) or not all(
                isinstance(f, str) or (isinstance(f, dict) and (f.get("name") or f.get("html"))) for f in feats):
            errors.append("%s: features must be strings or {name, html} objects" % where)

        for key in ("functions", "spec_sections", "details"):
            items = m.get(key, [])
            # A function may be just a title and an image; the others need text.
            needs_html = key != "functions"
            if not isinstance(items, list) or not all(
                    isinstance(x, dict) and x.get("title")
                    and (x.get("html") or (not needs_html and x.get("image")))
                    for x in items):
                errors.append("%s: %s must be a list of {title, html%s} objects"
                              % (where, key, "" if needs_html else " and/or image"))
                continue
            for x in items:
                _check_path(where, key + " image", x.get("image"), errors)

        _check_path(where, "image", m.get("image"), errors)
        _check_path(where, "brochure", m.get("brochure"), errors)
    return errors


# --------------------------------------------------------------------------
# Rendering: product cards
# --------------------------------------------------------------------------
def detail_href(m):
    return "product-%s.html" % m["id"]


def render_card(m, indent="                "):
    i = indent
    href = esc(detail_href(m))
    out = ['%s    <article class="model-card" id="model-%s">' % (i, esc(m["id"]))]
    if m.get("image"):
        alt = m.get("image_alt") or "%s robot" % m["name"]
        out.append('%s        <a href="%s" class="model-card-media" tabindex="-1" aria-hidden="true">' % (i, href))
        out.append('%s            <img src="%s" alt="%s" loading="lazy">' % (i, esc(m["image"]), esc(alt)))
        out.append('%s        </a>' % i)
    out.append('%s        <div class="model-card-body">' % i)
    flags = []
    if m.get("badge"):
        flags.append('<span class="model-badge">%s</span>' % esc(m["badge"]))
    if youtube_id(m.get("video")):
        flags.append('<span class="model-video-flag"><i class="fas fa-circle-play" aria-hidden="true"></i> Video</span>')
    if flags:
        out.append('%s            <div class="model-flags">%s</div>' % (i, "".join(flags)))
    out.append('%s            <h3><a href="%s">%s</a></h3>' % (i, href, esc(m["name"])))
    if m.get("tagline"):
        out.append('%s            <p class="model-tagline">%s</p>' % (i, esc(m["tagline"])))
    out.append('%s            <p>%s</p>' % (i, esc(m["description"])))
    out.append('%s            <div class="model-actions">' % i)
    out.append('%s                <a href="%s" class="btn btn-primary">View Details <i class="fas fa-arrow-right" aria-hidden="true"></i><span class="visually-hidden"> about %s</span></a>'
               % (i, href, esc(m["name"])))
    out.append('%s            </div>' % i)
    out.append('%s        </div>' % i)
    out.append('%s    </article>' % i)
    return out


def render_slot(category, models):
    items = [m for m in models if m["category"] == category]
    if not items:
        return ""
    indent = "                "
    lines = ['%s<div class="model-grid">' % indent]
    for m in items:
        lines += render_card(m, indent)
    lines.append('%s</div>' % indent)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Rendering: detail pages
# --------------------------------------------------------------------------
def page_chrome(products_page):
    """Split products.html into the nav and footer reused by detail pages."""
    body_start = products_page.index("<body>")
    main_start = products_page.index('<main id="main">')
    main_end = products_page.index("</main>")
    nav = products_page[body_start:main_start]
    footer = products_page[main_end:]
    # Products stays highlighted, but aria-current belongs only to the
    # products page itself, not to the pages beneath it.
    nav = nav.replace('href="products.html" class="active" aria-current="page"',
                      'href="products.html" class="active"')
    return nav, footer


def render_head(m):
    title = "%s | %s" % (m["name"], m.get("title") or m["description"].rstrip("."))
    desc = plain_text(m.get("summary_html")) or m["description"]
    if len(desc) > 158:
        desc = desc[:155].rsplit(" ", 1)[0] + "..."
    return """<!DOCTYPE html>
<html lang="en">
<head>
    %s
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="%s">
    <meta name="robots" content="index, follow">

    <meta property="og:title" content="%s">
    <meta property="og:description" content="%s">
    <meta property="og:site_name" content="BayBot Dynamics">
    <meta property="og:type" content="product">

    <title>%s | BayBot Dynamics</title>
    <link rel="canonical" href="%s">
    <link rel="icon" href="assets/favicon.ico" type="image/x-icon">

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="styles.css">
</head>
""" % (GENERATED_MARKER, esc(desc), esc(m["name"]), esc(desc), esc(title), esc(detail_href(m)))


def render_video(m):
    vid = youtube_id(m.get("video"))
    if not vid:
        return ""
    label = "%s in action" % m["name"]
    # Click-to-load: only a thumbnail loads until the visitor presses play, so
    # YouTube's player (and its cookies) never load for people who don't
    # watch. Without JavaScript the poster is simply a link to YouTube.
    return """
        <section class="product-video-section" id="video" aria-labelledby="video-heading">
            <div class="container">
                <div class="section-header text-center">
                    <span class="section-label light">Video</span>
                    <h2 class="section-title light" id="video-heading">Watch the %s in Action</h2>
                </div>
                <div class="video-embed" data-video-id="%s" data-title="%s">
                    <a class="video-embed-poster" href="https://www.youtube.com/watch?v=%s" target="_blank" rel="noopener">
                        <img src="https://i.ytimg.com/vi/%s/hqdefault.jpg" alt="" loading="lazy">
                        <span class="video-embed-play" aria-hidden="true"><i class="fas fa-play"></i></span>
                        <span class="visually-hidden">Play video: %s</span>
                    </a>
                </div>
            </div>
        </section>
""" % (esc(m["name"]), esc(vid), esc(label), esc(vid), esc(vid), esc(label))


def render_features(m):
    feats = m.get("features") or []
    if not feats:
        return ""
    items = []
    for f in feats:
        if isinstance(f, str):
            f = {"name": f}
        body = sanitize_html(f.get("html"))
        items.append("""                    <div class="product-feature">
                        <span class="product-feature-icon"><i class="fas fa-check" aria-hidden="true"></i></span>
                        <div>
%s%s                        </div>
                    </div>""" % (
            ('                            <h3>%s</h3>\n' % esc(f["name"])) if f.get("name") else "",
            ('                            <div class="rich-text">%s</div>\n' % body) if body else "",
        ))
    return """
        <section class="industries-section" id="features" aria-labelledby="features-heading">
            <div class="container">
                <div class="section-header text-center">
                    <span class="section-label">Key Features</span>
                    <h2 class="section-title" id="features-heading">What Sets the %s Apart</h2>
                </div>
                <div class="product-feature-grid">
%s
                </div>
            </div>
        </section>
""" % (esc(m["name"]), "\n".join(items))


def render_functions(m):
    funcs = m.get("functions") or []
    if not funcs:
        return ""
    rows = []
    for n, f in enumerate(funcs):
        body = sanitize_html(f.get("html"))
        text = """                    <div class="product-function-text">
                        <span class="section-label">Function %d</span>
                        <h3>%s</h3>
%s                    </div>""" % (n + 1, esc(f["title"]),
                                 ('                        <div class="rich-text">%s</div>\n' % body) if body else "")
        if f.get("image"):
            img = """                    <div class="product-function-media">
                        <img src="%s" alt="%s: %s" loading="lazy">
                    </div>""" % (esc(f["image"]), esc(m["name"]), esc(f["title"]))
            inner = (img + "\n" + text) if n % 2 == 0 else (text + "\n" + img)
            cls = "product-function"
        else:
            inner = text
            cls = "product-function product-function-textonly"
        rows.append('                <div class="%s">\n%s\n                </div>' % (cls, inner))
    return """
        <section class="about-section" id="functions" aria-labelledby="functions-heading">
            <div class="container">
                <div class="section-header text-center">
                    <span class="section-label">How It Works</span>
                    <h2 class="section-title" id="functions-heading">Core Functions</h2>
                </div>
%s
            </div>
        </section>
""" % "\n".join(rows)


def render_specs(m):
    sections = m.get("spec_sections") or []
    details = m.get("details") or []
    table = m.get("specs") or []
    if not (sections or details or table):
        return ""
    blocks = []
    for d in details:
        blocks.append("""                    <div class="spec-block">
                        <h3>%s</h3>
                        <div class="rich-text">%s</div>
                    </div>""" % (esc(d["title"]), sanitize_html(d["html"])))
    for s in sections:
        blocks.append("""                    <div class="spec-block">
                        <h3>%s</h3>
                        <div class="rich-text">%s</div>
                    </div>""" % (esc(s["title"]), sanitize_html(s["html"])))
    if table:
        rows = "\n".join('                                <tr><th scope="row">%s</th><td>%s</td></tr>' % (esc(a), esc(b))
                         for a, b in table)
        blocks.append("""                    <div class="spec-block">
                        <h3>At a Glance</h3>
                        <table class="spec-table">
                            <caption class="visually-hidden">%s specifications</caption>
                            <tbody>
%s
                            </tbody>
                        </table>
                    </div>""" % (esc(m["name"]), rows))
    brochure = ""
    if m.get("brochure"):
        brochure = """
                <div class="section-cta">
                    <a href="%s" class="btn btn-outline" download>Download Spec Sheet <i class="fas fa-download" aria-hidden="true"></i></a>
                </div>""" % esc(m["brochure"])
    return """
        <section class="industries-section" id="specifications" aria-labelledby="specs-heading">
            <div class="container">
                <div class="section-header text-center">
                    <span class="section-label">Specifications</span>
                    <h2 class="section-title" id="specs-heading">Technical Details</h2>
                </div>
                <div class="spec-blocks">
%s
                </div>%s
            </div>
        </section>
""" % ("\n".join(blocks), brochure)


def render_related(m, models):
    others = [o for o in models if o["category"] == m["category"] and o["id"] != m["id"]]
    if not others:
        return ""
    cards = []
    for o in others:
        cards += render_card(o, "                ")
    return """
        <section class="about-section" id="related" aria-labelledby="related-heading">
            <div class="container">
                <div class="section-header text-center">
                    <span class="section-label">%s</span>
                    <h2 class="section-title" id="related-heading">Related Models</h2>
                </div>
                <div class="model-grid">
%s
                </div>
            </div>
        </section>
""" % (esc(CATEGORY_LABELS.get(m["category"], "More Robots")), "\n".join(cards))


def render_detail(m, models, nav, footer):
    cat_label = CATEGORY_LABELS.get(m["category"], m["category"].title())
    summary = sanitize_html(m.get("summary_html"))
    overview = sanitize_html(m.get("overview_html"))
    industries = m.get("industries") or []

    image = ""
    if m.get("image"):
        image = """                    <div class="product-hero-media">
                        <img src="%s" alt="%s">
                    </div>""" % (esc(m["image"]), esc(m.get("image_alt") or "%s robot" % m["name"]))

    jump = []
    if youtube_id(m.get("video")):
        jump.append('<a href="#video" class="btn btn-outline btn-lg"><i class="fas fa-circle-play" aria-hidden="true"></i> Watch Video</a>')

    body = """
        <section class="product-hero">
            <div class="container">
                <nav class="breadcrumb breadcrumb-left" aria-label="Breadcrumb">
                    <a href="index.html">Home</a>
                    <span aria-hidden="true">/</span>
                    <a href="products.html">Products</a>
                    <span aria-hidden="true">/</span>
                    <a href="products.html#%s">%s</a>
                    <span aria-hidden="true">/</span>
                    <span aria-current="page">%s</span>
                </nav>
                <div class="product-hero-grid">
                    <div class="product-hero-text">
                        <span class="section-label">%s</span>
                        <h1>%s</h1>
                        %s
                        <div class="rich-text product-hero-summary">%s</div>
                        <div class="product-hero-cta">
                            <a href="schedule-demo.html" class="btn btn-primary btn-lg">Request a Demo <i class="fas fa-arrow-right" aria-hidden="true"></i></a>
                            %s
                        </div>
                    </div>
%s
                </div>
            </div>
        </section>
""" % (
        esc(m["category"]), esc(cat_label), esc(m["name"]),
        esc(cat_label), esc(m["name"]),
        ('<p class="product-hero-title">%s</p>' % esc(m["title"])) if m.get("title") else "",
        summary or "<p>%s</p>" % esc(m["description"]),
        "".join(jump),
        image,
    )

    body += render_video(m)

    if overview or industries:
        chips = ""
        if industries:
            chips = """
                    <div class="industry-chips">
                        <h3>Deployed In</h3>
                        <ul>
%s
                        </ul>
                    </div>""" % "\n".join('                            <li>%s</li>' % esc(x) for x in industries)
        body += """
        <section class="about-section" id="overview" aria-labelledby="overview-heading">
            <div class="container">
                <div class="product-overview">
                    <span class="section-label">Overview</span>
                    <h2 class="section-title" id="overview-heading">About the %s</h2>
                    <div class="rich-text section-description">%s</div>%s
                </div>
            </div>
        </section>
""" % (esc(m["name"]), overview or "<p>%s</p>" % esc(m["description"]), chips)

    body += render_features(m)
    body += render_functions(m)
    body += render_specs(m)
    body += render_related(m, models)
    body += """
        <section class="cta-section">
            <div class="container text-center">
                <h2 class="section-title">See the %s in Your Space</h2>
                <p class="section-description">
                    Tell us about your facility and we'll arrange a demo, online or in
                    person, along with specifications and pricing for your site.
                </p>
                <div class="hero-cta">
                    <a href="schedule-demo.html" class="btn btn-primary btn-lg">Request a Custom Demo <i class="fas fa-arrow-right" aria-hidden="true"></i></a>
                    <a href="contact.html" class="btn btn-outline btn-lg">Request Specifications</a>
                </div>
            </div>
        </section>
""" % esc(m["name"])

    return render_head(m) + nav + '<main id="main">' + body + "    " + footer


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def build(models, page):
    """Return (new products.html, {filename: html} for detail pages)."""
    new_page = page
    for cat in page_categories(page):
        new_page = slot_pattern(cat).sub(
            lambda mt: mt.group(1) + render_slot(cat, models) + mt.group(3), new_page)
    nav, footer = page_chrome(new_page)
    pages = {detail_href(m): render_detail(m, models, nav, footer) for m in models}
    return new_page, pages


def stale_detail_pages(keep):
    stale = []
    for path in glob.glob(os.path.join(ROOT, "product-*.html")):
        name = os.path.basename(path)
        if name in keep:
            continue
        with open(path, encoding="utf-8") as f:
            if GENERATED_MARKER in f.read(2000):
                stale.append(path)
    return stale


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="validate and report whether the pages are current; write nothing")
    ap.add_argument("--data", default=DATA, help=argparse.SUPPRESS)
    ap.add_argument("--out-dir", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    try:
        with open(args.data, encoding="utf-8") as f:
            models = json.load(f).get("models", [])
    except json.JSONDecodeError as e:
        sys.exit("data/models.json is not valid JSON: %s" % e)

    categories = page_categories(page)
    errors = validate(models, categories)
    if errors:
        print("Not building - fix these in data/models.json:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)

    new_page, pages = build(models, page)
    counts = ", ".join("%s: %d" % (c, sum(m["category"] == c for m in models)) for c in categories)
    out_dir = args.out_dir or ROOT
    stale = [] if args.out_dir else stale_detail_pages(set(pages))

    if args.check:
        outdated = [os.path.basename(PAGE)] if new_page != page else []
        for name, content in pages.items():
            path = os.path.join(ROOT, name)
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != content:
                outdated.append(name)
        outdated += [os.path.basename(p) + " (stale)" for p in stale]
        if outdated:
            print("Out of date (%s): %s. Run without --check." % (counts, ", ".join(outdated)))
            sys.exit(1)
        print("All pages up to date (%s; %d detail pages)." % (counts, len(pages)))
        return

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, os.path.basename(PAGE)), "w", encoding="utf-8") as f:
        f.write(new_page)
    for name, content in pages.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
    for path in stale:
        os.remove(path)
    print("Built %d model(s) (%s): products.html + %d detail page(s)%s."
          % (len(models), counts, len(pages),
             ("; removed %d stale page(s)" % len(stale)) if stale else ""))


if __name__ == "__main__":
    main()
