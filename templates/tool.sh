#!/bin/sh
: "$${QNX_DOCKER:?QNX_DOCKER is not set}"
: "$${QNX_CONTAINER_${manifest}:?QNX_CONTAINER_${manifest} is not set}"

exec "$$QNX_DOCKER" exec -w "$$(pwd)" "$$QNX_CONTAINER_${manifest}" ${binary} "$$@"
