#!/bin/bash
# Stage progress is not a byte-transfer percentage. Password prompts stay outside.
progress_percent=0
progress_ui=0
step() {
    stage=$1
    local number=1
    case "$stage" in
        'Official repositories and dependency preflight') number=1;;
        'Install dependencies') number=2;;
        'Portal configuration') number=3;;
        'System accounts and application') number=4;;
        'First administrator') number=5;;
        'Install selected addon files') number=6;;
        'HTTPS proxy and SELinux') number=7;;
        'Firewall and services') number=8;;
        'Verify HTTP and HTTPS') number=9;;
    esac
    progress_percent=$(( (number-1)*100/9 ))
    echo "==> [$number/9] $stage"
}
run() {
    local pid result=0 started=$SECONDS tick=0 line activity
    activity="${1##*/} ${2:-}"
    "$@" >>"$log" 2>&1 &
    pid=$!
    sleep .1
    if kill -0 "$pid" 2>/dev/null; then
    if [[ ${progress_ui:-0} == 1 ]]; then
        {
            while kill -0 "$pid" 2>/dev/null; do
                line=$(tail -n 1 "$log" | tr -cd '\11\12\15\40-\176' | tail -c 180)
                printf 'XXX\n%s\n%s\n\nRunning: %s\nElapsed: %ss\n%s\n\nStage progress; downloads and builds may take several minutes.\nXXX\n' "$progress_percent" "$stage" "$activity" "$((SECONDS-started))" "$line"
                sleep 1
            done
        } | whiptail --title 'Installing ServiceReady' --backtitle 'Rocky Linux 10 setup' --gauge "$stage" 16 78 "$progress_percent" || true
    else
        while kill -0 "$pid" 2>/dev/null; do
            if [[ -t 1 ]]; then
                printf '\r[%s%%] %s — %ss elapsed ' "$progress_percent" "$stage" "$((SECONDS-started))"
            elif (( tick%10 == 0 )); then
                echo "[$progress_percent%] $stage: $activity ($((SECONDS-started))s elapsed)"
            fi
            tick=$((tick+1));sleep 1
        done
        [[ ! -t 1 ]] || printf '\n'
    fi
    fi
    wait "$pid" || result=$?
    if (( result != 0 )); then
        echo "Failed: $stage ($activity), exit $result" >&2
        tail -n 35 "$log" >&2
        return "$result"
    fi
}
progress_complete() {
    progress_percent=100
    echo '[100%] All installation stages and health checks passed.'
}
