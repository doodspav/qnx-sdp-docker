import argparse
import json
import os
import shutil
import stat
import sys
import tempfile

from pathlib import Path
from string import Template
from typing import Dict, List, Optional

from _docker import Container, get_label


ARCHITECTURES = ["aarch64", "x86_64"]


AVAILABLE_MANIFESTS = [
    *[f"sysroot.{s}" for s in ["headers", "runtime", "static"]],
    *[f"toolchain.{t}" for t in ["cc"]],
]


TOOL_TEMPLATE_SH = Template("""\
#!/bin/sh
: "$${QNX_DOCKER:?QNX_DOCKER is not set}"
: "$${QNX_CONTAINER_${manifest}:?QNX_CONTAINER_${manifest} is not set}"

exec "$$QNX_DOCKER" exec -w "$$(pwd)" "$$QNX_CONTAINER_${manifest}" ${binary} "$$@"
""")


TOOL_TEMPLATE_CMD = Template("""\
@echo off
if not defined QNX_DOCKER (
    >&2 echo ERROR: QNX_DOCKER is not set
    exit /b 1
)
if not defined QNX_CONTAINER_${manifest} (
    >&2 echo ERROR: QNX_CONTAINER_${manifest} is not set
    exit /b 1
)

%QNX_DOCKER% exec -w "%cd%" %QNX_CONTAINER_${manifest}% %*
""")


def parse_cli() -> argparse.Namespace:

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
        choices=ARCHITECTURES,
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


def get_image_prefix(image: str, arch: str) -> Optional[Path]:
    """
    Gets the QNX prefix for the given architecture from the image if present.

    Prefixes are returned as an absolute path.
    """
    label = f"qnx.prefix.{arch}"
    prefix = get_label(image=image, label=label)
    return Path(prefix) if prefix else None


def parse_cli_manifest_names(args: argparse.Namespace) -> List[str]:
    """
    Parses the cli arguments to decide which manifest files need to be read.

    Manifest names are returned in the form of "{group}.{sub}" without the
    architecture.
    """
    opts = { k: v for k, v in vars(args).items() if k.startswith(f"{args.manifest}_") }
    opts = { k.removeprefix(f"{args.manifest}_"): v for k, v in opts.items() }

    # no flags set means return default, which is all the manifests
    if not any(opts.values()):
        return [f"{args.manifest}.{k}" for k in opts.keys()]

    # if flags are set, only return those manifests
    return [f"{args.manifest}.{k}" for k, v in opts.items() if v]


def get_image_manifest_names(
    container: Container, arch_to_prefix: Dict[str, Path]
) -> Dict[str, List[str]]:
    """
    Gets the manifest file names for the given architecture from the image if
    present.

    Manifest names are returned in the form of "{group}.{sub}" without the
    architecture.
    """
    arch_to_names: Dict[str, List[str]] = {}
    for a, p in arch_to_prefix.items():
        path = str(p / ".manifests")
        if (names := container.list_dir_with_cp(path)) is not None:
            names = [n.removesuffix(f".{a}") for n in names if n.endswith(f".{a}")]
            names = [n for n in names if n in AVAILABLE_MANIFESTS]
            arch_to_names[a] = names
    return arch_to_names


def read_manifest_file(container: Container, path: Path) -> List[Path]:
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
    container: Container, img_dir: Path, dst_dir: Path, files: List[Path]
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


def wrap_tools(dst_dir: Path, binary_names: List[str], manifest_name: str) -> None:
    """
    Creates wrapper scripts in the destination path for all given binary names.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_name.replace('.', '_').upper()

    is_windows = sys.platform == "win32"
    ext = ".cmd" if is_windows else ""
    template = TOOL_TEMPLATE_CMD if is_windows else TOOL_TEMPLATE_SH
    newline = "\r\n" if is_windows else "\n"

    for bn in binary_names:

        filepath = dst_dir / f"{bn}{ext}"
        content = template.substitute(binary=bn, manifest=manifest)

        with open(filepath, "w", newline=newline) as f:
            f.write(content)

        if not is_windows:
            filename = str(filepath)
            st = os.stat(filename)
            x_bit = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            os.chmod(filename, st.st_mode | x_bit)


def main() -> None:

    # parse args
    args = parse_cli()

    # check supported architectures
    supported_archs: Dict[str, Path] = {}
    for a in ARCHITECTURES:
        if (p := get_image_prefix(image=args.image, arch=a)) is not None:
            supported_archs[a] = p
    if args.show_archs:
        print(json.dumps(list(supported_archs.keys())))
        return
    if args.show_prefixes:
        print(json.dumps({ k: str(v) for k, v in supported_archs.items()}))
        return
    if not supported_archs:
        raise ValueError(f"No supported architectures found for image '{args.image}'")

    # set up requested architectures (default is any supported)
    args.arch = [] if args.arch is None else list(args.arch)
    unsupported_archs = set(args.arch) - set(supported_archs.keys())
    if unsupported_archs and not args.show_manifests:
        raise ValueError(
            f"Unsupported architecture(s) requested for image "
            f"'{args.image}': {', '.join(unsupported_archs)}"
        )
    requested_archs: Dict[str, Path] = {
        a: supported_archs[a] for a in args.arch
    }
    if not requested_archs:
        requested_archs = supported_archs

    with Container(image=args.image) as c:

        # get supported manifest files
        supported_manifest_names: Dict[str, List[str]] = \
            get_image_manifest_names(container=c, arch_to_prefix=supported_archs)
        if args.show_manifests:
            print(json.dumps(supported_manifest_names))
            return

        # parse requested manifest files
        manifest_paths: Dict[str, List[Path]] = {}
        for a, p in requested_archs.items():
            for name in parse_cli_manifest_names(args):
                if name not in supported_manifest_names.get(a, []):
                    raise ValueError(
                        f"Manifest name '{name}' not available for "
                        f"architecture '{a}' on image '{args.image}'"
                    )
                m = p / ".manifests" / f"{name}.{a}"
                manifest_paths.setdefault(a, [])
                manifest_paths[a] += read_manifest_file(container=c, path=m)

        if args.manifest == "sysroot":

            # copy files
            for a, paths in manifest_paths.items():
                image_prefix = requested_archs[a]
                host_prefix = image_prefix if args.mirror else Path(args.prefix)
                extract_files(
                    container=c,
                    img_dir=image_prefix,
                    dst_dir=host_prefix,
                    files=paths
                )

        elif args.manifest == "toolchain":

            # create wrapper scripts
            for a, paths in manifest_paths.items():
                image_prefix = requested_archs[a]
                host_prefix = image_prefix if args.mirror else Path(args.prefix)
                names = [p.name for p in paths]
                wrap_tools(
                    dst_dir=host_prefix,
                    binary_names=names,
                    manifest_name="toolchain"
                )

        else:
            raise ValueError(f"Unknown manifest '{args.manifest}'")


if __name__ == "__main__":
    main()
