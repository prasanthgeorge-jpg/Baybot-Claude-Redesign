#!/usr/bin/env python3
"""Import robot detail content from the live BayBot CMS into data/models.json.

The live baybotdynamics.com site reads its product pages from a public API:

    GET https://baybotdynamics.com/api/cms/bot-list
    GET https://baybotdynamics.com/api/cms/bot-details/<slug>

This script copies the detail content for each model into data/models.json:
YouTube video, title, summary, overview, features, functions (with their
images, downloaded unmodified into assets/images/models/functions/), genuine
specifications, and the industries each robot is deployed in.

It only fills CMS-derived fields. name, category, description, image, badge,
tagline, specs and brochure are left exactly as they are, so hand edits to
those survive a re-import.

Content filtered out, and reported, rather than published:
  * placeholder text (the "committed to revolutionizing the facilities, EVS,
    and janitorial fields" paragraph the CMS uses as filler, including a copy
    naming a different company);
  * any humanoid robot - not approved for sale in the USA.

Usage (from the site folder):
    python3 tools/import_from_cms.py                  # refresh all models
    python3 tools/import_from_cms.py --list           # show CMS robots
    python3 tools/import_from_cms.py --add "PUDU X1" --category cleaning
    python3 tools/import_from_cms.py --dry-run        # report only

Then run tools/build_models.py to regenerate the pages.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_models import (DATA, HUMANOID, ROOT, SLUG, plain_text,  # noqa: E402
                          sanitize_html, youtube_id)

API = "https://baybotdynamics.com/api/cms"
FUNCTION_DIR = "assets/images/models/functions"
MODEL_DIR = "assets/images/models"
PLACEHOLDER = re.compile(r"committed to revolutionizing|pringle robotics|lorem ipsum", re.I)
DETAIL_FIELDS = (("hardware_desc", "Design & Hardware"),
                 ("model_desc", "Intelligent Operation"),
                 ("obstacle_desc", "Obstacle Avoidance"))
CMS_FIELDS = ("cms_slug", "title", "summary_html", "overview_html", "video",
              "industries", "features", "functions", "spec_sections", "details")


def is_humanoid(bot, detail):
    """True if the CMS describes this robot as humanoid anywhere.

    Checked across the whole record, not just the name: the FlashBot Arm's
    name and title look like a delivery robot, and only its overview says
    "semi-humanoid". Industry records are left out because they list other
    robots' names.
    """
    record = {k: v for k, v in (detail or {}).items() if k != "industries"}
    return bool(HUMANOID.search(bot.get("name", "") + " " + bot.get("title", "") + " " + json.dumps(record)))


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url, dest):
    # CMS URLs sometimes contain raw spaces; quote them without double-encoding
    # the parts that are already percent-encoded.
    safe_url = urllib.parse.quote(url, safe=":/?&=%#+,")
    req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    os.makedirs(os.path.dirname(os.path.join(ROOT, dest)), exist_ok=True)
    with open(os.path.join(ROOT, dest), "wb") as f:
        f.write(data)
    return len(data)


def ext_of(url):
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    return ".jpg" if ext == ".jpeg" else (ext or ".png")


def norm(name):
    return re.sub(r"\s+", " ", (name or "")).strip().lower()


def is_placeholder(raw):
    return bool(PLACEHOLDER.search(plain_text(raw)))


def clean(raw, where, skipped):
    """Sanitised HTML, or '' when empty or placeholder (recorded in skipped)."""
    if not plain_text(raw):
        return ""
    if is_placeholder(raw):
        skipped.append(where)
        return ""
    out = sanitize_html(raw)
    # Editors sometimes leave a stray test word at the end of a block
    # (the live CC1 summary ends "...is critical. test").
    cleaned = re.sub(r"\s*\b(?:test|testing)\b\s*(?=</(?:p|li)>|$)", "", out, flags=re.I)
    if cleaned != out:
        skipped.append("stray 'test' removed from %s" % where)
    return cleaned


def extract(model_id, d, skipped, dry_run):
    out = {"cms_slug": d.get("slug", "")}

    title = re.sub(r"\s+", " ", d.get("title") or "").strip()
    if title and not HUMANOID.search(title):
        out["title"] = title

    out["summary_html"] = clean(d.get("banner_desc"), "summary", skipped) or clean(d.get("short_desc"), "short description", skipped)
    out["overview_html"] = clean(d.get("service_desc"), "overview", skipped)

    vid = youtube_id(d.get("youTube_link"))
    if vid:
        out["video"] = vid

    out["industries"] = [re.sub(r"\s+", " ", i["name"]).strip()
                         for i in d.get("industries", []) if i.get("status", True) and i.get("name")]

    feats = []
    for f in d.get("features", []):
        if not f.get("status"):
            continue
        body = clean(f.get("desc"), "feature '%s'" % (f.get("name") or "untitled"), skipped)
        name = re.sub(r"\s+", " ", f.get("name") or "").strip()
        if name:
            name = name[0].upper() + name[1:]
        if body or name:
            feats.append({k: v for k, v in (("name", name), ("html", body)) if v})
    out["features"] = feats

    funcs = []
    n = 0
    for f in d.get("functions", []):
        if not f.get("status"):
            continue
        body = clean(f.get("desc"), "function '%s'" % f.get("title"), skipped)
        title_ = re.sub(r"\s+", " ", f.get("title") or "").strip()
        # Some functions carry their whole message in the title with an empty
        # description (the T300's), which is still worth showing with its image.
        if not title_ or not (body or f.get("image")):
            continue
        n += 1
        item = {"title": title_}
        if body:
            item["html"] = body
        if f.get("image"):
            dest = "%s/%s-%d%s" % (FUNCTION_DIR, model_id, n, ext_of(f["image"]))
            if not dry_run:
                download(f["image"], dest)
            item["image"] = dest
        funcs.append(item)
    out["functions"] = funcs

    specs = []
    for s in d.get("specifications", []):
        if not s.get("status"):
            continue
        body = clean(s.get("desc"), "specification '%s'" % s.get("name"), skipped)
        if body and s.get("name"):
            specs.append({"title": re.sub(r"\s+", " ", s["name"]).strip(), "html": body})
    out["spec_sections"] = specs

    details = []
    for key, heading in DETAIL_FIELDS:
        body = clean(d.get(key), heading.lower(), skipped)
        if body:
            details.append({"title": heading, "html": body})
    out["details"] = details

    # Empty lists/strings are dropped so the JSON stays readable.
    return {k: v for k, v in out.items() if v}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true", help="list robots in the CMS and exit")
    ap.add_argument("--add", metavar="NAME_OR_SLUG", help="add a robot from the CMS that isn't on the site yet")
    ap.add_argument("--category", help="category for --add (cleaning, delivery, industrial, quadruped)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    args = ap.parse_args()

    bots = fetch_json(API + "/bot-list").get("details", [])
    by_name = {norm(b["name"]): b for b in bots}
    by_slug = {b["slug"]: b for b in bots}

    if args.list:
        with open(DATA, encoding="utf-8") as f:
            have = {norm(m["name"]) for m in json.load(f)["models"]}
        for b in bots:
            if norm(b["name"]) in have:
                state = "on site"
            else:
                detail = fetch_json("%s/bot-details/%s" % (API, b["slug"])).get("details") or {}
                state = "EXCLUDED (humanoid)" if is_humanoid(b, detail) else "not on site"
            print("  %-22s %-20s %s" % (b["name"].strip(), state, b["slug"]))
        return

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    models = data["models"]

    if args.add:
        bot = by_slug.get(args.add) or by_name.get(norm(args.add))
        if not bot:
            sys.exit("No CMS robot named or slugged '%s'. Try --list." % args.add)
        detail = fetch_json("%s/bot-details/%s" % (API, bot["slug"])).get("details") or {}
        if is_humanoid(bot, detail):
            sys.exit("'%s' is a humanoid robot. Humanoids are excluded from the site (not approved for sale in the USA)." % bot["name"].strip())
        if not args.category:
            sys.exit("--add needs --category (cleaning, delivery, industrial or quadruped).")
        if any(norm(m["name"]) == norm(bot["name"]) for m in models):
            sys.exit("'%s' is already on the site; run without --add to refresh it." % bot["name"].strip())
        mid = re.sub(r"[^a-z0-9]+", "-", norm(bot["name"])).strip("-")
        if not SLUG.match(mid):
            sys.exit("Couldn't derive an id from '%s'." % bot["name"])
        image = ""
        if bot.get("banner_img"):
            image = "%s/%s%s" % (MODEL_DIR, mid, ext_of(bot["banner_img"]))
            if not args.dry_run:
                download(bot["banner_img"], image)
        new = {
            "id": mid,
            "name": bot["name"].strip(),
            "category": args.category,
            "description": plain_text(detail.get("short_desc") or bot.get("short_desc")) or bot.get("title", ""),
        }
        if image:
            new["image"] = image
            new["image_alt"] = "%s robot" % new["name"]
        models.append(new)
        print("Added %s (%s)." % (new["name"], args.category))

    report = []
    removed = []
    for m in models:
        bot = by_slug.get(m.get("cms_slug")) or by_name.get(norm(m["name"]))
        if not bot:
            report.append("  %-22s not in CMS - left unchanged" % m["name"])
            continue
        detail = fetch_json("%s/bot-details/%s" % (API, bot["slug"])).get("details") or {}
        if is_humanoid(bot, detail):
            removed.append(m)
            report.append("  %-22s REMOVED - the CMS describes it as humanoid (not approved in the USA)" % m["name"])
            continue
        skipped = []
        fields = extract(m["id"], detail, skipped, args.dry_run)
        for k in CMS_FIELDS:
            m.pop(k, None)
        m.update(fields)
        got = [k for k in ("video", "summary_html", "overview_html") if k in fields]
        counts = ["%d %s" % (len(fields[k]), k.replace("_", " ")) for k in ("features", "functions", "spec_sections", "details") if fields.get(k)]
        line = "  %-22s %s" % (m["name"], ", ".join(got + counts))
        if skipped:
            line += "\n  %-22s   placeholder text skipped: %s" % ("", ", ".join(skipped))
        report.append(line)

    models = [m for m in models if m not in removed]

    # Keep a stable, readable key order in the JSON.
    order = ("id", "name", "category", "badge", "tagline", "description", "image", "image_alt",
             "title", "summary_html", "overview_html", "video", "industries", "features",
             "functions", "spec_sections", "details", "specs", "brochure", "cms_slug")
    data["models"] = [{k: m[k] for k in order if k in m} | {k: v for k, v in m.items() if k not in order}
                      for m in models]

    print("\n".join(report))
    if args.dry_run:
        print("\nDry run - nothing written.")
        return
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("\nUpdated data/models.json. Now run: python3 tools/build_models.py")


if __name__ == "__main__":
    main()
