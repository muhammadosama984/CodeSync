# CodeSync

A lightweight version control system built from scratch in Python — inspired by Git. CodeSync implements core Git concepts like blobs, trees, commits, branches, and staging, using only Python's standard library.

## What It Does

CodeSync gives you a local version control workflow similar to Git:

- Initialize a repository in any directory
- Stage files for commit
- Commit snapshots with a message and author
- Create and switch branches
- View commit history
- Check working directory status (staged, unstaged, untracked, deleted files)

All data is stored in a `.mogit` directory, mirroring how Git uses `.git`.

## Requirements

- Python 3.9 or higher
- [pipx](https://pipx.pypa.io) (for installation)

## Installation

```bash
pipx install git+https://github.com/muhammadosama984/CodeSync.git
```

To upgrade to the latest version:

```bash
pipx upgrade codesync
```

To uninstall:

```bash
pipx uninstall codesync
```

## Usage

### Initialize a repository

```bash
codesync init
```

### Stage files

```bash
codesync add file.txt
codesync add .          # stage everything
```

### Commit changes

```bash
codesync commit -m "your message"
codesync commit -m "your message" --author "Your Name"
```

### Check status

```bash
codesync status
```

### View commit history

```bash
codesync log
codesync log -n 5       # limit to last 5 commits
```

### Branch operations

```bash
codesync branch                  # list branches
codesync branch feature-x        # create a branch
codesync branch -d feature-x     # delete a branch
```

### Switch branches

```bash
codesync checkout main
codesync checkout -b new-branch  # create and switch
```

## How It Works

| Concept | Description |
|---------|-------------|
| **Blob** | Stores file content, hashed with SHA-1 and compressed with zlib |
| **Tree** | Represents a directory snapshot (list of blobs) |
| **Commit** | Points to a tree, parent commit(s), author, and message |
| **Index** | Staging area stored as JSON in `.mogit/index` |
| **HEAD** | Points to the current branch in `.mogit/HEAD` |
| **Refs** | Branch pointers stored in `.mogit/refs/heads/` |
