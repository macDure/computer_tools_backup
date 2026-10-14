#!/usr/bin/env bash
set -euo pipefail

backup_root="${HOME}/.tmux-config-backups"
target="${HOME}/.tmux.conf"
script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
save_wrapper_source="${script_dir}/tmux-resurrect-save-low-priority"
save_wrapper_target="${HOME}/.local/bin/tmux-resurrect-save-low-priority"

if ! command -v tmux >/dev/null 2>&1; then
    printf '%s\n' 'tmux is not installed. Install it first, then rerun this script.' >&2
    exit 1
fi

probe_socket="tmux_config_probe_$$"
cleanup_probe() {
    tmux -L "$probe_socket" kill-server >/dev/null 2>&1 || true
}
trap cleanup_probe EXIT

# tmux 3.0a (Ubuntu 20.04) does not support the server-level copy-command
# option used by the original Ubuntu 24.04 configuration. Start an isolated
# probe session first: show-options alone fails when the option is unset, even
# on tmux versions that support it.
if tmux -L "$probe_socket" -f /dev/null new-session -d -s __tmux_config_probe '/bin/sleep 30' >/dev/null 2>&1 &&
    tmux -L "$probe_socket" set-option -s copy-command '' >/dev/null 2>&1; then
    source_config="${script_dir}/tmux.conf"
    config_variant='original/server-level copy-command'
else
    source_config="${script_dir}/tmux.conf.ubuntu20.04"
    config_variant='Ubuntu 20.04/direct copy-pipe-and-cancel'
fi

if [[ ! -f "$source_config" ]]; then
    printf 'Missing config snapshot: %s\n' "$source_config" >&2
    exit 1
fi

if [[ ! -f "$save_wrapper_source" ]]; then
    printf 'Missing low-priority save wrapper: %s\n' "$save_wrapper_source" >&2
    exit 1
fi

printf 'Using config: %s (%s)\n' "$source_config" "$config_variant"

if [[ -e "$target" || -L "$target" ]]; then
    stamp="$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_root"
    cp -a -- "$target" "$backup_root/.tmux.conf.$stamp"
    printf 'Existing config backed up to: %s\n' "$backup_root/.tmux.conf.$stamp"
fi

# Install the wrapper before the config that points Continuum at it.
if [[ -e "$save_wrapper_target" || -L "$save_wrapper_target" ]]; then
    stamp="$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_root"
    cp -a -- "$save_wrapper_target" "$backup_root/tmux-resurrect-save-low-priority.$stamp"
    printf 'Existing save wrapper backed up to: %s\n' "$backup_root/tmux-resurrect-save-low-priority.$stamp"
fi
mkdir -p "$(dirname -- "$save_wrapper_target")"
install -m 755 -- "$save_wrapper_source" "$save_wrapper_target"
printf 'Installed low-priority save wrapper: %s\n' "$save_wrapper_target"

install -m 600 -- "$source_config" "$target"
printf 'Installed: %s\n' "$target"

if tmux list-sessions >/dev/null 2>&1; then
    tmux source-file "$target"
    printf '%s\n' 'Running tmux server reloaded.'
else
    printf '%s\n' 'No running tmux server detected; the config will load for the next server.'
fi

printf '%s\n' 'Review DISPLAY and XAUTHORITY in ~/.tmux.conf if the destination machine differs.'
