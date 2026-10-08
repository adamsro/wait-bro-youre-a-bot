"""Ask LLM judges how likely each account's comments are AI-written.

--unit account: one call per account with all its comments (the realistic setup).
--unit comment: one call per single comment (first comment of each account), to show
how much worse single-comment judging is.

Output: data/judge_<unit>_<model>.jsonl (resumable).
"""

import argparse
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor

from common import DATA, append_jsonl, chat, read_jsonl

SYSTEM_V1 = (
    "You review Reddit accounts for AI-generated writing. You will see comments from ONE account, "
    "each with a short snippet of the thread it replied to. Estimate the probability (0-100) that "
    "this account's comments were written by an AI language model rather than a person. "
    'Answer with JSON only: {"ai_probability": <0-100>, "reason": "<one sentence>"}'
)


# v2: judges behavior across the whole history, not surface tells a bot prompt can switch off.
SYSTEM_V2 = (
    "You review a Reddit account to estimate whether an AI language model writes its comments. "
    "You will see several comments from ONE account, each with a snippet of the thread it replied to.\n\n"
    "Judge the account as a whole. Ignore surface typography (dashes, quote styles, capitalization, "
    "slang, typos): bot operators can tell a model to fake or avoid any of these.\n"
    "Look instead at how the account behaves across its history:\n"
    "- Real people are uneven. Some comments are lazy, off-topic, half-joking, wrong, or only make sense "
    "to someone already in the conversation. Model-written accounts are consistently on point: every "
    "comment answers the thread directly, competently, and at a similar level of effort.\n"
    "- Models tend to round a comment off: a closing takeaway, a balanced caveat, a neat summary or quip.\n"
    "- Real people bring their own life: specific personal details, running interests, strong odd opinions, "
    "obscure knowledge, inside references. Models produce plausible but generic experience that could fit anyone.\n"
    "- Real people write differently in different places; model-written accounts keep one voice and one "
    "register everywhere.\n"
    "- Model replies often restate or paraphrase the comment they answer before adding to it.\n\n"
    "No single cue is proof; weigh the pattern across all comments. Estimate the probability (0-100) "
    "that this account's comments are AI-written.\n"
    'Answer with JSON only: {"ai_probability": <0-100>, "reason": "<one sentence>"}'
)
PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}


CONTEXT = True  # --no-context: comment text only, as the browser extension sees it


def render(comments: list[dict]) -> str:
    parts = []
    for i, c in enumerate(comments, 1):
        if CONTEXT:
            ctx = c["context"].replace("\n", " ")[:250]
            parts.append(f"<COMMENT n={i} subreddit={c['subreddit']}>\nTHREAD: {ctx}\nTEXT: {c['body']}\n</COMMENT>")
        else:
            parts.append(f"<COMMENT n={i} subreddit={c['subreddit']}>\n{c['body'][:400]}\n</COMMENT>")
    return "\n\n".join(parts)


def parse(text: str) -> float | None:
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return float(json.loads(m.group(0))["ai_probability"])
        except (ValueError, KeyError, TypeError):
            pass
    m = re.search(r"ai_probability\D*(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def judge(model: str, acct: dict, unit: str, system: str) -> dict:
    comments = list(acct["comments"])
    random.Random(acct["account"]).shuffle(comments)
    if unit == "comment":
        comments = comments[:1]
    # Judges are thinking models: low effort, with room for reasoning before the JSON.
    text, usage = chat(model, system, render(comments), max_tokens=4000, temperature=0, reasoning="low")
    return {
        "account": acct["account"],
        "label": acct["label"],
        "style": acct.get("style", "human"),
        "generator": acct.get("generator", "human"),
        "score": parse(text),
        "raw": text,
        "cost": usage.get("cost", 0) or 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--unit", choices=["account", "comment"], default="account")
    ap.add_argument("--limit", type=int, default=0, help="judge only the first N accounts of each label")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--prompt", choices=list(PROMPTS), default="v2")
    ap.add_argument("--no-context", action="store_true", help="omit thread snippets (what the extension sees)")
    args = ap.parse_args()
    global CONTEXT
    CONTEXT = not args.no_context

    humans, ais = read_jsonl(DATA / "human.jsonl"), read_jsonl(DATA / "ai.jsonl")
    if args.limit:
        humans, ais = humans[: args.limit], ais[: args.limit * 2]
    accounts = humans + ais

    for model in args.models:
        suffix = "" if args.prompt == "v1" else f"_{args.prompt}"  # v1 files predate the option
        suffix += "_noctx" if args.no_context else ""
        out_path = DATA / f"judge_{args.unit}_{model.replace('/', '_')}{suffix}.jsonl"
        done = {r["account"] for r in read_jsonl(out_path)}
        todo = [a for a in accounts if a["account"] not in done]
        cost = 0.0
        with ThreadPoolExecutor(args.workers) as pool:
            for row in pool.map(lambda a: judge(model, a, args.unit, PROMPTS[args.prompt]), todo):
                append_jsonl(out_path, row)
                cost += row["cost"]
        print(f"{model}: judged {len(todo)} accounts, ${cost:.3f}")


if __name__ == "__main__":
    main()
