# Random tools I make

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

## Markdown utilities

### onelinesummary (1.0)

```
Create one-line summary of all documents in a directory with links.

Usage:
    onelinesummary [options] PATH

Options:
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
