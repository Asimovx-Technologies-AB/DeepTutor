# Feature Specification: US-07 MCP Sandboxed Code Execution & Math Solver

## 📌 Feature Overview
DeepTutor incorporates a hardened Model Context Protocol (MCP) tool client that empowers AI study agents to execute Python calculations and solve complex mathematical equations. All execution is secured via AST-based import allowlisting, temporary isolated scratch directories, timeout limits, and restricted SymPy expression parsers to guarantee complete system security.

---

## 👤 User Persona
- **Persona:** Computer Science, Mathematics, Physics, and Engineering Students.
- **Need:** Real-time verifiable code execution and step-by-step calculus/algebra equation solutions without hallucinations.

---

## 📖 User Stories

### Story 7.1: AST-Sandboxed Python Execution
> **As a** STEM student,  
> **I want** the tutor to write and execute code snippets (e.g., simulations, sorting algorithms, statistical models),  
> **So that** I can see actual terminal outputs and verify algorithm behavior.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Running safe Python code
  Given a user requests a Python simulation (e.g. Monte Carlo pi calculation)
  When the MCP client evaluates the code
  Then the AST validator ensures only safe modules (math, numpy, random, statistics, etc.) are imported
  And executes in a dedicated temporary subprocess with a 15-second timeout
  And returns stdout output to the chat interface.

Scenario: Blocking hazardous code
  Given a user prompt attempts to import `os`, `sys`, `subprocess`, `socket`, or `shutil`
  When the AST validator parses the syntax tree
  Then the request is immediately rejected with a SecurityException before execution.
```

### Story 7.2: Secure SymPy Algebraic Solver
> **As a** math student,  
> **I want** the tutor to solve differential equations and integrals using an exact symbolic algebra engine,  
> **So that** mathematical answers are 100% rigorous and unhallucinated.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Solving symbolic math expressions
  Given a math query like "solve x^2 - 5x + 6 = 0"
  When the MCP math tool receives the expression
  Then `parse_expr` evaluates the syntax in a restricted symbol environment (no arbitrary code execution)
  And returns the exact mathematical roots `[2, 3]` with formatted KaTeX output.
```

---

## 🛠️ Technical Details & Security Controls

### Core Module
* `backend/app/mcp_client.py` - Manages AST validation (`_validate_safe_code`), subprocess isolation, and SymPy algebra evaluation.

### Security Controls
* **AST Import Allowlist:** Explicitly permits mathematical and data science modules (`math`, `random`, `datetime`, `collections`, `itertools`, `numpy`, `sympy`, `scipy`, `pandas`, `json`, `re`) and blocks OS/network primitives.
* **Execution Guardrails:** 15s execution timeout, 100 KB max output capture, isolated scratch directory per execution.
