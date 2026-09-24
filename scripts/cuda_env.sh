#!/usr/bin/env bash
# Source this before the transcribe step: the pip CUDA libraries are not on the loader path by default.
# usage: source scripts/cuda_env.sh
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_py="${VIRTUAL_ENV:-$_here/../venv}/bin/python"
export LD_LIBRARY_PATH="$("$_py" -c 'import nvidia.cublas.lib as a, nvidia.cudnn.lib as b; print(a.__path__[0]+":"+b.__path__[0])'):${LD_LIBRARY_PATH:-}"
export PATH="$HOME/.deno/bin:$PATH"
