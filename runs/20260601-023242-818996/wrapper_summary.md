# tau2 runtime traced baseline wrapper

- status: `tau2_runtime_traced_baseline_passed`
- reason: tau2 completed successfully
- provider: `openai`
- model: `gpt-4.1-mini`
- paid API acknowledgement: `True`
- tau2 executed: `True`
- returncode: `0`
- command: `/Users/yoheinakajima/activegraph-tau2-bench/.venv/bin/python /Users/yoheinakajima/activegraph-tau2-bench/experiments/tau2_runtime_trace/traced_tau2_cli.py run --domain airline --agent llm_agent --agent-llm openai/gpt-4.1-mini --user user_simulator --user-llm openai/gpt-4.1-mini --num-trials 1 --max-steps 30 --max-concurrency 1 --save-to /Users/yoheinakajima/activegraph-tau2-bench/runs/20260601-023242-818996/tau2_output --log-level INFO --task-ids 8`
- passive write-intent observer enabled: `True`

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

Provider env status: `{'known_provider': True, 'required_env_vars': ['OPENAI_API_KEY'], 'satisfied': True}`

No API key values are printed or stored by this wrapper.

## Copied tau2 artifacts

- `runs/20260601-023242-818996/tau2_artifacts/results.json` copied from `runs/20260601-023242-818996/tau2_output/results.json`
