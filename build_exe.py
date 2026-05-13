import PyInstaller.__main__
import os
import sys

# Define the entry point
entry_point = 'main.py'

# Define asset folders to include
# Syntax: (source, destination)
# On Windows, destination and source are separated by ';' in the command line,
# but as a list in PyInstaller.__main__.run it's just strings.
assets = [
    ('assests', 'assests'),
    ('font', 'font'),
]

# Build the command arguments
args = [
    entry_point,
    '--onefile',
    '--noconsole',
    '--name=mikuBreak',
    '--icon=assests/appIcon.png',
]

# Add data files
for src, dest in assets:
    if os.path.exists(src):
        # On Windows, separator is ';'
        args.append(f'--add-data={src}{os.pathsep}{dest}')

print(f"Starting build with args: {args}")

try:
    PyInstaller.__main__.run(args)
    print("\nBuild successful! Your executable is in the 'dist' folder.")
except Exception as e:
    print(f"\nBuild failed: {e}")
