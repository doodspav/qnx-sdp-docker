# qnx only runs on this platform; do not override it
ARG _QNX_HOST_PLATFORM="linux/amd64"


FROM debian:bookworm-slim AS base-sysroot

# options
ARG QNX_SDP_ROOT="sdp/qnx800"
ARG QNX_VER="8.0.0"
ARG GCC_VER="12.2.0"

# labels
LABEL qnx.prefix.aarch64="/sysroot/aarch64"
LABEL qnx.prefix.x86_64="/sysroot/x86_64"

# generic target header files
COPY "${QNX_SDP_ROOT}/target/qnx/usr/include/" "/sysroot/aarch64/target/qnx/usr/include/"
COPY "${QNX_SDP_ROOT}/target/qnx/usr/include/" "/sysroot/x86_64/target/qnx/usr/include/"

# generic host header files included for convenience
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/include/" "/sysroot/aarch64/host/linux/x86_64/usr/include/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/include/" "/sysroot/x86_64/host/linux/x86_64/usr/include/"

# aarch64 compiler header files (plugin is included for convenience even though it's host)
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/aarch64-unknown-nto-qnx${QNX_VER}/${GCC_VER}/include/" \
     "/sysroot/aarch64/host/linux/x86_64/usr/lib/gcc/aarch64-unknown-nto-qnx${QNX_VER}/${GCC_VER}/include/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/aarch64-unknown-nto-qnx${QNX_VER}/${GCC_VER}/plugin/include/" \
     "/sysroot/aarch64/host/linux/x86_64/usr/lib/gcc/aarch64-unknown-nto-qnx${QNX_VER}/${GCC_VER}/plugin/include/"

# x86_64 compiler header files (plugin is included for convenience even though it's host)
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/x86_64-pc-nto-qnx${QNX_VER}/${GCC_VER}/include/" \
     "/sysroot/x86_64/host/linux/x86_64/usr/lib/gcc/x86_64-pc-nto-qnx${QNX_VER}/${GCC_VER}/include/"
COPY "${QNX_SDP_ROOT}/host/linux/x86_64/usr/lib/gcc/x86_64-pc-nto-qnx${QNX_VER}/${GCC_VER}/plugin/include/" \
     "/sysroot/x86_64/host/linux/x86_64/usr/lib/gcc/x86_64-pc-nto-qnx${QNX_VER}/${GCC_VER}/plugin/include/"

# generic target runtime dependencies
COPY "${QNX_SDP_ROOT}/target/qnx/usr/lib/" "/sysroot/aarch64/target/qnx/usr/lib/"
COPY "${QNX_SDP_ROOT}/target/qnx/usr/lib/" "/sysroot/x86_64/target/qnx/usr/lib/"

# aarch64 target runtime dependencies
COPY "${QNX_SDP_ROOT}/target/qnx/aarch64le/lib/"     "/sysroot/aarch64/target/qnx/aarch64le/lib/"
COPY "${QNX_SDP_ROOT}/target/qnx/aarch64le/usr/lib/" "/sysroot/aarch64/target/qnx/aarch64le/usr/lib/"

# x86_64 target runtime dependencies
COPY "${QNX_SDP_ROOT}/target/qnx/x86_64/lib/"     "/sysroot/x86_64/target/qnx/x86_64/lib/"
COPY "${QNX_SDP_ROOT}/target/qnx/x86_64/usr/lib/" "/sysroot/x86_64/target/qnx/x86_64/usr/lib/"

# remove unnecessary artifacts
RUN set -eux; \
    rm -rf '/sysroot/aarch64/target/qnx/aarch64le/lib/dll'            \
           '/sysroot/aarch64/target/qnx/aarch64le/usr/lib/python3.11' \
           '/sysroot/x86_64/target/qnx/x86_64/lib/dll'                \
           '/sysroot/x86_64/target/qnx/x86_64/usr/lib/python3.11';    \
    find '/sysroot' \( \
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
    find '/sysroot' -path '*/usr/lib/valgrind/*' -type f -not -name '*.*' -delete; \
    find '/sysroot' -type d -empty -delete; \
    :

# create manifest files
RUN set -eux; \
    mkdir -p "/sysroot/aarch64/.manifests"; \
    cd "/sysroot/aarch64";                  \
    {                                       \
        find "." -not -path "./.manifests" -not -path "./.manifests/*" -type f | sort; \
        find "." -not -path "./.manifests" -not -path "./.manifests/*" -type l | sort; \
    } | sed "s|^\./||" > ".manifests/sysroot.aarch64";                                 \
    mkdir -p "/sysroot/x86_64/.manifests"; \
    cd "/sysroot/x86_64";                  \
    {                                      \
        find "." -not -path "./.manifests" -not -path "./.manifests/*" -type f | sort; \
        find "." -not -path "./.manifests" -not -path "./.manifests/*" -type l | sort; \
    } | sed "s|^\./||" > ".manifests/sysroot.x86_64";                                  \
    :


FROM scratch AS aarch64-sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"

COPY --from=base-sysroot "/sysroot/aarch64/" "${QNX_PREFIX}/"


FROM scratch AS x86_64-sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=base-sysroot "/sysroot/x86_64/" "${QNX_PREFIX}/"


FROM scratch AS sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"
LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=base-sysroot "/sysroot/aarch64/" "${QNX_PREFIX}/"
COPY --from=base-sysroot "/sysroot/x86_64/"  "${QNX_PREFIX}/"
