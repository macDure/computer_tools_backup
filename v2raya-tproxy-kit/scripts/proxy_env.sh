# Shell helpers for refreshing proxy environment variables.
# Source this file; executing it cannot change the parent shell environment.

proxy_env_show() {
  local output
  output=$(
    env | grep -Ei '^(http|https|all|no)_proxy=' || true
    env | grep -E '^(HTTP|HTTPS|ALL|NO)_PROXY=' || true
  )
  if [ -n "$output" ]; then
    printf '%s\n' "$output"
  else
    printf 'No proxy environment variables are set in this terminal.\n'
  fi
}

proxy_env_off() {
  unset http_proxy https_proxy all_proxy no_proxy
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
  printf 'Proxy environment cleared for this terminal.\n'
}

proxy_env_v2raya() {
  export http_proxy='http://127.0.0.1:20171'
  export https_proxy='http://127.0.0.1:20171'
  export HTTP_PROXY="$http_proxy"
  export HTTPS_PROXY="$https_proxy"
  export all_proxy='socks5h://127.0.0.1:20170'
  export ALL_PROXY="$all_proxy"
  export no_proxy='localhost,127.0.0.0/8,::1'
  export NO_PROXY="$no_proxy"
  printf 'Proxy environment set to v2rayA: http=20171 socks=20170\n'
}

proxy_env_v2rayn() {
  export http_proxy='http://127.0.0.1:10808'
  export https_proxy='http://127.0.0.1:10808'
  export HTTP_PROXY="$http_proxy"
  export HTTPS_PROXY="$https_proxy"
  export all_proxy='socks5h://127.0.0.1:10808'
  export ALL_PROXY="$all_proxy"
  export no_proxy='localhost,127.0.0.0/8,::1'
  export NO_PROXY="$no_proxy"
  printf 'Proxy environment set to v2rayN: 10808\n'
}

proxy_env_port_open() {
  ss -lnt 2>/dev/null | grep -q "127.0.0.1:$1 "
}

proxy_env_auto() {
  local proxy_vars
  proxy_vars="${http_proxy:-}${https_proxy:-}${all_proxy:-}${HTTP_PROXY:-}${HTTPS_PROXY:-}${ALL_PROXY:-}"

  # Default for v2rayA tproxy: no terminal proxy variables are needed. If this
  # terminal has no proxy environment, keep it that way.
  if [ -z "$proxy_vars" ]; then
    printf 'No proxy environment variables are set; nothing to refresh.\n'
    return 0
  fi

  case "$proxy_vars" in
    *127.0.0.1:10808*)
      if proxy_env_port_open 10808; then
        printf 'Proxy environment points to v2rayN 10808, and the port is alive.\n'
      else
        printf 'Proxy environment points to v2rayN 10808, but the port is not listening.\n'
        proxy_env_off
      fi
      ;;
    *127.0.0.1:20171*|*127.0.0.1:20170*)
      if proxy_env_port_open 20171 || proxy_env_port_open 20170; then
        printf 'Proxy environment points to v2rayA 20171/20170, and v2rayA proxy ports are alive.\n'
      else
        printf 'Proxy environment points to v2rayA 20171/20170, but v2rayA proxy ports are not listening.\n'
        proxy_env_off
      fi
      ;;
    *)
      printf 'Proxy environment points to an unknown proxy target; leaving it unchanged.\n'
      ;;
  esac
}

alias proxy-show='proxy_env_show'
alias proxy-off='proxy_env_off'
alias proxy-v2raya='proxy_env_v2raya'
alias proxy-v2rayn='proxy_env_v2rayn'
alias proxy-auto='proxy_env_auto'

proxy_env_auto
