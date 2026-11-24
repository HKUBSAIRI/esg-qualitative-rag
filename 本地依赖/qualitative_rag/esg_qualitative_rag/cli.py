from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run_benchmark, verify_published_results


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="esg-qualitative-rag")
    subparsers = root.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run the qualitative ESG retrieval benchmark")
    run.add_argument("--corpus-dir", type=Path, default=PROJECT_ROOT / "data" / "corpus")
    run.add_argument("--ground-truth-dir", type=Path, default=PROJECT_ROOT / "data" / "ground_truth")
    run.add_argument("--metrics", type=Path, default=PROJECT_ROOT / "data" / "metrics" / "metrics_53.json")
    run.add_argument("--output", type=Path, default=PROJECT_ROOT / "outputs" / "run")
    run.add_argument(
        "--embedding-cache",
        type=Path,
        default=PROJECT_ROOT / "results" / "no_reranker_20x53" / "embedding_cache",
    )
    run.add_argument("--metric-ids", type=int, nargs="+", default=list(range(1, 54)))
    run.add_argument("--candidate-k", type=int, default=150)
    run.add_argument("--top-k", type=int, default=50)

    verify = subparsers.add_parser("verify-results", help="recompute metrics from published results")
    verify.add_argument("--ground-truth-dir", type=Path, default=PROJECT_ROOT / "data" / "ground_truth")
    verify.add_argument(
        "--results-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "no_reranker_20x53" / "results",
    )
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "run":
        result = run_benchmark(
            corpus_dir=args.corpus_dir,
            ground_truth_dir=args.ground_truth_dir,
            metrics_path=args.metrics,
            output_dir=args.output,
            embedding_cache=args.embedding_cache,
            metric_ids=set(args.metric_ids),
            candidate_k=args.candidate_k,
            top_k=args.top_k,
        )
    else:
        result = verify_published_results(
            ground_truth_dir=args.ground_truth_dir,
            results_dir=args.results_dir,
            metric_ids=set(range(1, 54)),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

