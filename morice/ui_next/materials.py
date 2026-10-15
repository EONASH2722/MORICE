"""Compatibility name for the shared procedural material, not a second renderer."""
from .energy_field import EnergyField


class MaterialBackdrop(EnergyField):
    pass
