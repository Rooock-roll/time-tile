#!/usr/bin/env python3
"""
Generate static TIME live-tile content for public hosting (plan A).

Each build rotates which article is "current", so consecutive shell polls
(every 30 min per uap:TileUpdate) walk through the five newest stories.

Outputs:
    tile.xml        adaptive tile XML for the CURRENT article + its picture
    img/art-N.jpg   composited 620x620 backgrounds for all five slots
    articles.json   metadata (titles + rotation cursor), newest first
"""

import json
import os
import re
import sys
import datetime
import urllib.request

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, "img")
TILE_XML = os.path.join(ROOT, "tile.xml")
ARTICLES = os.path.join(ROOT, "articles.json")

FEED = os.environ.get("TIME_FEED", "http://feeds2.feedburner.com/time/topstories")

# cdn.jsdelivr.net is NOT reachable from this user's network (connection reset),
# while the fastly / gcore edges work fine. Prefer the reachable one so the
# tile can actually download its pictures.
DEFAULT_CDN = "https://fastly.jsdelivr.net/gh/Rooock-roll/time-tile@main"
CDN_BASE = os.environ.get("TILE_CDN_BASE", DEFAULT_CDN).rstrip("/")
MAX_SLOTS = 5
TILE_PX = 620
UA = "Mozilla/5.0 TimeTileBuilder"
PROXY = os.environ.get("TIME_PROXY", "").strip()


def log(msg):
    print(msg, flush=True)


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if PROXY:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
        with opener.open(req, timeout=timeout) as r:
            return r.read()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def decode_entities(s):
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"),
                 ("&#39;", "'"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s


def parse_items(xml_text):
    items = []
    pos = 0
    while len(items) < MAX_SLOTS:
        i = xml_text.find("<item>", pos)
        if i < 0:
            i = xml_text.find("<item ", pos)
        if i < 0:
            break
        j = xml_text.find("</item>", i)
        if j < 0:
            j = len(xml_text)
        chunk = xml_text[i:j]

        t1, t2 = chunk.find("<title>"), chunk.find("</title>")
        title = ""
        if t1 >= 0 and t2 > t1:
            title = chunk[t1 + 7:t2].strip().replace("<![CDATA[", "").replace("]]>", "").strip()
            title = decode_entities(title)

        img = ""
        m = chunk.find("<media:content")
        if m >= 0:
            u = chunk.find('url="', m)
            if u >= 0:
                e = chunk.find('"', u + 5)
                if e > 0:
                    img = decode_entities(chunk[u + 5:e])
        if not img:
            k = chunk.find("<img")
            if k >= 0:
                u = chunk.find('src="', k)
                if u >= 0:
                    e = chunk.find('"', u + 5)
                    if e > 0:
                        img = decode_entities(chunk[u + 5:e])

        # summary text: <description> holds a plain sentence in the TIME feed
        summary = ""
        d1, d2 = chunk.find("<description>"), chunk.find("</description>")
        if d1 >= 0 and d2 > d1:
            summary = chunk[d1 + 13:d2].strip().replace("<![CDATA[", "").replace("]]>", "").strip()
            summary = decode_entities(summary)
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()
        # fall back to the first paragraph of content:encoded
        if not summary:
            c1, c2 = chunk.find("<content:encoded>"), chunk.find("</content:encoded>")
            if c1 >= 0 and c2 > c1:
                ce = chunk[c1 + 17:c2].replace("<![CDATA[", "").replace("]]>", "")
                # Some posts (shopping round-ups) ship no <description> at all, and
                # their first paragraph carries attributes or inline tags, so the
                # old strict "<p>...</p>" match came back empty and the tile lost
                # its body text. Accept attributes/inline markup, then fall back to
                # stripping every tag from the whole body.
                m = re.search(r"<p[^>]*>(.*?)</p>", ce, re.S)
                if m:
                    inner = re.sub(r"<[^>]+>", " ", m.group(1))
                    summary = re.sub(r"\s+", " ", decode_entities(inner)).strip()
                if not summary:
                    flat = re.sub(r"<[^>]+>", " ", ce)
                    summary = re.sub(r"\s+", " ", decode_entities(flat)).strip()

        if title:
            items.append({"title": title, "summary": summary, "image": img})
        pos = j + 7
    return items


BODY_INDENT = "\u3000\u3000"   # 两个全角空格：正文首行空两格


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def clip(s, n):
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n - 1] + "\u2026"


def make_tile(src_bytes, out_path, size=TILE_PX, quality=86):
    if not HAS_PIL:
        return False
    import io
    im = Image.open(io.BytesIO(src_bytes)).convert("RGB")
    w, h = im.size
    if w < 100 or h < 100:
        return False
    scale = max(size / w, size / h)
    nw, nh = int(w * scale + 0.5), int(h * scale + 0.5)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - size) // 2, (nh - size) // 2
    im = im.crop((left, top, left + size, top + size))

    from PIL import ImageDraw
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    start = int(size * 0.42)
    for y in range(start, size):
        a = int(205 * (y - start) / max(1, size - start))
        d.line([(0, y), (size, y)], fill=(0, 0, 0, a))
    im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    im.save(out_path, "JPEG", quality=quality, optimize=True)
    return True


def build_single(article, index, all_titles):
    img_url = "%s/img/art-%d.jpg" % (CDN_BASE, index) if CDN_BASE else "img/art-%d.jpg" % index
    title = article.get("title", "")
    summary = article.get("summary", "")
    lines = ['<?xml version="1.0"?>', "<tile>", '  <visual branding="logo">']
    # titles are capped at 2 lines so the rest of the tile is available for the
    # article body; body length grows with the tile size
    # Real usable heights (canvas minus padding and the 26px logo strip):
    #   Medium 150x150 -> 100px   Wide 310x150 -> 100px   Large 310x310 -> 260px
    # The wide tile is the tight one: a caption-size 2-line title + 4 body lines = 92px.
    # The large tile has room to spare, so it gets a much longer excerpt.
    for tmpl, style, tmax, slimit, smax in (
            ("TileMedium", "base", 2, 0, 0),            # medium: title only
            ("TileWide", "caption", 2, 165, 4),         # wide: 2-line title + 4-line body
            ("TileLarge", "subtitle", 3, 470, 8)):      # large: 3-line title + 8-line body
        lines.append('    <binding template="%s">' % tmpl)
        lines.append('      <image src="%s" placement="background" hint-crop="none"/>' % esc(img_url))
        lines.append('      <text hint-style="%s" hint-maxlines="%d" hint-wrap="true">%s</text>'
                     % (style, tmax, esc(title)))
        if slimit > 0 and summary:
            lines.append('      <text hint-style="%s" hint-maxlines="%d" hint-wrap="true">%s</text>'
                         % ("captionSubtle", smax, BODY_INDENT + esc(clip(summary, slimit))))
        lines.append("    </binding>")
    # small tile gets a plain text line (no image fits comfortably)
    lines.append('    <binding template="TileSmall">')
    lines.append('      <text hint-style="caption">%s</text>' % esc(clip(title, 24)))
    lines.append("    </binding>")
    lines.append("  </visual>")
    lines.append("</tile>")
    return "\n".join(lines) + "\n"


def main():
    os.makedirs(IMG_DIR, exist_ok=True)
    log("fetching feed: " + FEED)
    raw = fetch(FEED).decode("utf-8", errors="replace")
    items = parse_items(raw)
    if not items:
        log("no items parsed - leaving existing output untouched")
        return 1
    log("parsed %d items; newest: %s" % (len(items), items[0]["title"]))
    titles = [i["title"] for i in items]

    # previous rotation state, so each build shows the NEXT article
    cursor = 0
    prev_show = -1
    if os.path.exists(ARTICLES):
        try:
            prev = json.load(open(ARTICLES, encoding="utf-8"))
            prev_show = int(prev.get("showing", -1))
            if prev.get("titles") and prev["titles"][0] == titles[0]:
                cursor = (prev_show + 1) % max(1, len(items))
                log("previous set matched; advancing from slot %d" % prev_show)
            else:
                log("new feed content; restarting rotation at slot 0")
        except Exception:
            pass

    for idx, a in enumerate(items):
        out = os.path.join(IMG_DIR, "art-%d.jpg" % idx)
        if not a["image"]:
            log("  [%d] no image in feed, keeping previous composite if any" % idx)
            continue
        try:
            data = fetch(a["image"])
            if make_tile(data, out):
                log("  [%d] art-%d.jpg (%d bytes)" % (idx, idx, os.path.getsize(out)))
        except Exception as e:
            log("  [%d] image failed: %s" % (idx, e))

    # if a slot has no composite, borrow the first available one for display
    have = [i for i in range(MAX_SLOTS) if os.path.exists(os.path.join(IMG_DIR, "art-%d.jpg" % i))]
    if not have:
        log("no composites available - cannot build a useful tile")
        return 1

    show_idx = cursor % len(items)
    if show_idx not in have:
        # fall back to whichever slot actually has a picture
        log("  slot %d has no picture, falling back to slot %d" % (show_idx, have[0]))
        show_idx_img = have[0]
    else:
        show_idx_img = show_idx

    xml = build_single(items[show_idx], show_idx_img, titles)
    open(TILE_XML, "w", encoding="utf-8").write(xml)
    log("wrote tile.xml -> showing slot %d: %s" % (show_idx, clip(items[show_idx]["title"], 50)))

    json.dump({"updated": datetime.datetime.now(datetime.UTC).isoformat(),
               "showing": show_idx, "next": (show_idx + 1) % max(1, len(items)),
               "titles": titles, "articles": items},
              open(ARTICLES, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("wrote articles.json (next -> slot %d)" % ((show_idx + 1) % max(1, len(items))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
