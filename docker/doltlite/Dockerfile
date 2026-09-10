# The DoltLite worker and the container that stays up: the pinned .deb packages over Debian 13
# (DoltLite v0.50.9 links glibc 2.38; Debian 12's 2.36 refuses it) plus Debian's stock sqlite3
# shell, which is the baseline engine of the SQLite/DoltLite pair. scripts/lite_image.py downloads
# and checksums the packages into build/doltlite/, which is this Dockerfile's context.
FROM debian:13-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY libdoltlite0_0.50.9_amd64.deb doltlite_0.50.9_amd64.deb /tmp/
RUN dpkg -i /tmp/libdoltlite0_0.50.9_amd64.deb /tmp/doltlite_0.50.9_amd64.deb && rm /tmp/*.deb
CMD ["sleep", "infinity"]
