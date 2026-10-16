#!/usr/bin/env bash
# Provisioning/scheduling is separate; this script never creates a bucket or changes a DB.
set -euo pipefail
umask 077
: "${PGHOST:?}" "${PGPORT:?}" "${PGUSER:?}" "${PGDATABASE:?}"
: "${EWU_BACKUP_CERT:?public PEM certificate path}" "${EWU_BACKUP_BUCKET:?approved independent bucket}"
: "${EWU_BACKUP_DIR:?private working directory}"
# PGPASSWORD/.pgpass and AWS role credentials are supplied securely; never on argv or logs.
mkdir -p "$EWU_BACKUP_DIR"
exec 9>"$EWU_BACKUP_DIR/backup.lock"
flock -n 9 || exit 75
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_id=$(openssl rand -hex 8)
object_key="ewu/postgres/$stamp-$backup_id.dump.cms"
artifact="$EWU_BACKUP_DIR/$stamp-$backup_id.dump.cms"
# No plaintext backup or private recovery key is written to the producer.
pg_dump -Fc | openssl cms -encrypt -binary -aes-256-gcm -outform DER -out "$artifact" "$EWU_BACKUP_CERT"
checksum=$(openssl dgst -sha256 -binary "$artifact" | openssl base64 -A)
aws s3api put-object --bucket "$EWU_BACKUP_BUCKET" --key "$object_key" --body "$artifact" \
 --if-none-match '*' --server-side-encryption AES256 --checksum-algorithm SHA256 --checksum-sha256 "$checksum" > "$artifact.upload.json"
# Verify bytes retrieved from the independent destination, not just an upload exit code.
aws s3api get-object --bucket "$EWU_BACKUP_BUCKET" --key "$object_key" --checksum-mode ENABLED "$artifact.readback" > "$artifact.readback.json"
cmp --silent "$artifact" "$artifact.readback"
sha256sum "$artifact" > "$artifact.sha256"
printf '%s\n' 'ENCRYPTED_OFFSITE_UPLOAD_VERIFIED'
# Retain encrypted local artifacts. Retention/deletion requires a separate approved policy.
