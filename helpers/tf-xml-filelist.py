#!/usr/bin/env python3
import xml.etree.ElementTree as ET


def get_filelist(xmlstring):
    r = ET.fromstring(xmlstring)
    ns = {
        's3': 'http://doc.s3.amazonaws.com/2006-03-01',
    }
    filelist = []
    for cnt in r.findall('s3:Contents', ns):
        key = cnt.find('s3:Key', ns)
        fname = key.text
        if fname.endswith('/') or not (fname.startswith('linux') or fname.startswith('mac') or fname.startswith('windows')):
            continue

        size = cnt.find('s3:Size', ns).text
        filelist.append((fname, size))

    return filelist


if __name__ == "__main__":
    import fileinput
    xmlstring = '\n'.join([line for line in fileinput.input()])
    filelist = get_filelist(xmlstring)
    for fname, size in filelist:
        print("{}\t{}".format(fname, size))

# vim: ts=4 sw=4 sts=4 expandtab
