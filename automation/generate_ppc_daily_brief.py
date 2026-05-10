import argparse
import asyncio
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path


NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

PRIORITY_KEYWORDS = [
    "performance max",
    "pmax",
    "google ads",
    "microsoft advertising",
    "paid search",
    "search ads",
    "shopping",
    "retail media",
    "amazon",
    "meta",
    "tiktok",
    "programmatic",
    "ctv",
    "conversion",
    "measurement",
    "attribution",
    "affiliate",
    "commerce",
    "ai",
]


def strip_html(value: str) -> str:
    value = value or ""
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: str):
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def child_text(element, names):
    for name in names:
        found = element.find(name, NS)
        if found is not None and found.text:
            return found.text

    wanted = {name.split("}")[-1].split(":")[-1] for name in names}
    for child in list(element):
        if child.tag.split("}")[-1] in wanted and child.text:
            return child.text
    return ""


def link_for(element):
    text = child_text(element, ["link"])
    if text.startswith("http"):
        return text.strip()

    for child in list(element):
        if child.tag.split("}")[-1] == "link" and child.attrib.get("href"):
            return child.attrib["href"]
    return text.strip()


def collect_feeds(opml_path: Path):
    root = ET.parse(opml_path).getroot()
    body = root.find("body")
    feeds = []

    def walk(node, folders):
        title = node.attrib.get("text") or node.attrib.get("title") or ""
        if node.attrib.get("xmlUrl"):
            feeds.append(
                {
                    "title": title,
                    "xmlUrl": node.attrib["xmlUrl"],
                    "htmlUrl": node.attrib.get("htmlUrl", ""),
                    "folders": list(folders),
                }
            )
            return

        next_folders = folders + ([title] if title else [])
        for child in list(node):
            if child.tag.endswith("outline"):
                walk(child, next_folders)

    for child in list(body):
        if child.tag.endswith("outline"):
            walk(child, [])

    return [feed for feed in feeds if any(folder.lower() == "sem" for folder in feed["folders"])]


def fetch_recent_items(feeds, cutoff):
    items = []
    errors = []
    user_agent = "Mozilla/5.0 (compatible; ChasPPCDailyBrief/1.0)"

    for feed in feeds:
        try:
            request = urllib.request.Request(feed["xmlUrl"], headers={"User-Agent": user_agent})
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = response.read(2_000_000)

            document = ET.fromstring(payload)
            entries = []
            entries.extend(document.findall(".//item"))
            entries.extend(document.findall(".//{http://www.w3.org/2005/Atom}entry"))

            for entry in entries[:25]:
                title = strip_html(child_text(entry, ["title", "atom:title"]))
                link = link_for(entry)
                date_text = child_text(
                    entry,
                    ["pubDate", "published", "updated", "atom:published", "atom:updated", "dc:date"],
                )
                published = parse_date(date_text)
                if published is None or published < cutoff:
                    continue

                summary = strip_html(
                    child_text(entry, ["description", "summary", "atom:summary", "content:encoded"])
                )
                if len(summary) > 560:
                    summary = summary[:560].rsplit(" ", 1)[0] + "..."

                if title and link:
                    items.append(
                        {
                            "feed": feed["title"],
                            "title": title,
                            "link": link,
                            "published": published.isoformat(),
                            "summary": summary,
                        }
                    )
        except Exception as exc:
            errors.append({"feed": feed["title"], "url": feed["xmlUrl"], "error": str(exc)[:240]})

    items.sort(key=lambda item: item["published"], reverse=True)
    deduped = []
    seen = set()
    for item in items:
        key = (re.sub(r"\W+", "", item["title"].lower())[:90], item["link"].split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped, errors


def score_item(item):
    haystack = f"{item['title']} {item.get('summary', '')} {item.get('feed', '')}".lower()
    score = sum(3 for keyword in PRIORITY_KEYWORDS if keyword in haystack)
    if "ppc" in haystack:
        score += 4
    if "google" in haystack:
        score += 2
    if "ads" in haystack or "advertising" in haystack:
        score += 2
    if "vpn" in haystack or "recipe" in haystack:
        score -= 4
    return score


def select_items(items, limit=8):
    selected = sorted(items, key=lambda item: (score_item(item), item["published"]), reverse=True)
    return selected[:limit]


def sentence_for(item):
    summary = item.get("summary") or ""
    if summary:
        return summary.rstrip(".")
    return item["title"].rstrip(".")


def build_script(selected, now):
    date = now.strftime("%B %d, %Y").replace(" 0", " ")
    if not selected:
        return (
            f"Chas's PPC Daily Brief for {date}.\n\n"
            "There were no fresh SEM or PPC items in the exported feed folder over the last 24 hours. "
            "For today, the best move is a maintenance pass: check yesterday's anomalies, review search term drift, "
            "scan Performance Max placement and asset data, and make sure any major account changes have enough time "
            "to exit the learning period before drawing conclusions."
        )

    lines = [
        f"Chas's PPC Daily Brief for {date}.",
        "",
        "Here are the paid media and search stories worth carrying into today's work.",
        "",
    ]

    transitions = [
        "First",
        "Second",
        "Third",
        "Fourth",
        "Fifth",
        "Sixth",
        "Seventh",
        "Finally",
    ]

    for index, item in enumerate(selected):
        transition = transitions[index] if index < len(transitions) else "Next"
        title = item["title"].rstrip(".")
        summary = sentence_for(item)
        if len(summary) < 80:
            summary = f"{summary}. The useful question is what this changes for budget, measurement, or channel mix"

        lines.append(
            f"{transition}: {title}. {summary}. "
            "For a PPC operator, the practical read is to separate the headline from the account impact: "
            "does this affect bidding, feed quality, creative testing, measurement, or where budget should move next?"
        )
        lines.append("")

    lines.append(
        "The thread through today's brief is visibility. Automation keeps getting more capable, but the edge still goes "
        "to teams that can explain where the money went, what changed behavior, and what would have happened anyway."
    )
    return "\n".join(lines).strip()


def build_summary(selected, total_count, now):
    date = now.strftime("%B %d, %Y").replace(" 0", " ")
    lines = [
        "# Chas's PPC Daily Brief",
        "",
        f"Generated on {date} from the Feedly OPML SEM folder using items published in the last 24 hours.",
        f"Recent items found: {total_count}. Selected for episode: {len(selected)}.",
        "",
        "## Sources",
        "",
    ]
    if selected:
        for item in selected:
            lines.append(f"- {item['title']} ({item['feed']}): {item['link']}")
    else:
        lines.append("- No fresh SEM/PPC feed items found in the last 24 hours.")
    return "\n".join(lines) + "\n"


def make_cover(path: Path, now):
    from PIL import Image, ImageDraw, ImageFont

    width = height = 1400
    image = Image.new("RGB", (width, height), "#101820")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 980, width, height], fill="#F2AA4C")
    draw.rectangle([90, 90, width - 90, height - 90], outline="#F2AA4C", width=8)
    draw.rectangle([120, 1010, width - 120, 1260], fill="#101820")

    def load_font(size, bold=False):
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size)
        return ImageFont.load_default()

    draw.text((135, 150), "PRIVATE DAILY RADIO", font=load_font(54, True), fill="#F2AA4C")
    draw.text((135, 310), "Chas's", font=load_font(126, True), fill="white")
    draw.text((135, 455), "PPC Daily", font=load_font(126, True), fill="white")
    draw.text((135, 600), "Brief", font=load_font(126, True), fill="white")
    draw.text((135, 810), "Paid search, retail media, CTV, and ad tech signals.", font=load_font(58), fill="#D8DEE9")
    draw.text((155, 1055), now.strftime("%A, %B %d").replace(" 0", " ").upper(), font=load_font(48), fill="white")
    draw.text((155, 1120), "FIVE-MINUTE OPERATOR BRIEF", font=load_font(42), fill="white")
    image.save(path, quality=94)


async def render_audio(script_path: Path, audio_path: Path, subtitles_path: Path, voice: str):
    import edge_tts

    text = script_path.read_text(encoding="utf-8")
    communicate = edge_tts.Communicate(text=text, voice=voice)
    submaker = edge_tts.SubMaker()
    with audio_path.open("wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
    subtitles_path.write_text(submaker.get_srt(), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opml", default=r"C:\Users\chasd\AppData\Local\Temp\subscriptions.opml")
    parser.add_argument("--out-dir", default="ppc_daily_brief")
    parser.add_argument("--voice", default="en-US-AriaNeural")
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()

    opml_path = Path(args.opml)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)

    feeds = collect_feeds(opml_path)
    items, errors = fetch_recent_items(feeds, cutoff)
    selected = select_items(items)

    run_date = datetime.now().strftime("%Y-%m-%d")
    script_path = out_dir / "episode_script.txt"
    summary_path = out_dir / "episode_summary.md"
    feed_items_path = out_dir / "feed_items.json"
    selected_path = out_dir / "selected_sources.json"
    cover_path = out_dir / "cover.jpg"
    audio_path = out_dir / f"chas_ppc_daily_brief_{run_date}.mp3"
    latest_audio_path = out_dir / "chas_ppc_daily_brief.mp3"
    subtitles_path = out_dir / f"chas_ppc_daily_brief_{run_date}.srt"

    script = build_script(selected, datetime.now())
    script_path.write_text(script, encoding="utf-8")
    summary_path.write_text(build_summary(selected, len(items), datetime.now()), encoding="utf-8")
    feed_items_path.write_text(
        json.dumps(
            {
                "generated_at": now.isoformat(),
                "cutoff": cutoff.isoformat(),
                "feed_count": len(feeds),
                "items": items,
                "errors": errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    selected_path.write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")
    make_cover(cover_path, datetime.now())
    asyncio.run(render_audio(script_path, audio_path, subtitles_path, args.voice))
    latest_audio_path.write_bytes(audio_path.read_bytes())

    result = {
        "audio": str(audio_path.resolve()),
        "latest_audio": str(latest_audio_path.resolve()),
        "cover": str(cover_path.resolve()),
        "summary": str(summary_path.resolve()),
        "script": str(script_path.resolve()),
        "selected_count": len(selected),
        "recent_count": len(items),
    }
    (out_dir / "latest_run.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
