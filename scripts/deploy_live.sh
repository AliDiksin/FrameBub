#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REMOTE_HOST=${BUB_DEPLOY_HOST:-100.110.34.55}
REMOTE_USER=${BUB_DEPLOY_USER:-alwaly}
REMOTE=${REMOTE_USER}@${REMOTE_HOST}
SSH_KEY=${BUB_DEPLOY_SSH_KEY:-$HOME/.ssh/id_ed25519_bub_fedora}
LIVE_DIR=${BUB_DEPLOY_DIR:-/var/lib/bub}
STAGE_DIR=${BUB_DEPLOY_STAGE_DIR:-$LIVE_DIR/.deploy-stage}
EXCLUDES=$ROOT/.deployignore
DRY_RUN=0
INCLUDE_WORKBOOKS=0
NO_RESTART=0

usage() {
    cat <<'EOF'
Usage: scripts/deploy_live.sh [--dry-run] [--include-workbooks] [--no-restart]

Stages and verifies the current Bub tree, synchronizes deployable changes to
the live Fedora service, and restarts Bub only when live files changed.

  --dry-run            Show local-to-stage changes without writing or restarting
  --include-workbooks  Include ODS files; excluded by default to protect cron data
  --no-restart         Apply files but leave the current process running
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --include-workbooks) INCLUDE_WORKBOOKS=1 ;;
        --no-restart) NO_RESTART=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ ! -f "$EXCLUDES" ]; then
    printf 'Missing deploy exclude file: %s\n' "$EXCLUDES" >&2
    exit 1
fi
if [ ! -r "$SSH_KEY" ]; then
    printf 'Missing SSH key: %s\n' "$SSH_KEY" >&2
    exit 1
fi

if [ -f /.flatpak-info ] && command -v flatpak-spawn >/dev/null 2>&1; then
    host_exec() { flatpak-spawn --host "$@"; }
else
    host_exec() { "$@"; }
fi

remote() {
    host_exec ssh \
        -o BatchMode=yes \
        -o ConnectTimeout=15 \
        -o IdentitiesOnly=yes \
        -i "$SSH_KEY" \
        "$REMOTE" "$@"
}

run_rsync() {
    host_exec rsync "$@"
}

printf 'Preflight %s:%s\n' "$REMOTE" "$LIVE_DIR"
remote "test \"\$(hostname)\" = fedora && test -d '$LIVE_DIR' && test -x '$LIVE_DIR/.venv/bin/python' && test \"\$(systemctl is-active bub.service)\" = active"
if remote "pgrep -f '[s]ync_sf6_google_sheet.py' >/dev/null"; then
    printf 'SF6 workbook sync is currently running; deployment aborted.\n' >&2
    exit 1
fi
remote "mkdir -p '$STAGE_DIR'"

set -- \
    -aH \
    --omit-dir-times \
    --delete-delay \
    --itemize-changes \
    --out-format=%i\ %n%L \
    --exclude-from="$EXCLUDES"
if [ "$INCLUDE_WORKBOOKS" -eq 0 ]; then
    set -- "$@" "--exclude=*.ods"
fi
if [ "$DRY_RUN" -eq 1 ]; then
    set -- "$@" --dry-run
fi

printf 'Comparing local files with deployment stage...\n'
stage_changes=$(run_rsync "$@" -e "ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $SSH_KEY" "$ROOT/" "$REMOTE:$STAGE_DIR/")
if [ -n "$stage_changes" ]; then
    printf '%s\n' "$stage_changes"
else
    printf 'Deployment stage already matches local deployable files.\n'
fi
if [ "$DRY_RUN" -eq 1 ]; then
    exit 0
fi

printf 'Verifying staged Python sources and application wiring...\n'
remote "'$LIVE_DIR/.venv/bin/python' -m compileall -q '$STAGE_DIR' && cd '$LIVE_DIR' && PYTHONPATH='$STAGE_DIR' '$LIVE_DIR/.venv/bin/python' -c 'import sys; sys.path.insert(0, \"$STAGE_DIR\"); import bot; assert bot.client and bot.tree and callable(bot.main)'"

workbook_exclude="--exclude=*.ods"
if [ "$INCLUDE_WORKBOOKS" -eq 1 ]; then
    workbook_exclude=""
fi
live_changes=$(remote "rsync -aHn --omit-dir-times --delete-delay --itemize-changes --out-format='%i %n%L' --exclude-from='$STAGE_DIR/.deployignore' $workbook_exclude '$STAGE_DIR/' '$LIVE_DIR/'")
if [ -z "$live_changes" ]; then
    printf 'Live deployment already matches the verified stage; restart skipped.\n'
    exit 0
fi
printf '%s\n' "$live_changes"

printf 'Applying verified files...\n'
remote "if ! cmp -s '$STAGE_DIR/requirements.txt' '$LIVE_DIR/requirements.txt'; then '$LIVE_DIR/.venv/bin/python' -m pip install -r '$STAGE_DIR/requirements.txt'; fi"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir=$LIVE_DIR/.deploy-backups/$timestamp
remote "mkdir -p '$backup_dir' && rsync -aH --omit-dir-times --delete-delay --backup --backup-dir='$backup_dir' --exclude-from='$STAGE_DIR/.deployignore' $workbook_exclude '$STAGE_DIR/' '$LIVE_DIR/'"

if [ "$NO_RESTART" -eq 1 ]; then
    printf 'Files deployed without restart. Backup: %s:%s\n' "$REMOTE" "$backup_dir"
    exit 0
fi

printf 'Restarting Bub through systemd Restart=always...\n'
remote 'old_pid=$(systemctl show -p MainPID --value bub.service); test "$old_pid" -gt 0; kill -TERM "$old_pid"; attempts=0; while [ "$attempts" -lt 45 ]; do sleep 1; new_pid=$(systemctl show -p MainPID --value bub.service); state=$(systemctl is-active bub.service || true); if [ "$state" = active ] && [ "$new_pid" -gt 0 ] && [ "$new_pid" != "$old_pid" ]; then printf "Bub restarted: old_pid=%s new_pid=%s\n" "$old_pid" "$new_pid"; exit 0; fi; attempts=$((attempts + 1)); done; systemctl status bub.service --no-pager; exit 1'
printf 'Deployment complete. Backup: %s:%s\n' "$REMOTE" "$backup_dir"
