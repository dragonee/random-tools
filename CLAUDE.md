# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python package called `randomtools` - a collection of standalone command-line utilities for various maintenance and data processing tasks. The project is managed with uv, built with the `uv_build` backend, and installs console scripts for each tool.

## Development Commands

### Environment Setup
```bash
# Create .venv and install the package with its dependencies
uv sync

# Run a tool inside that environment
uv run evenings
```

### Build and Installation
```bash
# Build the sdist and wheel into dist/
uv build

# Put the tools on PATH, following the working tree
uv tool install --editable .
```

## Architecture

### Package Structure
- `src/randomtools/` - Main package directory containing all tools
- `src/randomtools/config/` - Configuration handling, particularly for Google API integration
- Each tool is implemented as a standalone Python module with a `main()` function
- All console entry points are defined in `pyproject.toml` under `[project.scripts]`

### Tool Categories

**Calendar Tools:**
- `evenings` (`calendar_availability.py`) - Google Calendar integration for checking evening availability

**CSV/JSON Processing:**
- `copiesfromcsv`, `maptocsv`, `maptocsvcolumn` - Various CSV manipulation utilities
- `sodamatcher` - Specialized tool for matching SoDA member emails with GUID maps

**File Management:**
- `movetoguids` - Copy files to GUID-named files with JSON mapping
- `pdfrepeat` - PDF processing utility

**Markdown/Documentation:**
- `onelinesummary` - Generate markdown summaries of directory contents
- `usecase` - Extract use cases from markdown files

### Dependencies
- `docopt` - Command-line argument parsing (all tools use docopt-style help strings)
- `pydantic` - Data validation and parsing
- `google-*` packages - Google Calendar API integration
- `thefuzz` - Fuzzy string matching
- `requests` - HTTP requests
- `openpyxl` - Writing xlsx workbooks

Dependencies live in `[project] dependencies` in `pyproject.toml`; add them with `uv add <package>`.

### Configuration
- Google Calendar tools require `~/.google/config.ini` with Google API credentials
- Configuration is handled through the `GoogleConfigFile` class in `config/google.py`

## Development Notes

- Each tool follows the docopt pattern with help strings as module docstrings
- Tools are designed to be independent utilities, not part of a larger framework
- `uv build` writes to `dist/`; the stale `build/` directory is a leftover from setuptools
- Version numbers are maintained in individual tool docstrings and pyproject.toml