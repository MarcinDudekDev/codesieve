# CodeSieve

**Deterministic code quality grading for AI coding workflows.**

CodeSieve runs 8 principle-based sieves against your Python, PHP, JavaScript, and TypeScript code and produces a 1-10 score per principle, with an aggregate letter grade (A-F). No LLM calls, no flaky heuristics -- just fast, reproducible static analysis powered by tree-sitter.

Built for the AI-assisted coding loop: let your agent write code, then grade it automatically before committing. Works as a CLI tool, CI gate, or quality feedback signal for any AI coding agent.

## Why CodeSieve?

Traditional linters focus on style. CodeSieve focuses on **design principles** -- the things that make code maintainable, readable, and correct:

| Sieve | What it measures |
|-------|-----------------|
| **KISS** | Cyclomatic complexity, function length, parameter count |
| **Nesting** | Max and average nesting depth of control flow |
| **Naming** | Convention compliance (PEP 8 for Python, PSR-1/PSR-12 for PHP), abbreviated names |
| **ErrorHandling** | Bare excepts, empty handlers, broad catches without re-raise |
| **TypeHints** | Type annotation coverage, `declare(strict_types=1)` for PHP (PSR-12) |
| **MagicNumbers** | Unexplained numeric literals in function bodies |
| **GuardClauses** | Functions wrapping entire body in a single if-block |
| **DeprecatedAPI** | Calls to deprecated/removed PHP functions with replacement suggestions |
| **Comments** | Docstring/JSDoc coverage on named functions |
| **DRY** | Duplicate function bodies — identical logic extracted instead of copied |

Each sieve produces a score from 1.0 (worst) to 10.0 (best), specific findings with line numbers, and an actionable summary. Scores are weighted and combined into an aggregate grade.

## Install

```bash
pip install codesieve
```

Requires Python 3.10+.

## Usage

```bash
# Scan a single file
codesieve scan app.py
codesieve scan index.php
codesieve scan app.ts

# Scan a directory (picks up .py, .php, .js, .jsx, .ts, .tsx files)
codesieve scan src/

# JSON output for CI pipelines
codesieve scan src/ --format json

# Fail CI if quality drops below threshold
codesieve scan src/ --fail-under 7.0

# Run specific sieves only
codesieve scan src/ --sieves KISS,Naming,TypeHints

# List all available sieves
codesieve sieves
```

## Example Output

```
  CodeSieve Report -- src/myapp/handlers.py (174 lines, Python)
+-----------------+---------+------------+--------------------------------------+
| Sieve           |  Score  | Type       | Summary                              |
+-----------------+---------+------------+--------------------------------------+
| KISS            |   6.9   | determ.    | avg CC=7.7, max fn length=35         |
| Nesting         |   7.8   | determ.    | max depth=3, avg depth=2.2           |
| Naming          |  10.0   | determ.    | 0 violations in 40 names (0%)        |
| ErrorHandling   |  10.0   | determ.    | No try blocks in 6 functions         |
| TypeHints       |   9.5   | determ.    | 94% type coverage (11/12 params)     |
| MagicNumbers    |  10.0   | determ.    | no magic numbers                     |
| GuardClauses    |  10.0   | determ.    | all functions use good return patterns|
| DeprecatedAPI   |  10.0   | determ.    | No deprecated API calls found        |
+-----------------+---------+------------+--------------------------------------+
| AGGREGATE       |   8.9   |            | Grade: A                             |
+-----------------+---------+------------+--------------------------------------+
```

## PHP Support

CodeSieve understands PHP idioms and enforces established standards:

- **PSR-1 naming**: camelCase methods, PascalCase classes, UPPER_SNAKE constants -- with standard citations in findings
- **PSR-12 strict types**: flags files missing `declare(strict_types=1)`
- **Error handling**: detects empty catch blocks, broad `\Exception`/`\Throwable` catches without re-throw
- **Deprecated API detection**: 24 deprecated/removed functions (mysql_*, ereg*, `each()`, `create_function()`, `utf8_encode()`, `strftime()`) with specific replacement suggestions and PHP version references

## Configuration

Create a `.codesieve.yml` in your project root:

```bash
codesieve init
```

```yaml
# .codesieve.yml
exclude:
  - "**/.venv/**"
  - "**/migrations/**"
  - "**/vendor/**"

weights:
  KISS: 0.20
  Nesting: 0.15
  Naming: 0.15
  ErrorHandling: 0.10
  TypeHints: 0.08
  MagicNumbers: 0.05
  GuardClauses: 0.05
  DeprecatedAPI: 0.05

fail_under: 7.0
```

Adjust weights to match what matters most for your project. Sieves with weight `0` are skipped.

## Use with AI Agents

CodeSieve is designed as a quality gate in AI coding loops:

```
Agent writes code --> CodeSieve grades it --> Agent reads feedback --> Agent improves code
```

The JSON output (`--format json`) gives structured feedback that any AI agent can parse and act on. The `--fail-under` flag works as a CI gate to prevent quality regressions.

## Pre-commit

Add CodeSieve as a [pre-commit](https://pre-commit.com/) hook:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/MarcinDudekDev/codesieve
    rev: v0.1.0
    hooks:
      - id: codesieve
        args: ["--fail-under", "7.0"]
```

## Language Support

| Language | Status | Standards |
|----------|--------|-----------|
| Python | Supported | PEP 8 |
| PHP | Supported | PSR-1, PSR-12 |
| JavaScript | Supported | camelCase, PascalCase |
| TypeScript | Supported | camelCase, PascalCase, type annotations |
| Go | Planned | |

CodeSieve uses [tree-sitter](https://tree-sitter.github.io/) for parsing, making new language support straightforward -- each language needs its own sieve implementations that understand the language's idioms and conventions.

## Roadmap

- [x] Python support (8 sieves)
- [x] PHP support (8 sieves, PSR-1/PSR-12 enforcement, deprecated API detection)
- [x] JavaScript/TypeScript support (camelCase/PascalCase, TS type annotations)
- [ ] `--watch` mode for continuous feedback
- [x] GitHub Actions integration
- [x] Pre-commit hook
- [x] More sieves: Comments (docstring coverage), DRY (duplicate function bodies)
- [ ] More sieves: SRP, Complexity
- [ ] Custom sieve plugins

## Contributing

Contributions are welcome! CodeSieve is in early development and there's plenty of room to help:

- **Add a sieve** -- each sieve is a self-contained class in `src/codesieve/sieves/`
- **Add language support** -- tree-sitter grammars + language-specific sieve implementations
- **Improve scoring** -- better heuristics, edge case handling, calibration
- **Write tests** -- more fixture files, edge cases, regression tests

```bash
# Development setup
git clone https://github.com/MarcinDudekDev/codesieve.git
cd codesieve
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

See the existing sieves in `src/codesieve/sieves/` for the pattern -- each one extends `BaseSieve` and implements an `analyze()` method that receives a parsed AST and returns scored findings.

## License

MIT -- see [LICENSE](LICENSE).
