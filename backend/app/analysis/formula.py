"""Safe arithmetic evaluator for user-defined metrics (AST whitelist)."""
import ast
import operator

_BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_eval(expr: str, variables: dict[str, float]) -> float:
    """Evaluate an arithmetic expression over named variables.

    Only numbers, variable names, + - * /, unary +/- and parentheses are
    allowed; anything else raises ValueError.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"invalid formula: {e}") from e
    try:
        return float(_eval(tree.body, variables))
    except ZeroDivisionError as e:
        raise ValueError("division by zero") from e


def _eval(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"unknown variable: {node.id}")
        return float(variables[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval(node.left, variables),
                                       _eval(node.right, variables))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand, variables))
    raise ValueError(f"disallowed expression element: {ast.dump(node)[:60]}")
