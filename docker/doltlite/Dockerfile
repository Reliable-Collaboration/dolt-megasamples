# The DoltLite worker and the container that stays up: the release's two .deb packages over Debian
# 13 (DoltLite links glibc 2.38; Debian 12's 2.36 refuses it) plus the sqlite3 shell, the baseline
# engine of the SQLite/DoltLite pair, built from sqlite.org's release tarball so the pair compares
# the newest SQLite with the newest DoltLite. Both versions come from versions.json:
# scripts/lite_image.py downloads what it names into build/doltlite/ (this Dockerfile's context),
# checks the SHA-256s, and passes the names in. The base image is named by digest.
FROM debian:13-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132 AS sqlite
RUN apt-get update && apt-get install -y --no-install-recommends gcc make libc6-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
ARG SQLITE_TARBALL
COPY ${SQLITE_TARBALL} /tmp/sqlite.tar.gz
RUN mkdir /tmp/sqlite && tar -xzf /tmp/sqlite.tar.gz -C /tmp/sqlite --strip-components=1 \
    && cd /tmp/sqlite && ./configure --prefix=/opt/sqlite && make -j"$(nproc)" && make install

FROM debian:13-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY --from=sqlite /opt/sqlite/bin/sqlite3 /usr/local/bin/sqlite3
COPY --from=sqlite /opt/sqlite/lib/ /usr/local/lib/
RUN ldconfig
ARG LITE_VERSION
COPY libdoltlite0_${LITE_VERSION}_amd64.deb doltlite_${LITE_VERSION}_amd64.deb /tmp/
RUN dpkg -i /tmp/libdoltlite0_${LITE_VERSION}_amd64.deb /tmp/doltlite_${LITE_VERSION}_amd64.deb && rm /tmp/*.deb
CMD ["sleep", "infinity"]
