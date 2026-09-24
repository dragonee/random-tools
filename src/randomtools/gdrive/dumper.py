"""Dump Google Drive files into local documents.

Usage:
    dumper [options] [--match FILTER]... [<link>...]

Options:
    -c, --config SECTION   Section of ~/.google/config.ini to authorize with [default: Google].
    -i, --input FILE       Read links from a YAML or plain text file ('-' for stdin).
    -o, --output PATH      Where to write: a directory (default: .), or the file
                           to write into with --concat (default: stdout).
    --sheet-format FORMAT  Dump spreadsheets as xlsx, csv or md [default: xlsx].
    --form-format FORMAT   Dump form responses as xlsx, dir or md [default: xlsx].
    -m, --match FILTER     Only dump form responses answering QUESTION=ANSWER.
    --concat               Write everything into a single markdown stream.
    -q, --quiet            Do not report what was written.
    -h, --help             Show this message.
    --version              Show version information.

Links come from the command line, from a file given with --input, or from
standard input, one per line:

    dumper --config WorkGoogle https://docs.google.com/document/d/ID/edit
    cat links.txt | dumper -o dump/
    dumper -i links.yml -o dump/

The --input file is a list of links, a list of {name, link} maps, or a
name -> link map when it is YAML; one link per line (# comments allowed)
otherwise.

What each kind of file becomes:

    Document      markdown
    Spreadsheet   an xlsx file, a csv file per tab, or a markdown table per tab
    Form          an xlsx file of responses, a markdown document, or a
                  directory holding one markdown file per question and one
                  per respondent
    Presentation  pdf, as Drive exports it
    Anything else downloaded in the format it is stored in

A folder is walked to the bottom, subfolders becoming subdirectories of the
output; shortcuts are followed to what they point at. A file that cannot be
dumped is reported and the rest of the folder still runs.

With --concat every file is rendered as markdown and written to one place,
which is what --sheet-format md and --form-format md do on their own. The
folder structure flattens into one stream, and files that are not text are
reported and left out.

With --match, forms are narrowed down to the responses giving an answer:

    dumper --form-format dir --match "Team=Design" -o dump/ FORM_LINK

The question goes by its title and the answer by its text, case aside. A
checkbox matches when any box ticked does, and an empty answer ("Team=")
matches those who left the question blank. Given more than once, --match
keeps the responses matching every question named, and any of the answers
named for the same question. A form that does not ask a question named is
skipped.

The config section holds the paths to the OAuth client and to the token
cached from it, so several accounts can each have their own section:

    [WorkGoogle]
    token_path = ~/.google/work-token.pickle
    credentials_path = ~/.google/work-credentials.json
"""

import sys
from pathlib import Path

from docopt import docopt
from googleapiclient.discovery import build

from ..config.google import GoogleConfigFile
from . import docs, forms, links, markdown, sheets
from .auth import authorize

VERSION = '1.2'

DOCUMENT = 'application/vnd.google-apps.document'
SPREADSHEET = 'application/vnd.google-apps.spreadsheet'
FORM = 'application/vnd.google-apps.form'
FOLDER = 'application/vnd.google-apps.folder'
SHORTCUT = 'application/vnd.google-apps.shortcut'

GOOGLE_TYPE = 'application/vnd.google-apps.'

PDF = 'application/pdf'

FIELDS = 'id,name,mimeType,shortcutDetails(targetId)'

SHEET_FORMATS = ('xlsx', 'csv', 'md')
FORM_FORMATS = ('xlsx', 'dir', 'md')


class Skip(Exception):
    """Something deliberately passed over, rather than something gone wrong."""


class Directory:
    """A directory to write into, keeping every file it writes distinct."""

    concat = False

    def __init__(self, path, quiet=False):
        self.path = Path(path).expanduser()
        self.quiet = quiet
        self.taken = set()

    def child(self, name):
        directory = Directory(self.path / name, quiet=self.quiet)
        directory.taken = self.taken

        return directory

    def unique(self, name):
        path = self.path / name
        stem, suffix = path.stem, path.suffix
        counter = 2

        while path in self.taken:
            path = self.path / '{}-{}{}'.format(stem, counter, suffix)
            counter += 1

        self.taken.add(path)

        return path

    def write(self, name, content):
        path = self.unique(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding='utf-8')

        self.report(path)

        return path

    def reserve(self, name):
        """Claim a path for something that writes itself, like a workbook."""

        path = self.unique(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        return path

    def report(self, path):
        if not self.quiet:
            print(path, file=sys.stderr)


class Concat:
    """Everything as one markdown stream, sections split by a rule."""

    concat = True

    def __init__(self, stream):
        self.stream = stream
        self.written = False

    def child(self, name):
        """A stream has no folders to descend into."""

        return self

    def add(self, text):
        if self.written:
            self.stream.write('\n---\n\n')

        self.stream.write(text.rstrip('\n') + '\n')
        self.written = True


def services(creds):
    return (
        build('drive', 'v3', credentials=creds),
        build('sheets', 'v4', credentials=creds),
        build('forms', 'v1', credentials=creds),
    )


def describe(drive, file_id):
    return drive.files().get(
        fileId=file_id,
        fields=FIELDS,
        supportsAllDrives=True,
    ).execute()


def contents(drive, folder_id):
    """Everything directly inside a folder, folders first, then by name."""

    page_token = None

    while True:
        result = drive.files().list(
            q="'{}' in parents and trashed = false".format(folder_id),
            fields='nextPageToken,files({})'.format(FIELDS),
            orderBy='folder,name',
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        for entry in result.get('files', []):
            yield entry

        page_token = result.get('nextPageToken')

        if not page_token:
            break


def dump(link, api, out, options):
    """Dump one link. Returns how many files under it could not be dumped."""

    remote = describe(api[0], link.file_id)

    return dump_remote(remote, link.name or remote.get('name'), api, out, options)


def dump_remote(remote, name, api, out, options, seen=None):
    drive, sheets_service, forms_service = api

    file_id = remote['id']
    mime_type = remote.get('mimeType', '')
    name = name or file_id

    if mime_type == SHORTCUT:
        target = remote.get('shortcutDetails', {}).get('targetId')

        if not target:
            raise ValueError("{} is a shortcut to nothing".format(name))

        return dump_remote(describe(drive, target), name, api, out, options, seen)

    if mime_type == FOLDER:
        return dump_folder(remote, name, api, out, options, seen)

    if mime_type == DOCUMENT:
        dump_document(drive, file_id, name, out)
    elif mime_type == SPREADSHEET:
        dump_spreadsheet(drive, sheets_service, file_id, name, out, options)
    elif mime_type == FORM:
        dump_form(forms_service, file_id, name, out, options)
    elif mime_type.startswith(GOOGLE_TYPE):
        dump_as_pdf(drive, file_id, name, out)
    else:
        dump_file(drive, file_id, name, out)

    return 0


def dump_folder(folder, name, api, out, options, seen=None):
    """Walk a folder, reporting what fails rather than stopping on it."""

    seen = set() if seen is None else seen

    if folder['id'] in seen:
        return 0

    seen.add(folder['id'])

    inside = out.child(markdown.slug(name, fallback='folder'))
    failed = 0

    for entry in contents(api[0], folder['id']):
        try:
            failed += dump_remote(entry, entry.get('name'), api, inside, options, seen)
        except Skip as skipped:
            print("skipped {}".format(skipped), file=sys.stderr)
        except Exception as error:
            failed += 1
            print("{}: {}".format(entry.get('name', entry['id']), error), file=sys.stderr)

    return failed


def dump_document(drive, file_id, name, out):
    text = docs.export_text(drive, file_id)

    if out.concat:
        return out.add('{}\n\n{}'.format(markdown.heading(name), text))

    out.write(markdown.slug(name) + '.md', text)


def dump_spreadsheet(drive, sheets_service, file_id, name, out, options):
    if out.concat or options['--sheet-format'] == 'md':
        spreadsheet = sheets.fetch(sheets_service, file_id)
        spreadsheet.title = name
        text = sheets.to_markdown(spreadsheet)

        if out.concat:
            return out.add(text)

        return out.write(markdown.slug(name) + '.md', text)

    if options['--sheet-format'] == 'xlsx':
        return out.write(
            markdown.slug(name) + '.xlsx',
            docs.export_bytes(drive, file_id, sheets.XLSX),
        )

    spreadsheet = sheets.fetch(sheets_service, file_id)
    single = len(spreadsheet.sheets) == 1

    for title, rows in spreadsheet.sheets:
        file_name = markdown.slug(name) if single else '{}-{}'.format(
            markdown.slug(name), markdown.slug(title, fallback='sheet')
        )

        out.write(file_name + '.csv', sheets.to_csv(rows))


def dump_form(forms_service, file_id, name, out, options):
    form = forms.fetch(forms_service, file_id)
    form.title = name

    try:
        forms.keep_matching(form, options['--match'])
    except LookupError as missing:
        raise Skip("{}, which does not ask {!r}".format(name, str(missing)))

    if out.concat or options['--form-format'] == 'md':
        text = forms.to_markdown(form)

        if out.concat:
            return out.add(text)

        return out.write(markdown.slug(name) + '.md', text)

    if options['--form-format'] == 'xlsx':
        path = out.reserve(markdown.slug(name) + '.xlsx')
        forms.to_xlsx(form, path)
        out.report(path)

        return path

    directory = out.child(markdown.slug(name))
    questions = directory.child('questions')
    people = directory.child('people')

    for index, question in enumerate(form.questions, start=1):
        questions.write(
            '{:02d}-{}.md'.format(index, markdown.slug(question.title, fallback='question')),
            forms.question_markdown(form, question),
        )

    for response in form.responses:
        people.write(
            markdown.slug(response.label, fallback='respondent') + '.md',
            forms.person_markdown(form, response),
        )


def dump_as_pdf(drive, file_id, name, out):
    """Slides, drawings and the like, in the one format Drive exports them all as."""

    if out.concat:
        raise Skip("{}, which only exports as a pdf".format(name))

    return out.write(markdown.slug(name) + '.pdf', docs.export_bytes(drive, file_id, PDF))


def dump_file(drive, file_id, name, out):
    data = docs.download_bytes(drive, file_id)

    if out.concat:
        try:
            return out.add('{}\n\n{}'.format(markdown.heading(name), data.decode('utf-8')))
        except UnicodeDecodeError:
            raise Skip("{}, which is not text".format(name))

    return out.write(Path(name).name, data)


def validate(options):
    if options['--sheet-format'] not in SHEET_FORMATS:
        raise SystemExit("--sheet-format must be one of: {}".format(', '.join(SHEET_FORMATS)))

    if options['--form-format'] not in FORM_FORMATS:
        raise SystemExit("--form-format must be one of: {}".format(', '.join(FORM_FORMATS)))


def parse_matches(filters):
    """QUESTION=ANSWER filters as (question, answer) pairs."""

    matches = []

    for text in filters:
        question, equals, answer = text.partition('=')

        if not equals or not question.strip():
            raise SystemExit("--match takes QUESTION=ANSWER, not {!r}".format(text))

        matches.append((question, answer))

    return matches


def main():
    options = docopt(__doc__, version=VERSION)

    validate(options)

    options['--match'] = parse_matches(options['--match'])

    try:
        wanted = links.collect(options['<link>'], options['--input'])
    except (links.LinkError, OSError) as error:
        raise SystemExit(str(error))

    if not wanted:
        raise SystemExit("No links given; pass them as arguments, with --input, or on standard input.")

    config = GoogleConfigFile(section=options['--config'])

    api = services(authorize(config.token_path, config.credentials_path))

    output = options['--output']
    stream = None

    if options['--concat']:
        try:
            stream = open(output, 'w', encoding='utf-8') if output else sys.stdout
        except OSError as error:
            raise SystemExit(str(error))

        out = Concat(stream)
    else:
        out = Directory(output or '.', quiet=options['--quiet'])

    failed = 0

    try:
        for link in wanted:
            try:
                failed += dump(link, api, out, options)
            except Skip as skipped:
                print("skipped {}".format(skipped), file=sys.stderr)
            except Exception as error:
                failed += 1
                print("{}: {}".format(link.url, error), file=sys.stderr)
    finally:
        if stream is not None and stream is not sys.stdout:
            stream.close()

    if failed:
        raise SystemExit("{} file(s) could not be dumped".format(failed))
