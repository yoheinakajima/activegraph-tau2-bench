# tau2 source map (blocked)

- Date (UTC): 2026-05-26
- Upstream repo: https://github.com/sierra-research/tau2-bench
- Upstream commit hash: **unavailable (vendoring blocked by network policy)**

## Status

Vendoring attempts failed in this environment with HTTP 403 / CONNECT tunnel failures, so this file intentionally avoids pretending source inspection succeeded.

Attempted commands:

```bash
git clone https://github.com/sierra-research/tau2-bench vendor/tau2-bench
git clone --depth 1 https://github.com/sierra-research/tau2-bench vendor/tau2-bench
curl -L -f https://github.com/sierra-research/tau2-bench/archive/refs/heads/main.tar.gz -o /tmp/tau2-bench-main.tar.gz
```

## Required follow-up once network access is available

1. Vendor source into `vendor/tau2-bench/`.
2. Record exact provenance:
   - `git -C vendor/tau2-bench rev-parse HEAD`
   - `git -C vendor/tau2-bench remote -v`
   - `git -C vendor/tau2-bench branch --show-current`
   - `git -C vendor/tau2-bench describe --tags --always --dirty`
3. Replace this blocked placeholder with a real source map for:
   - CLI/run entrypoints
   - half-duplex interface
   - orchestrator / turn loop
   - user simulator
   - environment state
   - tools / policy / task data
   - evaluation/scoring and output format
   - seed/reproducibility knobs
   - no-LLM smoke candidates
