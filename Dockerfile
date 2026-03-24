# qnx only runs on this platform; do not override it
ARG _QNX_HOST_PLATFORM="linux/amd64"


FROM debian:bookworm-slim AS internal-sysroot-base

# options
ARG QNX_SDP_ROOT="sdp/qnx800"
ARG QNX_VER="8.0.0"
ARG GCC_VER="12.2.0"

# generic target header files
COPY "${QNX_SDP_ROOT}/target/qnx/usr/include/" "/q/sysroot/aarch64/target/qnx/usr/include/"
COPY "${QNX_SDP_ROOT}/target/qnx/usr/include/" "/q/sysroot/x86_64/target/qnx/usr/include/"

# aarch64 compiler header files
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/aarch64-unknown-nto-qnx${QNX_VER}/${GCC_VER}/include/" \
     "/q/sysroot/aarch64/host/linux/x86_64/usr/lib/gcc/aarch64-unknown-nto-qnx${QNX_VER}/${GCC_VER}/include/"

# x86_64 compiler header files
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/x86_64-pc-nto-qnx${QNX_VER}/${GCC_VER}/include/" \
     "/q/sysroot/x86_64/host/linux/x86_64/usr/lib/gcc/x86_64-pc-nto-qnx${QNX_VER}/${GCC_VER}/include/"

# generic target runtime dependencies
COPY "${QNX_SDP_ROOT}/target/qnx/usr/lib/" "/q/sysroot/aarch64/target/qnx/usr/lib/"
COPY "${QNX_SDP_ROOT}/target/qnx/usr/lib/" "/q/sysroot/x86_64/target/qnx/usr/lib/"

# aarch64 target runtime dependencies
COPY "${QNX_SDP_ROOT}/target/qnx/aarch64le/lib/"     "/q/sysroot/aarch64/target/qnx/aarch64le/lib/"
COPY "${QNX_SDP_ROOT}/target/qnx/aarch64le/usr/lib/" "/q/sysroot/aarch64/target/qnx/aarch64le/usr/lib/"

# x86_64 target runtime dependencies
COPY "${QNX_SDP_ROOT}/target/qnx/x86_64/lib/"     "/q/sysroot/x86_64/target/qnx/x86_64/lib/"
COPY "${QNX_SDP_ROOT}/target/qnx/x86_64/usr/lib/" "/q/sysroot/x86_64/target/qnx/x86_64/usr/lib/"

# remove unnecessary artifacts
RUN set -eux; \
    rm -rf '/q/sysroot/aarch64/target/qnx/aarch64le/lib/dll'            \
           '/q/sysroot/aarch64/target/qnx/aarch64le/usr/lib/python3.11' \
           '/q/sysroot/x86_64/target/qnx/x86_64/lib/dll'                \
           '/q/sysroot/x86_64/target/qnx/x86_64/usr/lib/python3.11';    \
    find '/q/sysroot' -not -path '*/include/*' \(  \
        -name '*.sym'  -o \
        -name '*.py'   -o \
        -name '*.json' -o \
        -name '*.txt'  -o \
        -name '*.xml'  -o \
        -name '*.html' -o \
        -name '*.js'   -o \
        -name '*.css'  -o \
        -name '*.supp'    \
    \) -delete; \
    find '/q/sysroot' -path '*/usr/lib/valgrind/*' -type f -not -name '*.*' -delete; \
    find '/q/sysroot' -type d -empty -delete; \
    :

# create manifest files
# manifest contains all files so that we can extract them
RUN set -eux; \
    for arch in "aarch64" "x86_64"; do            \
        mkdir -p "/q/sysroot/${arch}/.manifests"; \
        cd "/q/sysroot/${arch}";                  \
        { \
            find "." -not -path "./.manifests" -not -path "./.manifests/*" -type f | sort; \
            find "." -not -path "./.manifests" -not -path "./.manifests/*" -type l | sort; \
        } | sed "s|^\./||" | while IFS= read -r file; do \
            case "${file}" in \
                */include/*) echo "${file}" >> ".manifests/sysroot.headers.${arch}" ;; \
                *.so|*.so.*) echo "${file}" >> ".manifests/sysroot.runtime.${arch}" ;; \
                *)           echo "${file}" >> ".manifests/sysroot.static.${arch}"  ;; \
            esac; \
        done; \
    done; \
    :


FROM scratch AS aarch64-sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"

COPY --from=internal-sysroot-base "/q/sysroot/aarch64/" "${QNX_PREFIX}/"


FROM scratch AS x86_64-sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=internal-sysroot-base "/q/sysroot/x86_64/" "${QNX_PREFIX}/"


FROM scratch AS sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"
LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=internal-sysroot-base "/q/sysroot/aarch64/" "${QNX_PREFIX}/"
COPY --from=internal-sysroot-base "/q/sysroot/x86_64/"  "${QNX_PREFIX}/"


FROM debian:bookworm-slim AS internal-toolchain-base

# options
ARG QNX_SDP_ROOT="sdp/qnx800"
ARG QNX_VER="8.0.0"
ARG GCC_VER="12.2.0"

# [core] host runtime dependencies that are not part of sysroot
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/" "/q/toolchain/core/aarch64/host/linux/x86_64/usr/lib/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/" "/q/toolchain/core/x86_64/host/linux/x86_64/usr/lib/"

# [core] remove unnecessary dependencies
RUN set -eux; \
    rm -rf "/q/toolchain/core/aarch64/host/linux/x86_64/usr/lib/gcc" \
           "/q/toolchain/core/x86_64/host/linux/x86_64/usr/lib/gcc"; \
    :

# [cc] compiler configuration files
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/etc/" "/q/toolchain/cc/aarch64/host/linux/x86_64/etc/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/etc/" "/q/toolchain/cc/x86_64/host/linux/x86_64/etc/"

# [cc] remove unnecessary configurations
RUN set -eux; \
    rm -rf /q/toolchain/cc/aarch64/host/linux/x86_64/etc/qcc/gcc/${GCC_VER}/*x86_64*   \
           /q/toolchain/cc/x86_64/host/linux/x86_64/etc/qcc/gcc/${GCC_VER}/*aarch64* ; \
    echo 'CONF=gcc_ntoaarch64le' > "/q/toolchain/cc/aarch64/host/linux/x86_64/etc/qcc/gcc/${GCC_VER}/default"; \
    echo 'CONF=gcc_ntox86_64'    > "/q/toolchain/cc/x86_64/host/linux/x86_64/etc/qcc/gcc/${GCC_VER}/default";  \
    :

# [cc] host runtime dependencies that are not part of sysroot
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/" "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/lib/gcc/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/" "/q/toolchain/cc/x86_64/host/linux/x86_64/usr/lib/gcc/"

# [cc] remove unnecessary dependencies
RUN set -eux; \
    rm -rf /q/toolchain/cc/aarch64/host/linux/x86_64/usr/lib/gcc/*x86_64*   \
           /q/toolchain/cc/x86_64/host/linux/x86_64/usr/lib/gcc/*aarch64* ; \
    :

# [cc] host binary executables (aarch64)
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/qcc" "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/qcc"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/q++" "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/q++"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-ar*"       "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-as*"       "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-c++*"      "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-cpp*"      "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-g++*"      "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-gcc*"      "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-gcov*"     "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-gprof*"    "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-ld*"       "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-lto-dump*" "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-nm*"       "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-objcopy*"  "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-ranlib*"   "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/bin/*-strip*"    "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/"

# [cc] host binary executables (x86_64)
# symlinks are relative, so no issue here
RUN set -eux; \
    mkdir -p  "/q/toolchain/cc/x86_64/host/linux/x86_64/usr/bin/"; \
    cp -a  "/q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/."   \
           "/q/toolchain/cc/x86_64/host/linux/x86_64/usr/bin/";    \
    :

# [cc] remove unnecessary binary executables
RUN set -eux; \
    rm -rf /q/toolchain/cc/aarch64/host/linux/x86_64/usr/bin/*x86_64*   \
           /q/toolchain/cc/x86_64/host/linux/x86_64/usr/bin/*aarch64* ; \
    :

# [cc] create manifest files
# manifest contains just binary files so that we know what tools to wrap
RUN set -eux; \
    for arch in "aarch64" "x86_64"; do                 \
        mkdir -p "/q/toolchain/cc/${arch}/.manifests"; \
        cd "/q/toolchain/cc/${arch}";                  \
        { \
            find "./host/linux/x86_64/usr/bin" -type f | sort;  \
            find "./host/linux/x86_64/usr/bin" -type l | sort;  \
        } | sed "s|^\./||" > ".manifests/toolchain.cc.${arch}"; \
    done; \
    :


FROM scratch AS internal-aarch64-toolchain-core

ARG QNX_PREFIX="/opt/qnx/qnx800"

COPY --from=internal-toolchain-base "/q/toolchain/core/aarch64/" "${QNX_PREFIX}/"

ENV MAKEFLAGS="-I${QNX_PREFIX}/target/qnx/usr/include"
ENV PATH="${QNX_PREFIX}/host/linux/x86_64/usr/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV QNX_TARGET="${QNX_PREFIX}/target/qnx"
ENV QNX_HOST="${QNX_PREFIX}/host/linux/x86_64"


FROM scratch AS internal-x86_64-toolchain-core

ARG QNX_PREFIX="/opt/qnx/qnx800"

COPY --from=internal-toolchain-base "/q/toolchain/core/x86_64/" "${QNX_PREFIX}/"

ENV MAKEFLAGS="-I${QNX_PREFIX}/target/qnx/usr/include"
ENV PATH="${QNX_PREFIX}/host/linux/x86_64/usr/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV QNX_TARGET="${QNX_PREFIX}/target/qnx"
ENV QNX_HOST="${QNX_PREFIX}/host/linux/x86_64"


FROM scratch AS internal-toolchain-core

ARG QNX_PREFIX="/opt/qnx/qnx800"

COPY --from=internal-toolchain-base "/q/toolchain/core/aarch64/" "${QNX_PREFIX}/"
COPY --from=internal-toolchain-base "/q/toolchain/core/x86_64/"  "${QNX_PREFIX}/"

ENV MAKEFLAGS="-I${QNX_PREFIX}/target/qnx/usr/include"
ENV PATH="${QNX_PREFIX}/host/linux/x86_64/usr/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV QNX_TARGET="${QNX_PREFIX}/target/qnx"
ENV QNX_HOST="${QNX_PREFIX}/host/linux/x86_64"


FROM internal-aarch64-toolchain-core AS aarch64-toolchain-cc

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"

COPY --from=internal-sysroot-base   "/q/sysroot/aarch64/"      "${QNX_PREFIX}/"
COPY --from=internal-toolchain-base "/q/toolchain/cc/aarch64/" "${QNX_PREFIX}/"


FROM internal-x86_64-toolchain-core AS x86_64-toolchain-cc

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=internal-sysroot-base   "/q/sysroot/x86_64/"      "${QNX_PREFIX}/"
COPY --from=internal-toolchain-base "/q/toolchain/cc/x86_64/" "${QNX_PREFIX}/"


FROM internal-toolchain-core AS toolchain-cc

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"
LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=internal-sysroot-base   "/q/sysroot/aarch64/"      "${QNX_PREFIX}/"
COPY --from=internal-toolchain-base "/q/toolchain/cc/aarch64/" "${QNX_PREFIX}/"

# this coming seconds means "etc/qcc/gcc/${GCC_VER}/default" is x86_64
COPY --from=internal-sysroot-base   "/q/sysroot/x86_64/"      "${QNX_PREFIX}/"
COPY --from=internal-toolchain-base "/q/toolchain/cc/x86_64/" "${QNX_PREFIX}/"


FROM internal-aarch64-toolchain-core AS aarch64-toolchain

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"

COPY --from=aarch64-toolchain-cc "${QNX_PREFIX}/" "${QNX_PREFIX}/"


FROM internal-x86_64-toolchain-core AS x86_64-toolchain

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=x86_64-toolchain-cc "${QNX_PREFIX}/" "${QNX_PREFIX}/"


FROM internal-toolchain-core AS toolchain

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"
LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=toolchain-cc "${QNX_PREFIX}/" "${QNX_PREFIX}/"
