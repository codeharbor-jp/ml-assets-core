"""
FeatureHasher の具体実装。
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from application.services.feature_builder import FeatureHasher


class JsonFeatureHasher(FeatureHasher):
    """
    feature_spec と preprocessing 設定を JSON ダンプし SHA-256 でハッシュ化する実装。
    """

    def compute_hash(self, feature_spec: Mapping[str, str], preprocessing: Mapping[str, str]) -> str:
        payload = {
            "feature_spec": _to_sorted_mapping(feature_spec),
            "preprocessing": _to_sorted_mapping(preprocessing),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _to_sorted_mapping(mapping: Mapping[str, str]) -> Mapping[str, str]:
    return {key: mapping[key] for key in sorted(mapping)}

