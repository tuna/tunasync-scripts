#!/usr/bin/env python3
from datetime import datetime
from pyquery import PyQuery as pq


def get_filelist(htmlstring):
    d = pq(htmlstring)
    for tr in d('table').find('tr'):
        tds = pq(tr).find('td')
        if len(tds) != 4:
            continue
        fname = tds[0].find('a').text
        mdate = tds[2].text
        md5 = tds[3].text
        ts = datetime.strptime(mdate, "%Y-%m-%d %H:%M:%S").strftime("%s")
        yield (fname, ts, md5)


if __name__ == "__main__":
    import argparse
    import fileinput

    parser = argparse.ArgumentParser()
    parser.add_argument("htmlfile", nargs='?', default="-")
    args = parser.parse_args()

    if args.htmlfile == "-":
        htmlstring = '\n'.join([line for line in fileinput.input()])
    else:
        with open(args.htmlfile) as f:
            htmlstring = f.read()

    for file_record in get_filelist(htmlstring):
        print("\t".join(file_record))


# vim: ts=4 sw=4 sts=4 expandtab
