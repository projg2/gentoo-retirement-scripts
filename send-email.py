#!/usr/bin/env python3
# Send undertaker mail (and update bugs)
# Released under the terms of 2-clause BSD license

import argparse
import base64
import collections
import datetime
import email
import email.charset
import email.utils
import os
import pwd
import subprocess
import sys

import bugzilla
import jinja2


def grab_ldap(host, dev, infos):
    """
    Grab required information from LDAP via SSH to @host.
    @infos is a list of LDAP keys to fetch.

    Returns a dict of requested information.  Note that some keys
    may be missing if LDAP does not have the requested data.
    """

    ret = collections.defaultdict(list)
    with subprocess.Popen(
            ['ssh', host, 'ldapsearch', '-Z', '-LLL',
                'uid={}'.format(dev), *infos],
            stdout=subprocess.PIPE) as ssh:
        sout, serr = ssh.communicate()
        assert ssh.wait() == 0

        for l in sout.decode().splitlines():
            if not l:
                continue
            k, v = l.split(': ', 1)
            # base64-encoded
            if k.endswith(':'):
                k = k[:-1]
                v = base64.b64decode(v, validate=True).decode('utf8')
            if k == 'dn':
                assert v == 'uid={},ou=devs,dc=gentoo,dc=org'.format(dev)
            else:
                ret[k].append(v)

    return ret


def sign_mail(mail):
    """
    Add OpenPGP signature to @mail.
    """

    body = mail.get_payload().encode('utf8')

    with subprocess.Popen(['gpg', '--clearsign'],
                          stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as gpg:
        sout, serr = gpg.communicate(body)
        assert gpg.wait() == 0

    mail.set_payload(sout.decode('utf8'))


def send_mail(host, mail, signature):
    """
    Send mail @mail via sendmail-over-SSH to @host.

    @signature specifies full name for envelope sender.
    """

    with subprocess.Popen(
            ['ssh', host, 'sendmail', '-i', '-t'],
            stdin=subprocess.PIPE) as ssh:
        ssh.communicate(mail.as_string().encode('utf8'))
        assert ssh.wait() == 0


def main(prog_name, *argv):
    argp = argparse.ArgumentParser(prog=prog_name)
    argp.add_argument('--dev-bug',
            type=int,
            help='Dev bug number (needed if not in LDAP')
    argp.add_argument('--ldap-ssh-host',
            default='dev.gentoo.org',
            help='Host to SSH for LDAP information')
    argp.add_argument('--sendmail-ssh-host',
            default='dev.gentoo.org',
            help='Host to SSH for sendmail')
    argp.add_argument('--signature',
            default=pwd.getpwuid(os.getuid()).pw_gecos.split(',')[0],
            help='Your signature')
    argp.add_argument('template',
            type=argparse.FileType('r'),
            help='Mail template file')
    argp.add_argument('dev',
            help='Developer username')
    argp.add_argument('lastcommit',
            nargs='?',
            type=lambda x: datetime.datetime.strptime(x, '%Y-%m-%d').date(),
            help='Last commit (yyyy-mm-dd)')

    args = argp.parse_args(argv)

    token_file = os.path.expanduser('~/.bugz_token')
    try:
        with open(token_file, 'r') as f:
            token = f.read().strip()
    except IOError:
        print('Put bugzilla API key into ~/.bugz_token')
        return 1

    print('* Getting developer info from LDAP ...')
    ldap = grab_ldap(args.ldap_ssh_host, args.dev,
            ('cn', 'givenName', 'email', 'gentooStatus', 'gentooDevBug'))
    assert ldap['gentooStatus'] == ['active']
    assert len(ldap['cn']) == 1
    assert len(ldap['givenName']) == 1

    devbug = None
    if 'gentooDevBug' in ldap:
        assert len(ldap['gentooDevBug']) == 1
        devbug = int(ldap['gentooDevBug'][0])
    if args.dev_bug is not None:
        devbug = args.dev_bug
    if devbug is None:
        print("Please set gentooDevBug in LDAP or pass --dev-bug!")
        return 1

    tmpl = jinja2.Template(args.template.read())
    mail = email.message_from_string(tmpl.render(
            devname=args.dev,
            firstname=ldap['givenName'][0],
            fullname=ldap['cn'][0],
            today=datetime.date.today(),
            lastcommit=args.lastcommit,
            signature=args.signature))

    print('* Checking the dev bug ...')
    bz = bugzilla.Bugzilla('https://bugs.gentoo.org',
                           api_key=token)
    bug = bz.getbug(devbug)
    assert bug.product == 'Gentoo Developers/Staff'
    upd_args = {}
    if bug.component != 'Retirement':
        upd_args['component'] = 'Retirement'
    if bug.status == 'RESOLVED':
        upd_args['status'] = 'CONFIRMED'
    upd_args['comment'] = mail['Bug-Comment']
    upd_args['reset_assigned_to'] = True
    upd_args['summary'] = mail['Bug-Title']
    upd_args['whiteboard'] = mail['Bug-Whiteboard']
    del mail['Bug-Comment']
    del mail['Bug-Title']
    del mail['Whiteboard']
    upd = bz.build_update(**upd_args)

    addr_to = '{}@gentoo.org'.format(args.dev)
    retire_alias = 'retirement@gentoo.org'
    addr_cc = ldap['email']
    if addr_to in addr_cc:
        addr_cc.remove(addr_to)
    addr_cc.append(retire_alias)

    mail['Content-Type'] = 'text/plain; charset=UTF-8'
    mail['To'] = email.utils.formataddr((ldap['cn'][0], addr_to))
    mail['CC'] = ', '.join(addr_cc)
    mail['Reply-To'] = retire_alias

    print('* Signing the mail ...')
    sign_mail(mail)
    print('* Sending the mail ...')
    send_mail(args.sendmail_ssh_host, mail, args.signature)
    print('* Updating Bugzilla ...')
    bz.update_bugs([devbug], upd)

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv))
