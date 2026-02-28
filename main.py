import argparse
import json
from pathlib import Path
import sys
from textwrap import indent


    




class Repository:
    def __init__(self, path = "."):
        self.path = Path(path).resolve()
        self.git_dir = self.path / ".mogit"

        self.objects_dir = self.git_dir / "objects"
        self.refs_dir = self.git_dir / "refs"
        self.heads_dir = self.refs_dir / "heads"
        self.head_file = self.git_dir / "HEAD"

        self.index_file = self.git_dir / "index"
    
    def add_file(self, path: Path) -> None:
        full_path = self.path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        # read the file content

        content = full_path.read_bytes()
        # create a blob object from the content

        # store the blob object in the database (.git/objects)
        # update the index 
        pass

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

        self.index_file.write_text(json.dumps({}, indent=2))
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