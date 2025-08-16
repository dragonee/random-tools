# The `jira` tool

I'd like to have a tool that would help me create worklogs on Jira issues. 

This tool should have the following features:

## Provide a "shell-like" access in the tool

This is mostly implemented in `src/randomtools/jira.py` – I copied it from another project

Maintain the structure so that the following will be preserved:

1. A loop waits for user input
2. User can write issue name and time
   1. Filter out all issues, if not ambiguous, then this issue is chosen, else ask for clarification
3. In addition, a couple of commands can be specified, described below: `list`, `add`, `exclude`, `create`, `update`

## Logging time

When the user writes the issue name and time, the time is logged in to the list of issues.

The program should print out all the worklogs for the current day from the API.

## Saved and excluded items

An user can use two commands to add arbitrary issues to the list

- `add ISSUE`
- `exclude ISSUE`

The `add` command would save the issue so that it's always displayed, regardless of whether work was logged on it. If it was in the excluded list, it would remove it from this list.

The `exclude` command would remove the issue from the saved list, and add that to the excluded list, so that it won't show in the list of issue, even if user worked on that.

The saved and excluded lists should be two sets, and the backend should save it as two json files.

## Creating new issues

An user can use the `create PROJECTNAME Issue description` command in order to create an arbitrary issue in Jira. At the end, display link to Jira issue in a copy-friendly manner, and add it to the `saved` list.

## Get recent issues with time logged on

1. That tool should get issues from the last 7 days that I have worked on
2. These should be stored and cached
3. If the cache file doesn't exist or `update` command is run, the tool would refresh the cache