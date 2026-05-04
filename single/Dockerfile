ARG XRAY_IMAGE=ghcr.io/xtls/xray-core:26.4.17@sha256:1880a26aee27e82d779b9632a88d5256403e8b33d9abffa1c7920f2fffb73bc3
ARG SINGBOX_IMAGE=ghcr.io/sagernet/sing-box@sha256:9bed1fcb406bd971d1b48c7f824e5128d63543ca278cdcd6b5737c19941e404d

FROM ${XRAY_IMAGE} AS xray-core

FROM ${SINGBOX_IMAGE} AS singbox-core

FROM python:3.12-alpine

WORKDIR /app

COPY app.py /app/app.py
COPY relay_admin /app/relay_admin
COPY --from=xray-core /usr/local/bin/xray /opt/bundled-bin/xray
COPY --from=singbox-core /usr/local/bin/sing-box /opt/bundled-bin/sing-box
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /opt/bundled-bin/xray /opt/bundled-bin/sing-box /entrypoint.sh

EXPOSE 18080 11080

ENTRYPOINT ["/entrypoint.sh"]
