"""Safety checks for graph equation parsing and rendering."""

import re
from typing import Optional


class GraphSafetyError(Exception):
    """Raised when a graph equation fails safety validation."""
    pass


def sanitize_equation(equation: str) -> str:
    """Remove potentially dangerous characters from equations."""
    if not equation:
        return ""
    # Allow only math operators, numbers, variables, and common functions
    sanitized = re.sub(r'[^a-zA-Z0-9+\-*/.()^\s]', '', equation)
    return sanitized.strip()


def validate_equation(equation: str) -> bool:
    """Check if an equation is safe and valid."""
    if not equation or len(equation) > 500:
        return False
    
    # Check for balanced parentheses
    if equation.count('(') != equation.count(')'):
        return False
    
    # Check for balanced brackets
    if equation.count('[') != equation.count(']'):
        return False
    
    # Prevent division by constants that might be zero
    if re.search(r'/\s*0(?:[^0-9.]|$)', equation):
        return False
    
    return True


def safe_evaluate_point(equation: str, x_value: float, max_attempts: int = 1) -> Optional[float]:
    """Safely evaluate an equation at a point."""
    try:
        # Simple evaluation for common cases
        # This is a basic implementation - production should use sympy or numpy
        import math
        
        # Replace x with the actual value
        expr = equation.replace('x', f'({x_value})')
        
        # Limit to safe functions
        safe_names = {
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'sqrt': math.sqrt,
            'log': math.log,
            'exp': math.exp,
            'abs': abs,
            'pow': pow,
        }
        
        result = eval(expr, {"__builtins__": {}}, safe_names)
        
        if not isinstance(result, (int, float)):
            return None
        
        if not (-1e10 < result < 1e10):  # Prevent extreme values
            return None
        
        return float(result)
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    except Exception:
        return None
