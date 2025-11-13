"""
ワーカーエントリポイント。
"""

from .inference_worker import InferenceWorker, InferenceWorkerConfig

__all__ = [
    "InferenceWorker",
    "InferenceWorkerConfig",
]

