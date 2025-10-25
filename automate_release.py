#!/usr/bin/env python3
"""
Automates the process of building and deploying the release package to the setup branch.
This script is meant to be run from your main development branch (e.g., 'main' or 'master').
"""

import os
import subprocess
import shutil
from pathlib import Path
import sys

def confirm(prompt):
    """Get user confirmation."""
    while True:
        reply = input(f"{prompt} [y/n]: ").lower().strip()
        if reply[:1] == 'y':
            return True
        if reply[:1] == 'n':
            return False

def run_command(cmd, cwd='.', check=True):
    """Run a command and optionally exit if it fails."""
    print(f"\nRunning command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result

def main():
    print("=== Automated Release Packager for 'setup' branch ===")
    
    original_branch = ""
    try:
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
        original_branch = result.stdout.strip()
        print(f"Starting from branch: '{original_branch}'")
        if original_branch == "setup":
            print("\nWarning: It's recommended to run this script from your main development branch, not from 'setup'.")
            if not confirm("Continue anyway?"):
                sys.exit("Aborted.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Not a git repository or git command not found.")
        sys.exit(1)

    # --- 1. Run the packaging script ---
    if not confirm("\nStep 1: Run the packaging script? (scripts/PackageEverything.py)"):
        sys.exit("Aborted.")

    packaging_script = Path("scripts/PackageEverything.py")
    if not packaging_script.exists():
        print(f"Error: Cannot find {packaging_script}. Make sure you are in the project root.")
        sys.exit(1)

    run_command(["python3", str(packaging_script)])

    # --- 2. Find the new package directory ---
    publish_dir = Path("Publish")
    try:
        package_dir = next(publish_dir.glob("DAMX-*"))
        print(f"\nFound package directory: {package_dir}")
    except StopIteration:
        print("Error: Could not find package directory in Publish/")
        sys.exit(1)

    # --- 3. Copy artifacts to a temporary location ---
    temp_dir = Path(f"/tmp/release_package_temp_{os.getpid()}")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    shutil.copytree(package_dir, temp_dir)
    print(f"Copied artifacts to temporary location: {temp_dir}")

    # --- 4. Switch to setup branch ---
    if not confirm("\nStep 2: Switch to 'setup' branch to begin update?"):
        shutil.rmtree(temp_dir)
        sys.exit("Aborted.")
    
    run_command(["git", "checkout", "setup"])

    try:
        # --- 5. Clean the setup branch ---
        print("\nCleaning the 'setup' branch...")
        run_command(["git", "rm", "-rf", "."], check=False)
        run_command(["git", "clean", "-fdx"], check=False)
        print("Branch cleaned.")

        # --- 6. Copy new files back ---
        print("\nCopying new release files into the branch...")
        for item in temp_dir.iterdir():
            target = Path(item.name)
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        print("Files copied.")

        # --- 7. Commit the changes ---
        if not confirm("\nStep 3: Commit the new release package?"):
            print("Aborting commit. You are still on the 'setup' branch.")
            sys.exit()

        run_command(["git", "add", "."])
        commit_message = f"build: Release package v{package_dir.name.split('-')[-1]}"
        run_command(["git", "commit", "-m", commit_message])
        print("Changes committed.")

        # --- 8. Push to origin ---
        if not confirm("\nStep 4: Force push to 'origin setup'? (This will overwrite remote history)"):
            print("Aborting push. You are still on the 'setup' branch with local commits.")
            sys.exit()

        run_command(["git", "push", "origin", "setup", "--force"])
        print("\n🎉 Successfully updated and pushed the setup branch!")

    finally:
        # --- 9. Return to original branch and clean up ---
        print(f"\nReturning to original branch: '{original_branch}'")
        run_command(["git", "checkout", original_branch])
        shutil.rmtree(temp_dir)
        # Also remove the original publish folder
        if publish_dir.exists():
            shutil.rmtree(publish_dir)
        print("Cleanup complete.")

if __name__ == "__main__":
    main()