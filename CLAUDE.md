# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a thermodynamic AI agents project built in Python that analyzes thermodynamic data for chemical compounds. The system uses a two-agent architecture:

1. **Thermo Agent** - Extracts parameters from user queries (compounds, temperature, phases, etc.)
2. **SQL Agent** - Generates SQL queries to retrieve thermodynamic data from the database

The agents use Agent-to-Agent (A2A) communication through PydanticAI framework and interact with a SQLite database containing thermodynamic compound data.

## Commands

### Environment Setup
```bash
# Install dependencies
uv sync

# Activate virtual environment
uv shell

# Run the main application
uv run python main.py
```

### Development
```bash
# Add new dependencies
uv add package-name

# Add development dependencies
uv add --dev package-name

# Run individual agent tests
uv run python src/thermo_agents/main_thermo_agent.py
uv run python src/thermo_agents/sql_agent.py
```

### Jupyter Notebooks
```bash
# Run Jupyter with the virtual environment
uv run python -m ipykernel

# Then select .venv (Python 3.12) kernel in VS Code
```

## Architecture

### Core Components

- **main.py** - Interactive CLI application entry point
- **src/thermo_agents/main_thermo_agent.py** - Primary agent for parameter extraction
- **src/thermo_agents/sql_agent.py** - SQL query generation agent
- **src/thermo_agents/prompts.py** - All system prompts for both agents
- **src/thermo_agents/thermo_agents_logger.py** - Session-based logging system

### Agent Flow

1. User input → Thermo Agent extracts parameters using `EXTRACT_INPUTS_PROMPT`
2. If SQL needed → SQL Agent generates query using extracted parameters
3. Both agents use OpenRouter/OpenAI API through PydanticAI
4. Session logging tracks all interactions in `logs/sessions/`

### Data Models

Key Pydantic models:
- `ExtractedParameters` - Output from thermo agent with compounds, temperature, phases, etc.
- `SQLQueryResult` - Output from SQL agent with query, explanation, expected columns
- `ThermoAgentConfig` - Dependency injection for agent configuration

### Configuration

Environment variables in `.env`:
- `OPENROUTER_API_KEY` - API key for LLM access
- `LLM_BASE_URL` - OpenRouter API endpoint
- `LLM_DEFAULT_MODEL` - Default LLM model (e.g., openai/gpt-oss-120b)
- `DB_PATH` - Path to thermodynamic database (data/thermo_data.db)
- `LOG_LEVEL` - Logging level (INFO, DEBUG, etc.)

### Database Schema

The `compounds` table contains:
- Chemical formulas, names, phases (s/l/g/aq)
- Thermodynamic properties: H298, S298, heat capacity coefficients f1-f6
- Temperature ranges (Tmin, Tmax), melting/boiling points
- 316,434 records with 32,790 unique chemical formulas

### Agent Patterns

- Uses dependency injection through dataclass configs
- Async/await pattern for all agent operations
- Structured output with Pydantic models
- Error handling with fallback responses
- Session logging for debugging and analysis

## Project Structure

```
src/thermo_agents/
├── __init__.py
├── main_thermo_agent.py    # Parameter extraction agent
├── sql_agent.py           # SQL generation agent
├── prompts.py             # All system prompts
└── thermo_agents_logger.py # Session logging

data/
└── thermo_data.db         # SQLite thermodynamic database

logs/sessions/             # Session log files
docs/                      # Jupyter notebooks and documentation
main.py                    # CLI application entry point
```

## Development Notes

- Project uses `uv` for dependency management (not pip/conda)
- All agents are async and use PydanticAI framework
- Russian language interface for users, English for internal processing
- Temperature handling: Celsius input converted to Kelvin internally
- Database queries optimized for chemical formula and phase-specific searches