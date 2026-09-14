---
name: plan-build-test-no-hardcoding
description: Use whenever the user asks to build, implement, fix, or automate a coding task. Ensures the agent plans the approach before writing any code, avoids hardcoded values, writes advanced/production-grade code, and tests the resulting file(s) before declaring the task done. Trigger on requests like "build X", "implement Y", "write a script/module/function for Z", "automate this", or "create a tool that does...".
---

# Plan, Build Robustly, and Test

This skill governs how the agent should approach any coding task from start to
finish: think before typing, write code that generalizes instead of code that
only works for one example, and never claim a task is complete without
actually verifying it runs correctly.

## When to use this skill

- The user asks to write, build, implement, fix, or refactor any piece of code.
- The user asks to automate a task or create a script/tool/module.
- The task involves more than a trivial one-line change.

## How to use it

### 1. Plan before writing any code

- Restate the goal in your own words and identify the inputs, outputs, and
  edge cases before touching the editor.
- Break the task into clear steps (data flow, functions/modules needed,
  external dependencies, error conditions).
- Identify unknowns or ambiguous requirements and resolve them (ask the user
  only if genuinely blocking; otherwise pick the most sensible default and
  state the assumption).
- Only after the plan is clear, proceed to implementation.

### 2. No hardcoded values

- Do not hardcode file paths, magic numbers, credentials, sample inputs, IDs,
  URLs, or dataset-specific values directly into the logic.
- Use configuration, function parameters, environment variables, CLI
  arguments, or constants defined once at the top of the file (clearly
  named) instead of inlining literals throughout the code.
- Any value that could plausibly change between runs, environments, or users
  must be an input, not a literal buried in the code.
- Detect things dynamically where possible (e.g. discover file types,
  read schema from data, compute sizes) rather than assuming fixed values.

### 3. Write advanced-level code

- Use idiomatic, modern patterns for the language (proper typing/type hints,
  clear function/class boundaries, docstrings/comments explaining *why*, not
  just *what*).
- Handle errors and edge cases explicitly — do not let the code silently fail
  or assume happy-path input only.
- Structure the code to be modular and reusable (small functions with single
  responsibilities) rather than one long script.
- Follow language-specific best practices and linting conventions; avoid
  code smells (deep nesting, duplicated logic, unclear naming).

### 4. Test the file before finishing

- After writing the code, actually run it — do not just visually inspect it.
- Test with realistic inputs, including at least one edge case and one
  invalid/unexpected input, to confirm error handling works.
- If the code fails, fix it and re-run until it passes; never present
  untested code as finished.
- Briefly report what was tested and the result (pass/fail) as part of
  finishing the task.

## Definition of done

A task is only complete when:
1. The approach was planned before coding.
2. No hardcoded, one-off values remain in the logic.
3. The code follows advanced/production-quality conventions.
4. The code has been executed and verified to work, including at least one
   edge case.
