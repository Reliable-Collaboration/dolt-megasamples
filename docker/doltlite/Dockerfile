# The DoltLite worker and the container that stays up: the release's two .deb packages over Debian
# 13 (DoltLite links glibc 2.38; Debian 12's 2.36 refuses it) plus Debian's stock sqlite3 shell,
# which is the baseline engine of the SQLite/DoltLite pair. The version comes from versions.json:
# scripts/lite_image.py downloads the packages it names into build/doltlite/ (this Dockerfile's
# context), checks their SHA-256, and passes the version in as LITE_VERSION. One version per result
# set (2026-09-12): moving it (`python3 scripts/versions.py --latest doltlite`) means every DoltLite
# unit is measured again. The base image is named by digest so a rebuild gives the same sqlite3.
FROM debian:13-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132
ARG LITE_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY libdoltlite0_${LITE_VERSION}_amd64.deb doltlite_${LITE_VERSION}_amd64.deb /tmp/
RUN dpkg -i /tmp/libdoltlite0_${LITE_VERSION}_amd64.deb /tmp/doltlite_${LITE_VERSION}_amd64.deb && rm /tmp/*.deb
CMD ["sleep", "infinity"]
