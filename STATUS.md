# Status and next steps (2026-10-07)

Where this project stands, so a new session can pick it up.

## What exists

| What | Where | State |
|---|---|---|
| Benchmark (this repo) | `~/proj/wait-bro-youre-a-bot`, [github](https://github.com/adamsro/wait-bro-youre-a-bot) | public, pushed |
| Raw benchmark data | `data/` here (git-ignored: real Reddit comments + usernames) | local only, never publish |
| Extension fork | `~/proj/bot-detector`, [github](https://github.com/adamsro/bot-detector), fork of [gkbii/bot-detector](https://github.com/gkbii/bot-detector) | pushed; AI-written score added in `c6b5866`; 228/228 tests pass |

## Decisions made (and why)

- **Fork gkbii/bot-detector rather than build from scratch.** It already does badges, Arctic Shift
  fetching (Reddit's own `about.json` 403s), queueing and caching, and has three deterministic scores
  (automation / agenda / authenticity, including the "unpopular positions on home turf" signal). It had
  nothing for LLM accounts that post at human pace. No upstream PRs planned; it's our fork.
- **AI-written = one LLM call per account, never per comment** (AUROC 0.97+ vs 0.75).
- **Judge model: `openai/gpt-6-luna` via OpenRouter, comment text only** (AUROC 0.997, ~$0.00025 per
  account). Haiku 5.5 works but misses more casual bots. gpt-oss / Mistral Small are near coin-flip.
  DeepSeek V4 Flash costs more than Haiku because of reasoning tokens. Opus was dropped as too expensive
  and unnecessary: we generate the AI accounts, so the labels are known.
- **Prompt judges behavior, not typography** (em-dashes etc. are trivially avoided by a bot prompt).
- **Bands** for the extension: judge raw score < 15 low, 15-49 moderate, 50+ high.
- **Key handling:** OpenRouter key in the extension options, stored in `chrome.storage.local` (not sync).

## Open items

1. **Load the extension in Chrome and use it on real threads** (not done yet; needs the owner):
   `chrome://extensions` → Developer mode → Load unpacked → `~/proj/bot-detector/extension`, then
   paste the OpenRouter key in the extension options. Click "bot?" next to a username.
2. **Hidden-history marker**: show "history hidden" on the badge, and fall back to the archive.
   Arctic Shift archives comments at post time, so hidden profiles should still score; not verified.
3. **Free account signals into the judge prompt**: account age, karma, hidden flag, as facts at the top.
   Measure on the same 180 accounts first (~$0.05 with Luna, `--no-context`).
4. **Harder AI accounts**: the casual prompt is easy mode. Add a third style that's actively tuned to
   evade (persona, typos, uneven effort) and re-measure.
5. **Real bot ground truth**: r/TheseFuckingAccounts reports or Bot Bouncer bans as a test set beyond
   self-generated bots.
6. Unfinished judges: Qwen 3.8 Flash and Gemma 4 stopped early (16 and 6 accounts); low priority.
7. **The post** (owner's idea for attention): lead with the finding, not the extension, e.g.
   "I tested whether cheap AI models can spot AI-written Reddit accounts". Candidate subs:
   r/TheseFuckingAccounts, r/dataisbeautiful (needs an [OC] chart), r/SideProject. Credit gkbii.

## Traps found

- **Reasoning models eat `max_tokens`**: Gemini/GPT/Qwen-flash returned empty or cut-off text at
  200-600 tokens. Judges use `max_tokens=4000` + `reasoning: low`; generation rejects
  `finish_reason=length` and refusals. Cut-off AI replies made every judge look better than it was.
- **Arctic Shift throttles with HTTP 422** ("Timeout. Maybe slow down a bit"), not 429; subreddit-wide
  searches need narrow time windows. `common.arctic()` retries with backoff.
- **Extension cache**: verdicts are cached 12 h, so accounts checked before saving the key need "Re-check".

## Rerun the benchmark

```bash
cd ~/proj/wait-bro-youre-a-bot
echo 'OPENROUTER_API_KEY=...' > .env          # or export it
python3 judge.py openai/gpt-6-luna --no-context  # reuses data/ if present
python3 score.py
```

Fresh data from scratch: `collect_human.py`, then `generate_ai.py` (~$1), then judges.
