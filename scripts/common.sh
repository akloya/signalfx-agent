MY_SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

extra_cflags_build_arg() {
  # If this isn't true then let build use default
  if [[ ${DEBUG-} == 'true' ]]
  then
    echo "--build-arg extra_cflags='-g -O0'"
  fi
}

do_docker_build() {
  local image_name=$1
  local image_tag=$2
  local target_stage=$3
  local agent_version=${4:-$image_tag}
  local operating_system=${5:-"linux"}
  local collectd_commit=${COLLECTD_COMMIT}
  local collectd_version=${COLLECTD_VERSION}

  cache_flags=
  if [[ ${PULL_CACHE-} == "yes" ]]; then
    cache_flags=$($MY_SCRIPT_DIR/docker-cache-from $target_stage)
  fi

  docker build \
    -t $image_name:$image_tag \
    -f $MY_SCRIPT_DIR/../Dockerfile \
    --pull \
    --build-arg agent_version=${agent_version} \
    --build-arg GOOS=${operating_system} \
    --build-arg collectd_version=${collectd_version} \
    --build-arg collectd_commit=${collectd_commit} \
    --target $target_stage \
    --label agent.version=${agent_version} \
    $(extra_cflags_build_arg) \
    $cache_flags \
    $MY_SCRIPT_DIR/.. 
}
