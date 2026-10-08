"""Score judge outputs against the human/AI labels.

AUROC: chance a random AI account scores above a random human one (1.0 perfect, 0.5 coin flip).
Catch@5%: share of AI accounts caught at a threshold that wrongly flags at most 5% of humans.
"""

from collections import defaultdict

from common import DATA, read_jsonl


def auroc(pos: list[float], neg: list[float]) -> float:
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg)) if pos and neg else float("nan")


def catch_at(pos: list[float], neg: list[float], fpr: float) -> float:
    neg_sorted = sorted(neg, reverse=True)
    allowed = int(fpr * len(neg_sorted))
    threshold = neg_sorted[allowed] if allowed < len(neg_sorted) else float("-inf")
    return sum(p > threshold for p in pos) / len(pos) if pos else float("nan")


def main() -> None:
    files = sorted(DATA.glob("judge_*.jsonl"))
    print(f"{'judge':55} {'n':>4} {'AUROC':>6} {'catch@5%':>9} {'cost':>7}  per-subset AUROC")
    for f in files:
        rows = [r for r in read_jsonl(f) if r["score"] is not None]
        failed = len(read_jsonl(f)) - len(rows)
        neg = [r["score"] for r in rows if r["label"] == "human"]
        pos = [r["score"] for r in rows if r["label"] == "ai"]
        subsets = defaultdict(list)
        for r in rows:
            if r["label"] == "ai":
                subsets[r["style"]].append(r["score"])
                subsets[r["generator"].split("/")[-1]].append(r["score"])
        detail = "  ".join(f"{k}={auroc(v, neg):.2f}" for k, v in sorted(subsets.items()))
        cost = sum(r["cost"] for r in read_jsonl(f))
        name = f.stem.removeprefix("judge_") + (f" ({failed} unparsed)" if failed else "")
        print(f"{name:55} {len(rows):>4} {auroc(pos, neg):>6.3f} {catch_at(pos, neg, 0.05):>9.2f} ${cost:>6.3f}  {detail}")


if __name__ == "__main__":
    main()
