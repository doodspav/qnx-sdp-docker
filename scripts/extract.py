import argparse
import shutil
import tempfile

from pathlib import Path
from typing import Dict, List, Optional

from _docker import Container, get_label


ARCHITECTURES = ["aarch64", "x86_64"]


def parse_cli() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Extract artifacts from a Docker image using manifest files.",
    )

    parser.add_argument(
        "-i", "--image",
        help="image from which to extract artifacts",
    )
    parser.add_argument(
        "--show-prefix",
        action="store_true",
        help="print the image's QNX prefix and exit",
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

    args, remaining = parser.parse_known_args()
    if remaining:
        args = parser.parse_args(remaining, namespace=args)

    if not args.image:
        parser.error("the following arguments are required: -i/--image")

    if not args.show_prefix:
        if not args.manifest:
            parser.error("a MANIFEST subcommand is required")
        if not args.prefix and not args.mirror:
            parser.error("one of the following arguments are required: -p/--prefix, -m/--mirror")

    return args


def parse_manifest_names(args: argparse.Namespace) -> List[str]:
    """
    Parses the cli arguments to decide which manifest files need to be read.
    """
    opts = { k: v for k, v in vars(args).items() if k.startswith(f"{args.manifest}_") }
    opts = { k.removeprefix(f"{args.manifest}_"): v for k, v in opts.items() }

    # no flags set means return default, which is the root manifest
    if not any(opts.values()):
        return [args.manifest]

    # if flags are set, only return those manifests
    return [f"{args.manifest}.{k}" for k, v in opts.items() if v]


def get_image_prefix(image: str, arch: str) -> Optional[Path]:
    """
    Gets the QNX prefix for the given architecture from the image if present.
    """
    label = f"qnx.prefix.{arch}"
    prefix = get_label(image=image, label=label)
    return Path(prefix) if prefix else None


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
                print(tmp_f)
                raise RuntimeError(
                    f"The file does not exist in the image: {img_dir / f}"
                )

            if tmp_f.is_symlink():
                if dst_f.exists() or dst_f.is_symlink():
                    dst_f.unlink()
                dst_f.symlink_to(tmp_f.readlink())
            else:
                shutil.copy2(tmp_f, dst_f)


def main() -> None:

    # parse args
    args = parse_cli()

    # check supported architectures
    supported_archs: Dict[str, Path] = {}
    for a in ARCHITECTURES:
        if (p := get_image_prefix(image=args.image, arch=a)) is not None:
            supported_archs[a] = p
    if not supported_archs:
        raise ValueError(f"No supported architectures found for image '{args.image}'")

    # set up requested architectures (default is any supported)
    args.arch = [] if args.arch is None else list(args.arch)
    unsupported_archs = set(args.arch) - set(supported_archs.keys())
    if unsupported_archs:
        raise ValueError(
            f"Unsupported architecture(s) requested for image "
            f"'{args.image}': {', '.join(unsupported_archs)}"
        )
    requested_archs: Dict[str, Path] = {
        a: supported_archs[a] for a in args.arch
    }
    if not requested_archs:
        requested_archs = supported_archs

    # print prefixes if that's all we care about
    if args.show_prefix:
        for a, p in requested_archs.items():
            print(f"{a}: {p}")
        return

    with Container(image=args.image) as c:

        # get manifest files
        manifest_files: Dict[str, List[Path]] = {}
        for a, p in requested_archs.items():
            for name in parse_manifest_names(args):
                m = p / ".manifests" / f"{name}.{a}"
                manifest_files[a] = read_manifest_file(container=c, path=m)

        # copy files
        for a, paths in manifest_files.items():
            image_prefix = requested_archs[a]
            host_prefix = image_prefix if args.mirror else Path(args.prefix)
            extract_files(
                container=c,
                img_dir=image_prefix,
                dst_dir=host_prefix,
                files=paths
            )


if __name__ == "__main__":
    main()
