"""Generate AI "accounts" that reply to the same threads as each human account.

For every human account, two AI accounts are made: one with a plain prompt and one
told to pass as a casual redditor. Each AI account uses a single generator model for
all its comments (a real bot runs one model with one prompt). Reply length targets the
matching human comment's length, so length alone can't give the answer away.

Output: data/ai.jsonl
"""

import argparse
import re
from concurrent.futures import ThreadPoolExecutor

from common import DATA, append_jsonl, chat, read_jsonl, word_count

GENERATORS = [
    "google/gemini-3.8-flash",
    "openai/gpt-5.6-luna",
    "meta-llama/llama-4-maverick",
    "qwen/qwen3-235b-a22b-2507",  # instruct (no hidden reasoning eating the token budget)
]

PROMPTS = {
    "plain": (
        "Write a reply to the following Reddit thread, as a comment in r/{sub}. "
        "Aim for about {n} words. Output only the comment text."
    ),
    "casual": (
        "You are a long-time redditor posting in r/{sub}. Reply to the thread below the way a real "
        "person types on Reddit: casual, opinionated, sometimes lowercase, no lists, no headers, no "
        "sign-offs, never sound like an assistant. Aim for about {n} words. Output only the comment text."
    ),
}


REFUSAL = re.compile(r"\bI (cannot|can't|won't|am unable to) (generate|help|provide|create|write)|\bas an AI\b", re.I)


def reply(model: str, system: str, context: str) -> tuple[str, dict] | None:
    """A complete, non-refusing reply, or None. Cut-off or refused text would leak the label."""
    for _ in range(3):
        text, usage = chat(model, system, context, max_tokens=4000, temperature=0.9, reasoning="low")
        if text and usage.get("finish_reason") != "length" and not REFUSAL.search(text):
            return text, usage
    return None


def generate_account(human: dict, style: str, model: str) -> dict:
    comments = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
    for c in human["comments"]:
        system = PROMPTS[style].format(sub=c["subreddit"], n=word_count(c["body"]))
        got = reply(model, system, c["context"])
        if got is None:
            continue  # a real bot operator would discard refusals too
        text, usage = got
        for k in usage_total:
            usage_total[k] += usage.get(k, 0) or 0
        comments.append({"body": text, "subreddit": c["subreddit"], "context": c["context"]})
    return {
        "account": f"ai_{style}_{human['account']}",
        "label": "ai",
        "style": style,
        "generator": model,
        "comments": comments,
        "usage": usage_total,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    humans = read_jsonl(DATA / "human.jsonl")
    out_path = DATA / "ai.jsonl"
    done = {r["account"] for r in read_jsonl(out_path)}
    jobs = []
    for i, h in enumerate(humans):
        for j, style in enumerate(PROMPTS):
            if f"ai_{style}_{h['account']}" not in done:
                jobs.append((h, style, GENERATORS[(i + j) % len(GENERATORS)]))

    with ThreadPoolExecutor(args.workers) as pool:
        for n, acct in enumerate(pool.map(lambda job: generate_account(*job), jobs), 1):
            append_jsonl(out_path, acct)
            print(f"{n}/{len(jobs)} {acct['account']} ({acct['generator']}) ${acct['usage']['cost']:.4f}")


if __name__ == "__main__":
    main()
