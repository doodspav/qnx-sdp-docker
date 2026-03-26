import io
import subprocess
import sys
import tarfile

from pathlib import Path
from typing import List, Optional


def get_label(target: str, label: str) -> Optional[str]:
    """
    Gets the value of a label from the given image or container if it is set.
    """
    if '"' in label:
        raise ValueError(f"Label cannot contain double quotes: {label!r}")

    formatted_label = f'{{{{index .Config.Labels "{label}"}}}}'
    result = subprocess.run(
        ["docker", "inspect", "--format", formatted_label, target],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to inspect '{target}': {result.stderr.strip()}"
        )
    value = result.stdout.strip()
    return value if value else None


class Container:

    def __init__(self, image: str, *, deferred: bool = False) -> None:
        self._image = image
        self._id: Optional[str] = None
        if not deferred:
            self.create()

    def __del__(self) -> None:
        self.remove()

    def __enter__(self) -> "Container":
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.remove()

    def create(self) -> None:
        """
        Creates the container if it doesn't exist.
        """
        if self._id is not None:
            return

        result = subprocess.run(
            ["docker", "create", self._image, "true"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create container from image '{self._image}': "
                f"{result.stderr.strip()}"
            )
        self._id = result.stdout.strip()

    def _get_id_or_raise(self) -> str:
        """
        Gets the id of the container or raises an exception if it has not yet
        been created.
        """
        if self._id is None:
            raise RuntimeError("Container has not been created")
        return self._id

    @property
    def cid(self) -> str:
        return self._get_id_or_raise()

    @property
    def image(self) -> str:
        return self._image

    def remove(self) -> None:
        """
        Removes the container if it exists.
        """
        if self._id is None:
            return

        result = subprocess.run(
            ["docker", "rm", self._id],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(
                f"Failed to remove container '{self._id}': "
                f"{result.stderr.strip()}",
                file=sys.stderr
            )
        else:
            self._id = None

    def listdir_with_cp(self, path: str) -> Optional[List[str]]:
        """
        Lists the non-recursive contents of a directory if it is accessible and
        returns the relative file names. Excludes "." and "..".

        This is implemented using cp, so it will copy the entire directory.
        This may be expensive and unwanted for large directories or files.
        """
        container_id = self._get_id_or_raise()
        result = subprocess.run(
            ["docker", "cp", f"{container_id}:{path}", "-"],
            capture_output=True,
        )

        if result.returncode != 0:
            if str(path).encode() in result.stderr:
                return None
            raise RuntimeError(
                f"Failed to list files from container directory '{path}': "
                f"{result.stderr.strip()}"
            )

        t = tarfile.open(fileobj=io.BytesIO(result.stdout))
        members = t.getmembers()
        if not members[0].isdir():
            raise RuntimeError(
                f"Expected a directory but got a file: {path}"
            )
        return [
            m.name.split("/", 1)[1]  # dirname/filename, strip leading dir
            for m in members if m.name and m.name.count("/") == 1
        ]

    def read_file(self, path: str) -> Optional[bytes]:
        """
        Reads a file from the container if it is accessible and returns its
        contents as bytes.
        """
        container_id = self._get_id_or_raise()
        result = subprocess.run(
            ["docker", "cp", f"{container_id}:{path}", "-"],
            capture_output=True,
        )

        if result.returncode != 0:
            if str(path).encode() in result.stderr:
                return None
            raise RuntimeError(
                f"Failed to read file from container '{path}': "
                f"{result.stderr.strip()}"
            )

        t = tarfile.open(fileobj=io.BytesIO(result.stdout))
        member = t.getmembers()[0]
        if not member.isfile():
            raise RuntimeError(
                f"Expected a file but got a directory: {path}"
            )
        return t.extractfile(member).read()

    def extract_path(self, img_path: str, dst_path: Path) -> bool:
        """
        Copies a file or directory from the container to the host if it is
        accessible, creating any required directories in the destination path.
        """
        container_id = self._get_id_or_raise()
        dst_path.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["docker", "cp", f"{container_id}:{img_path}", f"{dst_path}"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            if str(img_path) in result.stderr:
                return False
            raise RuntimeError(
                f"Failed to extract file from container '{img_path}': "
                f"{result.stderr.strip()}"
            )

        return True
