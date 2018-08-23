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
WB_MAIL_RE = re.compile(r'^(first|second|third)-e?mail-sent: (\d{4}-\d{2}-\d{2})')

# in months
MAIL_TIMES = {
    'first': 4,
    'second': 1,
    'third': 1,
}


def main(prog_name, *argv):
    argp = argparse.ArgumentParser(prog=prog_name)
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
        if WB_INFRA_RE.match(b.whiteboard):
            continue

        m = WB_MAIL_RE.match(b.whiteboard)
        if m is None:
            print('{}\n  Unknown whiteboard: {}'.format(b, b.whiteboard))
            continue

        which = m.group(1)
        when = datetime.date.fromisoformat(m.group(2))

        mail_time = MAIL_TIMES[which]
        next_when = when
        while mail_time > 0:
            _, days_in_month = calendar.monthrange(
                    next_when.year, next_when.month)
            next_when += datetime.timedelta(days=days_in_month)
            mail_time -= 1

        if datetime.date.today() >= next_when:
            print('{}\n  Status: {}; pending since: {}'
                    .format(b, b.whiteboard, next_when.isoformat()))

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv))
