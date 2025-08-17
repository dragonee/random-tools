"""GitHub repository synchronization tool for managing multiple repositories.

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
"""

import os
import sys
import subprocess
import datetime
from pathlib import Path

from docopt import docopt

VERSION = '1.0'

def run_git_command(directory, command, check=True):
    """Run a git command in the specified directory."""
    try:
        result = subprocess.run(
            ['git'] + command.split(),
            cwd=directory,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stdout.strip(), e.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def is_git_repository(directory):
    """Check if directory is a git repository."""
    success, _, _ = run_git_command(directory, "status", check=False)
    return success

def get_current_branch(directory):
    """Get the current branch name."""
    success, stdout, _ = run_git_command(directory, "branch --show-current", check=False)
    if success:
        return stdout.strip()
    return None

def has_changes(directory):
    """Check if repository has any changes (staged, unstaged, or untracked)."""
    # Check for staged changes
    success, stdout, _ = run_git_command(directory, "diff --cached --quiet", check=False)
    if not success:  # Exit code != 0 means there are staged changes
        return True
    
    # Check for unstaged changes
    success, stdout, _ = run_git_command(directory, "diff --quiet", check=False)
    if not success:  # Exit code != 0 means there are unstaged changes
        return True
    
    # Check for untracked files
    success, stdout, _ = run_git_command(directory, "ls-files --others --exclude-standard", check=False)
    if success and stdout.strip():
        return True
    
    return False

def show_git_status(directory):
    """Display git status for the repository."""
    success, stdout, stderr = run_git_command(directory, "status --porcelain", check=False)
    if success and stdout:
        print(f"  Changes in {directory.name}:")
        for line in stdout.split('\n'):
            if line.strip():
                print(f"    {line}")
        return True
    return False

def get_user_strategy():
    """Ask user to choose synchronization strategy."""
    while True:
        print("\nChoose synchronization strategy:")
        print("  a) Commit + pull with rebase + push")
        print("  b) Stash + pull + stash pop")
        print("  s) Skip this repository")
        
        choice = input("Enter choice (a/b/s): ").lower().strip()
        
        if choice in ['a', 'b', 's']:
            return choice
        
        print("Invalid choice. Please enter 'a', 'b', or 's'.")

def strategy_commit_rebase_push(directory, commit_message):
    """Execute commit + rebase + push strategy."""
    print(f"  → Executing commit + rebase + push strategy...")
    
    # Stage all changes
    success, stdout, stderr = run_git_command(directory, "add .")
    if not success:
        print(f"  ✗ Failed to stage changes: {stderr}")
        return False
    
    # Commit changes
    success, stdout, stderr = run_git_command(directory, f'commit -m "{commit_message}"')
    if not success:
        print(f"  ✗ Failed to commit changes: {stderr}")
        return False
    
    print(f"  ✓ Committed changes")
    
    # Pull with rebase
    success, stdout, stderr = run_git_command(directory, "pull --rebase")
    if not success:
        print(f"  ✗ Rebase failed: {stderr}")
        print(f"  Manual intervention required in {directory.name}")
        return False
    
    print(f"  ✓ Pulled with rebase")
    
    # Push changes
    success, stdout, stderr = run_git_command(directory, "push")
    if not success:
        print(f"  ✗ Failed to push: {stderr}")
        return False
    
    print(f"  ✓ Pushed changes")
    return True

def strategy_stash_pull_pop(directory):
    """Execute stash + pull + stash pop strategy."""
    print(f"  → Executing stash + pull + stash pop strategy...")
    
    # Stash changes
    success, stdout, stderr = run_git_command(directory, "stash push -m 'github-synchronize auto-stash'")
    if not success:
        print(f"  ✗ Failed to stash changes: {stderr}")
        return False
    
    print(f"  ✓ Stashed changes")
    
    # Pull changes
    success, stdout, stderr = run_git_command(directory, "pull")
    if not success:
        print(f"  ✗ Failed to pull: {stderr}")
        return False
    
    print(f"  ✓ Pulled changes")
    
    # Pop stash
    success, stdout, stderr = run_git_command(directory, "stash pop")
    if not success:
        print(f"  ✗ Stash pop failed (conflicts): {stderr}")
        print(f"  Manual intervention required in {directory.name}")
        return False
    
    print(f"  ✓ Applied stashed changes")
    return True

def process_repository(directory, commit_message):
    """Process a single repository."""
    repo_name = directory.name
    print(f"\n📁 Processing repository: {repo_name}")
    
    # Check if it's a git repository
    if not is_git_repository(directory):
        print(f"  ⚠️  Not a git repository, skipping")
        return True
    
    # Check current branch
    current_branch = get_current_branch(directory)
    if current_branch != 'main':
        print(f"  ⚠️  Not on main branch (currently on '{current_branch}')")
        
        # Check if there are uncommitted changes
        if has_changes(directory):
            print(f"  ⚠️  Has uncommitted changes, skipping")
            return True
        
        # No uncommitted changes, offer to checkout main
        print("  💡 No uncommitted changes detected")
        while True:
            choice = input("  Switch to main branch and pull? (y/n/s): ").lower().strip()
            if choice == 'y':
                # Checkout main
                success, stdout, stderr = run_git_command(directory, "checkout main")
                if not success:
                    print(f"  ✗ Failed to checkout main: {stderr}")
                    return False
                print(f"  ✓ Switched to main branch")
                
                # Pull latest changes
                success, stdout, stderr = run_git_command(directory, "pull")
                if not success:
                    print(f"  ✗ Failed to pull: {stderr}")
                    return False
                print(f"  ✓ Pulled latest changes")
                return True
            elif choice == 'n':
                print(f"  ⏭️  Staying on '{current_branch}' branch")
                return True
            elif choice == 's':
                print(f"  ⏭️  Skipping repository")
                return True
            else:
                print("  Invalid choice. Please enter 'y', 'n', or 's'.")
                continue
    
    # Check for changes
    if not has_changes(directory):
        print(f"  ✓ No changes detected, pulling latest changes...")
        
        # Pull latest changes
        success, stdout, stderr = run_git_command(directory, "pull")
        if not success:
            print(f"  ✗ Failed to pull: {stderr}")
            return False
        
        print(f"  ✓ Pulled latest changes")
        return True
    
    # Show git status
    show_git_status(directory)
    
    # Get user strategy
    strategy = get_user_strategy()
    
    if strategy == 's':
        print(f"  ⏭️  Skipping repository")
        return True
    elif strategy == 'a':
        return strategy_commit_rebase_push(directory, commit_message)
    elif strategy == 'b':
        return strategy_stash_pull_pop(directory)
    
    return False

def main():
    """Main entry point for github-synchronize command."""
    arguments = docopt(__doc__, version=VERSION)
    
    # Generate default commit message with current date
    current_date = datetime.date.today().strftime('%Y-%m-%d')
    default_message = f"docs: update {current_date}"
    
    commit_message = arguments.get('--message') or default_message
    current_dir = Path.cwd()
    
    print(f"🔄 GitHub Synchronize Tool")
    print(f"📂 Working directory: {current_dir}")
    print(f"💬 Default commit message: '{commit_message}'")
    
    # Get all 1st level subdirectories
    subdirectories = [d for d in current_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    if not subdirectories:
        print("No subdirectories found.")
        return 0
    
    print(f"Found {len(subdirectories)} subdirectories")
    
    # Process each repository
    failed_repos = []
    
    for directory in sorted(subdirectories):
        try:
            success = process_repository(directory, commit_message)
            if not success:
                failed_repos.append(directory.name)
                print(f"\n❌ Stopping due to failure in {directory.name}")
                break
        except KeyboardInterrupt:
            print(f"\n⚠️  Interrupted by user")
            return 1
        except Exception as e:
            print(f"\n❌ Unexpected error processing {directory.name}: {e}")
            failed_repos.append(directory.name)
            break
    
    # Summary
    print(f"\n📊 Summary:")
    if failed_repos:
        print(f"❌ Failed on repository: {failed_repos[0]}")
        print(f"💡 Please resolve conflicts manually and re-run the tool")
        return 1
    else:
        print(f"✅ All repositories processed successfully")
        return 0

if __name__ == '__main__':
    exit(main())