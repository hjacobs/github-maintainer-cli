#!/usr/bin/env python3

import click
import codecs
import os
import requests
import stups_cli.config
import yaml

from clickclick import print_table, Action

CONFIG_DIR = click.get_app_dir('github-maintainer-cli')

adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
session = requests.Session()
session.mount('http://', adapter)
session.mount('https://', adapter)


def get_my_repos(my_emails, token):
    headers = {'Authorization': 'Bearer {}'.format(token)}
    page = 1
    while True:
        response = session.get('https://api.github.com/user/repos', params={'per_page': 100, 'page': page},
                               headers=headers)
        response.raise_for_status()
        for gh_repo in response.json():
            contents_url = gh_repo['contents_url']
            r = session.get(contents_url.replace('{+path}', 'MAINTAINERS'), headers=headers)
            if r.status_code == 200:
                b64 = r.json()['content']
                maintainers = codecs.decode(b64.encode('utf-8'), 'base64').decode('utf-8')
                maintainers = list(filter(None, maintainers.split('\n')))
                for maintainer in maintainers:
                    name, _, email = maintainer.strip().partition('<')
                    email = email.strip().rstrip('>')
                    if email in my_emails:
                        repo = {}
                        for key in ['url', 'name', 'full_name', 'description', 'private', 'language',
                                    'stargazers_count', 'subscribers_count', 'forks_count', 'fork']:
                            repo[key] = gh_repo.get(key)
                        repo['maintainers'] = maintainers
                        yield repo

        page += 1
        if 'next' not in response.headers.get('Link'):
            break


@click.command()
def cli():
    config = stups_cli.config.load_config('github-maintainer-cli')
    emails = config.get('emails')
    token = config.get('github_access_token')

    if not emails:
        raise click.UsageError('No emails configured')

    if not token:
        raise click.UsageError('No GitHub access token configured')

    os.makedirs(CONFIG_DIR, exist_ok=True)

    path = os.path.join(CONFIG_DIR, 'repositories.yaml')

    try:
        with open(path) as fd:
            repositories = yaml.safe_load(fd)
    except:
        repositories = {}

    if not repositories:
        with Action('Scanning repositories..') as act:
            for repo in get_my_repos(emails, token):
                repositories[repo['url']] = repo
                act.progress()

        with open(path, 'w') as fd:
            yaml.safe_dump(repositories, fd)

    rows = []
    for url, repo in sorted(repositories.items()):
        rows.append(repo)

    print_table(['full_name', 'stargazers_count', 'subscribers_count', 'forks_count'], rows)


if __name__ == '__main__':
    cli()
