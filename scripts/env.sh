#!/usr/bin/env bash
# Source this file from any directory to use Packwise's project-local toolchain.
#
#   source scripts/env.sh
#
# It does not install tools. Run `./scripts/dev setup` first if `.packwise-env`
# has not been created on this machine.

if [ -n "${BASH_SOURCE[0]:-}" ]; then
  _packwise_env_script="${BASH_SOURCE[0]}"
else
  _packwise_env_script="$0"
fi

_packwise_repo_root="$(cd "$(dirname "${_packwise_env_script}")/.." && pwd)"
_packwise_env_home="${_packwise_repo_root}/.packwise-env"

_packwise_prepend_path() {
  local var_name="$1"
  local value="$2"
  local current_value="${!var_name:-}"

  case ":${current_value}:" in
    *":${value}:"*)
      ;;
    *)
      if [ -n "${current_value}" ]; then
        export "${var_name}=${value}:${current_value}"
      else
        export "${var_name}=${value}"
      fi
      ;;
  esac
}

export PACKWISE_REPO_ROOT="${_packwise_repo_root}"
export PACKWISE_ENV_HOME="${_packwise_env_home}"
export GRADLE_USER_HOME="${PACKWISE_ENV_HOME}/gradle"
export PIP_CACHE_DIR="${PACKWISE_ENV_HOME}/pip-cache"
export PYTHONPYCACHEPREFIX="${PACKWISE_ENV_HOME}/pycache"
_packwise_prepend_path PYTHONPATH "${PACKWISE_REPO_ROOT}/apps/agent"

if [ -d "${PACKWISE_ENV_HOME}/python" ]; then
  # shellcheck source=/dev/null
  source "${PACKWISE_ENV_HOME}/python/bin/activate"
fi

if [ -d "${PACKWISE_ENV_HOME}/jdk" ]; then
  export JAVA_HOME="${PACKWISE_ENV_HOME}/jdk"
  export PACKWISE_JDK21_HOME="${JAVA_HOME}"
  _packwise_prepend_path PATH "${JAVA_HOME}/bin"
fi

unset -f _packwise_prepend_path
unset _packwise_env_script
unset _packwise_repo_root
unset _packwise_env_home
