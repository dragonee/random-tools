"""Slack API client library for channel operations, messaging, and file uploads.

Provides a unified interface to common Slack Web API methods. All functions
accept a Slack API token (xoxp-... user token) as their first argument.
Configuration is handled separately via ``randomtools.config.slack.SlackConfigFile``.

Modules:
    channels -- Channel lookup, listing, membership, and history.
    messages -- Sending text messages via chat.postMessage.
    files    -- File uploads via the external upload flow.
"""

from .channels import (
    SlackAPIError,
    ChannelNotFoundError,
    find_channel,
    fetch_all_channels,
    fetch_channel_members,
    fetch_last_message_ts,
)
from .messages import post_message
from .files import upload_file
