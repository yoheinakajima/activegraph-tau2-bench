# tau2 model baseline run

- status: `tau2_model_baseline_passed`
- reason: tau2 completed successfully
- paid API acknowledgement: `True`
- provider: `openai`
- model: `gpt-4.1-mini`
- tau2 model name: `openai/gpt-4.1-mini`
- domain: `mock`
- task_id: `create_task_1`
- num_tasks: `1`
- max_steps: `2`
- concurrency: `1`
- tau2 output path: `runs/20260531-042306-420109/tau2_output`
- returncode: `0`

## tau2 command

```bash
cd vendor/tau2-bench && uv run tau2 run --domain mock --agent llm_agent --agent-llm openai/gpt-4.1-mini --user user_simulator --user-llm openai/gpt-4.1-mini --num-trials 1 --max-steps 2 --max-concurrency 1 --save-to /Users/yoheinakajima/activegraph-tau2-bench/runs/20260531-042306-420109/tau2_output --log-level INFO --task-ids create_task_1
```

## API key-like environment variable presence

- `ANTHROPIC_API_KEY`: `True`
- `AWS_ACCESS_KEY_ID`: `False`
- `AWS_SECRET_ACCESS_KEY`: `False`
- `AZURE_OPENAI_API_KEY`: `False`
- `COHERE_API_KEY`: `False`
- `DEEPSEEK_API_KEY`: `False`
- `FIREWORKS_API_KEY`: `False`
- `GEMINI_API_KEY`: `False`
- `GOOGLE_API_KEY`: `False`
- `GOOGLE_APPLICATION_CREDENTIALS`: `False`
- `GOOGLE_CLOUD_PROJECT`: `False`
- `GROQ_API_KEY`: `False`
- `MISTRAL_API_KEY`: `False`
- `OPENAI_API_KEY`: `True`
- `OPENROUTER_API_KEY`: `False`
- `PERPLEXITYAI_API_KEY`: `False`
- `PERPLEXITY_API_KEY`: `False`
- `TOGETHER_API_KEY`: `False`
- `XAI_API_KEY`: `False`

No API key values are printed or stored by this wrapper.

## Copied tau2 artifacts

- `runs/20260531-042306-420109/tau2_artifacts/results.json` copied from `runs/20260531-042306-420109/tau2_output/results.json`
