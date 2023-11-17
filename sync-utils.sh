#!/usr/bin/env bash
# Copyright (c) 2023 Hagb (Junyu Guo)
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Usage:
# 
#   Use in bash script by introducing this file via `.` or `source` as the
#   first command, and run interruptible jobs by `run-sync-job` command,
#   such as `run-sync-job rsync src dst`.
#
#   The script will:
#   - obtain or create the lock depending on the filename of the script, and
#     release it after exit. Don't need to manage them manually.
#   - forward the signals to the job and keep waiting for the job's exit after
#     receiving signals in _FORWARD_SINGALS.
#   - block signals in _FORWARD_SINGALS when other commands are running, so
#     they will not be interrupted by signals sent to the script. Notice that
#     they should not run for too long, for tunasync uses KILL signal to kill
#     the process, if the script is still alive 2 seconds after tunasync used
#     TERM signal to kill.
#   - the pending signals would be sent to the job when the next run-sync-job
#     in this script is run.
#
#   Function:
#   - run-sync-job: see the above explanation.
#
#   Variables:
#   - pendding_signals: pendding signals, splitted by space. When the next
#     run-sync-job is run, these signals will be sent to the job. Its values
#     are from _FORWARD_SINGALS.
#   - handled_signals: handled signals, i.e. signals having been sent to
#     jobs. Similar to pendding_signals.
#
#   All functions and variables whose names are started with "_" are private --
#   users should not call, read or modify them.


_EXEC="$0"
_EXECNAME="$(basename -- "$0")"
_ARGS=("$@")
_FORWARD_SINGALS="SIGHUP SIGINT SIGQUIT SIGTERM SIGTSTP SIGCONT"
_LOCKFILE=/run/tunasync-scripts/"$_EXECNAME".lock
_lockfd=
_unlock_cmds=
_running_jobspec=
_init=0

pendding_signals=
handled_signals=

_flock_cmd() { echo flock -$1 $_lockfd; }

_flock() { eval "$(_flock_cmd $1)"; }

_is_file_of_fd_deleted() {
    # https://unix.stackexchange.com/questions/592720/check-if-a-filedescriptor-refers-to-a-deleted-file-in-bash
    readlink /proc/$$/fd/$1 | grep -q ' (deleted)$'
}

_save-signals() {
#     # like `lambda s: list(set(s))` in python
#     local IFS=' ' s s2 out="" flag=0
#     for s in ${_FORWARD_SINGALS}; do
#         flag=0
#         for s2 in "$@"; do
#             if [ "$s" = "$s2" ]; then
#                 flag=1
#             fi
#         done
#         if [ $flag = 1 ]; then
#             out="$out $s"
#         fi
#     done
#     echo $out
    # keep it simple...
    echo "$@"
}

_sig-handler() {
    local IFS signals
    # These operations are all written in one command to avoid being interrupted by signals
    IFS=. \
    signals=( $(
        IFS=' '
        if kill -$1 $_running_jobspec 2>/dev/null; then
            _signal-handle-msg $1 >&2 || true
            handled_signals="$(_save-signals $handled_signals $1)"
        else
            _signal-block-msg $1 >&2 || true
            pendding_signals="$(_save-signals $pendding_signals $1)"
        fi
        echo "$pendding_signals"."$handled_signals"
    ) ) \
    pendding_signals="${signals[0]}" \
    handled_signals="${signals[1]}"
}

_exit-handler() {
    _flock u
    # If no other process is obtaining the lock, just delete it.
    _flock xn &&
        ! _is_file_of_fd_deleted $_lockfd &&
        rm -f "$_LOCKFILE" ||
        true
    # It is possible that someone tried to obtain the lock after we run
    # `_flock xn` and before we remove the lock file, so unlock it again.
    _flock u
}

# get "&2 3" from "[2]+ 3 xxxxx" printed by jobs -l
_parse-jobs() {
    local output="$(sed -E 's/^\[([0-9]+)\][^ ]* +([0-9]+)($|[^0-9].*)/%\1 \2/')" &&
    if ! { echo "$output" | grep -qvE '^(%[0-9]+ [0-9]+|$)'; }; then
        echo "$output"
        return 0
    fi
    return 1
}

_get-jobspec() {
    local parsed jobline jobinfo IFS="
"
    parsed="$(jobs -l 2>/dev/null | _parse-jobs)" &&
    for jobline in ${parsed}; do
        IFS=" "
        jobinfo=( ${jobline} )
        if [ "$1" = "${jobinfo[1]}" ]; then
            echo "${jobinfo[0]}"
            return 0
        fi
    done
    return 1
}

_try-lock() {
    if _flock xn; ret=$?; [ $ret = 1 ]; then
        echo "Waiting for the lock... (locked by pid $(cat <&$_lockfd))" >&2 || true
        if run-sync-job $(_flock_cmd x); ret=$?; [ $ret != 0 ]; then
            if [ $ret -gt 127 ]; then
                echo "Killed by SIG$( kill -L $((ret-128)) ) when obtaining the lock" >&2 || true
                exit $ret
            fi
        else
            echo "Get the lock successful." >&2 || true
        fi
    fi
    if [ $ret != 0 ]; then
        echo "Failed to obtain the lock, exit status code $ret" >&2 || true
    fi
    return $ret
}

# emulate sigblock
_unset-running-jobspec() {
    _running_jobspec=
}

_set-running-jobspec() {
    local IFS signals
    # These operations are all written in one command to avoid being interrupted by signals
    _running_jobspec="$1" \
    IFS=. \
    signals=( $(
        IFS=' '
        old_pendding_signals="$pendding_signals"
        pendding_signals=
        _signal-handle-msg() { true; }
        _signal-block-msg() { true; }
        for s in $old_pendding_signals; do
            _sig-handler $s
        done
        echo "$pendding_signals"."$handled_signals"
    ) ) \
    pendding_signals="${signals[0]}" \
    handled_signals="${signals[1]}"
}

_initialize-sync-script() {
#     local m_flag=$([[ $- =~ m ]] && echo - || echo +)
    local IFS=" 
"
    set -m

    _signal-handle-msg() { true; }
    _signal-block-msg() { true; }
    _run-msg() { true; }

    # initialize signals trap
    local s
    trap "" SIGTTIN SIGTTOU
    for s in $_FORWARD_SINGALS ; do
        trap "_sig-handler $s" $s
    done

    _init=1

    # avoid passing SIGINT, SIGQUIT or SIGTSTP directly to subprocesses
    if [ -z "$_BACKGROUND" ]; then
        _signal-handle-msg() { printf "%s[$$]: receive %s\n" "$_EXECNAME" "$1"; }
        _signal-block-msg() { _signal-handle-msg "$@"; }
        _BACKGROUND=1 run-sync-job "$_EXEC" "${_ARGS[@]}"
        exit
    fi

    # obtain lock
    mkdir -p "$(dirname "$_LOCKFILE")"
    if ! exec {_lockfd}<>"$_LOCKFILE"; then
        echo "Failed to create lock file $_LOCKFILE!" >&2 || true
        exit 1
    fi
    ## To unlock after execute exec, unlock on subprocess instead of EXIT trap
    ## https://stackoverflow.com/a/73175707
    (tail --pid $$ -f /dev/null >/dev/null; _exit-handler) &
    _try-lock || exit $?
    ## We should ensure that the lock file we lock is $_LOCKFILE at this time.
    ## It might be deleted when being obtained. See `_exit-handler`.
    while _is_file_of_fd_deleted $_lockfd; do
        _flock u
        eval "exec $_lockfd>&-"
        eval "exec $_lockfd<>\"\$_LOCKFILE\""
        _try-lock || exit $?
    done
    echo $$ >"$_LOCKFILE"

    _signal-handle-msg() { printf "%s[$$]: receive %s (sent to the job)\n" "$_EXECNAME" "$1"; }
    _signal-block-msg() { printf "%s[$$]: receive %s (blocked until the next run-sync-job)\n" "$_EXECNAME" "$1"; }
    _run-msg() { printf "%s[$$]: run %s\n" "$_EXECNAME" "${*@Q}"; }

#     set ${m_flag}m
}

run-sync-job() {
#     local m_flag=$([[ $- =~ m ]] && echo - || echo +)
    if [ 1 != "$_init" ]; then
        echo "Error: initialize-sync-script function should be run first!" >&2 || true
#         set ${m_flag}m
        return 1
    fi
    set -m
    _run-msg "$@" >&2 || true
    exec "$@" &
    # new process with the same pid after the old one exits is possible, so we
    # use jobspec instead of pid to kill or check the subprocess.
    local pid=$! jobspec
    if ! jobspec=$(_get-jobspec $pid); then
        # Unexpected!
        echo Warning: cannot find the jobspec of $pid. >&2 || true
        jobspec=$pid
    fi
    _set-running-jobspec $jobspec
    # trap can interrupt wait, so check the job after running wait
    while kill -0 $jobspec 2>/dev/null; do
        wait $pid 2>/dev/null || true
        jobs -sl 2>/dev/null | _parse-jobs | grep -Eq "^${jobspec} | ${jobspec}\$" && kill -SIGSTOP $$
    done
    _unset-running-jobspec
#     set ${m_flag}m
    wait $pid
}

_initialize-sync-script
