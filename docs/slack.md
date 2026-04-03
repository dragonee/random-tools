# `randomtools.slack`

Slack API client library for channel operations, messaging, and file uploads.

All functions accept a Slack API token (`xoxp-...` user token) as their first argument. Token management is handled by `randomtools.config.slack.SlackConfigFile`, which reads `~/.slack/config.ini`.

## Configuration

```ini
# ~/.slack/config.ini
[Slack]
token = xoxp-...
```

## Exceptions

### `SlackAPIError(method, error)`

Base exception for Slack API errors. Attributes:

- `method` (str) -- the API method that failed (e.g. `"conversations.list"`).
- `error` (str) -- error string returned by Slack.

### `ChannelNotFoundError(channel_name)`

Subclass of `SlackAPIError`. Raised when `find_channel()` cannot resolve a channel name.

- `channel_name` (str) -- the name that was looked up.

## `channels` module

### `find_channel(token, channel_name)`

Resolve a channel name to its ID.

- Strips leading `#` from the name.
- If *channel_name* looks like a channel ID (starts with `C`, rest alphanumeric), returns it directly without an API call.

**Returns:** `(channel_id, channel_name)` -- *channel_name* is `None` when a raw ID was passed in.

**Raises:** `ChannelNotFoundError`, `SlackAPIError`

```python
from randomtools.slack import find_channel

channel_id, name = find_channel(token, "#general")
channel_id, _    = find_channel(token, "C01234ABCDE")
```

### `fetch_all_channels(token, exclude_archived=True)`

Fetch all accessible channels (public and private) with pagination.

**Returns:** `list[dict]` -- channel objects as returned by the Slack API.

**Raises:** `SlackAPIError`

```python
from randomtools.slack import fetch_all_channels

channels = fetch_all_channels(token)
for ch in channels:
    print(ch['name'], ch['id'])
```

### `fetch_channel_members(token, channel_id)`

Fetch all member user IDs from a channel.

**Returns:** `list[str]` -- Slack user IDs.

**Raises:** `SlackAPIError`

### `fetch_last_message_ts(token, channel_id)`

Get the timestamp of the most recent message in a channel.

**Returns:** `float | None` -- Unix timestamp, or `None` if the channel is empty or the call fails.

## `messages` module

### `post_message(token, channel_id, text)`

Send a text message to a channel via `chat.postMessage`. Supports Slack mrkdwn formatting.

**Returns:** `dict` -- Slack API response.

**Raises:** `SlackAPIError`

```python
from randomtools.slack import find_channel, post_message

channel_id, _ = find_channel(token, "general")
post_message(token, channel_id, "Hello, world!")
```

## `files` module

### `upload_file(token, channel_id, filename, content, initial_comment=None, title=None)`

Upload a file to a channel using the 3-step external upload flow.

| Argument | Type | Description |
|---|---|---|
| `token` | `str` | Slack API token |
| `channel_id` | `str` | Target channel ID |
| `filename` | `str` | Display name (e.g. `"report.md"`) |
| `content` | `bytes` | File content |
| `initial_comment` | `str \| None` | Message posted alongside the file |
| `title` | `str \| None` | File title in Slack (defaults to *filename*) |

**Returns:** `dict` -- Slack API response.

**Raises:** `SlackAPIError`

```python
from pathlib import Path
from randomtools.slack import find_channel, upload_file

channel_id, _ = find_channel(token, "general")
p = Path("report.md")
upload_file(token, channel_id, p.name, p.read_bytes(),
            initial_comment="Weekly report", title=p.stem)
```

## CLI: `slack-send`

```
Usage:
    slack-send [options] CHANNEL [TEXT...]
    slack-send [options] CHANNEL -f FILE [TEXT...]

Options:
    -f FILE, --file FILE    Send FILE as a Slack file upload.
    -h, --help              Show this message.
    --version               Show version information.
```

When `-f` is combined with text, the text is sent as the file's accompanying comment. Without `-f`, text is sent as a regular message. Text can come from arguments or stdin.

```bash
# Send a message
slack-send general "Hello, world!"

# Pipe from stdin
echo "Deploy complete" | slack-send general

# Upload a file
slack-send general -f report.md

# Upload a file with a comment
slack-send general -f report.md "Weekly report"
echo "See attached" | slack-send general -f report.md
```
