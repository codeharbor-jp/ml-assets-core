"""
通知系アダプタの公開API。
"""

from .slack import SlackConfig, SlackNotifier, SlackWebhookNotifier

__all__ = [
    "SlackConfig",
    "SlackNotifier",
    "SlackWebhookNotifier",
]

