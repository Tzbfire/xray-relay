FROM ghcr.io/xtls/xray-core:26.4.17@sha256:1880a26aee27e82d779b9632a88d5256403e8b33d9abffa1c7920f2fffb73bc3 AS xray-core

FROM ghcr.io/sagernet/sing-box@sha256:9bed1fcb406bd971d1b48c7f824e5128d63543ca278cdcd6b5737c19941e404d AS singbox-core

FROM python:3.12-alpine

WORKDIR /app

COPY app.py /app/app.py
COPY --from=xray-core /usr/local/bin/xray /usr/local/bin/xray
COPY --from=singbox-core /usr/local/bin/sing-box /usr/local/bin/sing-box
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /usr/local/bin/xray /usr/local/bin/sing-box /entrypoint.sh

EXPOSE 18080 11080

ENTRYPOINT ["/entrypoint.sh"]
