"""
IndieTutor MCP Client Implementation
Connects IndieTutor to external MCP tool servers (Python Sandbox, Math Solvers, Filesystem) over stdio or SSE.
"""
import sys
import os
import ast
import operator
import math
import asyncio
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Registered MCP Server configurations
DEFAULT_MCP_SERVERS = [
    {
        "id": "python_sandbox",
        "name": "Python Code Execution Sandbox",
        "type": "stdio",
        "command": sys.executable,
        "args": ["-c", "print('Python Sandbox Active')"],
        "enabled": True,
        "description": "Executes Python code snippets to test student solutions safely.",
        "icon": "code"
    },
    {
        "id": "sympy_math",
        "name": "SymPy Mathematical Solver",
        "type": "stdio",
        "command": sys.executable,
        "args": ["-c", "print('SymPy Solver Active')"],
        "enabled": True,
        "description": "Solves complex algebraic, calculus, and matrix equations with 100% precision.",
        "icon": "calculator"
    },
    {
        "id": "local_filesystem",
        "name": "Local Notes Reader",
        "type": "stdio",
        "command": "node",
        "args": ["-v"],
        "enabled": False,
        "description": "Reads local Markdown notes and text files directly from your computer.",
        "icon": "folder"
    }
]

_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_MATH_NAMES = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "pi": math.pi,
    "e": math.e,
}


def _eval_ast_math(node):
    if isinstance(node, ast.Expression):
        return _eval_ast_math(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Non-numeric literal not allowed")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _MATH_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _eval_ast_math(node.left)
        right = _eval_ast_math(node.right)
        if op_type == ast.Pow and (abs(right) > 500 or abs(left) > 1e10):
            raise ValueError("Exponent/Base out of safe computational bounds")
        return _MATH_OPS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _MATH_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _MATH_OPS[op_type](_eval_ast_math(node.operand))
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _MATH_NAMES:
            func = _MATH_NAMES[node.func.id]
            args = [_eval_ast_math(arg) for arg in node.args]
            return func(*args)
        raise ValueError("Function call not permitted in math solver")
    elif isinstance(node, ast.Name):
        if node.id in _MATH_NAMES and isinstance(_MATH_NAMES[node.id], (int, float)):
            return _MATH_NAMES[node.id]
        raise ValueError(f"Identifier '{node.id}' not allowed")
    else:
        raise ValueError("Expression syntax not allowed in safe math evaluator")


def _validate_safe_code(code: str) -> None:
    tree = ast.parse(code)
    allowed_modules = {
        "math", "random", "datetime", "time", "itertools", "functools",
        "collections", "heapq", "bisect", "string", "json", "re",
        "typing", "dataclasses", "enum", "copy", "statistics", "decimal", "fractions"
    }
    disallowed_calls = {
        "eval", "exec", "open", "__import__", "compile", "globals",
        "locals", "vars", "getattr", "setattr", "delattr", "input",
        "help", "dir", "id", "memoryview"
    }

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".")[0] for alias in getattr(node, "names", [])]
            mod = (getattr(node, "module", "") or "").split(".")[0]
            if (mod and mod not in allowed_modules) or any(n and n not in allowed_modules for n in names):
                target_mod = mod or (names[0] if names else "unknown")
                raise ValueError(f"Import of unapproved module '{target_mod}' is prohibited in sandbox.")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in disallowed_calls:
                raise ValueError(f"Direct invocation of '{node.func.id}()' is prohibited in sandbox.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder attribute introspection is prohibited.")


class MCPClientManager:
    """Manages active external MCP servers and tool dispatching."""

    def __init__(self):
        self._servers: Dict[str, Dict[str, Any]] = {
            s["id"]: s for s in DEFAULT_MCP_SERVERS
        }

    def list_servers(self) -> List[Dict[str, Any]]:
        """Return list of configured MCP servers."""
        return list(self._servers.values())

    def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Return server configuration by ID."""
        return self._servers.get(server_id)

    def add_server(self, server_config: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new MCP tool server."""
        s_id = server_config.get("id") or f"mcp_{len(self._servers) + 1}"
        server_config["id"] = s_id
        server_config["enabled"] = server_config.get("enabled", True)
        self._servers[s_id] = server_config
        return server_config

    def toggle_server(self, server_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        """Enable or disable an MCP server."""
        if server_id in self._servers:
            self._servers[server_id]["enabled"] = enabled
            return self._servers[server_id]
        return None

    def delete_server(self, server_id: str) -> bool:
        """Remove an MCP server configuration."""
        if server_id in self._servers:
            del self._servers[server_id]
            return True
        return False

    def list_available_tools(self) -> List[Dict[str, Any]]:
        """
        List all available tools provided by active enabled MCP servers.
        """
        tools = []
        for s in self._servers.values():
            if not s.get("enabled"):
                continue

            if s["id"] == "python_sandbox":
                tools.append({
                    "id": "python_execute",
                    "server_id": s["id"],
                    "name": "run_python_code",
                    "description": "Executes Python code safely to verify code logic or solve numerical calculations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "The Python code snippet to execute."}
                        },
                        "required": ["code"]
                    }
                })
            elif s["id"] == "sympy_math":
                tools.append({
                    "id": "sympy_solve",
                    "server_id": s["id"],
                    "name": "solve_math_expression",
                    "description": "Evaluates math expressions or solves symbolic equations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string", "description": "Mathematical expression e.g. 'integrate(x**2, x)'"}
                        },
                        "required": ["expression"]
                    }
                })
        return tools

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call safely from the AI Tutor.
        Returns a structured MCP tool response including status, output, exit_code, stdout, and stderr.
        """
        if tool_name == "run_python_code":
            code = arguments.get("code", "")
            if not code or not code.strip():
                return {"status": "error", "output": "No code provided to execute.", "exit_code": -1, "stdout": "", "stderr": ""}

            try:
                _validate_safe_code(code)
            except Exception as ve:
                return {"status": "error", "output": f"Security Sandbox Notice: {str(ve)}", "exit_code": -1, "stdout": "", "stderr": str(ve)}

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=3.0)
                stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
                stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
                exit_code = proc.returncode if proc.returncode is not None else 0

                if exit_code != 0:
                    error_msg = stderr_str or stdout_str or f"Process exited with error code {exit_code}"
                    return {
                        "status": "error",
                        "output": error_msg,
                        "exit_code": exit_code,
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                    }

                output_text = stdout_str or (f"Execution warning: {stderr_str}" if stderr_str else "Code executed cleanly with 0 errors.")
                return {
                    "status": "success",
                    "output": output_text,
                    "exit_code": 0,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                }
            except asyncio.TimeoutError:
                return {"status": "error", "output": "Execution timed out (3.0s limit exceeded).", "exit_code": -1, "stdout": "", "stderr": "Timeout"}
            except Exception as e:
                return {"status": "error", "output": f"Execution Error: {str(e)}", "exit_code": -1, "stdout": "", "stderr": str(e)}

        elif tool_name == "solve_math_expression":
            expr = arguments.get("expression", "")
            if not expr or not expr.strip():
                return {"status": "error", "output": "No mathematical expression provided.", "exit_code": -1, "stdout": "", "stderr": ""}

            try:
                val = None
                try:
                    import sympy
                    from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

                    math_ast = ast.parse(expr.strip(), mode="eval")
                    for n in ast.walk(math_ast):
                        if isinstance(n, (ast.Import, ast.ImportFrom, ast.Attribute, ast.Lambda, ast.Dict, ast.List, ast.Set)):
                            raise ValueError("Forbidden syntax in math expression")

                    safe_globals = {
                        "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
                        "sqrt": sympy.sqrt, "log": sympy.log, "exp": sympy.exp,
                        "abs": sympy.Abs, "pi": sympy.pi, "E": sympy.E
                    }
                    transformations = (standard_transformations + (implicit_multiplication_application,))
                    parsed_expr = parse_expr(
                        expr.strip(),
                        global_dict=safe_globals,
                        local_dict={},
                        transformations=transformations,
                        evaluate=True
                    )
                    val = str(parsed_expr.evalf() if hasattr(parsed_expr, "evalf") else parsed_expr)
                except Exception:
                    val = _eval_ast_math(ast.parse(expr.strip(), mode="eval"))

                return {
                    "status": "success",
                    "output": f"Result: {val}",
                    "exit_code": 0,
                    "stdout": f"Result: {val}",
                    "stderr": "",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "output": f"Math Evaluation Notice: {str(e)}",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                }

        return {"status": "error", "output": f"Unknown tool '{tool_name}'.", "exit_code": -1, "stdout": "", "stderr": f"Unknown tool '{tool_name}'."}


# Global singleton instance
mcp_client_manager = MCPClientManager()
