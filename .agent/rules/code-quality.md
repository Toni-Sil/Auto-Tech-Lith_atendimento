---
trigger: always_on
---

description: "Executes code quality analysis on a target directory. Use to identify issues and generate a quality report."
---

# Code Quality Skill

This skill executes a code quality analyzer script to check for issues in the target directory.

## Usage

To run the code quality analysis:

```bash
python scripts/analyze.py <target_path> [--verbose] [--json] [--output <file_path>]
```

### Arguments

- `target_path`: The path to the directory or file to analyze.
- `--verbose`, `-v`: Enable verbose output.
- `--json`: Output results as JSON.
- `--output`, `-o`: Write output to a specific file.

## Example

```bash
python .agent/skills/skills/code-quality/scripts/analyze.py src --verbose
```
