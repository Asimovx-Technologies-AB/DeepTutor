"""
Utility script to audit source code for hardcoded secrets, absolute paths, or suspicious patterns.
Usage:
    python check_no_hardcoding.py <path-to-check>
"""

import sys
import re
from pathlib import Path

# Suspicious patterns to flag
RULES = [
    (r"(?:api_key|secret|password|token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "Possible hardcoded secret / API key"),
    (r"[A-Za-z]:\\[Uu]sers\\[^\\]+", "Hardcoded Windows absolute user path"),
    (r"postgresql://[^:]+:[^@]+@localhost", "Hardcoded credentials in DB URI"),
    (r"https?://localhost:\d+", "Hardcoded localhost URL in business logic (use config)"),
]

def scan_file(filepath: Path) -> list[str]:
    issues = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [f"Could not read {filepath}: {e}"]

    for line_idx, line in enumerate(content.splitlines(), start=1):
        # Ignore comments or markdown headings
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        for pattern, description in RULES:
            if re.search(pattern, line):
                issues.append(f"Line {line_idx}: [{description}] -> {line.strip()[:80]}")

    return issues

def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    print(f"Scanning target: {target.resolve()}")

    if target.is_file():
        files = [target]
    else:
        files = [
            p for p in target.rglob("*")
            if p.is_file()
            and p.suffix in {".py", ".ts", ".tsx", ".js"}
            and "node_modules" not in p.parts
            and ".venv" not in p.parts
            and ".git" not in p.parts
        ]

    total_issues = 0
    for f in files:
        issues = scan_file(f)
        if issues:
            print(f"\n[!] {f.relative_to(target.parent if target.is_file() else target)}:")
            for issue in issues:
                print(f"    - {issue}")
                total_issues += 1

    if total_issues == 0:
        print("\n[OK] No obvious hardcoded secrets, paths, or credentials detected.")
        sys.exit(0)
    else:
        print(f"\n[WARNING] Found {total_issues} potential hardcoding issues.")
        sys.exit(1)

if __name__ == "__main__":
    main()
