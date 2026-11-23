#!/bin/sh
# Run by the official Nginx entrypoint before starting Nginx.
mediroute_duckdns_prepare() {
    [ -n "${MEDIROUTE_DUCKDNS_LABEL:-}" ] || return 0
    printf '%s\n' "$MEDIROUTE_DUCKDNS_LABEL" | grep -Eq '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$' || return 1
    printf '%s\n' "${MEDIROUTE_DUCKDNS_TOKEN:-}" | grep -Eq '^[A-Za-z0-9_-]{16,128}$' || return 1
    [ -n "${MEDIROUTE_DUCKDNS_CERT:-}" ] && [ -n "${MEDIROUTE_DUCKDNS_KEY:-}" ] || return 1

    # Use /run and keep the certificate files readable only by the Nginx master user.
    mkdir -p -m 700 /run/mediroute-tls || return 1
    (umask 077
     printf '%s\n' "$MEDIROUTE_DUCKDNS_CERT" > /run/mediroute-tls/fullchain.pem &&
     printf '%s\n' "$MEDIROUTE_DUCKDNS_KEY" > /run/mediroute-tls/privkey.pem
    ) || return 1
    sed "s/__DUCKDNS_HOST__/${MEDIROUTE_DUCKDNS_LABEL}.duckdns.org/g" \
        /etc/nginx/mediroute-duckdns.conf > /etc/nginx/conf.d/duckdns.conf || return 1
    nginx -t || return 1

    # DuckDNS detects the calling IPv4. The task must egress through its own public IP.
    # Pass the token on stdin to curl, so it never appears in arguments or diagnostics.
    result=$(
        printf 'url = "https://www.duckdns.org/update?domains=%s&token=%s&ip="\n' \
            "$MEDIROUTE_DUCKDNS_LABEL" "$MEDIROUTE_DUCKDNS_TOKEN" |
            curl --config - --ipv4 --proto '=https' --fail --silent \
                --connect-timeout 5 --max-time 12 --retry 2 --retry-max-time 25
    ) || return 1
    [ "$result" = OK ] || return 1
    printf 'DuckDNS accepted the IPv4 update for %s.duckdns.org\n' "$MEDIROUTE_DUCKDNS_LABEL"
}

if ! mediroute_duckdns_prepare; then
    echo 'DuckDNS startup failed. Check the certificate, configuration and DNS update.' >&2
    exit 1
fi
