# Published backup-agent image (ghcr.io/<owner>/igab-backup): postgres client
# tools + age + the backup agent script baked in, so Unraid/CA installs don't
# need to mount anything from the repo. Compose dev/production keeps mounting
# scripts/db-backup.sh directly; this image exists for image-only deployments.
FROM postgres:18-alpine

RUN apk add --no-cache age

COPY db-backup.sh /db-backup.sh

ENTRYPOINT ["sh", "/db-backup.sh"]
