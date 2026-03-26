from pathlib import Path
from typing import TypeAlias

try:
    from . import _docker
except ImportError:
    import _docker


Architecture: TypeAlias = str
ManifestComponent: TypeAlias = str
ManifestRoot: TypeAlias = str
ManifestMap: TypeAlias = dict[ManifestRoot, list[ManifestComponent]]


ARCHITECTURES: list[Architecture] = [
    "aarch64",
    "x86_64",
]

MANIFESTS: ManifestMap = {
    "sysroot": [
        "headers",
        "runtime",
        "static",
    ],
    "toolchain": [
        "cc",
    ]
}


def checked_available_prefixes(target: str) -> dict[Architecture, Path]:
    """
    Gets the QNX prefix for all supported architectures from the given image or
    container, checking that at least one prefix is available.
    """
    arch_to_prefix: dict[Architecture, Path] = {}

    # try to get prefix for all possible architectures
    for a in ARCHITECTURES:
        label = f"qnx.prefix.{a}"
        prefix = _docker.get_label(target=target, label=label)

        # skip architecture if not supported
        if prefix is not None:
            arch_to_prefix[a] = Path(prefix)

    # check at least one prefix is available
    if not arch_to_prefix:
        raise RuntimeError(f"No available architectures found")
    return arch_to_prefix


def checked_available_manifests(
    container: _docker.Container
) -> dict[Architecture, ManifestMap]:
    """
    Gets all available manifests for all supported architectures on the given
    container, checking that at least one manifest is available.
    """
    arch_to_manifests: dict[Architecture, ManifestMap] = {}
    arch_to_prefix: dict[Architecture, Path] = checked_available_prefixes(
        target=container.cid
    )

    # try to get manifests for all supported prefixes
    for a, p in arch_to_prefix.items():
        path = str(p / ".manifests")
        names = container.listdir_with_cp(path=path)

        # ensure that manifests exist
        if names is None:
            raise RuntimeError(
                f"No manifests directory exists or is accessible in image "
                f"'{container.image}' at path: {path}"
            )
        names = [n.removesuffix(f".{a}") for n in names if n.endswith(f".{a}")]

        # parse supported manifests
        for name in names:
            root, component = name.split(".", 1)
            if root in MANIFESTS:
                if component in MANIFESTS[root]:

                    # save manifest
                    arch_to_manifests.setdefault(a, {})
                    arch_to_manifests[a].setdefault(root, [])
                    arch_to_manifests[a][root].append(component)

    # check at least one manifest is available
    if not arch_to_manifests:
        raise RuntimeError(f"No available manifests found")
    return arch_to_manifests


def checked_supported_architectures(
    available: list[Architecture],
    requested: list[Architecture],
) -> list[Architecture]:
    """
    Gets the intersection of available and requested architectures, checking
    that no requested architectures are unavailable and that at least one
    architecture is available.
    """
    supported = [a for a in requested if a in available]
    unsupported = [a for a in requested if a not in available]
    if unsupported:
        raise RuntimeError(
            f"Unsupported architecture(s) requested: {', '.join(unsupported)}"
        )
    if not supported:
        raise RuntimeError("No supported architectures found")
    return supported


def checked_supported_manifests(
    available: dict[Architecture, ManifestMap],
    requested: dict[Architecture, ManifestMap],
) -> dict[Architecture, ManifestMap]:
    """
    Gets the intersection of available and requested manifests, checking
    that no requested manifests are unavailable and that at least one
    manifest component is available.
    """
    supported: dict[Architecture, ManifestMap] = {}

    # check architecture support
    u_archs = [a for a in requested if a not in available]
    if u_archs:
        raise RuntimeError(
            f"Unsupported architecture(s) requested: "
            f"{', '.join(u_archs)}"
        )
    sup_archs = [a for a in requested if a in available]

    # go through manifests in supported architectures
    for a in sup_archs:
        rq_roots = list(requested[a].keys())
        av_roots = list(available[a].keys())

        # check manifest root support
        u_roots = [r for r in rq_roots if r not in av_roots]
        if u_roots:
            raise RuntimeError(
                f"Unsupported manifest(s) requested for architecture {a}: "
                f"{', '.join(u_roots)}"
            )
        sup_roots = [r for r in rq_roots if r in av_roots]

        # go through components in supported manifests
        for r in sup_roots:
            rq_comps = requested[a][r]
            av_comps = available[a][r]

            # check manifest component support
            u_comps = [c for c in rq_comps if c not in av_comps]
            if u_comps:
                raise RuntimeError(
                    f"Unsupported manifest component(s) requested for manifest "
                    f"{r} for architecture {a}: {', '.join(u_comps)}"
                )
            sup_comps = [c for c in rq_comps if c in av_comps]

            # save as supported
            if sup_comps:
                supported.setdefault(a, {})[r] = sup_comps

    if not supported:
        raise RuntimeError("No supported manifests found")
    return supported
