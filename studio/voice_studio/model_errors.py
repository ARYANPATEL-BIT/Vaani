"""The model's two failures, in their own module so routes can catch them
without importing torch (model.py imports it; tests with a fake model never
should)."""


class GpuBusy(Exception):
    """CUDA ran out of memory. Nothing is broken; retry when memory is free."""


class ModelError(Exception):
    """The model cannot run as configured (no CUDA device, no watermarker).
    The message is ours, never a secret, and safe to show the user."""
