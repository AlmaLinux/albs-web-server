#!/usr/bin/env bash

gpg_key_blueprint=$( gpg --list-keys test@albs.local | head -n 2 | tail -1 )

# Generating GPG key if it doesn't exist
if [ -z "$gpg_key_blueprint" ]; then
    echo "No GPG key found, generating a new one..."

    echo "Key-Type: 1
    Key-Length: 2048
    Subkey-Type: 1
    Subkey-Length: 2048
    Name-Real: Test GPG key for ALBS sign node
    Name-Email: \"test@albs.local\"
    Expire-Date: 0
    Passphrase: 1234567890" > gpg_key_scenario

    gpg --batch --gen-key gpg_key_scenario
    gpg_key_blueprint=$( gpg --list-keys test@albs.local | head -n 2 | tail -1 )

fi

gpg_key_blueprint=${gpg_key_blueprint: -16}

# Setting according env variables
if [ ! -f "../albs-sign-file/.env" ]; then
    echo "Generating .env for albs-sign-file"
    echo "SF_PASS_DB_DEV_PASS=\"1234567890\"
SF_PASS_DB_DEV_MODE=True
SF_PGP_KEYS_ID=[\"$gpg_key_blueprint\"]
SF_JWT_SECRET_KEY=\"access-secret\"
SF_HOST_GNUPG=\"~/.gnupg\"
SF_ROOT_URL=\"/sign-file\"" > ../albs-sign-file/.env
fi

sed -i 's/^TEST_SIGN_KEY_ID=".*"/TEST_SIGN_KEY_ID="'"$gpg_key_blueprint"'"/' tests/test-vars.env
