"""Deterministic geographic capabilities extending MORICE's existing Kernel."""
from .contracts import Coordinate, Location, SpatialContext
from .service import SpatialService

__all__ = ['Coordinate', 'Location', 'SpatialContext', 'SpatialService']
