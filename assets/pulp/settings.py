# Pulp settings for the local docker-compose multi-container stack.
# Mounted at /etc/pulp/settings.py in every pulp-minimal/pulp-web service.
# Reference: https://pulpproject.org/pulpcore/docs/admin/reference/settings/
#
# DEV ONLY — these values match the local docker-compose defaults
# (postgres/password, admin/password). Do not reuse them anywhere real.

SECRET_KEY = "albs-local-dev-pulp-secret-key-not-for-production"
CONTENT_ORIGIN = "http://pulp"

DATABASES = {
    "default": {
        "HOST": "postgres",
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "pulp",
        "USER": "postgres",
        "PASSWORD": "password",
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"sslmode": "prefer"},
    }
}

CACHE_ENABLED = True
# Renamed from "redis" to avoid a service-name clash with the ALBS redis in the
# same compose project.
REDIS_HOST = "pulp_redis"
REDIS_PORT = 6379
REDIS_PASSWORD = ""

ANSIBLE_API_HOSTNAME = "http://pulp_api:24817"
ANSIBLE_CONTENT_HOSTNAME = "http://pulp_content:24816/pulp/content"

# PulpExport / PulpImport (matches the ../volumes/pulp/exports bind mount).
ALLOWED_IMPORT_PATHS = ["/srv/exports", "/tmp"]
ALLOWED_EXPORT_PATHS = ["/srv/exports", "/tmp"]

# pulp_container token auth
TOKEN_SERVER = "http://pulp_api:24817/token/"
TOKEN_AUTH_DISABLED = False
TOKEN_SIGNATURE_ALGORITHM = "ES256"
PUBLIC_KEY_PATH = "/etc/pulp/keys/container_auth_public_key.pem"
PRIVATE_KEY_PATH = "/etc/pulp/keys/container_auth_private_key.pem"

ANALYTICS = False
STATIC_ROOT = "/var/lib/operator/static/"
