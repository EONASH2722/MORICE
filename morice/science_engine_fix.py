"""Fixes for science_engine.py - improves robustness of graph rendering."""

import re
from typing import List, Dict, Any, Optional


def validate_and_repair_artifact(artifact: Dict[str, Any]) -> bool:
    """Validate a science artifact and repair if possible."""
    if not artifact:
        return False
    
    # Check for required fields
    required = {'series', 'x_range', 'y_range'}
    if not all(key in artifact for key in required):
        return False
    
    # Validate series data
    series = artifact.get('series', [])
    if not isinstance(series, list) or len(series) == 0:
        return False
    
    for s in series:
        if not isinstance(s, dict):
            continue
        
        # Check for required series fields
        if not all(k in s for k in ['x', 'y', 'label', 'color']):
            continue
        
        # Validate x and y are lists of numbers
        x_data = s.get('x', [])
        y_data = s.get('y', [])
        
        if not isinstance(x_data, list) or not isinstance(y_data, list):
            continue
        
        # Remove non-numeric values
        try:
            s['x'] = [float(v) for v in x_data if isinstance(v, (int, float))]
            s['y'] = [float(v) for v in y_data if isinstance(v, (int, float))]
        except (ValueError, TypeError):
            continue
        
        # Ensure equal length
        min_len = min(len(s['x']), len(s['y']))
        s['x'] = s['x'][:min_len]
        s['y'] = s['y'][:min_len]
    
    # Validate ranges
    try:
        x_range = artifact.get('x_range', [-10, 10])
        y_range = artifact.get('y_range', [-10, 10])
        
        if isinstance(x_range, (list, tuple)) and len(x_range) == 2:
            artifact['x_range'] = (float(x_range[0]), float(x_range[1]))
        
        if isinstance(y_range, (list, tuple)) and len(y_range) == 2:
            artifact['y_range'] = (float(y_range[0]), float(y_range[1]))
    except (ValueError, TypeError):
        artifact['x_range'] = (-10, 10)
        artifact['y_range'] = (-10, 10)
    
    return True


def extract_equation_safely(text: str) -> Optional[str]:
    """Extract and validate an equation from text."""
    if not text or len(text) > 500:
        return None
    
    # Common equation patterns
    patterns = [
        r'y\s*=\s*([^,;\n]+)',  # y = ...
        r'f\s*\(\s*x\s*\)\s*=\s*([^,;\n]+)',  # f(x) = ...
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            equation = match.group(1).strip()
            if equation and len(equation) < 200:
                return equation
    
    return None


def is_valid_graph_request(text: str) -> bool:
    """Check if text looks like a graph request."""
    if not text:
        return False
    
    keywords = {'graph', 'plot', 'equation', 'function', 'curve', 'y='}
    lowered = text.lower()
    
    return any(kw in lowered for kw in keywords)
