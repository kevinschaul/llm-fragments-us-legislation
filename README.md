# llm-fragments-us-legislation

[![PyPI](https://img.shields.io/pypi/v/llm-fragments-us-legislation.svg)](https://pypi.org/project/llm-fragments-us-legislation/)
[![Changelog](https://img.shields.io/github/v/release/kevinschaul/llm-fragments-us-legislation?include_prereleases&label=changelog)](https://github.com/kevinschaul/llm-fragments-us-legislation/releases)
[![Tests](https://github.com/kevinschaul/llm-fragments-us-legislation/actions/workflows/test.yml/badge.svg)](https://github.com/kevinschaul/llm-fragments-us-legislation/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/kevinschaul/llm-fragments-us-legislation/blob/main/LICENSE)

Load bills from Congress.gov as LLM fragments

## Installation

Install this plugin in the same environment as [LLM](https://llm.datasette.io/).

```bash
llm install llm-fragments-us-legislation
```

## Usage

First set the enviornment variable `CONGRESS_API_KEY` ([sign up for a key here](https://api.congress.gov/sign-up/)).

Use `-f bill:bill_id` to include the bill text. `bill_id` takes the format `[type][number]-[congress]` (e.g. `hr1-119`).

```bash
llm -f bill:hr1-119 'Summarize this bill' -m gemini-2.5-pro-preview-05-06
```

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:

```bash
cd llm-fragments-us-legislation
python -m venv venv
source venv/bin/activate
```

Now install the dependencies and test dependencies:

```bash
python -m pip install -e '.[test]'
```

To run the tests:

```bash
python -m pytest
```
