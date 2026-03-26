import argparse
import json
import os
import shutil
import stat
import sys
import tempfile

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Optional

try:
    from . import _docker
    from . import _query
except ImportError:
    import _docker
    import _query


@dataclass
class ManifestCli:
    arch: _query.Architecture
    image_prefix: Path
    host_prefix: Path
    root: _query.ManifestRoot
    components: list[_query.ManifestComponent]


def parse_cli() -> argparse.Namespace:
    """
    Parses all cli arguments and enforces requirements.
    """
    parser = argparse.ArgumentParser(
        description="Extract artifacts from a Docker image using manifest files.",
    )

    parser.add_argument(
        "-i", "--image",
        help="image from which to extract artifacts",
    )
    parser.add_argument(
        "--show-prefixes",
        action="store_true",
        help="print the image's QNX prefix for each supported architecture and exit",
    )
    parser.add_argument(
        "--show-manifests",
        action="store_true",
        help="print the image's manifest file names for each supported architecture and exit",
    )
    parser.add_argument(
        "--show-archs",
        action="store_true",
        help="print the image's supported architectures and exit",
    )
    parser.add_argument(
        "-a", "--arch",
        action="append",
        default=[],
        choices=_query.ARCHITECTURES,
        help="architecture(s) for which to extract artifacts (default: all present on the image)",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-p", "--prefix",
        help="host destination path into which to extract artifacts",
    )
    group.add_argument(
        "-m", "--mirror",
        action="store_true",
        help="extract artifacts to the same path as in the image",
    )

    subparsers = parser.add_subparsers(dest="manifest", metavar="MANIFEST")

    sysroot = subparsers.add_parser(
        "sysroot",
        help="extract sysroot artifacts",
        description="If no component flags are set, all components will be extracted."
    )
    sysroot.add_argument(
        "--headers",
        dest="sysroot_headers",
        action="store_true",
        help="extract headers from the sysroot",
    )
    sysroot.add_argument(
        "--runtime",
        dest="sysroot_runtime",
        action="store_true",
        help="extract runtime libraries from the sysroot",
    )
    sysroot.add_argument(
        "--static",
        dest="sysroot_static",
        action="store_true",
        help="extract static files (e.g., .a, .link, .o) from the sysroot",
    )

    toolchain = subparsers.add_parser(
        "toolchain",
        help="create wrapper scripts for toolchain binaries",
        description="If no component flags are set, all components will be wrapped.",
    )
    toolchain.add_argument(
        "--cc",
        dest="toolchain_cc",
        action="store_true",
        help="create wrapper scripts for compiler (and related) binaries",
    )

    args, remaining = parser.parse_known_args()
    if remaining:
        args = parser.parse_args(remaining, namespace=args)

    if not args.image:
        parser.error("the following arguments are required: -i/--image")

    if not any((args.show_prefixes, args.show_archs, args.show_manifests)):
        if not args.manifest:
            parser.error("a MANIFEST subcommand is required")
        if not args.prefix and not args.mirror:
            parser.error("one of the following arguments are required: -p/--prefix, -m/--mirror")

    return args


def transform_cli(args: argparse.Namespace) -> Optional[list[ManifestCli]]:
    """
    Parses the requested manifests from the cli arguments, checking that
    everything is supported.

    One ManifestCli instance is created per supported architecture.

    If cli flags to display information and exit are passed, this function will
    return None.
    """
    try:
        # parse basics
        root = args.manifest
        component_flags: dict[str, bool] = {
            k.removeprefix(f"{root}_"): v for k, v in vars(args).items()
            if k.startswith(f"{root}_")
        }

        # print and exit if necessary
        prefixes = _query.checked_available_prefixes(target=args.image)
        if args.show_archs:
            print(json.dumps(list(prefixes.keys())))
            return None
        if args.show_prefixes:
            print(json.dumps({ a: str(p) for a, p in prefixes.items() }))
            return None
        if args.show_manifests:
            with _docker.Container(image=args.image) as c:
                manifests = _query.checked_available_manifests(container=c)
                print(json.dumps(manifests))
                return None

        # parse architectures (none set defaults to all supported)
        if args.arch:
            supported_archs = _query.checked_supported_architectures(
                available=list(prefixes.keys()), requested=args.arch
            )
            prefixes = {
                a: p for a, p in prefixes.items() if a in supported_archs
            }

        with _docker.Container(image=args.image) as c:

            # parse manifests (none set defaults to all supported)
            manifests = _query.checked_available_manifests(container=c)
            if any(component_flags.values()):
                requested_manifests = {}
                for a in prefixes.keys():
                    requested_manifests.setdefault(a, {})[root] =\
                        [k for k, v in component_flags.items() if v]
                manifests = _query.checked_supported_manifests(
                    available=manifests, requested=requested_manifests
                )

            # create cli objects
            clis: list[ManifestCli] = []
            for a, p in prefixes.items():
                if root not in manifests[a]:
                    raise RuntimeError(
                        f"Manifest '{root}' is not supported for architecture "
                        f"'{a}'"
                    )
                clis.append(ManifestCli(
                    arch=a,
                    image_prefix=p,
                    host_prefix=p if args.mirror else Path(args.prefix),
                    root=root,
                    components=manifests[a][root],
                ))
            return clis

    except Exception as e:
        raise RuntimeError(f"Failed for image '{args.image}'") from e


def read_manifest_file(container: _docker.Container, path: Path) -> list[Path]:
    """
    Reads the manifest file at the given path from the image if it exists,
    otherwise raises an exception.
    """
    byte_data = container.read_file(str(path))
    if byte_data is None:
        raise RuntimeError(
            f"The manifest file does not exist or is not accessible: {path}"
        )

    data = byte_data.decode().strip()
    lines = data.split("\n")
    paths = []
    for line in lines:
        s = line.strip()
        if s:
            paths.append(Path(s))

    if not paths:
        raise RuntimeError(f"The manifest file is empty: {path}")
    return paths


def extract_files(
        container: _docker.Container,
        img_dir: Path, dst_dir: Path, files: list[Path]
) -> None:
    """
    Copies the given files relative to the source path on the image to the host
    relative to the destination path, otherwise raises an exception.
    """
    with tempfile.TemporaryDirectory() as tmp_name:

        tmp_dir = Path(tmp_name)
        if not container.extract_path(img_path=f"{img_dir}/.", dst_path=tmp_dir):
            raise RuntimeError(
                f"The directory does not exist or is not accessible: {img_dir}"
            )

        for f in files:

            tmp_f = tmp_dir / f
            dst_f = dst_dir / f
            dst_f.parent.mkdir(parents=True, exist_ok=True)

            if not tmp_f.exists():
                raise RuntimeError(
                    f"The file does not exist in the image: {img_dir / f}"
                )

            if tmp_f.is_symlink():
                if dst_f.exists() or dst_f.is_symlink():
                    dst_f.unlink()
                dst_f.symlink_to(tmp_f.readlink())
            else:
                shutil.copy2(tmp_f, dst_f)


def wrap_tools(dst_dir: Path, binary_names: list[str], manifest_name: str) -> None:
    """
    Creates wrapper scripts in the destination path for all given binary names.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_name.replace('.', '_').upper()

    is_windows = sys.platform == "win32"
    ext = ".cmd" if is_windows else ""
    newline = "\r\n" if is_windows else "\n"

    templates_dir = Path(__file__).parent.parent / "templates"
    template_path = templates_dir / f"tool.{'cmd' if is_windows else 'sh'}"
    template = Template(template_path.read_text())

    for bn in binary_names:

        filepath = dst_dir / f"{bn}{ext}"
        content = template.substitute(binary=bn, manifest=manifest)

        with open(filepath, "w", newline=newline) as f:
            f.write(content)

        if not is_windows:
            st = os.stat(filepath)
            x_bit = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            os.chmod(filepath, st.st_mode | x_bit)


def main() -> None:

    try:
        # get manifests
        args = parse_cli()
        manifests = transform_cli(args)

        with _docker.Container(image=args.image) as c:

            # small speedup for sysroot (so we don't copy files multiple times)
            if len(set(m.image_prefix for m in manifests)) > 1:
                raise RuntimeError(
                    "All image prefix values must be identical "
                    "(this is not a hard requirement, just makes code simpler)"
                )
            if len(set(m.host_prefix for m in manifests)) > 1:
                raise RuntimeError(
                    "All host prefix values must be identical "
                    "(this is not a hard requirement, just makes code simpler)"
                )
            if len(set(m.root for m in manifests)) > 1:
                raise RuntimeError(
                    "All manifest values must be identical "
                    "(this is not a hard requirement, just makes code simpler)"
                )

            # read contents from all manifest files
            manifest_contents: dict[str, list[Path]] = {}
            root = None
            image_prefix = None
            host_prefix = None
            for m in manifests:
                root = m.root
                image_prefix = m.image_prefix
                host_prefix = m.host_prefix
                for comp in m.components:
                    name_noarch = f"{m.root}.{comp}"
                    name = f"{name_noarch}.{m.arch}"
                    mp = m.image_prefix / ".manifests" / f"{name}"
                    contents = read_manifest_file(container=c, path=mp)
                    manifest_contents.setdefault(name_noarch, []).extend(contents)

            if root == "sysroot":

                # copy files
                all_paths = [p for paths in manifest_contents.values() for p in paths]
                extract_files(
                    container=c,
                    img_dir=image_prefix,
                    dst_dir=host_prefix,
                    files=all_paths,
                )

            elif root == "toolchain":

                # create wrapper scripts
                for name, paths in manifest_contents.items():
                    wrap_tools(
                        dst_dir=host_prefix,
                        binary_names=[p.name for p in paths],
                        manifest_name=name,
                    )

    except Exception as e:
        chain = []
        current = e
        while current is not None:
            chain.append( str(current))
            current = current.__cause__ or current.__context__
        for msg in reversed(chain):
            print(f"Error: {msg}", file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()
