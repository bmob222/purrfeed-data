#!/usr/bin/env python3
"""Purrfeed catalog builder.

Pulls vertical kitten/cat videos from the official Pexels API and writes catalog.json,
which the Purrfeed app reads from GitHub Pages. The API key never ships in the app, and one
daily run (a few dozen requests) stays far under Pexels' 25k/month limit no matter how many
people use the app.

Pexels API guidelines honoured: every item carries the creator name + profile URL and the
Pexels page URL, and the app shows "Video by <name> on Pexels" linking back.

    python3 build_catalog.py            # rebuild catalog.json
    python3 build_catalog.py --publish  # rebuild + git commit + push
"""
import json, random, ssl, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = (Path.home() / ".pexels_key").read_text().strip()
try:
    import certifi                          # python.org / framework builds ship no CA bundle
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()

# (search query, theme) — theme drives which affiliate products show next to the video
QUERIES = [
    ("kitten", "cute"), ("kittens", "cute"), ("cute kitten", "cute"),
    ("kitten playing", "play"), ("cat playing", "play"), ("cat toy", "play"),
    ("kitten sleeping", "sleepy"), ("cat sleeping", "sleepy"), ("cat bed", "sleepy"),
    ("cat eating", "food"), ("cat drinking water", "food"),
    ("funny cat", "funny"), ("cat jumping", "funny"),
    ("cat grooming", "care"), ("cat brushing", "care"),
    ("cat scratching", "home"), ("cat window", "home"), ("cat box", "home"),
]
PAGES_PER_QUERY = 2
MIN_S, MAX_S = 4, 45


def api(path, **params):
    url = f"https://api.pexels.com/videos/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": KEY, "User-Agent": "purrfeed-catalog/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.load(r)


def pick_file(files, want_w):
    """Portrait mp4 closest to want_w wide (without going under 540)."""
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
           and f["height"] > f["width"] and f["width"] >= 540]
    if not mp4:
        return None
    return min(mp4, key=lambda f: (abs(f["width"] - want_w), -f["width"]))


def main():
    seen, videos = set(), []
    for q, theme in QUERIES:
        for page in range(1, PAGES_PER_QUERY + 1):
            try:
                d = api("search", query=q, orientation="portrait", size="medium", per_page=80, page=page)
            except Exception as e:
                print(f"  {q} p{page}: {e}", file=sys.stderr)
                continue
            for v in d.get("videos", []):
                if v["id"] in seen or not (MIN_S <= v.get("duration", 0) <= MAX_S):
                    continue
                sd, hd = pick_file(v["video_files"], 720), pick_file(v["video_files"], 1080)
                if not sd:
                    continue
                seen.add(v["id"])
                videos.append({
                    "id": f"px{v['id']}", "source": "pexels", "theme": theme,
                    "video": sd["link"], "video_hd": (hd or sd)["link"],
                    "poster": v.get("image"), "duration": v["duration"],
                    "width": sd["width"], "height": sd["height"],
                    "credit": v["user"]["name"], "credit_url": v["user"]["url"], "page_url": v["url"],
                })
            time.sleep(0.4)
        print(f"{q:<20} → {len(videos)} total")
    random.seed(datetime.now(timezone.utc).strftime("%Y-%m-%d"))   # new order each day
    random.shuffle(videos)
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "count": len(videos), "videos": videos}
    (HERE / "catalog.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"catalog.json: {len(videos)} videos")
    if "--publish" in sys.argv:
        subprocess.run(["git", "add", "catalog.json", "products.json"], cwd=HERE, check=True)
        r = subprocess.run(["git", "commit", "-qm", f"catalog refresh {out['generated']}"], cwd=HERE)
        if r.returncode == 0:
            subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=HERE, check=True)
            print("published")


if __name__ == "__main__":
    main()
