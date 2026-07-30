#!/usr/bin/env python3
"""NWK rank-up alerts.

Watches the Noobs With Keyboards Wise Old Man group and posts a Discord
webhook message whenever a member crosses a Total Level rank threshold.

Runs on a schedule (GitHub Actions cron). State lives in state.json next to
this file: the last known total level per member, so each threshold is only
announced once. New members are seeded silently — no retroactive pings.

Usage:
    DISCORD_WEBHOOK_URL=... python3 rankup_bot.py
    python3 rankup_bot.py --dry-run   # fetch + print, no Discord post
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

GROUP_ID = 12678  # Noobs With Keyboards — https://wiseoldman.net/groups/12678
WOM_API = "https://api.wiseoldman.net/v2"
USER_AGENT = "nwk-rankup-bot (Noobs With Keyboards clan rank-up alerts)"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
PAGE_SIZE = 50  # WOM API max per page

# The clan's "How to Rank Up" table, highest first.
THRESHOLDS = [
    (2376, "Maxed", "🔥"),
    (2300, "Zenyte", "🧡"),
    (2150, "Onyx", "🖤"),
    (2000, "Dragonstone", "💜"),
    (1750, "Diamond", "🤍"),
    (1500, "Ruby", "❤️"),
    (1000, "Emerald", "💚"),
    (750, "Sapphire", "💙"),
    (500, "Red Topaz", "🩷"),
]


def rank_for(level):
    """Highest threshold at or below `level`, or None below the first rank."""
    for threshold in THRESHOLDS:
        if level >= threshold[0]:
            return threshold
    return None


def get_json(url, attempts=4):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == attempts - 1:
                raise
            # Cap the sleep: WOM sends huge Retry-After values to shared IPs
            # (e.g. GitHub runners); better to fail fast and let the next
            # scheduled run try than to burn billed minutes sleeping.
            wait = min(int(err.headers.get("Retry-After") or 0) or 30 * (attempt + 1), 120)
            print(f"Rate limited by WOM, retrying in {wait}s...")
            time.sleep(wait)


def fetch_levels():
    """username -> {name, level} for every group member, via group hiscores."""
    levels = {}
    offset = 0
    while True:
        page = get_json(
            f"{WOM_API}/groups/{GROUP_ID}/hiscores"
            f"?metric=overall&limit={PAGE_SIZE}&offset={offset}"
        )
        for row in page:
            player = row["player"]
            level = (row.get("data") or {}).get("level")
            if level:
                levels[player["username"]] = {
                    "name": player["displayName"],
                    "level": level,
                }
        if len(page) < PAGE_SIZE:
            return levels
        offset += PAGE_SIZE


def post_discord(lines):
    url = os.environ["DISCORD_WEBHOOK_URL"]
    # Chunk to stay under Discord's 2000-char content limit.
    chunk = []
    for line in lines + [None]:
        if line is None or len("\n".join(chunk + [line])) > 1900:
            if chunk:
                body = json.dumps(
                    {"content": "\n".join(chunk), "allowed_mentions": {"parse": []}}
                ).encode()
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp.read()
            chunk = []
        if line is not None:
            chunk.append(line)


def request_group_update():
    """Ask WOM to refresh outdated members, so clanmates without the RuneLite
    plugin still get their rank-ups noticed. No-op without the group's
    verification code (optional WOM_VERIFICATION_CODE secret)."""
    code = os.environ.get("WOM_VERIFICATION_CODE")
    if not code:
        return
    body = json.dumps({"verificationCode": code}).encode()
    req = urllib.request.Request(
        f"{WOM_API}/groups/{GROUP_ID}/update-all",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        print("Requested WOM refresh of outdated members.")
    except urllib.error.HTTPError as err:
        # 429 just means we asked again too soon — refresh is best-effort.
        print(f"Group refresh request skipped (HTTP {err.code}).")


def main():
    dry_run = "--dry-run" in sys.argv

    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    players = state.setdefault("players", {})
    first_run = not players

    request_group_update()
    current = fetch_levels()

    alerts = []
    for username, info in sorted(current.items()):
        prev = players.get(username)
        players[username] = info
        if prev is None:
            continue  # first run or new member: seed silently
        new_rank = rank_for(info["level"])
        old_rank = rank_for(prev["level"])
        if new_rank and new_rank != old_rank:
            threshold, rank_name, emoji = new_rank
            if threshold == 2376:
                alerts.append(
                    f"🎉🔥 **{info['name']}** just hit **TL 2376 — MAXED TOTAL!** "
                    f"Due for the {emoji} **{rank_name}** rank!"
                )
            else:
                alerts.append(
                    f"🎉 **{info['name']}** hit **TL {info['level']}** — "
                    f"due for the {emoji} **{rank_name}** rank ({threshold}+)!"
                )

    # Forget members who left the group.
    for username in list(players):
        if username not in current:
            del players[username]

    if alerts:
        print("\n".join(alerts))
        if not dry_run:
            post_discord(alerts)
    else:
        print(f"No rank-ups. Tracking {len(players)} members.")

    if first_run:
        print(f"First run: seeded {len(players)} members, no alerts sent.")

    # Dry runs never advance state, except the very first run, which writes
    # the seed so the real bot alerts from day one instead of re-seeding.
    if not dry_run or first_run:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
            f.write("\n")


if __name__ == "__main__":
    main()
