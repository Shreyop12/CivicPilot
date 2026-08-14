# CivicPilot

An agent that answers questions about US federal government activity — proposed
rules, and the spending related to them — by orchestrating purpose-built MCP
servers over Federal Register and USAspending data.

## Install

```
pip install -e .
```

## Configuration

CivicPilot calls Groq's API for the underlying LLM. Set the required
environment variable before running:

```
export GROQ_API_KEY=your-api-key-here
```

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
