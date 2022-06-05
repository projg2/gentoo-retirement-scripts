#!/usr/bin/env python
# vim:se fileencoding=utf8 :
# (c) 2017-2021 Michał Górny
# (c) 2018 Amy Liffey
# 2-clause BSD license

import argparse
from collections import defaultdict, namedtuple
import errno
import glob
import io
import json
from lxml.builder import E
import lxml.etree as etree
import os
import os.path
import sys
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--path', help='Path to your repo /home/user/gentoo/', required=True)
    parser.add_argument('-e', '--email', help='Email of person you want to retire user@gentoo.org', required=True)
    parser.add_argument('-r', '--repoman', help='Add if you want to run repoman', action='store_true')
    args = parser.parse_args()

    # Store packages which are maintained by the person
    pkg = set()
    grabs = set()

    for f in glob.glob(os.path.join(args.path, '*/*/metadata.xml')):
        # Store subpath, parse xml
        subpath = os.path.relpath(f, args.path)
        xml = etree.parse(f)
        r = xml.getroot()

        # Check if the retired person maintains the package
        maints = r.findall('maintainer')
        for m in maints:
            if m.findtext('email') == args.email:
                pkg.add('/'.join(subpath.split('/', 2)[:2]))
                break
        else:
            continue

        # Check if the package has any proxied maintainers left
        other_proxied_maint = False
        for pm in maints:
            if (pm.findtext('email') != args.email
                    and not pm.findtext('email').endswith('@gentoo.org')):
                other_proxied_maint = True
                break

        # Remove proxy-maint project if no proxied maintainers are left
        if not other_proxied_maint:
            for p in maints:
                if p.findtext('email') == 'proxy-maint@gentoo.org':
                    r.remove(p)
            maints = r.findall('maintainer')

        # the last maintainer standing? we need maintainer-needed now!
        if len(maints) == 1:
            c = etree.Comment(' maintainer-needed ')
            c.tail = m.tail
            r.replace(m, c)
            grabs.add('/'.join(subpath.split('/')[:2]))
        else:
            if m.getprevious() is not None:
                m.getprevious().tail = m.tail
            r.remove(m)

        # Write all the changes to the metadata.xml
        with open(f, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            xml.write(f, encoding='UTF-8', pretty_print=True)

    # Run pkgcheck on modified packages
    if args.repoman and pkg:
        subprocess.Popen(
            ['pkgcheck', 'scan', '-c', 'PackageMetadataXmlCheck'] +
            sorted(pkg), cwd=args.path).wait()

    if grabs:
        print('Packages up for grabs:')
        for g in sorted(grabs):
            print(g)
    elif pkg:
        print('No packages up for grabs')
    else:
        print('No packages reassigned')
    return 0


if __name__ == '__main__':
    exit(main())
