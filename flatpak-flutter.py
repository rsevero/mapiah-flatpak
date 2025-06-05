#!/usr/bin/env python3

__license__ = 'MIT'
import subprocess
import shutil
import argparse
import os
import sys
import yaml
import json
import urllib.parse
import urllib.request
import asyncio

from typing import Optional
from pathlib import Path
from flutter_sdk_generator.flutter_sdk_generator import generate_sdk
from flutter_app_fetcher.flutter_app_fetcher import fetch_flutter_app
from pubspec_generator.pubspec_generator import PUB_CACHE
from cargo_generator.cargo_generator import generate_sources as generate_cargo_sources
from pubspec_generator.pubspec_generator import generate_sources as generate_pubspec_sources

RUST_VERSION = '1.83.0'

__version__ = '0.6.0'
build_path = '.flatpak-builder/build'
sandbox_root = '/run/build'


class Dumper(yaml.Dumper):
    def increase_indent(self, flow=False, *args, **kwargs):
        return super().increase_indent(flow=flow, indentless=False)


def _get_manifest_from_git(manifest: str, from_git: str, from_git_branch: str):
    manifest_name = Path(manifest).name
    options = [
        'git',
        'clone',
        '--depth',
        '1',
        from_git,
        f'{build_path}/{manifest_name}',
    ] if from_git_branch is None else [
        'git',
        'clone',
        '--branch',
        from_git_branch,
        '--depth',
        '1',
        from_git,
        f'{build_path}/{manifest_name}',
    ]
    manifest_path = f'{build_path}/{manifest_name}/{manifest}'

    if os.path.isfile(manifest_path):
        return_code = 0
    else:
        return_code = subprocess.run(options, stdout=subprocess.PIPE, check=True).returncode

    if return_code == 0:
        shutil.copyfile(manifest_path, manifest_name)
        shutil.rmtree(f'{build_path}/{manifest_name}')


def _fetch_flutter_app(
    manifest_path: str,
    app_module: str,
    releases_path: str,
    app_pubspec: str,
    source: Optional[str]=None,
    rust_version: Optional[str]=None
):
    with open(manifest_path, 'r') as input_stream:
        suffix = (Path(manifest_path).suffix)

        if suffix == '.yml' or  suffix == '.yaml':
            manifest = yaml.full_load(input_stream)
        else:
            manifest = json.load(input_stream)

        releases_path += '/flutter'
        app_id, tag, build_id = fetch_flutter_app(manifest, app_module, build_path, releases_path, app_pubspec, rust_version)

        # Write converted manifest to file
        with open(f'{app_id}{suffix}', 'w') as output_stream:
            if suffix == '.json':
                json.dump(manifest, output_stream, indent=4, sort_keys=False)
            else:
                source = source if source is not None else manifest_path
                prepend = f'''# Generated from {source}, do not edit
# Visit the flatpak-flutter project at https://github.com/TheAppgineer/flatpak-flutter
'''
                output_stream.write(prepend)
                yaml.dump(data=manifest, stream=output_stream, indent=2, sort_keys=False, Dumper=Dumper)

        app = app_module if app_module is not None else app_id.split('.')[-1]

        return app, tag, build_id


def _create_pub_cache(build_path_app: str, pubspec_path = None):
    full_pubspec_path = build_path_app if pubspec_path is None else f'{build_path_app}/{pubspec_path}'
    pub_cache = f'{os.getcwd()}/{build_path_app}/.{PUB_CACHE}'
    flutter = 'flutter/bin/flutter'
    options = f'PUB_CACHE={pub_cache} {build_path_app}/{flutter} pub get -C {full_pubspec_path}'

    subprocess.run([options], stdout=subprocess.PIPE, shell=True, check=True)


def _generate_pubspec_sources(app: str, app_pubspec:str, extra_pubspecs: str, build_id: int):
    flutter_tools = 'flutter/packages/flutter_tools'
    pubspec_paths = [
        f'{build_path}/{app}/{app_pubspec}/pubspec.lock',
        f'{build_path}/{app}/{flutter_tools}/pubspec.lock',
    ]

    if extra_pubspecs:
        paths = extra_pubspecs.split(',')
        for path in paths:
            pubspec_paths.append(f'{build_path}/{app}/{path}/pubspec.lock')

    pubspec_sources = generate_pubspec_sources(pubspec_paths)
    pubspec_sources.append({
        'type': 'file',
        'path': 'package_config.json',
        'dest': f'{flutter_tools}/.dart_tool',
    })

    with open('pubspec-sources.json', 'w') as out:
        json.dump(pubspec_sources, out, indent=4, sort_keys=False)
        out.write('\n')

    abs_path = str(Path(f'{build_path}/{app}').absolute())
    package_config = ''

    with open(f'{build_path}/{app}/{flutter_tools}/.dart_tool/package_config.json', 'r') as input:
        for line in input.readlines():
            package_config += line.replace(f'{app}-{build_id}', app).replace(abs_path, f'{sandbox_root}/{app}')

    with open('package_config.json', 'w') as out:
        out.write(package_config)


def _generate_cargo_sources(app: str, cargo_locks: str, releases: str):
    if cargo_locks:
        cargo_paths = []
        paths = cargo_locks.split(',')

        for path in paths:
            cargo_paths.append(f'{build_path}/{app}/{path}/Cargo.lock')

        cargo_sources = asyncio.run(generate_cargo_sources(cargo_paths))

        with open('cargo-sources.json', 'w') as out:
            json.dump(cargo_sources, out, indent=4, sort_keys=False)
            out.write('\n')

        shutil.copyfile(f'{releases}/rust/{RUST_VERSION}/rustup.json', f'rustup-{RUST_VERSION}.json')


def _get_sdk_module(app: str, tag: str, releases: str):
    shutil.copyfile(f'{releases}/flutter/flutter-shared.sh.patch', 'flutter-shared.sh.patch')

    if os.path.isfile(f'{releases}/flutter/{tag}/flutter-sdk.json'):
        shutil.copyfile(f'{releases}/flutter/{tag}/flutter-sdk.json', f'flutter-sdk-{tag}.json')
    else:
        generated_sdk = generate_sdk(f'{build_path}/{app}/flutter')

        with open(f'flutter-sdk-{tag}.json', 'w') as out:
            json.dump(generated_sdk, out, indent=4, sort_keys=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('MANIFEST', help='Path to the manifest')
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s-{__version__}')
    parser.add_argument('--app-module', metavar='NAME', help='Name of the app module in the manifest')
    parser.add_argument('--app-pubspec', metavar='PATH', help='Path to the app pubspec')
    parser.add_argument('--extra-pubspecs', metavar='PATHS', help='Comma separated list of extra pubspec paths')
    parser.add_argument('--cargo-locks', metavar='PATHS', help='Comma separated list of Cargo.lock paths')
    parser.add_argument('--from-git', metavar='URL', required=False, help='Get input files from git repo')
    parser.add_argument('--from-git-branch', metavar='BRANCH', required=False, help='Branch to use in --from-git')
    parser.add_argument('--keep-build-dirs', action='store_true', help="Don't remove build directories after processing")

    args = parser.parse_args()
    manifest_path = args.MANIFEST
    raw_url = None

    if 'FLUTTER_SDK_RELEASES' in os.environ:
        releases_path = os.environ['FLUTTER_SDK_RELEASES']
    else:
        releases_path = f'{str(Path(sys.argv[0]).parent)}/releases'

    if args.from_git:
        url = urllib.parse.urlparse(args.from_git)
        manifest_path = Path(manifest_path).name

        if url.hostname == 'github.com' and args.from_git_branch is not None:
            path = str(url.path).split('.git')[0]
            raw_url = f'https://raw.githubusercontent.com{path}/{args.from_git_branch}/{args.MANIFEST}'
            urllib.request.urlretrieve(raw_url, manifest_path)
        else:
            _get_manifest_from_git(args.MANIFEST, args.from_git, args.from_git_branch)

    app_pubspec = '.' if args.app_pubspec is None else args.app_pubspec
    rust_version = None if args.cargo_locks is None else RUST_VERSION
    app, tag, build_id = _fetch_flutter_app(manifest_path, args.app_module, releases_path, app_pubspec, raw_url, rust_version)

    if tag is not None:
        _create_pub_cache(f'{build_path}/{app}', args.app_pubspec)
        _generate_pubspec_sources(app, app_pubspec, args.extra_pubspecs, build_id)
        _generate_cargo_sources(app, args.cargo_locks, releases_path)
        _get_sdk_module(app, tag, releases_path)

        if not args.keep_build_dirs:
            shutil.rmtree(f'{build_path}/{app}-{build_id}')
            os.remove(f'{build_path}/{app}')

if __name__ == '__main__':
    main()
