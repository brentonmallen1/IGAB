#!/bin/sh
# IGAB backup agent — runs in the db-backup container (postgres:16-alpine).
#
# Every poll it: touches a heartbeat, re-reads backup settings from the
# app_settings table (so UI changes apply without a restart), executes any
# command the API dropped in /backups/.agent/command.json (backup-now or
# restore), and runs a scheduled backup when one is due. The API half of
# this protocol lives in backend/src/igab/services/backup_service.py.
#
# Environment (defaults, and the fallback when DB settings are unreadable
# or out of bounds):
#   PGHOST / PGUSER / PGPASSWORD / PGDATABASE — connection (set by compose)
#   BACKUP_INTERVAL_HOURS  hours between scheduled backups (default 24)
#   BACKUP_KEEP_DAYS       prune files older than this many days (default 30)
#   BACKUP_KEEP_MIN        never prune below this many newest files per kind,
#                          regardless of age — a silent month of failed
#                          backups must not delete the last good ones (7)
#   BACKUP_AGE_RECIPIENT   optional age public key (age1...); when set, dumps
#                          and attachment archives are encrypted to it (*.age)
#   BACKUP_RUN_ONCE        set to 1 to run a single poll cycle and exit (testing)
set -u

BK=/backups
AG=$BK/.agent
POLL_S=10

ENV_INTERVAL="${BACKUP_INTERVAL_HOURS:-24}"
ENV_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
ENV_KEEP_MIN="${BACKUP_KEEP_MIN:-7}"
ENV_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"

log() { echo "[db-backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

mkdir -p "$AG"

# $1=value $2=lo $3=hi $4=fallback — echoes value if a sane integer, else fallback
clamp_int() {
    case "$1" in
        '' | *[!0-9]*) echo "$4"; return ;;
    esac
    if [ "$1" -lt "$2" ] || [ "$1" -gt "$3" ]; then echo "$4"; else echo "$1"; fi
}

# Settings precedence mirrors the app's SettingsService: DB row > env > default.
# Bounds mirror the API's validation; anything unreadable falls back to env.
read_settings() {
    INTERVAL=$(clamp_int "$ENV_INTERVAL" 1 168 24)
    KEEP_DAYS=$(clamp_int "$ENV_KEEP_DAYS" 1 365 30)
    KEEP_MIN=$(clamp_int "$ENV_KEEP_MIN" 1 100 7)
    RECIPIENT="$ENV_RECIPIENT"
    rows=$(psql -X -tA -F '|' -c \
        "SELECT key, coalesce(value, '') FROM app_settings WHERE key LIKE 'backup_%'" \
        2>/dev/null) || return 0
    while IFS='|' read -r k v; do
        case "$k" in
            backup_interval_hours) INTERVAL=$(clamp_int "$v" 1 168 "$INTERVAL") ;;
            backup_keep_days) KEEP_DAYS=$(clamp_int "$v" 1 365 "$KEEP_DAYS") ;;
            backup_keep_min) KEEP_MIN=$(clamp_int "$v" 1 100 "$KEEP_MIN") ;;
            backup_age_recipient)
                case "$v" in
                    age1*) RECIPIENT="$v" ;;
                    '') RECIPIENT="" ;;
                esac
                ;;
        esac
    done <<EOF
$rows
EOF
}

# Encryption is requested — never fall back to writing plaintext.
ensure_age() {
    [ -z "$RECIPIENT" ] && return 0
    command -v age >/dev/null 2>&1 && return 0
    if apk add --no-cache age >/dev/null 2>&1; then
        log "installed age for encrypted backups"
        return 0
    fi
    log "ERROR: encryption requested but 'age' could not be installed (no network?)"
    return 1
}

# Delete files matching pattern $1 that are older than KEEP_DAYS, but always
# keep the KEEP_MIN newest ones no matter how old they are.
prune() {
    ls -1t $BK/$1 2>/dev/null | tail -n +"$((KEEP_MIN + 1))" | while read -r f; do
        if [ -n "$(find "$f" -type f -mtime +"$KEEP_DAYS" 2>/dev/null)" ]; then
            rm -f "$f" && log "pruned $f"
        fi
    done
}

# Encrypt $1 in place to $1.age when a recipient is configured; echoes the
# final path. Temp-file callers rename afterwards, so partial output never
# lands under a real backup name.
encrypt_maybe() {
    if [ -n "$RECIPIENT" ]; then
        age -r "$RECIPIENT" -o "$1.age" "$1" || return 1
        rm -f "$1"
        echo "$1.age"
    else
        echo "$1"
    fi
}

# $1 = file prefix: "igab" for scheduled/manual, "igab-prerestore" for the
# safety dump taken before a restore
dump_db() {
    ts=$(date +%Y%m%d-%H%M%S)
    tmp="$BK/.tmp-$1-$ts.dump"
    pg_dump -Fc -f "$tmp" || { rm -f "$tmp"; return 1; }
    final=$(encrypt_maybe "$tmp") || { rm -f "$tmp" "$tmp.age"; return 1; }
    out="$BK/$(basename "$final" | sed 's/^\.tmp-//')"
    mv "$final" "$out"
    log "wrote $out"
}

backup_attachments() {
    [ -d /attachments ] || return 0
    [ -n "$(find /attachments -type f 2>/dev/null | head -n 1)" ] || return 0
    manifest=$( (cd /attachments && find . -type f -exec md5sum {} + 2>/dev/null) | sort | md5sum | cut -d' ' -f1 )
    state=$AG/attachments-manifest
    if [ -f "$state" ] && [ "$(cat "$state")" = "$manifest" ]; then
        return 0
    fi
    ts=$(date +%Y%m%d-%H%M%S)
    tmp="$BK/.tmp-igab-attachments-$ts.tar.gz"
    tar -C /attachments -czf "$tmp" . || { rm -f "$tmp"; return 1; }
    final=$(encrypt_maybe "$tmp") || { rm -f "$tmp" "$tmp.age"; return 1; }
    out="$BK/$(basename "$final" | sed 's/^\.tmp-//')"
    mv "$final" "$out"
    echo "$manifest" > "$state"
    log "wrote $out"
}

backup_cycle() {
    ok=0
    if ! ensure_age; then
        ok=1
    else
        if dump_db igab; then
            prune "igab-????????-??????.dump*"
        else
            log "ERROR: database dump failed — skipping prune so old backups survive"
            ok=1
        fi
        if backup_attachments; then
            prune "igab-attachments-*"
        else
            log "ERROR: attachments archive failed"
            ok=1
        fi
    fi
    date +%s > "$AG/last-backup"
    if [ "$ok" -eq 0 ]; then rm -f "$AG/retry"; else touch "$AG/retry"; fi
    return $ok
}

backup_due() {
    last=$(cat "$AG/last-backup" 2>/dev/null || echo 0)
    case "$last" in '' | *[!0-9]*) last=0 ;; esac
    gap=$(( $(date +%s) - last ))
    [ "$gap" -ge $((INTERVAL * 3600)) ] && return 0
    # A failed cycle retries after 15 minutes instead of waiting a full interval
    [ -f "$AG/retry" ] && [ "$gap" -ge 900 ] && return 0
    return 1
}

# $1 id, $2 action, $3 state, $4 detail, $5 started_at, $6 finished_at
write_status() {
    d=$(printf '%s' "$4" | tr -d '"\\' | tr '\n' ' ')
    printf '{"id":"%s","action":"%s","state":"%s","detail":"%s","started_at":"%s","finished_at":"%s"}\n' \
        "$1" "$2" "$3" "$d" "$5" "$6" > "$AG/.status.tmp"
    mv "$AG/.status.tmp" "$AG/status.json"
}

# $1 file, $2 key — extracts a JSON string value (API-written JSON only;
# values are uuids/filenames, never contain quotes or escapes)
json_str() {
    sed -n 's/.*"'"$2"'": *"\([^"]*\)".*/\1/p' "$1"
}

do_restore() {
    id=$1; file=$2; pre=$3; started=$4
    case "$file" in
        igab-*.dump) ;;
        *)
            write_status "$id" restore error "invalid or encrypted dump: $file" "$started" "$(now_iso)"
            return
            ;;
    esac
    if [ ! -f "$BK/$file" ]; then
        write_status "$id" restore error "file not found: $file" "$started" "$(now_iso)"
        return
    fi
    if [ "$pre" = "true" ]; then
        write_status "$id" restore running "creating pre-restore backup" "$started" ""
        if ! ensure_age || ! dump_db igab-prerestore; then
            write_status "$id" restore error "pre-restore backup failed; database untouched" "$started" "$(now_iso)"
            return
        fi
        prune "igab-prerestore-*"
    fi
    write_status "$id" restore running "disconnecting sessions" "$started" ""
    psql -X -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$PGDATABASE' AND pid <> pg_backend_pid()" \
        >/dev/null 2>&1
    write_status "$id" restore running "restoring database" "$started" ""
    if pg_restore --clean --if-exists --no-owner -d "$PGDATABASE" "$BK/$file" \
        > "$AG/restore-log" 2>&1; then
        log "restored $file"
        write_status "$id" restore done "restore complete" "$started" "$(now_iso)"
    else
        err=$(tail -n 2 "$AG/restore-log" | tr '\n' ' ')
        log "ERROR: restore of $file failed: $err"
        write_status "$id" restore error "pg_restore failed: $err" "$started" "$(now_iso)"
    fi
}

handle_command() {
    [ -f "$AG/command.json" ] || return 0
    mv "$AG/command.json" "$AG/command.run" 2>/dev/null || return 0
    id=$(json_str "$AG/command.run" id)
    action=$(json_str "$AG/command.run" action)
    file=$(json_str "$AG/command.run" file)
    pre=false
    grep -q '"pre_backup": *true' "$AG/command.run" && pre=true
    rm -f "$AG/command.run"
    started=$(now_iso)
    log "command: ${action:-unknown} ${file:-}"
    case "$action" in
        backup)
            write_status "$id" backup running "backing up" "$started" ""
            if backup_cycle; then
                write_status "$id" backup done "backup complete" "$started" "$(now_iso)"
            else
                write_status "$id" backup error "backup failed — see container logs" "$started" "$(now_iso)"
            fi
            ;;
        restore)
            do_restore "$id" "$file" "$pre" "$started"
            ;;
        *)
            write_status "${id:-unknown}" "${action:-unknown}" error "unknown command" "$started" "$(now_iso)"
            ;;
    esac
}

# Heartbeat runs in its own subshell so long dumps/restores don't make the
# agent look dead; it dies with the container (this script is PID 1).
( while true; do touch "$AG/heartbeat"; sleep 5; done ) &

log "agent started (poll ${POLL_S}s)"
while true; do
    find "$BK" -name ".tmp-*" -mmin +180 -delete 2>/dev/null
    read_settings
    handle_command
    if backup_due; then
        log "scheduled backup starting (interval ${INTERVAL}h, keep ${KEEP_DAYS}d/min ${KEEP_MIN})"
        backup_cycle || true
    fi
    [ "${BACKUP_RUN_ONCE:-0}" = "1" ] && exit 0
    sleep "$POLL_S"
done
