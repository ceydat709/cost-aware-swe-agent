# cost-aware-swe-agent

[![tests](https://github.com/ceydat709/cost-aware-swe-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/ceydat709/cost-aware-swe-agent/actions/workflows/tests.yml)

A small coding agent that fixes real GitHub issues from [SWE-bench Lite](https://www.swebench.com/),
built to answer one question: **how much bug-fixing ability can you get per dollar?**

> Status: work in progress. Results will be added as experiments run.

## Design

- **Minimal loop**: the model replies with one ```` ```bash ```` command per turn. That text protocol works
  even with small local models that don't support function calling.
- **Sandboxed execution**: commands run inside the task's SWE-bench Docker image (dependencies preinstalled)
  with only the task repo mounted and no network.
- **Verify-before-submit** (`--verify`): a submit is rejected if the repo's existing related tests show
  regressions versus the original code. Hidden grading tests are never used.
- **Any OpenAI-compatible provider**: Ollama (local, free), OpenRouter, GitHub Models, Gemini. Switch with `--base-url`.
- **Response cache**: every LLM call is cached in SQLite, so re-running an experiment is free and reproducible.
- **Cost accounting**: tokens, dollars, steps and wall time are logged per task (`runs/<name>/costs.jsonl`).

## Quickstart

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,eval]"
pytest

# Local model (free)
ollama pull qwen2.5-coder:7b
swe-agent --model qwen2.5-coder:7b --limit 1 --run-name smoke
swe-agent --model qwen2.5-coder:7b --limit 1 --run-name smoke-verify --verify

# Sanity-check the harness with the reference patches
scripts/evaluate.sh gold psf__requests-2317

# Score with the official harness
scripts/evaluate.sh smoke
```

## Roadmap

- [ ] Baseline: local 7B model on a fixed 30-task subset
- [ ] Cheap API model on the same subset
- [ ] Router: cheap model navigates, stronger model writes the patch
- [x] Verify-before-submit: reject patches that break previously passing tests
- [ ] Reproduce-first: require a failing test before editing
- [ ] Failure taxonomy (wrong file, bad edit, step limit, ...)
- [ ] Results table: solve rate vs. $/task vs. time

## Notes

- On Apple Silicon, SWE-bench images run under x86 emulation: ~10 min to score one task locally.
- The sandbox has no network, so tests that need it fail on the original code too and can't flag
  regressions; verification sees a weaker signal than the grading harness.

## Results

| Config | Tasks | Resolved | $/task | Avg steps |
|---|---|---|---|---|
| _coming soon_ | | | | |
