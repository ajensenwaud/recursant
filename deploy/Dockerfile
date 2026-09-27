# First build deploy/Dockerfile.dev as recursant-v4-dev:local.
FROM recursant-v4-dev:local AS build
COPY CMakeLists.txt /work/CMakeLists.txt
COPY core /work/core
RUN cmake -S /work -B /build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --target recursant -j2

FROM ubuntu@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libcurl4t64 libmicrohttpd12t64 libjansson4 libpcre2-8-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/recursant /usr/local/bin/recursant
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/recursant"]
CMD ["serve", "/etc/recursant/config.json"]
