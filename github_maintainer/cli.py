import click
import codecs
import datetime
import json
import os
import re
import requests
import stups_cli.config
import time
import yaml

from clickclick import print_table, Action, AliasedGroup, OutputFormat

CONFIG_DIR = click.get_app_dir('github-maintainer-cli')
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
session = requests.Session()
session.mount('http://', adapter)
session.mount('https://', adapter)

output_option = click.option('-o', '--output', type=click.Choice(['text', 'json', 'tsv']), default='text',
                             help='Use alternative output format')


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


def request(func, url, token, raise_for_status=True, **kwargs):
    kwargs['headers'] = {'Authorization': 'Bearer {}'.format(token)}
    response = func(url, **kwargs)
    if raise_for_status and response.status_code not in (200, 201):
        try:
            data = response.json()
            message = data['message']
        except:
            message = None
        if data:
            raise requests.HTTPError('GitHub returned status {} {}: {}'.format(
                                     response.status_code, response.reason, message))
        else:
            response.raise_for_status()
    return response


def get_my_issues(token):
    page = 1
    while True:
        response = request(session.get, 'https://api.github.com/issues', token,
                           params={'per_page': 100, 'page': page, 'filter': 'all'})
        for issue in response.json():
            yield issue
        page += 1
        if 'next' not in response.headers.get('Link', ''):
            break


def get_repos(token):
    page = 1
    while True:
        response = request(session.get, 'https://api.github.com/user/repos', token,
                           params={'per_page': 100, 'page': page})
        for gh_repo in response.json():
            contents_url = gh_repo['contents_url']
            r = request(session.get, contents_url.replace('{+path}', 'MAINTAINERS'), token, raise_for_status=False)
            if r.status_code == 200:
                b64 = r.json()['content']
                maintainers = codecs.decode(b64.encode('utf-8'), 'base64').decode('utf-8')
                maintainers = list(filter(None, maintainers.split('\n')))
            else:
                maintainers = []
            repo = {}
            for key in ['url', 'name', 'full_name', 'description', 'private', 'language',
                        'stargazers_count', 'subscribers_count', 'forks_count', 'fork']:
                repo[key] = gh_repo.get(key)
            repo['maintainers'] = maintainers
            yield repo

        page += 1
        if 'next' not in response.headers.get('Link'):
            break


def get_all_repositories():
    path = os.path.join(CONFIG_DIR, 'repositories.yaml')

    try:
        with open(path) as fd:
            repositories = yaml.safe_load(fd)
    except:
        repositories = {}
    return repositories


def get_repositories():
    config = stups_cli.config.load_config('github-maintainer-cli')

    my_emails = config.get('emails')
    my_repos = {}

    for url, repo in get_all_repositories().items():
        for maintainer in repo['maintainers']:
            name, _, email = maintainer.strip().partition('<')
            email = email.strip().rstrip('>')
            if email in my_emails:
                my_repos[url] = repo
    return my_repos


@click.group(cls=AliasedGroup, context_settings=CONTEXT_SETTINGS)
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


def get_git_email():
    with open(os.path.expanduser('~/.gitconfig')) as fd:
        for line in fd:
            key, sep, val = line.strip().partition('=')
            if key.strip() == 'email':
                return val.strip()


@cli.command()
@click.pass_obj
def configure(config):
    '''Configure GitHub access'''
    emails = config.get('emails', [])
    if not emails:
        try:
            emails = [get_git_email()]
        except:
            pass

    emails = click.prompt('Your email addresses (comma separated)', default=','.join(emails) or None)
    token = click.prompt('Your personal GitHub access token', hide_input=True,
                         default=config.get('github_access_token'))

    emails = list([mail.strip() for mail in emails.split(',')])
    config = {'emails': emails, 'github_access_token': token}

    repositories = {}
    with Action('Scanning repositories..') as act:
        for repo in get_repos(token):
            repositories[repo['url']] = repo
            act.progress()

    path = os.path.join(CONFIG_DIR, 'repositories.yaml')
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(path, 'w') as fd:
        yaml.safe_dump(repositories, fd)

    with Action('Storing configuration..'):
        stups_cli.config.store_config(config, 'github-maintainer-cli')


@cli.command()
@click.option('--show-issues', is_flag=True, help='Also show current number of open issues/PRs')
@output_option
@click.pass_obj
def repositories(config, show_issues, output):
    '''List repositories'''
    token = config.get('github_access_token')

    repositories = get_repositories()

    if show_issues:
        for issue in get_my_issues(token):
            repo = repositories.get(issue['repository']['url'])
            if repo:
                repo['open_issues'] = repo.get('open_issues', 0) + 1
                if issue.get('pull_request'):
                    repo['open_pull_requests'] = repo.get('open_pull_requests', 0) + 1

    rows = []
    for url, repo in sorted(repositories.items()):
        rows.append(repo)

    with OutputFormat(output):
        columns = ['full_name', 'stargazers_count', 'forks_count']
        if show_issues:
            columns += ['open_issues', 'open_pull_requests']
        print_table(columns, rows)


@cli.command()
@output_option
@click.pass_obj
def issues(config, output):
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
    with OutputFormat(output):
        print_table(['repository', 'number', 'title', 'labels', 'created_time', 'created_by'], rows)


@cli.command('pull-requests')
@output_option
@click.pass_obj
def pull_requests(config, output):
    '''List pull requests'''
    token = config.get('github_access_token')

    repositories = get_repositories()

    rows = []
    for issue in get_my_issues(token):
        pr = issue.get('pull_request')
        if pr:
            repo = repositories.get(issue['repository']['url'])
            if repo:
                r = request(session.get, pr['url'], token)
                pr = r.json()
                issue.update(**pr)
                issue['repository'] = repo['full_name']
                issue['created_time'] = parse_time(issue['created_at'])
                issue['created_by'] = issue['user']['login']
                issue['labels'] = ', '.join([l['name'] for l in issue['labels']])
                rows.append(issue)

    rows.sort(key=lambda x: (x['repository'], x['number']))
    with OutputFormat(output):
        print_table(['repository', 'number', 'title', 'labels', 'mergeable',
                     'mergeable_state', 'created_time', 'created_by'], rows)


@cli.command()
@click.argument('repo')
@click.argument('path')
@click.argument('pattern')
@click.argument('replacement')
@click.option('--base-branch', default='master', help='Base branch (default is "master")')
@click.option('--all-repositories', is_flag=True, help='Match all repositories, not only the ones I maintain')
@click.option('--title', help='Title of pull request')
@click.option('--body', help='Body of pull request')
@click.pass_obj
def patch(config, repo, path, pattern, replacement, base_branch, all_repositories, title, body):
    '''Replace a pattern in a single file in multiple repositories

    Example:

    github-maintainer patch 'zalando-stups/.*' Dockerfile 'stups/openjdk:8.*' stups/openjdk:8-24
    '''
    token = config.get('github_access_token')

    if all_repositories:
        repositories = get_all_repositories()
    else:
        repositories = get_repositories()

    repo_pattern = re.compile(repo)

    for key, val in repositories.items():
        if repo_pattern.search(key):
            # see https://gist.github.com/harlantwood/2935203
            with Action('Getting {}/{}..'.format(val['full_name'], path)) as act:
                response = request(session.get, val['url'] + '/contents/{}'.format(path), token, raise_for_status=False)
                if response.status_code == 200:
                    b64 = response.json()['content']
                    original_content = codecs.decode(b64.encode('utf-8'), 'base64').decode('utf-8')
                    content = re.sub(pattern, replacement, original_content)
                else:
                    original_content = content = None
                    act.ok('NOT FOUND')

            if content != original_content:
                safe_path = re.sub('[^a-z0-9-]', '', path.lower())
                branch_name = 'patch-{}-{}'.format(safe_path, time.strftime('%m-%d-%H-%M-%S'))
                title = title or 'Patch s/{}/{}/g'.format(pattern, replacement)
                with Action('Creating new branch {} and commit..'.format(branch_name)):
                    response = request(session.get, val['url'] + '/git/refs/heads/' + base_branch, token)
                    last_commit_sha = response.json()['object']['sha']

                    response = request(session.get, val['url'] + '/git/commits/' + last_commit_sha, token)
                    last_tree_sha = response.json()['tree']['sha']

                    response = request(session.post, val['url'] + '/git/refs', token,
                                       data=json.dumps({'ref': 'refs/heads/' + branch_name,
                                                        'sha': last_commit_sha}))
                    branch_sha = response.json()['object']['sha']

                    response = request(session.post, val['url'] + '/git/trees', token,
                                       data=json.dumps({'base_tree': last_tree_sha,
                                                        'tree': [{'type': 'blob',
                                                                  'path': path,
                                                                  'content': content,
                                                                  'mode': '100644'}]}))
                    data = response.json()
                    new_content_tree_sha = data['sha']

                    response = request(session.post, val['url'] + '/git/commits', token,
                                       data=json.dumps({'parents': [branch_sha],
                                                        'tree': new_content_tree_sha,
                                                        'message': title}))
                    new_commit_sha = response.json()['sha']

                    response = request(session.patch, val['url'] + '/git/refs/heads/' + branch_name, token,
                                       data=json.dumps({'sha': new_commit_sha}))

                with Action('Creating pull request..') as act:
                    body = body or 'Automatically created by github-maintainer-cli to patch {}'.format(path)
                    response = request(session.post, val['url'] + '/pulls', token,
                                       data=json.dumps({'title': title,
                                                        'head': branch_name,
                                                        'base': base_branch,
                                                        'body': body}))
                    act.ok(response.json()['_links']['html']['href'])


def main():
    cli()
