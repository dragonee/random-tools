"""Generate Markdown report of Jira worklogs for a given period.

Usage:
    jira-report [options]

Options:
    -h, --help              Show this message.
    --version               Show version information.
    --month                 Report for the current calendar month.
    --week                  Report for the current calendar week.
    -d, --from-date DATE    Start date (YYYY-MM-DD or relative).
    -D, --to-date DATE      End date (YYYY-MM-DD or relative).
    -Y, --last              Previous period (--month/--week) or yesterday.
    -L, --level LEVEL       Section nesting depth [default: 1].
    --skip-worklogs         Don't print individual worklog descriptions.
    -S, --skip-categorization  Don't group worklogs into sections.
    --reset                 Ignore saved section mappings (start fresh).
"""

import json
import datetime
import sys
from pathlib import Path

from docopt import docopt
import dateparser

from .config.jira import JiraConfigFile
from .jira import get_timelogs_for_time_period

VERSION = '1.0'

SECTIONS_FILE = Path.home() / '.jira' / 'report_sections.json'


def load_sections():
    """Load section assignments from JSON file."""
    if SECTIONS_FILE.exists():
        try:
            with open(SECTIONS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}


def save_sections(sections):
    """Save section assignments to JSON file."""
    SECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SECTIONS_FILE, 'w') as f:
        json.dump(sections, f, indent=2, ensure_ascii=False)


def resolve_period(arguments):
    """Determine (start_date, end_date) from CLI arguments."""
    today = datetime.date.today()
    last = arguments['--last']

    if arguments['--month']:
        if last:
            # Previous month
            first_of_current = today.replace(day=1)
            end_date = first_of_current - datetime.timedelta(days=1)
            start_date = end_date.replace(day=1)
        else:
            start_date = today.replace(day=1)
            # Last day of current month
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - datetime.timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - datetime.timedelta(days=1)
        return start_date, end_date

    if arguments['--week']:
        # Monday = 0
        monday = today - datetime.timedelta(days=today.weekday())
        if last:
            monday = monday - datetime.timedelta(weeks=1)
        sunday = monday + datetime.timedelta(days=6)
        return monday, sunday

    from_date = arguments['--from-date']
    to_date = arguments['--to-date']

    if from_date:
        parsed = dateparser.parse(from_date)
        if parsed is None:
            print(f"Error: Unable to parse from-date '{from_date}'", file=sys.stderr)
            sys.exit(1)
        start_date = parsed.date()
    else:
        # -Y without --month/--week means yesterday
        start_date = today - datetime.timedelta(days=1) if last else today

    if to_date:
        parsed = dateparser.parse(to_date)
        if parsed is None:
            print(f"Error: Unable to parse to-date '{to_date}'", file=sys.stderr)
            sys.exit(1)
        end_date = parsed.date()
    else:
        end_date = start_date

    return start_date, end_date


def assign_sections(worklogs_by_issue, sections):
    """Interactively assign sections to issues not yet in the store.

    Returns the updated sections dict.
    """
    known_section_names = sorted(set(sections.values()))

    for issue_key, info in sorted(worklogs_by_issue.items()):
        if issue_key in sections:
            continue

        # Build menu
        print(f"\n{issue_key}: {info['summary']}", file=sys.stderr)
        print("What section does this belong to?", file=sys.stderr)

        for i, name in enumerate(known_section_names, 1):
            print(f"  {i}) {name}", file=sys.stderr)

        prompt = f"[1-{len(known_section_names)} or write section name] > " if known_section_names else "[write section name] > "

        try:
            answer = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            sys.exit(1)

        if not answer:
            print("No section provided, skipping.", file=sys.stderr)
            continue

        # Check if numeric choice
        if answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(known_section_names):
                section_name = known_section_names[idx - 1]
            else:
                # Treat as new section name
                section_name = answer
        else:
            section_name = answer

        sections[issue_key] = section_name

        # Update known names for subsequent prompts
        if section_name not in known_section_names:
            known_section_names.append(section_name)
            known_section_names.sort()

    return sections


def format_duration(seconds):
    """Format seconds as 'Xh Ym'."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _make_node():
    """Create an empty tree node."""
    return {'_issues': {}, '_children': {}}


def _add_to_tree(root, parts, issues):
    """Insert issues into the tree at the given path."""
    node = root
    for part in parts:
        if part not in node['_children']:
            node['_children'][part] = _make_node()
        node = node['_children'][part]
    node['_issues'].update(issues)


def _node_total_seconds(node):
    """Sum timeSpentSeconds for this node and all descendants."""
    total = sum(
        sum(w['timeSpentSeconds'] for w in info['worklogs'])
        for info in node['_issues'].values()
    )
    for child in node['_children'].values():
        total += _node_total_seconds(child)
    return total


def _render_node(node, path_parts, depth, grand_total, lines, skip_worklogs):
    """Recursively render a tree node into Markdown lines.

    Collapses nodes that have no direct issues and exactly one child
    (e.g. operational -> commercial -> consulting becomes a single heading).
    """
    children = node['_children']
    issues = node['_issues']

    # Collapse: no direct issues and exactly one child
    if not issues and len(children) == 1:
        child_name = next(iter(children))
        _render_node(children[child_name], path_parts + [child_name],
                     depth, grand_total, lines, skip_worklogs)
        return

    # Render heading (skip for the virtual root)
    if path_parts:
        section_path = ':'.join(path_parts)
        total = _node_total_seconds(node)
        pct = total / grand_total * 100 if grand_total > 0 else 0
        heading = '#' * (depth + 1)
        lines.append(f"{heading} {section_path} ({format_duration(total)}, {pct:.0f}%)")
        lines.append("")

    # Render direct issues
    for issue_key in sorted(issues.keys()):
        info = issues[issue_key]
        issue_seconds = sum(w['timeSpentSeconds'] for w in info['worklogs'])
        lines.append(f"- {issue_key}: {format_duration(issue_seconds)} - {info['summary']}")
        if not skip_worklogs:
            for w in info['worklogs']:
                if w['comment']:
                    lines.append(f"  - {w['comment']}")

    if issues:
        lines.append("")

    # Render children
    for child_name in sorted(children.keys()):
        _render_node(children[child_name], path_parts + [child_name],
                     depth + 1, grand_total, lines, skip_worklogs)


def generate_report(start_date, end_date, worklogs_by_issue, sections,
                    skip_worklogs=False, level=1):
    """Generate the Markdown report string."""
    lines = []

    from_str = start_date.strftime('%Y-%m-%d')
    to_str = end_date.strftime('%Y-%m-%d')
    lines.append(f"# Report from {from_str} to {to_str}")
    lines.append("")

    # Compute grand total
    grand_total = sum(
        sum(w['timeSpentSeconds'] for w in info['worklogs'])
        for info in worklogs_by_issue.values()
    )
    lines.append(f"Total: {format_duration(grand_total)}")
    lines.append("")

    # Truncate section paths to requested depth and group issues
    by_section = {}
    for issue_key, info in worklogs_by_issue.items():
        section = sections.get(issue_key, 'Other')
        parts = section.split(':')
        truncated = ':'.join(parts[:level])
        by_section.setdefault(truncated, {})[issue_key] = info

    # Build tree from section paths
    root = _make_node()
    for section_path, issues in by_section.items():
        parts = section_path.split(':')
        _add_to_tree(root, parts, issues)

    # Render tree into Markdown
    _render_node(root, [], 0, grand_total, lines, skip_worklogs)

    return "\n".join(lines)


def main():
    """Main entry point for jira-report command."""
    arguments = docopt(__doc__, version=VERSION)

    try:
        config = JiraConfigFile()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Please create ~/.jira/config.ini with your Jira credentials", file=sys.stderr)
        return 1

    start_date, end_date = resolve_period(arguments)

    print(f"Fetching worklogs from {start_date} to {end_date}...", file=sys.stderr)

    worklogs = get_timelogs_for_time_period(config, start_date, end_date)

    if not worklogs:
        print("No worklogs found for the given period.", file=sys.stderr)
        return 0

    # Group worklogs by issue
    worklogs_by_issue = {}
    for w in worklogs:
        key = w['issue']
        if key not in worklogs_by_issue:
            worklogs_by_issue[key] = {
                'summary': w['summary'],
                'worklogs': [],
            }
        worklogs_by_issue[key]['worklogs'].append(w)

    skip_categorization = arguments['--skip-categorization']

    if skip_categorization:
        sections = {}
    else:
        # Load sections (unless --reset) and assign interactively
        sections = {} if arguments['--reset'] else load_sections()
        sections = assign_sections(worklogs_by_issue, sections)
        save_sections(sections)

    # Generate and print report
    level = int(arguments['--level'])
    report = generate_report(start_date, end_date, worklogs_by_issue, sections,
                             skip_worklogs=arguments['--skip-worklogs'],
                             level=level)
    print(report)

    return 0


if __name__ == '__main__':
    exit(main())
