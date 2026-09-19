# Random tools I made

## Table of Contents

- [Calendar availability](#calendar-availability)
- [Timers](#timers)
- [Google Drive](#google-drive)
- [CSV/JSON tools](#csvjson-tools)
- [File tools](#file-tools)
- [SoDA mail matcher](#soda-mail-matcher)
- [Containers](#containers)
- [Git Tools](#git-tools)
- [Clipboard utilities](#clipboard-utilities)
- [Markdown utilities](#markdown-utilities)
- [Other](#other)

## Calendar availability

### evenings (1.0)

```
Check if I'm free in the evening.

Usage: 
    evenings [options]

Options:
    -S, --stats           Show statistics.
    -a, --all             Show all evenings.
    -b, --busy            Show busy evenings.
    -d, --days DAYS       Number of days to check [default: 14].
    -s, --start DATE      Start date
    --hour-from HOUR      Start hour [default: 18].
    --hour-to HOUR        End hour [default: 22].
    -h, --help       Show this message.
    --version        Show version information.
```

## Timers

### timer (1.0)

```
A console stopwatch with flag times, like a race control clock.

Usage:
    timer [options] TIME...
    timer [options] FILE
    timer -h | --help
    timer --version

Arguments:
    TIME    Up to four times, in this order: green, yellow, red, disqualify.
            Bare numbers are minutes, so `timer 10 12 15` counts 10, 12 and
            15 minutes. Units and combinations work too: 90s, 6m30s,
            "6m 30s", 1h5m, 12:30 (mm:ss) and 1:02:30 (hh:mm:ss).
    FILE    A settings file with the same times under a [flags] section:

                [flags]
                green = 12m
                yellow = 15m
                red = 18m
                disqualify = 22m

            Quoted values are fine as well, so a .toml file written that way
            reads the same. Only green, yellow, red and disqualify are known.

Options:
    -s, --start        Start counting as the program runs, not on Space.
    -n, --now          A synonym for --start.
    --no-notify        Do not post macOS notifications when a flag is passed.
    --no-caffeinate    Do not keep the machine awake while the timer runs.
    -h, --help         Show this screen.
    --version          Show version.

Keys:
    Space    start the timer, and pause or resume it afterwards
    q        quit (Ctrl-C works too)

The clock keeps running past the last flag, so an overrun stays visible.
If `caffeinate` is around the machine is kept awake for as long as the timer
lives, and on macOS each flag also raises a notification. That notification
carries Script Editor's icon, since `osascript` is what posts it; install
`terminal-notifier` and it is posted through that instead.

Examples:
    timer 12m 15m 18m 22m
    timer 10 12 15
    timer -s 6m30s
    timer settings.toml
```

## Google Drive

### dumper (1.1)

```
Dump Google Drive files into local documents.

Usage:
    dumper [options] [<link>...]

Options:
    -c, --config SECTION   Section of ~/.google/config.ini to authorize with [default: Google].
    -i, --input FILE       Read links from a YAML or plain text file ('-' for stdin).
    -o, --output PATH      Where to write: a directory (default: .), or the file
                           to write into with --concat (default: stdout).
    --sheet-format FORMAT  Dump spreadsheets as xlsx, csv or md [default: xlsx].
    --form-format FORMAT   Dump form responses as xlsx, dir or md [default: xlsx].
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

The config section holds the paths to the OAuth client and to the token
cached from it, so several accounts can each have their own section:

    [WorkGoogle]
    token_path = ~/.google/work-token.pickle
    credentials_path = ~/.google/work-credentials.json
```

### Listing links in a file

`--input` takes a YAML file, where a link can carry the name its files are
written under:

```yaml
links:
  - https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit
  - name: Weekly retro
    link: https://docs.google.com/document/d/1BcDeFgHiJkLmNoPqRsTuVwXyZa/edit
  - name: Team survey
    link: https://docs.google.com/forms/d/1CdEfGhIjKlMnOpQrStUvWxYzAb/edit
  - https://drive.google.com/drive/folders/1DeFgHiJkLmNoPqRsTuVwXyZaBc
```

A plain map of names to links does the same:

```yaml
Weekly retro: https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit
Budget 2026: https://docs.google.com/spreadsheets/d/1BcDeFgHiJkLmNoPqRsTuVwXyZa/edit
```

A list of bare links, with no names, works too - and so does a plain text
file with one link per line, `#` starting a comment.

```
dumper -i links.yml -o dump/ --sheet-format md --form-format dir
dumper -i links.yml --concat -o everything.md
```

## CSV/JSON tools

### copiesfromcsv (1.0)

```
Usage: 
copiesfromcsv [options] CSVFILE INFILE 

Options:
    --column N    Use specific column, zero-indexed [default: 0]
    --drop-first  Drop first line.
    -h, --help  Show this message.
    --version   Show version information.
```

### maptocsv (1.0)

```
Convert a JSON map dictionary into CSV file with two columns

Usage:
    maptocsv [options] JSONMAP OUTFILE

Options:
    -k KEY_TITLE    Use the following for the first column of title row of CSV file.
    -v VALUE_TITLE  Use the following for the second column of title row of CSV file.
    -h, --help  Show this message.
    --version   Show version information.
```

### maptocsvcolumn (1.0)

```
Append a JSON map to a CSV column.

Usage:
    maptocsvcolumn [options] INFILE JSONMAP OUTFILE

Options:
    --first-row TEXT  Use the following for the first row in CSV file.
    --column NUM      Use this column as map key [default: 2].
    -h, --help  Show this message.
    --version   Show version information.
```

## File tools

### movetoguids (1.0)

```
Copy files in directory to GUID generated files.

Usage:
    movetoguids [options] IN_DIRECTORY OUT_DIRECTORY

Options:
    -p MAP      Persist files in a JSON map.
    -h, --help  Show this message.
    --version   Show version information.
```

### pdfrepeat (1.0)

```
Repeat a PDF multiple times

Usage:
    pdfrepeat [options] FILE N

Options:
    -o OUTPUT   Provide a filename for output file.
    -h, --help  Show this message.
    --version   Show version information.
```

### qr (1.0.0)

```
Generate QR codes from links with automatic file naming.

Usage:
    qr LINK [FILE] [options]
    qr -h | --help
    qr --version

Arguments:
    LINK    The URL or text to encode in the QR code
    FILE    Output filename (optional, will be slugified from LINK if not provided)

Options:
    -q --quiet    Quiet mode, suppress output messages.
    -h --help     Show this screen.
    --version     Show version.
```

## SoDA mail matcher

### sodamatcher (1.0)

```
Match SoDA members e-mails with GUID map. Output a new CSV file.

Usage:
    sodamatcher [options] IN_CSVFILE MAPFILE

Options:
    -p MAP           Persist JSON map.
    --no-drop-first  Drop first row in CSV file.
    --default FILE   Present this file for match [default: default.pdf].
    --column NUM     Use this column, zero-indexed [default: 2].  
    -h, --help  Show this message.
    --version   Show version information.
```

Usage of these scripts with matcher:

```
movetoguids -p soda/domain_map.json soda/domains/ soda/encoded/
sodamatcher -p soda/emails.json soda/users.csv soda/domain_map.json
maptocsvcolumn --first-row link soda/users.csv soda/emails.json soda/mailing.csv
maptocsv -k email -v link soda/domain_map.json soda/domain_map.csv
```

## Containers

### h (1.0)

```
Run things inside the docker container described by .container.ini.

Usage:
    h [COMMAND] [ARGUMENTS ...]
    h init [FILE]
    h -h | --help
    h --version

Examples:
    h sh                   a shell in the container
    h mix test             a configured command, with arguments
    h logs                 follow its output
    h cp local.txt         copy a file in
    h init                 write a starter .container.ini here

`h` on its own lists the commands the config file defines, alongside the
built-in ones: id, logs, cp, start, stop, restart and init.

The config file is looked up in the current directory, then its parents;
$CONTAINER_INI overrides all of that.

    [General]
    name = ^myapp-app-1$      ; docker's name filter, which it reads as a regex
    workdir = /app            ; default cwd for exec, default target for cp

    [sh]
    program = bash            ; h sh -> docker exec -it <id> bash
    help = a shell in the container

Every section other than [General] names a command. `program` is the only
required key; `help`, `tty`, `user`, `workdir` and `env` are optional, and
`user`, `workdir` and `env` may also be set in [General] as defaults.

`tty` is auto by default: the -t flag is passed only when this script is
itself attached to a terminal, so `h mix test` is interactive at a prompt
and pipes cleanly from cron or CI without needing a second no-tty command.

Options:
    -h, --help     Show this message.
    --version      Show version information.
```

`h init` writes a starter `.container.ini` — the same file as
[`src/randomtools/examples/container.ini`](src/randomtools/examples/container.ini) —
which you then point at your own container:

```
h init
docker ps                 # find the container's name
$EDITOR .container.ini    # name = ^myapp-app-1$
h                         # lists what you can now run in it
```

`container` is installed as a second name for the same tool, for when a
one-letter `h` is already taken on your machine.

## Git Tools

### push (1.0)

```
Git repository batch processor.

Usage:
    push [<commit_message>] [--path=<directory>]
    push (-h | --help)
    push --version

Arguments:
    <commit_message>  Commit message to use for all repositories.

Options:
    -h --help             Show this screen.
    --version             Show version.
    --path=<directory>    Directory to search for repositories (defaults to current directory).

Examples:
    push                           # Use default message "docs: update on <date>"
    push "feat: add new feature"   # Use custom commit message
    push --path=/home/user/code    # Search in specific directory
```

### github-synchronize (1.0)

```
GitHub repository synchronization tool for managing multiple repositories.

Usage: 
    github-synchronize [options]

Options:
    -m MESSAGE, --message=MESSAGE  Default commit message (defaults to current date)
    -h, --help                     Show this message.
    --version                      Show version information.

Description:
    Iterates through all 1st level subdirectories of the current directory
    and synchronizes git repositories. For each repository:
    
    1. Checks if on main branch (skips if not)
    2. Checks for changes and displays git status
    3. Offers synchronization strategies:
       a) Commit + pull with rebase + push
       b) Stash + pull + stash pop
    4. Stops on rebase conflicts or stash pop conflicts

Examples:
    github-synchronize                                    # Use default commit message
    github-synchronize -m "feat: add new research notes"  # Custom commit message
```

## Clipboard utilities

### copier (1.0)

```
Copier tool for clipboard management with YAML configuration.

Usage:
    copier [<file>]
    copier -c <name>
    copier -e <name>
    copier -h | --help
    copier --version

Options:
    -c <name>        Create a new configuration file and open it in editor.
    -e <name>        Open an existing configuration file in editor.
    -h, --help       Show this message.
    --version        Show version information.

Commands in shell:
    SECTION          - Copy section content to clipboard
    add KEY VALUE    - Add a new text section
    addfile KEY PATH - Add a new file section
    open SECTION     - Open a file section with 'open'
    list             - Show available sections
    config           - Show the raw YAML configuration
    edit             - Edit the YAML configuration file
    help             - Show this help
    
Quit by pressing Ctrl+D or Ctrl+C.

Configuration:
    Create ~/.info/<file>.yaml with sections. Each section can be:
    
    section_name:
      type: text|file|program
      (type-specific attributes)
    
    Types:
    - text (default): requires 'content' attribute
    - file: requires 'file' attribute (absolute path or relative to ~/.info/)
    - program: requires 'command' attribute (shell command)
    
    Example ~/.info/example.yaml:
    
    greeting:
      type: text
      content: "Hello, World!"
    
    current_dir:
      type: program
      command: "pwd"
    
    readme_absolute:
      type: file
      file: "~/README.md"
    
    readme_relative:
      type: file
      file: "snippets/readme.txt"
    
    simple_text: "This is just plain text"
```

## Markdown utilities

### onelinesummary (1.0.1)

```
Create one-line summary of all documents in a directory with links.

Usage:
    onelinesummary [options] PATH

Options:
    -p, --pattern PATTERN  Pattern to match files [default: *.md]
    -h, --help  Show this message.
    --version   Show version information.
```

### usecase (1.0.2)

```
List usecases from Markdown files as Markdown list.

Usage: 
    usecase [options] PATH

Options:
    --github-wiki    Display names in Github Wiki format
    -h HEADER, --header HEADER  Use header for file names.
    --no-colon       Do not put colon after file name.
    --help           Show this message.
    --version        Show version information.

Scenario file format:

# (vX.Y)            <- version, optional

## X. Something     <- a case

## X. .Hidden       <- This will not show up

## Cases

1. Some case        <- short notation
2. Some other case  <- can also be placed on top of file
```

## Other

### wish (1.0)

```
Get wishes for someone.

Usage: 
    wish [options]

Options:
    --plural         Display plural wishes.
    -h, --help       Show this message.
    --version        Show version information.
```
