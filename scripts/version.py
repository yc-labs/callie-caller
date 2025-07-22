#!/usr/bin/env python3
"""
Version management script for Callie Caller.
Handles semantic versioning and git tagging.
"""

import argparse
import subprocess
import sys
import re
from pathlib import Path

# Add parent directory to path to import version module
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from callie_caller._version import __version__, get_version_info
except ImportError:
    print("Error: Could not import version module. Run from project root.")
    sys.exit(1)


def run_command(cmd, check=True, capture_output=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=check, 
            capture_output=capture_output, 
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Error: {e}")
        sys.exit(1)


def get_current_version():
    """Get the current version from the version file."""
    return __version__


def update_version_file(new_version):
    """Update the version in _version.py file."""
    version_file = Path(__file__).parent.parent / "callie_caller" / "_version.py"
    
    # Read current content
    content = version_file.read_text()
    
    # Update version
    content = re.sub(
        r'__version__ = "[^"]*"',
        f'__version__ = "{new_version}"',
        content
    )
    
    # Write back
    version_file.write_text(content)
    print(f"Updated version to {new_version} in {version_file}")


def parse_version(version_str):
    """Parse a semantic version string."""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$', version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    
    major, minor, patch = map(int, match.groups()[:3])
    prerelease = match.group(4)
    
    return major, minor, patch, prerelease


def bump_version(current_version, component):
    """Bump version component."""
    major, minor, patch, prerelease = parse_version(current_version)
    
    if component == "major":
        major += 1
        minor = 0
        patch = 0
    elif component == "minor":
        minor += 1
        patch = 0
    elif component == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid component: {component}")
    
    return f"{major}.{minor}.{patch}"


def check_git_status():
    """Check if git working directory is clean."""
    result = run_command("git status --porcelain")
    if result.stdout.strip():
        print("Error: Git working directory is not clean.")
        print("Please commit or stash your changes before creating a release.")
        sys.exit(1)


def create_git_tag(version, message=None):
    """Create a git tag for the version."""
    tag_name = f"v{version}"
    
    if not message:
        message = f"Release version {version}"
    
    # Create annotated tag
    run_command(f'git tag -a {tag_name} -m "{message}"')
    print(f"Created git tag: {tag_name}")
    
    return tag_name


def push_tag(tag_name):
    """Push tag to remote repository."""
    run_command(f"git push origin {tag_name}")
    print(f"Pushed tag {tag_name} to remote")


def commit_version_change(version):
    """Commit the version file change."""
    run_command("git add callie_caller/_version.py")
    run_command(f'git commit -m "Bump version to {version}"')
    print(f"Committed version bump to {version}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Callie Caller versions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current version
  python scripts/version.py --show

  # Bump patch version (1.0.0 -> 1.0.1)
  python scripts/version.py --bump patch

  # Bump minor version (1.0.0 -> 1.1.0)  
  python scripts/version.py --bump minor

  # Bump major version (1.0.0 -> 2.0.0)
  python scripts/version.py --bump major

  # Set specific version
  python scripts/version.py --set 1.2.3

  # Create release (bump, commit, tag, push)
  python scripts/version.py --release patch
        """
    )
    
    parser.add_argument(
        '--show',
        action='store_true',
        help='Show current version information'
    )
    
    parser.add_argument(
        '--bump',
        choices=['major', 'minor', 'patch'],
        help='Bump version component'
    )
    
    parser.add_argument(
        '--set',
        metavar='VERSION',
        help='Set specific version (e.g., 1.2.3)'
    )
    
    parser.add_argument(
        '--release',
        choices=['major', 'minor', 'patch'],
        help='Create a release (bump version, commit, tag, and push)'
    )
    
    parser.add_argument(
        '--no-push',
        action='store_true',
        help='Skip pushing tags to remote (use with --release)'
    )
    
    parser.add_argument(
        '--message',
        help='Custom message for git tag'
    )
    
    args = parser.parse_args()
    
    if args.show:
        current = get_current_version()
        info = get_version_info()
        print(f"Current version: {current}")
        print(f"Version info: {info}")
        return
    
    if not any([args.bump, args.set, args.release]):
        parser.print_help()
        return
    
    current_version = get_current_version()
    print(f"Current version: {current_version}")
    
    # Determine new version
    if args.bump:
        new_version = bump_version(current_version, args.bump)
    elif args.set:
        new_version = args.set
        # Validate version format
        try:
            parse_version(new_version)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.release:
        new_version = bump_version(current_version, args.release)
    
    print(f"New version: {new_version}")
    
    # Update version file
    update_version_file(new_version)
    
    # If creating a release, handle git operations
    if args.release:
        # Check git status
        check_git_status()
        
        # Commit version change
        commit_version_change(new_version)
        
        # Create tag
        tag_name = create_git_tag(new_version, args.message)
        
        # Push tag unless --no-push specified
        if not args.no_push:
            push_tag(tag_name)
        
        print(f"\n✅ Release {new_version} created successfully!")
        print(f"   Tag: {tag_name}")
        
        if not args.no_push:
            print("   Pushed to remote repository")
        else:
            print("   Tag created locally (not pushed)")
        
        print(f"\nNext steps:")
        print(f"  1. Build and push Docker image:")
        print(f"     ./build.sh --version {new_version} --project YOUR_PROJECT_ID --push --latest")
        print(f"  2. Deploy to production:")
        print(f"     export GAR_IMAGE=us-central1-docker.pkg.dev/YOUR_PROJECT/callie-caller/callie-caller:{new_version}")
        print(f"     docker-compose -f docker-compose.prod.yml up -d")
    
    else:
        print(f"\n✅ Version updated to {new_version}")
        print("Note: Changes are not committed. Use --release to create a full release.")


if __name__ == "__main__":
    main() 