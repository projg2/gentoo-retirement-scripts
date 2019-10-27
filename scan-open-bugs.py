#!/usr/bin/env python3
# Scan retirement bugs
# Released under the terms of 2-clause BSD license

import argparse
import calendar
import datetime
import os.path
import re
import sys

import bugzilla


WB_INFRA_RE = re.compile(r'^infra-(retire|done): ')
WB_MAIL_RE = re.compile(r'^(first|second|third|fourth)-e?mail-sent: (\d{4}-\d{2}-\d{2})')
WB_RETIRE_RE = re.compile(r'^retirement-requested: (\d{4}-\d{2}-\d{2})')

# in months
MAIL_TIMES = {
    'first': 6,
    'second': 3,
    'third': 2,
    'fourth': 1,
}


def get_next_when(b, args):
    if WB_INFRA_RE.match(b.whiteboard):
        return None

    m = WB_MAIL_RE.match(b.whiteboard)
    if m is not None:
        which = m.group(1)
        when = datetime.date.fromisoformat(m.group(2))

        if which == 'first' and args.commit_access:
            return when + datetime.timedelta(days=14)
        if which == 'first' and args.reassignment:
            return when + datetime.timedelta(days=28)

        mail_time = MAIL_TIMES[which]
        yr = when.year
        mo = when.month
        add_days = 0
        while mail_time > 0:
            _, days_in_month = calendar.monthrange(yr, mo)
            add_days += days_in_month
            mo += 1
            if mo > 12:
                yr += 1
                mo = 1
            mail_time -= 1
        next_when = when + datetime.timedelta(days=add_days)
        return next_when

    m = WB_RETIRE_RE.match(b.whiteboard)
    if m is not None:
        when = datetime.date.fromisoformat(m.group(1))
        next_when = when + datetime.timedelta(days=14)
        return next_when

    print('{}\n  Unknown whiteboard: {}'.format(b, b.whiteboard))
    return None


def main(prog_name, *argv):
    argp = argparse.ArgumentParser(prog=prog_name)
    argp.add_argument('--all', action='store_true',
            help='List all open bugs, even if they are not pending yet')
    types = argp.add_mutually_exclusive_group()
    types.add_argument('--commit-access', action='store_true',
            help='Include commit access suspension pending after first mail')
    types.add_argument('--reassignment', action='store_true',
            help='Include package reassignment pending after first mail')
    args = argp.parse_args(argv)

    token_file = os.path.expanduser('~/.bugz_token')
    try:
        with open(token_file, 'r') as f:
            token = f.read().strip()
    except IOError:
        print('Put bugzilla API key into ~/.bugz_token')
        return 1

    bz = bugzilla.Bugzilla('https://bugs.gentoo.org',
                           api_key=token)

    q = bz.build_query(product='Gentoo Developers/Staff',
                       component='Retirement',
                       status=('UNCONFIRMED', 'CONFIRMED', 'IN_PROGRESS'))
    bugs = bz.query(q)

    for b in bugs:
        next_when = get_next_when(b, args)
        if next_when is None:
            continue

        if datetime.date.today() >= next_when:
            print('{}\n  Status: {}; pending since: {}\n  {}'
                    .format(b, b.whiteboard, next_when.isoformat(),
                            b.weburl))
        elif args.all:
            print('{}\n  Status: {}; deadline: {}\n  {}'
                    .format(b, b.whiteboard, next_when.isoformat(),
                            b.weburl))

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv))
