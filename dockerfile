FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl wget gnupg lsb-release locales \
      tini tmate tmux procps net-tools openssh-client vim less && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /opt/scripts

COPY scripts/start_tmate.sh /opt/scripts/start_tmate.sh
RUN chmod +x /opt/scripts/start_tmate.sh

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/scripts/start_tmate.sh"]
