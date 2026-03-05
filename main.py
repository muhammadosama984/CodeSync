from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from textwrap import indent
from typing import Dict
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
    
    def get_content(self) -> bytes:
        return self.content

class Repository:
    def __init__(self, path = "."):
        self.path = Path(path).resolve()
        self.git_dir = self.path / ".mogit"

        self.objects_dir = self.git_dir / "objects"
        self.refs_dir = self.git_dir / "refs"
        self.heads_dir = self.refs_dir / "heads"
        self.head_file = self.git_dir / "HEAD"

        self.index_file = self.git_dir / "index"

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
            return json.load(self.index_file.read_text())
        except:
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

    args = parser.parse_args()
 
    if not args.command:
        parser.print_help()
        return

    repo = Repository()


    try:
        if args.command == 'init':
            if not repo.init():
                print(f"Repository already initialized")
                return
        elif args.command == 'add':
            if not repo.git_dir.exists():
                print(f"Error: Not a repository")
                return
            print(args.paths)
            for path in args.paths:
                repo.add_path(path)
    except Exception as e:
        print(f'Error: {e}')
        sys.exit(1)

main()


# add garbage collector that if file change so old one is deleted