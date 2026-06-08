# Random tools I made

## Table of Contents

- [Calendar availability](#calendar-availability)
- [CSV/JSON tools](#csvjson-tools)
- [File tools](#file-tools)
- [SoDA mail matcher](#soda-mail-matcher)
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
