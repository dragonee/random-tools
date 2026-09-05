"""Authorize against the Google APIs the dumper needs, reusing one token file."""

import pickle
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/forms.responses.readonly',
]


def load(token_path):
    try:
        with open(token_path, 'rb') as token:
            return pickle.load(token)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError):
        return None


def save(creds, token_path):
    token_path = Path(token_path).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)


def covers(creds, scopes):
    return creds is not None and set(scopes) <= set(creds.scopes or [])


def authorize(token_path, credentials_path, scopes=SCOPES):
    """Return credentials for `scopes`, re-consenting only when we have to.

    The token file is shared with the other Google tools here, so a new
    consent asks for what is already in the token plus what is missing -
    otherwise two tools pointed at one token file would keep logging each
    other out.
    """

    creds = load(token_path)

    if covers(creds, scopes):
        if creds.valid:
            return creds

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save(creds, token_path)

            return creds

    wanted = set(scopes)

    if creds:
        wanted |= set(creds.scopes or [])

    wanted = sorted(wanted)

    print("Asking for access to: {}".format(', '.join(wanted)), file=sys.stderr)

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), wanted)
    creds = flow.run_local_server(port=0)

    save(creds, token_path)

    return creds
