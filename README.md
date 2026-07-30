# NWK Rank-up Bot

Pings the Noobs With Keyboards Discord when a clan member crosses a Total
Level rank threshold, so promotions never get missed.

```
Wise Old Man group 12678 (everyone's stats, auto-updated on logout
      │                    by members running the WOM RuneLite plugin)
      │  GitHub Actions cron, every 30 min
      ▼
rankup_bot.py — compares levels vs the rank table, remembers what it
      │         already announced (state.json)
      ▼
Discord webhook → 🎉 "Onyx hit TL 1000 — due for the 💚 Emerald rank!"
```

## Rank table

From the clan's "How to Rank Up" doc:

| TL | Rank |
|------|------------------|
| 500 | 🩷 Red Topaz |
| 750 | 💙 Sapphire |
| 1000 | 💚 Emerald |
| 1500 | ❤️ Ruby |
| 1750 | 🤍 Diamond |
| 2000 | 💜 Dragonstone |
| 2150 | 🖤 Onyx |
| 2300 | 🧡 Zenyte |
| 2376 | 🔥 Maxed |

To change it, edit `THRESHOLDS` in `rankup_bot.py`.

## How it works

- Every 30 minutes, GitHub Actions runs `rankup_bot.py`.
- The script reads the [Wise Old Man group hiscores](https://wiseoldman.net/groups/12678)
  for everyone's total level. WOM updates a player whenever they log out with
  the WOM RuneLite plugin installed, so alerts land within ~30 min of logout.
- `state.json` holds each member's last known level. A member is announced
  only when their current rank tier is higher than the one on record —
  each promotion pings exactly once.
- New members (and the very first run) are seeded silently: no retroactive
  pings for ranks earned before the bot was watching.
- Members who leave the clan/group are dropped from state automatically.

## Setup (already done, recorded for posterity)

1. Repo secret `DISCORD_WEBHOOK_URL` → the channel webhook
   (Settings → Secrets and variables → Actions).
2. Optional repo secret `WOM_VERIFICATION_CODE` → the WOM group's
   verification code. With it, each run asks WOM to refresh outdated
   members, so clanmates without the RuneLite plugin are covered too.
3. That's it. `workflow_dispatch` lets you trigger a manual run from the
   Actions tab to test.

## Local testing

```sh
python3 rankup_bot.py --dry-run   # fetches + prints, never posts to Discord
```

No dependencies — Python 3 stdlib only.

## Operations

- **Is it running?** → Actions tab. Green every ~30 min. A red run
  self-heals on the next tick (usually WOM rate limiting); only investigate
  if several in a row fail.
- **Manual run** → Actions → Rank-up alerts → Run workflow.
- **Change cadence** → the `cron:` line in `.github/workflows/rankups.yml`.
- **Change the rank table** → `THRESHOLDS` in `rankup_bot.py`.
- **Webhook leaked / channel change** → Discord channel → Integrations →
  Webhooks (regenerate or repoint), then update the `DISCORD_WEBHOOK_URL`
  secret.
- **Secrets** (Settings → Secrets and variables → Actions):
  - `DISCORD_WEBHOOK_URL` — required, where alerts go
  - `WOM_VERIFICATION_CODE` — optional, enables auto-refresh of stale members
  - `WOM_API_KEY` — optional, lifts WOM rate limits; not currently needed
- **Someone got announced wrong / re-announce someone** → edit their entry in
  `state.json` (lower the level to re-trigger, raise it to suppress).

## Branching

`main` is protected — changes go through a PR from `dev` (or a feature
branch). Scheduled runs commit `state.json` to `main` via a deploy key,
which is a ruleset bypass actor.

## Gotchas learned the hard way

- The WOM group-hiscores endpoint ignores `limit`/`offset` and returns the
  full member list in one response. Do not paginate it — that loops forever
  and rate-limits you into oblivion.
- WOM sends very large `Retry-After` values; sleeps are capped at 120s and
  the whole job at 15 min so a bad day fails fast instead of burning
  Actions minutes.
