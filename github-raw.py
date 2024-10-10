#!/usr/bin/env python3
import os
import threading
import queue
from pathlib import Path
import tempfile

import requests

BASE_URL = os.getenv("TUNASYNC_UPSTREAM_URL", "https://api.github.com/repos/")
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")
MIRROR_BASE_URL = os.getenv(
    "MIRROR_BASE_URL", "https://mirrors.tuna.tsinghua.edu.cn/github-raw/"
)


def raw_to_mirror(s: str) -> str:
    return s.replace("https://raw.githubusercontent.com/", MIRROR_BASE_URL)


def delete_line_with(w: str, s: str) -> str:
    return "\n".join(list(filter(lambda x: x.count(w) == 0, s.splitlines())))


def delete_line_with_gbpdistro(s: str) -> str:
    return delete_line_with("gbpdistro", s)


REPOS = [
    # owner/repo, tree, tree, tree, blob
    ## for stackage
    ["fpco/stackage-content", "master", "stack", "global-hints.yaml"],
    ## for rosdep
    {
        "path": [
            "ros/rosdistro",
            "master",
            "rosdep",
            "sources.list.d",
            "20-default.list",
        ],
        "filter": [raw_to_mirror, delete_line_with_gbpdistro],
    },
    ["ros/rosdistro", "master", "rosdep", "osx-homebrew.yaml"],
    ["ros/rosdistro", "master", "rosdep", "base.yaml"],
    ["ros/rosdistro", "master", "rosdep", "python.yaml"],
    ["ros/rosdistro", "master", "rosdep", "ruby.yaml"],
    ["ros/rosdistro", "master", "releases", "targets.yaml"],
    # for llvm-apt
    ["opencollab/llvm-jenkins.debian.net", "master", "llvm.sh"],
    # for docker-install
    ["docker/docker-install", "master", "install.sh"],
]

# connect and read timeout value
TIMEOUT_OPTION = (7, 10)
total_size = 0


# wrap around requests.get to use token if available
def github_get(*args, **kwargs):
    headers = kwargs["headers"] if "headers" in kwargs else {}
    if "GITHUB_TOKEN" in os.environ:
        headers["Authorization"] = "token {}".format(os.environ["GITHUB_TOKEN"])
    kwargs["headers"] = headers
    return requests.get(*args, **kwargs)


def github_tree(*args, **kwargs):
    headers = kwargs["headers"] if "headers" in kwargs else {}
    headers["Accept"] = "application/vnd.github.v3+json"
    kwargs["headers"] = headers
    return github_get(*args, **kwargs)


# NOTE blob API supports file up to 100MB
# To get larger one, we need raw.githubcontent, which is not implemented now
def github_blob(*args, **kwargs):
    headers = kwargs["headers"] if "headers" in kwargs else {}
    headers["Accept"] = "application/vnd.github.v3.raw"
    kwargs["headers"] = headers
    return github_get(*args, **kwargs)


def do_download(
    remote_url: str, dst_file: Path, remote_size: int, sha: str, filter=None
):
    # NOTE the stream=True parameter below
    with github_blob(remote_url, stream=True) as r:
        r.raise_for_status()
        tmp_dst_file = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="." + dst_file.name + ".",
                suffix=".tmp",
                dir=dst_file.parent,
                delete=False,
            ) as f:
                tmp_dst_file = Path(f.name)
                for chunk in r.iter_content(chunk_size=1024**2):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        # f.flush()
            # check for downloaded size
            downloaded_size = tmp_dst_file.stat().st_size
            if remote_size != -1 and downloaded_size != remote_size:
                raise Exception(
                    f"File {dst_file.as_posix()} size mismatch: downloaded {downloaded_size} bytes, expected {remote_size} bytes"
                )
            if filter != None:
                with open(tmp_dst_file, "r+") as f:
                    s = f.read()
                    for fil in filter:
                        s = fil(s)
                    f.seek(0)
                    f.truncate()
                    f.write(s)
            tmp_dst_file.chmod(0o644)
            target = dst_file.parent / ".sha" / sha
            print("symlink", dst_file)
            print("target", target)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_dst_file.replace(target)
            if dst_file.is_symlink():
                origin = dst_file.parent / os.readlink(dst_file)
                print("origin", origin)
                dst_file.unlink()
                origin.unlink()
            dst_file.symlink_to(Path(".sha") / sha)
        finally:
            if not tmp_dst_file is None:
                if tmp_dst_file.is_file():
                    tmp_dst_file.unlink()


def downloading_worker(q):
    while True:
        item = q.get()
        if item is None:
            break

        filter = item.pop(0)  # remove filter

        dst_file = Path("/".join(item))
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        item.pop(0)  # remove working dir
        owner_repo = item.pop(0)
        try:
            tree = item.pop(0)
            tree_child = item.pop(0)
            child_is_leaf = False
            url = ""
            sha = ""
            size = 0
            while not child_is_leaf:
                with github_tree(f"{BASE_URL}{owner_repo}/git/trees/{tree}") as r:
                    r.raise_for_status()
                    tree_json = r.json()
                    for child in tree_json["tree"]:
                        if tree_child == child["path"]:
                            if child["type"] == "tree":
                                tree = child["sha"]
                                tree_child = item.pop(0)
                            elif child["type"] == "blob":
                                child_is_leaf = True
                                url = child["url"]
                                size = child["size"]
                                sha = child["sha"]
                            else:
                                raise Exception
                            break
                    else:
                        raise Exception
            if not dst_file.is_symlink() or Path(os.readlink(dst_file)).name != sha:
                do_download(url, dst_file, size, sha, filter)
            else:
                print("Skip", dst_file)
        except Exception as e:
            print(e)
            print("Failed to download", dst_file, flush=True)
            if dst_file.is_file():
                dst_file.unlink()

        q.task_done()


def create_workers(n):
    task_queue = queue.Queue()
    for i in range(n):
        t = threading.Thread(target=downloading_worker, args=(task_queue,))
        t.start()
    return task_queue


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--working-dir", default=WORKING_DIR)
    parser.add_argument(
        "--workers", default=1, type=int, help="number of concurrent downloading jobs"
    )
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = args.working_dir
    task_queue = create_workers(args.workers)

    for cfg in REPOS:
        if isinstance(cfg, list):
            cfg.insert(0, working_dir)
            cfg.insert(0, None)
            task_queue.put(cfg)
        else:
            cfg["path"].insert(0, working_dir)
            cfg["path"].insert(0, cfg["filter"])
            task_queue.put(cfg["path"])

    # block until all tasks are done
    task_queue.join()
    # stop workers
    for i in range(args.workers):
        task_queue.put(None)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4 sts=4 expandtab
