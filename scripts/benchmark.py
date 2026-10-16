"""v0.4 model benchmark: candidate Ollama models on a fixed scoring sample.

Usage:
    python scripts/benchmark.py
    python scripts/benchmark.py --models qwen3:1.7b gemma3:1b lfm2.5
    python scripts/benchmark.py --host http://127.0.0.1:11434

Missing models are skipped (no auto-download). Needs Ollama running.
Compares: latency per call, JSON-valid rate, score spread on good-vs-bad
parts. Higher spread + faster + valid = better for the 1.7B-class job.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from precutter import score as score_mod

SAMPLE = [
    {"id": 0, "start": 0.0, "end": 18.5,
     "text": "herkese selam bugün yeni bölümdeyiz bakalım neler olacak"},
    {"id": 1, "start": 18.5, "end": 30.0,
     "text": "ıı şey yani ben ben şunu demek istedim hani şey yapalım"},
    {"id": 2, "start": 30.0, "end": 47.0,
     "text": "inanılmaz bir gol oldu tribünler yıkıldı tekrar izleyelim"},
    {"id": 3, "start": 47.0, "end": 55.0,
     "text": "dur dur baştan alıyorum üç iki bir kayıt tekrar"},
    {"id": 4, "start": 55.0, "end": 70.0,
     "text": "minecraftta elmas bulmanın en hızlı yolu derin kayrak seviyesi"},
    {"id": 5, "start": 70.0, "end": 78.0,
     "text": "off ya öldüm öldüm neyse neyse devam devam ediyoruz"},
    {"id": 6, "start": 78.0, "end": 95.0,
     "text": "yorumlara yazın sizce hangi taktiği deneyelim anket açtım"},
    {"id": 7, "start": 95.0, "end": 100.0,
     "text": "e e şey tamam tamam sustum devam et"},
]

# Good parts should score clearly above bad ones.
GOOD = {0, 2, 4, 6}
BAD = {1, 3, 5, 7}


def bench_model(host: str, model: str, rounds: int = 2) -> dict:
    latencies: list[float] = []
    valid = 0
    spreads: list[float] = []
    last_err = ""
    for _ in range(rounds):
        t0 = time.time()
        try:
            out = score_mod.score_batch(
                host, model, SAMPLE, "Minecraft gameplay", "tr")
            dt = time.time() - t0
            latencies.append(dt)
            valid += 1
            good = [s for i, (s, _) in out.items() if i in GOOD]
            bad = [s for i, (s, _) in out.items() if i in BAD]
            if good and bad:
                spreads.append(sum(good) / len(good) - sum(bad) / len(bad))
        except score_mod.OllamaError as exc:
            last_err = str(exc)
    return {
        "model": model,
        "calls": rounds,
        "valid": valid,
        "avg_latency_s": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "avg_spread": round(sum(spreads) / len(spreads), 1) if spreads else None,
        "error": last_err if not valid else "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark v0.4 scoring models.")
    ap.add_argument("--models", nargs="+",
                    default=["qwen3:1.7b", "gemma3:1b", "lfm2.5"])
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--rounds", type=int, default=2)
    args = ap.parse_args()
    print(f"{'model':<16}{'valid':<8}{'lat(s)':<8}{'spread':<8}note")
    for model in args.models:
        r = bench_model(args.host, model, args.rounds)
        lat = str(r["avg_latency_s"]) if r["avg_latency_s"] is not None else "-"
        spread = str(r["avg_spread"]) if r["avg_spread"] is not None else "-"
        note = "" if r["valid"] else r["error"][:70]
        print(f"{r['model']:<16}{r['valid']}/{r['calls']:<7}{lat:<8}{spread:<8}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
