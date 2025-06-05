FROM rsevero847/flutter-build:20.04

USER root

RUN set -o xtrace \
    && cd /opt \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y flatpak flatpak-builder \
    && rm -rf /var/lib/apt/lists/*

USER builder

RUN flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo \
    && flatpak install -y org.freedesktop.Sdk/x86_64/24.08 \
    && flatpak install -y org.freedesktop.Platform/x86_64/24.08 \
    && flatpak install -y flathub org.freedesktop.appstream-glib
