from __future__ import annotations

import argparse
import statistics
import time

from app.auth import SUPPORTED_TOKEN_ALGORITHMS, create_jwt_like_token, decode_and_verify_jwt_like_token


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _run_iterations(iterations: int, fn) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark supported token signing algorithms.")
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--warmup", type=int, default=500)
    args = parser.parse_args()

    payload = {
        "tid": "tok_perf",
        "sub": "usr_perf",
        "token_type": "user_token",
        "scopes": ["channels:read", "messages:write"],
        "iat": "2026-03-07T00:00:00Z",
    }
    signing_secret = "benchmark-secret"

    ranked: list[tuple[float, int, str]] = []
    for algorithm in SUPPORTED_TOKEN_ALGORITHMS:
        _run_iterations(
            args.warmup,
            lambda: create_jwt_like_token(payload, signing_secret, algorithm),
        )
        sign_samples = _run_iterations(
            args.iterations,
            lambda: create_jwt_like_token(payload, signing_secret, algorithm),
        )
        token = create_jwt_like_token(payload, signing_secret, algorithm)
        _run_iterations(
            args.warmup,
            lambda: decode_and_verify_jwt_like_token(token, signing_secret, algorithm),
        )
        verify_samples = _run_iterations(
            args.iterations,
            lambda: decode_and_verify_jwt_like_token(token, signing_secret, algorithm),
        )
        combined_samples = [sign + verify for sign, verify in zip(sign_samples, verify_samples)]
        ordered_combined = sorted(combined_samples)
        average_combined = statistics.fmean(ordered_combined)
        ranked.append((average_combined, len(token), algorithm))
        print(
            f"{algorithm}: token_bytes={len(token)} "
            f"sign_avg={statistics.fmean(sorted(sign_samples)):.4f}ms "
            f"verify_avg={statistics.fmean(sorted(verify_samples)):.4f}ms "
            f"combined_avg={average_combined:.4f}ms "
            f"combined_p50={_percentile(ordered_combined, 0.50):.4f}ms "
            f"combined_p95={_percentile(ordered_combined, 0.95):.4f}ms"
        )

    fastest = min(ranked)
    print(f"fastest={fastest[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
