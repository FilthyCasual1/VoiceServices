#!/bin/sh
# Sourceable repository preflight; only add community for the installed release.
ensure_community() {
    repository_file=$1
    alpine_version=$2
    branch=$(printf '%s\n' "$alpine_version" | awk -F. '{print "v" $1 "." $2}')
    if awk -v branch="$branch" '$0 !~ /^[[:space:]]*#/ && $1 ~ /\/(main|community)\/?$/ && !index($1,"/" branch "/") {bad=1} END {exit !bad}' "$repository_file"; then
        echo "Active main/community repositories mix Alpine releases. Keep only $branch repositories before installing." >&2
        return 1
    fi
    main_url=$(awk -v branch="$branch" '$0 !~ /^[[:space:]]*#/ && $1 ~ /\/main\/?$/ && index($1,"/" branch "/main") {print $1;exit}' "$repository_file")
    [ -n "$main_url" ] || { echo "No active $branch/main repository. Configure repositories for Alpine $alpine_version; edge/mixed-release fallback is not allowed." >&2; return 1; }
    community_url=$(printf '%s\n' "$main_url" | sed 's,/main/*$,/community,')
    if awk -v url="$community_url" '$0 !~ /^[[:space:]]*#/ && $1==url {found=1} END {exit !found}' "$repository_file"; then return 0; fi
    cp -p "$repository_file" "$repository_file.serviceready-backup"
    printf '\n%s\n' "$community_url" >> "$repository_file"
    echo "Enabled matching repository: $community_url"
}
