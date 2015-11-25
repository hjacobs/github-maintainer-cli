import click
import codecs
import datetime
import os
import requests
import stups_cli.config
import time
import yaml

from clickclick import print_table, Action, AliasedGroup

CONFIG_DIR = click.get_app_dir('github-maintainer-cli')

adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
session = requests.Session()
session.mount('http://', adapter)
session.mount('https://', adapter)


def parse_time(s: str) -> float:
    '''
    >>> parse_time('2015-04-14T19:09:01Z') > 0
    True
    '''
    try:
        utc = datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')
        ts = time.time()
        utc_offset = datetime.datetime.fromtimestamp(ts) - datetime.datetime.utcfromtimestamp(ts)
        local = utc + utc_offset
        return local.timestamp()
    except:
        return None


def get_my_issues(token):
    headers = {'Authorization': 'Bearer {}'.format(token)}
    page = 1
    while True:
        response = session.get('https://api.github.com/issues', params={'per_page': 100, 'page': page, 'filter': 'all'},
                               headers=headers)
        response.raise_for_status()
        for issue in response.json():
            yield issue
        page += 1
        if 'next' not in response.headers.get('Link', ''):
            break


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


def get_repositories():
    path = os.path.join(CONFIG_DIR, 'repositories.yaml')

    try:
        with open(path) as fd:
            repositories = yaml.safe_load(fd)
    except:
        repositories = {}
    return repositories


@click.group(cls=AliasedGroup)
@click.pass_context
def cli(ctx):
    config = stups_cli.config.load_config('github-maintainer-cli')

    emails = config.get('emails')
    token = config.get('github_access_token')

    if not 'configure'.startswith(ctx.invoked_subcommand or 'x'):
        if not emails:
            raise click.UsageError('No emails configured. Please run "configure".')

        if not token:
            raise click.UsageError('No GitHub access token configured. Please run "configure".')

    ctx.obj = config


@cli.command()
@click.pass_obj
def configure(config):
    '''Configure GitHub access'''
    emails = click.prompt('Your email addresses', default=','.join(config.get('emails')))
    token = click.prompt('Your personal GitHub access token', hide_input=True,
                         default=config.get('github_access_token'))

    emails = emails.split(',')
    config = {'emails': emails, 'github_access_token': token}

    repositories = {}
    with Action('Scanning repositories..') as act:
        for repo in get_my_repos(emails, token):
            repositories[repo['url']] = repo
            act.progress()

    path = os.path.join(CONFIG_DIR, 'repositories.yaml')
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(path, 'w') as fd:
        yaml.safe_dump(repositories, fd)

    with Action('Storing configuration..'):
        stups_cli.config.store_config(config, 'github-maintainer-cli')


@cli.command()
@click.pass_obj
def repositories(config):
    '''List repositories'''
    token = config.get('github_access_token')

    repositories = get_repositories()

    for issue in get_my_issues(token):
        repo = repositories.get(issue['repository']['url'])
        if repo:
            repo['open_issues'] = repo.get('open_issues', 0) + 1
            if issue.get('pull_request'):
                repo['open_pull_requests'] = repo.get('open_pull_requests', 0) + 1

    rows = []
    for url, repo in sorted(repositories.items()):
        rows.append(repo)

    print_table(['full_name', 'stargazers_count', 'forks_count', 'open_issues', 'open_pull_requests'], rows)


@cli.command()
@click.pass_obj
def issues(config):
    '''List open issues'''
    token = config.get('github_access_token')

    repositories = get_repositories()

    rows = []
    for issue in get_my_issues(token):
        if not issue.get('pull_request'):
            repo = repositories.get(issue['repository']['url'])
            if repo:
                issue['repository'] = repo['full_name']
                issue['created_time'] = parse_time(issue['created_at'])
                issue['created_by'] = issue['user']['login']
                issue['labels'] = ', '.join([l['name'] for l in issue['labels']])
                rows.append(issue)

    rows.sort(key=lambda x: (x['repository'], x['number']))
    print_table(['repository', 'number', 'title', 'labels', 'created_time', 'created_by'], rows)


@cli.command('pull-requests')
@click.pass_obj
def pull_requests(config):
    '''List pull requests'''
    token = config.get('github_access_token')

    repositories = get_repositories()

    rows = []
    for issue in get_my_issues(token):
        pr = issue.get('pull_request')
        if pr:
            repo = repositories.get(issue['repository']['url'])
            if repo:
                r = session.get(pr['url'], headers={'Authorization': 'Bearer {}'.format(token)})
                pr = r.json()
                issue.update(**pr)
                issue['repository'] = repo['full_name']
                issue['created_time'] = parse_time(issue['created_at'])
                issue['created_by'] = issue['user']['login']
                issue['labels'] = ', '.join([l['name'] for l in issue['labels']])
                rows.append(issue)

    rows.sort(key=lambda x: (x['repository'], x['number']))
    print_table(['repository', 'number', 'title', 'labels', 'mergeable',
                 'mergeable_state', 'created_time', 'created_by'], rows)


def main():
    cli()
