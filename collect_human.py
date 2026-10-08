"""Collect known-human Reddit accounts: comments written before ChatGPT launched (2022-11-30).

Samples authors from random 1-hour windows across varied subreddits, keeps authors with
enough substantive pre-cutoff comments, and attaches each comment's thread context
(post title/body + parent comment) so AI replies can be generated for the same threads.

Output: data/human.jsonl, one account per line.
"""

import argparse
import random
import re
from datetime import datetime, timedelta, timezone

from common import DATA, append_jsonl, arctic, read_jsonl, word_count

SUBS = [
    "AskReddit", "movies", "nba", "buildapc", "Cooking", "personalfinance", "gaming",
    "worldnews", "explainlikeimfive", "AskMen", "books", "technology", "relationship_advice",
    "fitness", "travel", "science",
]
CUTOFF = "2022-09-01"  # comfortably before ChatGPT's public launch
MIN_WORDS = 12
SKIP_BODY = {"[deleted]", "[removed]"}


def usable(body: str) -> bool:
    return body not in SKIP_BODY and word_count(body) >= MIN_WORDS and "i am a bot" not in body.lower()


def usable_row(r: dict) -> bool:
    """Skips moderator-distinguished comments, which are mostly canned templates."""
    return not r.get("distinguished") and usable(r.get("body", ""))


def candidate_authors(rng: random.Random, want: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    start, end = datetime(2018, 1, 1, tzinfo=timezone.utc), datetime(2022, 6, 1, tzinfo=timezone.utc)
    while len(out) < want:
        sub = rng.choice(SUBS)
        t = start + timedelta(seconds=rng.randrange(int((end - start).total_seconds())))
        rows = arctic(
            "comments/search", subreddit=sub, limit=100,
            after=t.strftime("%Y-%m-%dT%H:%M:%S"), before=(t + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            fields="author,body",
        )
        for r in rows:
            a = r.get("author") or ""
            if a in seen or a in ("[deleted]", "AutoModerator") or re.search(r"bot", a, re.I):
                continue
            if usable(r.get("body", "")):
                seen.add(a)
                out.append(a)
    rng.shuffle(out)
    return out


def contexts(comments: list[dict]) -> None:
    """Attach `context` (post title + selftext, plus parent comment when replying to one)."""
    link_ids = sorted({c["link_id"].removeprefix("t3_") for c in comments})
    parent_ids = sorted({c["parent_id"].removeprefix("t1_") for c in comments if c["parent_id"].startswith("t1_")})
    posts = {p["id"]: p for p in arctic("posts/ids", ids=",".join(link_ids), fields="id,title,selftext")}
    parents = {p["id"]: p for p in arctic("comments/ids", ids=",".join(parent_ids), fields="id,body")} if parent_ids else {}
    for c in comments:
        post = posts.get(c["link_id"].removeprefix("t3_"), {})
        selftext = (post.get("selftext") or "").strip()
        ctx = f"POST TITLE: {post.get('title', '(unknown)')}"
        if selftext and selftext not in SKIP_BODY:
            ctx += f"\nPOST BODY: {selftext[:600]}"
        if c["parent_id"].startswith("t1_"):
            parent = (parents.get(c["parent_id"].removeprefix("t1_"), {}).get("body") or "").strip()
            if not parent or parent in SKIP_BODY:
                c["context"] = None  # no usable thread to generate a matching AI reply for
                continue
            ctx += f"\nREPLYING TO COMMENT: {parent[:600]}"
        c["context"] = ctx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", type=int, default=60)
    ap.add_argument("--per", type=int, default=20, help="comments per account")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    out_path = DATA / "human.jsonl"
    done = {r["account"] for r in read_jsonl(out_path)}
    rng = random.Random(args.seed)
    authors = candidate_authors(rng, args.accounts * 3)
    kept = len(done)
    for author in authors:
        if kept >= args.accounts:
            break
        if author in done:
            continue
        rows = arctic("comments/search", author=author, before=CUTOFF, limit=100,
                      fields="body,subreddit,link_id,parent_id,created_utc,distinguished")
        good = [r for r in rows if usable_row(r)]
        if len({r["body"] for r in good}) < len(good) * 0.9:
            continue  # repeats itself: templated account, not a clean human sample
        rng.shuffle(good)
        good = good[: args.per * 2]
        contexts(good)
        picked = [c for c in good if c["context"]][: args.per]
        if len(picked) < args.per:
            continue
        append_jsonl(out_path, {"account": author, "label": "human", "comments": picked})
        kept += 1
        print(f"{kept}/{args.accounts} {author}")


if __name__ == "__main__":
    main()
