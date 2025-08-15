"""Git repository batch processor.

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

"""
import os
import subprocess
import datetime
from pathlib import Path
from docopt import docopt

VERSION = '1.0'


def is_git_repo(path):
    """Check if a directory is a git repository."""
    git_dir = Path(path) / '.git'
    return git_dir.exists()


def has_changes(repo_path):
    """Check if a git repository has uncommitted changes."""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        return len(result.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        return False


def get_git_status(repo_path):
    """Get git status output for a repository."""
    try:
        result = subprocess.run(
            ['git', 'status', '--short'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error getting status: {e}"


def find_git_repositories(search_path=None):
    """Find all git repositories in the specified directory and subdirectories."""
    if search_path:
        current_dir = Path(search_path).resolve()
        if not current_dir.exists():
            print(f"Error: Directory '{search_path}' does not exist")
            return []
        if not current_dir.is_dir():
            print(f"Error: '{search_path}' is not a directory")
            return []
    else:
        current_dir = Path.cwd()
    
    git_repos = []
    
    # Check current directory
    if is_git_repo(current_dir):
        git_repos.append(current_dir)
    
    # Check subdirectories (only one level deep to avoid deep recursion)
    for item in current_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            if is_git_repo(item):
                git_repos.append(item)
    
    return git_repos


def commit_all_and_push(repo_path, commit_message):
    """Commit all changes and push to remote."""
    try:
        # Add all changes
        subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
        
        # Commit with message
        subprocess.run(['git', 'commit', '-m', commit_message], cwd=repo_path, check=True)
        
        # Push to remote
        result = subprocess.run(['git', 'push'], cwd=repo_path, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  ✓ Successfully committed and pushed")
            return True
        else:
            print(f"  ✗ Push failed: {result.stderr.strip()}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error: {e}")
        return False


def commit_manually_and_push(repo_path):
    """Add all changes, open interactive git commit and then push."""
    try:
        # Add all changes first
        subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
        print("  Added all changes to staging area")
        
        # Open interactive commit (this will open the user's default editor)
        result = subprocess.run(['git', 'commit'], cwd=repo_path)
        
        if result.returncode == 0:
            # If commit was successful, push
            push_result = subprocess.run(['git', 'push'], cwd=repo_path, capture_output=True, text=True)
            
            if push_result.returncode == 0:
                print(f"  ✓ Successfully committed and pushed")
                return True
            else:
                print(f"  ✗ Push failed: {push_result.stderr.strip()}")
                return False
        else:
            print(f"  ⚠ Commit cancelled or failed")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error: {e}")
        return False


def get_user_choice():
    """Get user choice for what to do with the repository."""
    while True:
        print("\nChoose an action:")
        print("  1. Commit all and push with default message")
        print("  2. Commit manually and then push")
        print("  3. Skip this repository")
        print("  4. Stop processing")
        
        choice = input("Enter choice (1-4): ").strip()
        
        if choice in ['1', '2', '3', '4']:
            return choice
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


def process_repository(repo_path, commit_message):
    """Process a single repository with user interaction."""
    repo_name = repo_path.name if repo_path.name != '.' else 'current directory'
    
    print(f"\n{'='*60}")
    print(f"Repository: {repo_name}")
    print(f"Path: {repo_path}")
    print(f"{'='*60}")
    
    # Show git status
    status = get_git_status(repo_path)
    if status:
        print("Changes:")
        for line in status.split('\n'):
            print(f"  {line}")
    else:
        print("No changes detected")
        return True
    
    # Get user choice
    choice = get_user_choice()
    
    if choice == '1':
        print(f"\nCommitting with message: '{commit_message}'")
        return commit_all_and_push(repo_path, commit_message)
    
    elif choice == '2':
        print(f"\nOpening interactive commit...")
        return commit_manually_and_push(repo_path)
    
    elif choice == '3':
        print(f"\nSkipping repository")
        return True
    
    elif choice == '4':
        print(f"\nStopping processing")
        return False  # This will signal to stop processing
    
    return True


def main():
    """Main entry point for push command."""
    args = docopt(__doc__, version=VERSION)
    
    # Determine commit message
    commit_message = args['<commit_message>']
    if not commit_message:
        current_date = datetime.date.today().strftime('%Y-%m-%d')
        commit_message = f"docs: update on {current_date}"
    
    # Get search path
    search_path = args['--path']
    if search_path:
        print(f"Searching in directory: {search_path}")
    else:
        print(f"Searching in current directory: {Path.cwd()}")
    
    print(f"Default commit message: '{commit_message}'")
    
    # Find all git repositories
    repos = find_git_repositories(search_path)
    
    if not repos:
        search_location = search_path if search_path else "current directory"
        print(f"No git repositories found in {search_location} or subdirectories")
        return 0
    
    print(f"Found {len(repos)} git repositories")
    
    # Filter repositories with changes
    repos_with_changes = []
    for repo in repos:
        if has_changes(repo):
            repos_with_changes.append(repo)
    
    if not repos_with_changes:
        print("No repositories have uncommitted changes")
        return 0
    
    print(f"Found {len(repos_with_changes)} repositories with changes")
    
    # Process each repository
    processed = 0
    for repo in repos_with_changes:
        if not process_repository(repo, commit_message):
            # User chose to stop processing
            break
        processed += 1
    
    print(f"\n{'='*60}")
    print(f"Processed {processed} of {len(repos_with_changes)} repositories")
    print("Done!")
    
    return 0


if __name__ == '__main__':
    exit(main())