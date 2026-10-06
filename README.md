# cost-aware-swe-agent

A small coding agent that fixes real GitHub issues from [SWE-bench Lite](https://www.swebench.com/),
built to answer one question: **how much bug-fixing ability can you get per dollar?**

> Status: work in progress. Results will be added as experiments run.

## Design

- **Minimal loop**: the model replies with one ```` ```bash ```` command per turn. That text protocol works
  even with small local models that don't support function calling.
- **Sandboxed execution**: commands run inside a Docker container with only the task repo mounted and no network.
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

# Score with the official harness
scripts/evaluate.sh smoke
```

## Roadmap

- [ ] Baseline: local 7B model on a fixed 30-task subset
- [ ] Cheap API model on the same subset
- [ ] Router: cheap model navigates, stronger model writes the patch
- [ ] Reproduce-first: require a failing test before editing
- [ ] Failure taxonomy (wrong file, bad edit, step limit, ...)
- [ ] Results table: solve rate vs. $/task vs. time

## Results

| Config | Tasks | Resolved | $/task | Avg steps |
|---|---|---|---|---|
| _coming soon_ | | | | |
