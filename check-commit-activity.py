#!/usr/bin/env python3
# Check inactive developers for retirement bugs
# Released under the terms of 2-clause BSD license

import argparse
import datetime
import json
import os.path
import sys
import urllib.request

import bugzilla


def fdate(ts):
    return datetime.datetime.utcfromtimestamp(ts).date().isoformat()


def main(prog_name, *argv):
    argp = argparse.ArgumentParser(prog=prog_name)
    argp.add_argument('--min-inactivity', type=int, default=120,
            help='Minimum activity to complain about (in days)')
    argp.add_argument('--include-open', action='store_true',
            help='Include developers for whom retirement bugs are open')

    args = argp.parse_args(argv)

    if not args.include_open:
        token_file = os.path.expanduser('~/.bugz_token')
        try:
            with open(token_file, 'r') as f:
                token = f.read().strip()
        except IOError:
            print('Put bugzilla API key into ~/.bugz_token')
            return 1

        bz = bugzilla.Bugzilla('https://bugs.gentoo.org',
                               api_key=token)

    with urllib.request.urlopen(
            'https://qa-reports.gentoo.org/output/active-devs.json') as ju:
        assert ju.getcode() == 200
        data = json.load(ju)

    ref_date = (datetime.datetime.utcnow()
                - datetime.timedelta(days=args.min_inactivity))

    candidates = {}
    for dev, ranges in data:
        # .max of first range is the newest commit
        newest_commit = datetime.datetime.utcfromtimestamp(ranges[0][2])
        if newest_commit < ref_date:
            candidates[dev] = ranges[0]

    if not args.include_open:
        q = bz.build_query(product='Gentoo Developers/Staff',
                           component='Retirement',
                           status=('UNCONFIRMED', 'CONFIRMED', 'IN_PROGRESS'))
        bugs = bz.query(q)

        for b in bugs:
            if not b.alias:
                print('{}\n  Bug not aliased to nickname'.format(b))
                continue
            assert len(b.alias) == 1
            candidates.pop(b.alias[0], None)

    dev_len = max(len(x) for x in candidates)
    for dev, rang in sorted(candidates.items(), key=lambda kv: kv[1][2]):
        print('{:{devlen}}: last commit {}, {:>3} commits since {}'.format(
            dev, fdate(rang[2]), rang[0], fdate(rang[1]), devlen=dev_len))

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv))
