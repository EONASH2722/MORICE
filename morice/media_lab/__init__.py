"""Lazy generative media providers for MORICE's existing execution kernel.

This package never imports Torch, Diffusers or Transformers in the app process.
"""
from .contracts import ImageRequest, VideoRequest, ImageModelDescriptor, VideoModelDescriptor, Quality, ModelState

__all__ = ["ImageRequest", "VideoRequest", "ImageModelDescriptor", "VideoModelDescriptor", "Quality", "ModelState"]
