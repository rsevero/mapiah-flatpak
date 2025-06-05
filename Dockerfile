FROM python:3.8-slim

WORKDIR /usr/src/app

RUN apt-get update && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends git unzip

RUN pip install --no-cache-dir pyyaml toml

COPY flatpak-flutter.py ./flatpak-flutter
COPY cargo_generator/cargo_generator.py ./cargo_generator/
COPY flutter_app_fetcher/flutter_app_fetcher.py ./flutter_app_fetcher/
COPY flutter_sdk_generator/flutter_sdk_generator.py ./flutter_sdk_generator/
COPY pubspec_generator/pubspec_generator.py ./pubspec_generator/
COPY releases ./releases/

WORKDIR /usr/src/flatpak
ENV HOME=/usr/src/flatpak/.flatpak-builder
ENTRYPOINT [ "../app/flatpak-flutter" ]
