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
