# wait bro you're a bot

A quick, human-readable marker next to Reddit usernames: how likely the account is a bot,
and the evidence behind it, such as account age or whether the comment history is hidden.

## Idea

Score the **account**, not the single comment. One 40-word comment is too short for any
detector, but 20–50 comments from the same account together usually show a pattern.

### Account signals (cheap, no model)
- **Account age, karma, and gaps in activity.** Watch for new accounts with high activity, or long-dormant accounts that suddenly come alive.
- **Hidden profile history.** A visible history usually means a real person. There are valid
  reasons to hide your history, but a bot will probably keep its history private. Hidden history
  can still be partly recovered, because links to the account's comments keep appearing in search
  engine results (and in archives like Arctic Shift), but it takes more work.
- **Copied comments.** Karma-farming bots repost older top comments word for word. Check against the archive.
- **Restating the parent.** Bot replies often paraphrase the comment they answer while adding nothing new (embedding similarity).
- **Timing.** Posting around the clock, or replying faster than anyone could read and type.

### Writing signals (model needed)
- **LLM judge per account:** all of an account's recent comments go into one prompt, and the verdict is cached.
  Only run it on accounts the cheap signals leave undecided.
- **Binoculars and similar token-probability detectors:** these need probabilities for every token of
  the input text, which OpenAI-compatible endpoints (LM Studio, OpenRouter) don't provide. They need
  local transformers or vLLM `prompt_logprobs`.

Show the evidence behind each flag, not just a score. Every text detector flags
non-native English writers more often.

## Results

See [RESULTS.md](RESULTS.md). Short version: judge whole accounts, not comments; GPT-6 Luna reading
comment text only separated AI accounts from humans almost perfectly (AUROC 0.997) for ~$0.00025 per
account. The judge ships as the AI-written score in [adamsro/bot-detector](https://github.com/adamsro/bot-detector).

## Experiment: which cheap judge works?

1. `collect_human.py` collects known-human accounts. Their comments predate ChatGPT (before 2022-09), come from Arctic Shift, and are stored with their thread context.
2. `generate_ai.py` creates two AI accounts for each human account, replying to the same threads with matched lengths.
   One uses a plain prompt and the other is told to sound like a casual redditor. The generators are rotated: Gemini Flash, GPT Luna, Llama 4, and Qwen.
3. `judge.py <models…> [--unit account|comment]` asks each judge model for the probability that the account is AI, routed through OpenRouter.
4. `score.py` reports, for each judge, AUROC (how well its score separates AI accounts from human ones), the catch rate when no more than 5% of humans are wrongly flagged, the cost, and a breakdown by prompt style and generator.

```bash
python3 collect_human.py --accounts 60 --per 20
python3 generate_ai.py
python3 judge.py openai/gpt-6-luna anthropic/claude-haiku-5.5            # behavior prompt (v2), with thread context
python3 judge.py openai/gpt-6-luna --no-context                         # comment text only, as a browser extension sees it
python3 judge.py anthropic/claude-haiku-5.5 --unit comment --prompt v1  # single comments, for comparison
python3 score.py
```

The OpenRouter key is read from `OPENROUTER_API_KEY`, or from a `.env` file in this folder (`OPENROUTER_API_KEY=...`, git-ignored).

Caveats: the "human" accounts mean "pre-ChatGPT", so old-style bots such as repost bots can still be among them.
Judges from the same family as a generator may recognize their own model's writing, so check the breakdown by generator.
