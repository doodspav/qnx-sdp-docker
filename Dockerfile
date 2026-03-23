# qnx only runs on this platform; do not override it
ARG _QNX_HOST_PLATFORM="linux/amd64"


FROM debian:bookworm-slim AS base-sysroot

# options
ARG QNX_SDP_ROOT="sdp/qnx800"
ARG QNX_VER="8.0.0"
ARG GCC_VER="12.2.0"

# labels
LABEL qnx.prefix.aarch64="/q/sysroot/aarch64"
LABEL qnx.prefix.x86_64="/q/sysroot/x86_64"

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

COPY --from=base-sysroot "/q/sysroot/aarch64/" "${QNX_PREFIX}/"


FROM scratch AS x86_64-sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=base-sysroot "/q/sysroot/x86_64/" "${QNX_PREFIX}/"


FROM scratch AS sysroot

ARG QNX_PREFIX="/opt/qnx/qnx800"

LABEL qnx.prefix.aarch64="${QNX_PREFIX}"
LABEL qnx.prefix.x86_64="${QNX_PREFIX}"

COPY --from=base-sysroot "/q/sysroot/aarch64/" "${QNX_PREFIX}/"
COPY --from=base-sysroot "/q/sysroot/x86_64/"  "${QNX_PREFIX}/"
