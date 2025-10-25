#!/usr/bin/env python3
"""
Automates the process of building and deploying the release package to the setup branch.
"""

import os
import subprocess
import shutil
from pathlib import Path
import glob

def confirm(prompt):
    """Get user confirmation."""
    while True:
        reply = input(f"{prompt} [y/n]: ").lower().strip()
        if reply[:1] == 'y':
            return True
        if reply[:1] == 'n':
            return False

def run_command(cmd, cwd='.'):
    """Run a command and exit if it fails."""
    print(f"\nRunning command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
        exit(1)
    return result

def main():
    print("=== Automated Release Packager for 'setup' branch ===")

    # --- 1. Run the packaging script ---
    if not confirm("Step 1: Run the packaging script? (scripts/PackageEverything.py)"):
        print("Aborted.")
        return

    packaging_script = Path("scripts/PackageEverything.py")
    if not packaging_script.exists():
        print(f"Error: Cannot find {packaging_script}")
        return

    run_command(["python3", str(packaging_script)])

    # --- 2. Find the new package directory ---
    publish_dir = Path("Publish")
    try:
        package_dir = next(publish_dir.glob("DAMX-*"))
        print(f"\nFound package directory: {package_dir}")
    except StopIteration:
        print("Error: Could not find package directory in Publish/")
        return

    # --- 3. Copy artifacts to a temporary location ---
    temp_dir = Path("/tmp/release_package_temp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    shutil.copytree(package_dir, temp_dir)
    print(f"Copied artifacts to temporary location: {temp_dir}")

    # --- 4. Clean the setup branch ---
    if not confirm("\nStep 2: Clean the current branch? (git rm/clean)"):
        print("Aborted.")
        return

    run_command(["git", "rm", "-rf", "."])
    run_command(["git", "clean", "-fdx"])
    print("Branch cleaned.")

    # --- 5. Copy new files back ---
    print("\nCopying new release files into the branch...")
    for item in temp_dir.iterdir():
        target = Path(item.name)
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    shutil.rmtree(temp_dir) # Clean up temp
    print("Files copied.")

    # --- 6. Commit the changes ---
    if not confirm("\nStep 3: Commit the new release package?"):
        print("Aborted.")
        return

    run_command(["git", "add", "."])
    commit_message = f"build: Release package v{package_dir.name.split('-')[-1]}"
    run_command(["git", "commit", "-m", commit_message])
    print("Changes committed.")

    # --- 7. Push to origin ---
    if not confirm("\nStep 4: Force push to 'origin setup'? (This will overwrite remote history)"):
        print("Aborted.")
        return

    run_command(["git", "push", "origin", "setup", "--force"])
    print("\n🎉 Successfully updated and pushed the setup branch!")

if __name__ == "__main__":
    # Ensure we are on the setup branch
    try:
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
        current_branch = result.stdout.strip()
        if current_branch != "setup":
            print(f"Error: This script must be run from the 'setup' branch, but you are on '{current_branch}'.")
            exit(1)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Not a git repository or git command not found.")
        exit(1)

    main()
