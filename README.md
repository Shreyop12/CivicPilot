# CivicPilot

An agent that answers questions about US federal government activity — proposed
rules, and the spending related to them — by orchestrating purpose-built MCP
servers over Federal Register and USAspending data.

## Install

```
pip install -e .
```

## Configuration

CivicPilot calls Groq's API for the underlying LLM. Provide the required
`GROQ_API_KEY` either as a real environment variable:

```
export GROQ_API_KEY=your-api-key-here
```

or by copying `.env.example` to `.env` and filling in your key(s):

```
cp .env.example .env
```

`.env` is loaded automatically on startup and is git-ignored — never commit
it.

### Optional: fallback LLM

Set `OPENROUTER_API_KEY` to enable failover. Groq (the primary) is retried
with short backoff on a rate limit (HTTP 429); if retries are exhausted, or
on any other error (5xx, timeout, network fault), CivicPilot fails over to
OpenRouter's free `openai/gpt-oss-20b:free` model for that call. Without
`OPENROUTER_API_KEY` set, CivicPilot runs on Groq alone and a Groq outage or
rate limit fails the whole query.

## Run

```
civicpilot
```

or, without the console script:

```
python -m civicpilot.main
```

## Tests

```
pytest
```
