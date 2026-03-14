from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple
import zlib



class GitObjects:
    def __init__(self, obj_type: str, content: bytes):
        self.type = obj_type
        self.content = content

    def hash(self) -> str:
        header = f"{self.type} {len(self.content)}\0".encode()
        return hashlib.sha1(header + self.content).hexdigest()

    def serialize(self) -> bytes:
        header = f"{self.type} {len(self.content)}\0".encode()
        return zlib.compress(header + self.content)

    @classmethod
    def deserialize(cls, data: bytes) -> GitObjects:
        decompressed = zlib.decompress(data)
        null_index = decompressed.find(b"\0")
        header = decompressed[:null_index]
        content = decompressed[null_index + 1:]
        obj_type, size = header.decode().split(" ")
        return cls(obj_type, content)


class Blob(GitObjects):
    def __init__(self, content: bytes):
        super().__init__('blob', content)

class Tree(GitObjects):
    def __init__(self, entries: List[Tuple[str, str, str]] = None):
        self.entries = entries or []
        super().__init__('tree', self._serialize_entries())

    def _serialize_entries(self) -> bytes:
        content = b""
        for mode, name, blob_hash in sorted(self.entries):
            content += f"{mode} {name}\0".encode()
            content += bytes.fromhex(blob_hash)
        return content

    def add_entry(self, mode: str, name: str, blob_hash: str) -> None:
        self.entries.append((mode, name, blob_hash))
        self.content = self._serialize_entries()

    @classmethod
    def from_content(cls, content: bytes) -> Tree:
        tree = cls([])
        i = 0
        while i < len(content):
            null_index = content.find(b"\0", i)
            if null_index == -1:
                break
            
            mode_name = content[i:null_index].decode()
            mode, name = mode_name.split(" ", 1)
            obj_hash = content[null_index + 1:null_index + 21].hex()
            tree.entries.append((mode, name, obj_hash))
            i = null_index + 21
        return tree



class Commit(GitObjects):
    def __init__(self, tree_hash: str, parent_hash: List[str], author: str, committer: str, message: str, timestamp: int = None):
        self.tree_hash = tree_hash
        self.parent_hash = parent_hash
        self.author = author
        self.committer = committer
        self.message = message
        self.timestamp = timestamp or int(time.time())
        super().__init__('commit', self._serialize_commit())
    
    def _serialize_commit(self) -> bytes:
        lines = [f"tree {self.tree_hash}"]
        for parent in self.parent_hash:
            lines.append(f"parent {parent}")
        lines.append(f"author {self.author} {self.timestamp} +0000")
        lines.append(f"committer {self.committer} {self.timestamp} +0000")
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines).encode()
    
    @classmethod
    def from_content(cls, content: bytes) -> Commit:
        lines = content.decode().split("\n")
        tree_hash = None
        parent_hashes = []
        author = None
        committer = None
        message_start = 0

        for i, line in enumerate(lines):
            if line.startswith("tree "):
                tree_hash = line[5:]
            elif line.startswith("parent "):
                parent_hashes.append(line[7:])
            elif line.startswith("author "):
                author_parts = line[7:].rsplit(" ", 2)
                author = author_parts[0]
                timestamp = int(author_parts[1])
                timezone = author_parts[2]
            elif line.startswith("committer "):
                committer_parts = line[10:].rsplit(" ", 2)
                committer = committer_parts
            elif line == "":
                message_start = i + 1
                break
        
        message = "\n".join(lines[message_start:])
        return cls(tree_hash, parent_hashes, author, committer, message, timestamp)

    
class Repository:
    def __init__(self, path = "."):
        self.path = Path(path).resolve()
        self.git_dir = self.path / ".mogit"

        self.objects_dir = self.git_dir / "objects"
        self.refs_dir = self.git_dir / "refs"
        self.heads_dir = self.refs_dir / "heads"
        self.head_file = self.git_dir / "HEAD"

        self.index_file = self.git_dir / "index"

    def _branch_file(self, branch: str) -> Path:
        return self.heads_dir / branch

    def store_objects(self, obj: GitObjects) -> str:
        obj_hash = obj.hash()
        obj_dir = self.objects_dir / obj_hash[:2]
        obj_file = obj_dir / obj_hash[2:]

        if not obj_dir.exists():
            obj_dir.mkdir(exist_ok=True)
            obj_file.write_bytes(obj.serialize())
        
        return obj_hash

    def load_index(self) -> Dict[str, str]:
        if not self.index_file.exists():
            return {}
        try:
            return json.loads(self.index_file.read_text())
        except Exception:
            return {}

    def save_index(self, index: Dict[str, str]) -> None:
        self.index_file.write_text(json.dumps(index, indent=2))

    def add_file(self, path: Path) -> None:
        full_path = self.path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        # read the file content
     
        content = full_path.read_bytes()
        # create a blob object from the content
        blob = Blob(content)
        # store the blob object in the database (.git/objects)
        blob_hash = self.store_objects(blob) 
        # update the index 
        index = self.load_index()
        # Convert path to relative string for JSON serialization
        relative_path = str(path.relative_to(self.path))
        index[relative_path] = blob_hash
        self.save_index(index)
        
        print(f"Added {path} to the staging area")
    
    def add_directory(self, path: Path) -> None:
        # recursive traverse the directory
        # create blob objects for all files
        # store all blobs in the object database (.git/objects)
        # update the index to include all files
        # path is already a full path from add_path, so use it directly
        full_path = path if path.is_absolute() else self.path / path
        if not full_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not full_path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
        index = self.load_index()
        added_count = 0
        for file in full_path.rglob('*'):
            if file.is_file():
                # Skip files in .mogit or .git directories
                if ".mogit" in file.parts or ".git" in file.parts:
                    continue
                blob = Blob(file.read_bytes())
                blob_hash = self.store_objects(blob)
                relative_path = str(file.relative_to(self.path))
                index[relative_path] = blob_hash
                added_count += 1
        self.save_index(index)

        if added_count > 0:
            print(f"Added {added_count} files from directory {path}")
        else:
            print(f"No files found in directory {path}")


    

    def add_path(self, path: str) -> None:
        full_path = self.path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File or directory not found: {path}")
        if full_path.is_file():
            self.add_file(full_path) # one file
        elif full_path.is_dir():
            self.add_directory(full_path) # one or more files
        else:
            raise ValueError(f"Invalid path: {path}")

    def init(self) -> bool:

        if self.git_dir.exists():
            print(f"Error: {self.git_dir} already exists")
            return False

        # create the git directory
        self.git_dir.mkdir()
        self.objects_dir.mkdir()
        self.refs_dir.mkdir()
        self.heads_dir.mkdir()



        # create initial HEAD pointing to master
        self.head_file.write_text("ref: refs/heads/master\n")

        self.save_index({})

        print(f"Initialized empty PyGIT repository in {self.git_dir}")
        return True
    
    # we calculate file path from hash and deserialize the object
    def load_objects(self, obj_hash: str) -> GitObjects:
        obj_dir = self.objects_dir / obj_hash[:2]
        obj_file = obj_dir / obj_hash[2:]
        if not obj_file.exists():
            raise FileNotFoundError(f"Object not found: {obj_hash}")
        return GitObjects.deserialize(obj_file.read_bytes())

    def create_tree_from_index(self):
        index = self.load_index()
        if not index:
            tree = Tree()
            return self.store_objects(tree)
        
        dirs = {}
        files = {}
        for file_path, blob_hash in index.items():
            parts = file_path.split('/')
            if len(parts) == 1:
                files[parts[0]] = blob_hash
            else:
                dir_name = parts[0]
                if dir_name not in dirs:
                    dirs[dir_name] = {}

                current = dirs[dir_name]
                for part in parts[1:-1]: # want to skip the last part because it is the blob hash
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                current[parts[-1]] = blob_hash
        def create_tree_recursive(entries: dict):
            tree = Tree()
            for name, blob_hash in entries.items(): # blob_hash is a value of the key in the dictionary
                if isinstance(blob_hash, str): 
                    tree.add_entry('100644', name, blob_hash) # 100644 is the mode for a file
                elif isinstance(blob_hash, dict): 
                    subtree_hash = create_tree_recursive(blob_hash)
                    tree.add_entry('40000', name, subtree_hash)
            return self.store_objects(tree)


        root_entries = {**files}
        for dir_name, dir_contents in dirs.items():
            root_entries[dir_name] = dir_contents

        return create_tree_recursive(root_entries)

    
    def get_current_branch(self) -> str:
        if not self.head_file.exists():
            return "master"
        head_content = self.head_file.read_text().strip()
        # if head_content.startswith("ref: "):
        #     ref = head_content[5:]
        #     # Return short name for path: refs/heads/master -> master
        #     return ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
        if head_content.startswith("ref: refs/heads/"):
            return head_content[16:]
        return "HEAD"

    def get_branch_commit(self, branch: str) -> str:
        branch_file = self._branch_file(branch)
        if branch_file.exists():
            return branch_file.read_text().strip()
        return None

    def set_brach_commit(self, branch: str, commit_hash: str) -> None:
        branch_file = self._branch_file(branch)
        branch_file.write_text(commit_hash + "\n")

    # Backward-compatible wrapper for callers that use the correctly-spelled name.
    def set_branch_commit(self, branch: str, commit_hash: str) -> None:
        self.set_brach_commit(branch, commit_hash)

    
    def commit(self, message: str, author: str = 'Anonymous') -> None:  


        # create a tree object from the index (staging area)
        tree_hash = self.create_tree_from_index()
        current_branch = self.get_current_branch()
        parent_commit = self.get_branch_commit(current_branch)
        parent_hashes = [parent_commit] if parent_commit else []

        # some edge cases to handle - check index FIRST before creating tree
        index = self.load_index()
        if not index:
            print(f"No changes to commit")
            return None

        if parent_commit:
            parent_git_commit_obj = self.load_objects(parent_commit)
            parent_commit_data = Commit.from_content(parent_git_commit_obj.content)
            if tree_hash == parent_commit_data.tree_hash:
                print(f"No changes to commit")
                return None

        commit = Commit(
            tree_hash = tree_hash, 
            parent_hash = parent_hashes, 
            author = author, 
            committer = author, 
            message = message, 
            timestamp = int(time.time())
        )

        commit_hash = self.store_objects(commit)

        self.set_brach_commit(current_branch, commit_hash)
        self.save_index({})
        print(f"Committed changes to {commit_hash} on branch {current_branch}")
        return commit_hash

    def get_files_from_tree_recursive(self, tree_hash: str, prefix: str = '') -> set:
        files = set()
        try:
            tree_obj = self.load_objects(tree_hash)
            tree = Tree.from_content(tree_obj.content)
            for mode, name, obj_hash in tree.entries:
                full_name = f"{prefix}{name}" 
                if mode.startswith('100'):
                    files.add(full_name)
                elif mode.startswith('400'):
                    subtree_files = self.get_files_from_tree_recursive(obj_hash, f"{full_name}/")
                    files.update(subtree_files)   
                else:
                    print(f"Warning: Unknown mode {mode} in tree {tree_hash}")
        except Exception as e:
            print(f"Warning: Could not read tree {tree_hash}: {e}")
        return files
        
        
    def checkout(self, branch: str, create_branch: bool = False) -> None:
        # computed the files to clear from the previous commit
        previous_branch = self.get_current_branch()
        files_to_clear = set()
        try:
            previous_commit_hash = self.get_branch_commit(previous_branch)
            if previous_commit_hash:
                prev_commit_object = self.load_objects(previous_commit_hash)
                prev_commit = Commit.from_content(prev_commit_object.content)
                if prev_commit.tree_hash:
                    files_to_clear = self.get_files_from_tree_recursive(prev_commit.tree_hash)

        except Exception as e:
            files_to_clear = set()
        
        # created a new branch 
        branch_file = self._branch_file(branch)
        if not branch_file.exists():
            if not self.git_dir.exists():
                print(f"Error: Not a repository")
                return 
            if create_branch:
                if previous_commit_hash:
                    self.set_brach_commit(branch, previous_commit_hash)
                    print(f"Created new branch {branch} and checked it out")
                else:
                    print(f"No commit found on branch {current_branch}")
                    return
            else:
                print(f"Branch {branch} does not exist")
                print(f"Use 'git checkout -b {branch}' to create a new branch")
                return
        # update the HEAD file to point to the new branch 
        self.head_file.write_text(f"ref: refs/heads/{branch}\n")

        # restore working directory
        self.restore_working_directory(branch, files_to_clear)
        print(f"Switched to a new branch '{branch}'")     

    def restore_tree(self, tree_hash: str, path: Path) -> None:
            tree_obj = self.load_objects(tree_hash)
            tree = Tree.from_content(tree_obj.content)
            for mode, name, obj_hash in tree.entries:
                file_path = path / name
                if mode.startswith('100'):
                    blob_obj = self.load_objects(obj_hash)
                    blob = Blob(blob_obj.content)
                    file_path.write_bytes(blob.content)
                elif mode.startswith('400'):
                    file_path.mkdir(exist_ok=True)
                    self.restore_tree(obj_hash, file_path)  

        
    def restore_working_directory(self, branch: str, files_to_clear: Optional[set] = None) -> None:
        target_commit_hash = self.get_branch_commit(branch)
        if not target_commit_hash:
            return
        # remove files tracked by the previous branch

        for relative_path in sorted(files_to_clear):
            file_path = self.path / relative_path
            try:
                if file_path.is_file():
                    file_path.unlink()
            except Exception as e:
                pass


        target_commit_object = self.load_objects(target_commit_hash)
        target_commit = Commit.from_content(target_commit_object.content)
        if target_commit.tree_hash:
            self.restore_tree(target_commit.tree_hash, self.path)
            self.save_index({})

        
    def branch(self, branch_name: str, delete: bool = False):
        # delete
        if delete and branch_name:
            branch_file = self._branch_file(branch_name)
            if branch_file.exists():
                branch_file.unlink()
                print(f"Deleted branch {branch_name}")
            else:
                print(f"Branch {branch_name} not found")

            return

        current_branch = self.get_current_branch()
        if branch_name:
            current_commit = self.get_branch_commit(current_branch)
            if current_commit:
                self.set_branch_commit(branch_name, current_commit)
                print(f"Created branch {branch_name}")
            else:
                print(f"No commits yet, cannot create a new branch")
        else:
            branches = [
                branch_file.name
                for branch_file in self.heads_dir.iterdir()
                if branch_file.is_file() and not branch_file.name.startswith(".")
            ]

            for branch in sorted(branches):
                current_marker = "* " if branch == current_branch else "  "
                print(f"{current_marker}{branch}")

    def log(self, limit: int = 10) -> None:
        current_branch = self.get_current_branch() 
        commit_hash = self.get_branch_commit(current_branch)
        if not commit_hash:
            print(f"No commits yet")
            return
        count = 0
        while commit_hash and count < limit:
            commit_object = self.load_objects(commit_hash)
            commit = Commit.from_content(commit_object.content)
            print(f"{commit_hash}")
            print(f"Author: {commit.author}")
            print(f"Date: {time.ctime(commit.timestamp)}")
            print(f"Message: {commit.message}\n")
            commit_hash = commit.parent_hash[0] if commit.parent_hash else None
            count += 1
            
    def build_index_from_tree(self, tree_hash: str, prefix: str = '') -> dict:
        index = {}
        try:
            tree_obj = self.load_objects(tree_hash)
            tree = Tree.from_content(tree_obj.content)
            # list<tuple<str, str, str>>
            for mode, name, obj_hash in tree.entries:
                full_name = f"{prefix}{name}"
                if mode.startswith("100"):
                    index[full_name] = obj_hash
                elif mode.startswith("400"):
                    subindex = self.build_index_from_tree(obj_hash, f"{full_name}/")

                    index.update(subindex)
        except Exception as e:
            print(f"Warning: Could not read tree {tree_hash}: {e}")

        return index

    def get_all_files(self) -> List[Path]:
        files = []

        for item in self.path.rglob("*"):
            if ".git" in item.parts:
                continue

            if item.is_file():
                files.append(item)

        return files

    def status(self):
        # what branch we are on
        current_branch = self.get_current_branch()
        print(f"On branch {current_branch}")
        index = self.load_index()
        current_commit_hash = self.get_branch_commit(current_branch)

        # build the index of the latest commit
        last_index_files = {}
        if current_commit_hash:
            try:
                commit_obj = self.load_object(current_commit_hash)
                commit = Commit.from_content(commit_obj.content)
                if commit.tree_hash:
                    last_index_files = self.build_index_from_tree(commit.tree_hash)
            except:
                last_index_files = {}

        # figure out all the files present within the working directory
        working_files = {}  # file name -> hash
        for item in self.get_all_files():
            rel_path = str(item.relative_to(self.path))

            try:
                content = item.read_bytes()
                blob = Blob(content)
                working_files[rel_path] = blob.hash()
            except:
                continue

        staged_files = []
        unstaged_files = []
        untracked_files = []
        deleted_files = []

        # what files are staged for commit
        for file_path in set(index.keys()) | set(last_index_files.keys()):
            index_hash = index.get(file_path)
            last_index_hash = last_index_files.get(file_path)

            if index_hash and not last_index_hash:
                staged_files.append(("new file", file_path))
            elif index_hash and last_index_hash and index_hash != last_index_hash:
                staged_files.append(("modified", file_path))

        if staged_files:
            print("\nChanges to be committed:")
            for stage_status, file_path in sorted(staged_files):
                print(f"   {stage_status}: {file_path}")

        # what files have modified but not staged
        for file_path in working_files:
            if file_path in index:
                if working_files[file_path] != index[file_path]:
                    unstaged_files.append(file_path)

        if unstaged_files:
            print("\nChanges not staged for commit:")
            for file_path in sorted(unstaged_files):
                print(f"   modified: {file_path}")

        # what files are untracked
        for file_path in working_files:
            if file_path not in index and file_path not in last_index_files:
                untracked_files.append(file_path)

        if untracked_files:
            print("\nUntracked files:")
            for file_path in sorted(untracked_files):
                print(f"   {file_path}")

        # what files have been deleted
        for file_path in index:
            if file_path not in working_files:
                deleted_files.append(file_path)

        if deleted_files:
            print("\nDeleted files:")
            for file_path in sorted(deleted_files):
                print(f"   deleted: {file_path}")

        if (
            not staged_files
            and not unstaged_files
            and not deleted_files
            and not untracked_files
        ):
            print("\nnothing to commit, working tree clean")


def main(): 
    parser = argparse.ArgumentParser(
        description='PyGIT - A simple git clone'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # init command
    init_parser = subparsers.add_parser('init', help='Initialize a new repository')

    # add command
    add_parser = subparsers.add_parser('add', help='Add files to the staging area')
    add_parser.add_argument('paths', nargs='+', help='Files and directories to add')

    # commit command
    commit_parser = subparsers.add_parser('commit', help='Commit changes to the repository')
    commit_parser.add_argument('-m', '--message', help='Commit message', required=True)
    commit_parser.add_argument('--author', help='Author name')

    # checkout command
    checkout_parser = subparsers.add_parser('checkout', help='Checkout a branch')
    checkout_parser.add_argument('branch', help='Branch to checkout')
    checkout_parser.add_argument(
        '-b',
        action='store_true',
        dest='create_branch',
        help='Create a new branch and checkout to it')

    # branch command
    branch_parser = subparsers.add_parser('branch', help='List, create, or delete branches')
    branch_parser.add_argument('name', nargs='?')
    branch_parser.add_argument('-d', '--delete', action='store_true', help='Delete a branch')

    # log command
    log_parser = subparsers.add_parser('log', help='Show commit history')
    log_parser.add_argument('-n', '--limit', type=int,default=10,help='Limit the number of commits')

    #status command
    status_parser = subparsers.add_parser('status', help='Show the status of the working directory')

    args = parser.parse_args()
 
    if not args.command:
        parser.print_help()
        return

    repo = Repository()

    def ensure_repo_initialized() -> bool:
        if not repo.git_dir.exists():
            print("Error: Not a repository")
            return False
        return True

    def handle_add() -> None:
        print(args.paths)
        for path in args.paths:
            repo.add_path(path)

    try:
        if args.command == 'init':
            if not repo.init():
                print("Repository already initialized")
            return

        if not ensure_repo_initialized():
            return

        handlers = {
            'add': handle_add,
            'commit': lambda: repo.commit(args.message, args.author or 'Anonymous'),
            'checkout': lambda: repo.checkout(args.branch, args.create_branch),
            'branch': lambda: repo.branch(args.name, args.delete),
            'log': lambda: repo.log(args.limit),
            'status': repo.status,
        }

        handler = handlers.get(args.command)
        if handler:
            handler()
    except Exception as e:
        print(f'Error: {e}')
        sys.exit(1)

main()


# add garbage collector that if file change so old one is deleted
# add unit test for all this 
