# Random tools I made

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

## Jira Tools

### jira-dashboard-dates (1.0)

```
Jira Time Tracker auto-updater.

Usage:
    jira-dates [--date=<date>] [--format=<fmt>] [--dashboard=<id>] [--month-string=<str>] [--week-string=<str>]
    jira-dates (-h | --help)

Options:
    -h --help              Show this screen.
    --date=<date>          Reference date for calculations (YYYY-MM-DD format, defaults to today).
    --format=<fmt>         Date format [default: %Y-%m-%d].
    --dashboard=<id>       Dashboard ID (overrides config).
    --month-string=<str>   String to detect month gadgets (overrides config, defaults to "month").
    --week-string=<str>    String to detect week gadgets (overrides config, defaults to "week").

Examples:
    jira-dates                                    # Auto-update all time tracker gadgets to current periods
    jira-dates --date=2025-07-15                 # Use July 15, 2025 as reference date
    jira-dates --dashboard=123                    # Update specific dashboard
    jira-dates --month-string="monthly"          # Use "monthly" to detect month gadgets
    jira-dates --week-string="weekly"            # Use "weekly" to detect week gadgets

Configuration:
    Create ~/.jira/config.ini with:
    [Jira]
    domain = your-domain
    email = your-email@example.com
    api_token = your-api-token
    dashboard_id = 12345
    month_string = month  # Optional, defaults to "month"
    week_string = week    # Optional, defaults to "week"
```

### jira-dashboard (1.0)

```
Search Jira dashboards and list dashboard gadgets to find gadget IDs.

Usage:
    jira-dashboard [<dashboard_id>] [--filter=<type>] [--search=<query>] [--raw] [--properties=<gadget_id>] [--config=<gadget_id>]
    jira-dashboard (-h | --help)

Options:
    -h --help                Show this screen.
    --filter=<type>          Filter by gadget type (e.g., "TimeTrackingGadget").
    --search=<query>         Search dashboards by name/description.
    --raw                    Show raw JSON response.
    --properties=<gadget_id> Show properties for specific gadget ID.
    --config=<gadget_id>     Show gadgetConfig property value for specific gadget ID.

Examples:
    jira-dashboard                                 # List all available dashboards
    jira-dashboard 12345                           # List all gadgets in dashboard 12345
    jira-dashboard 12345 --filter=TimeTrackingGadget  # Filter time tracking gadgets
    jira-dashboard --search="My Dashboard"         # Search for dashboards by name
    jira-dashboard 12345 --raw                     # Show raw JSON response
    jira-dashboard 12345 --properties=11579       # Show properties for gadget 11579
    jira-dashboard 12345 --config=11579           # Show gadgetConfig for gadget 11579

Configuration:
    Create ~/.jira/config.ini with:
    [Jira]
    domain = your-domain
    email = your-email@example.com
    api_token = your-api-token
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
