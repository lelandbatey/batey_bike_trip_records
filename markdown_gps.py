import datetime
import argparse
import json
import csv
import sys
import io


class Charstream:
    def __init__(self, s: str):
        self.string = s
        self.idx = 0

    def getchar(self):
        i = self.idx
        self.idx += 1
        return self.string[i]

    def peak(self, n=1):
        i = self.idx
        return self.string[i:i + n]

    def skip(self, n=1):
        self.idx += n
        return


def parse_md_find_codeblocks(charstream):
    OTHER = 'OTHER'
    NEWLINE = 'NEWLINE'
    GRAVE_1 = 'GRAVE_1'
    GRAVE_2 = 'GRAVE_2'
    INSIDE_CODEBLOCK = 'INSIDE_CODEBLOCK'
    END_GRAVE_1 = 'END_GRAVE_1'
    END_GRAVE_2 = 'END_GRAVE_2'

    codeblocks = list()

    state = NEWLINE
    try:
        while True:
            if state == NEWLINE:
                c = charstream.getchar()
                if c == '`':
                    state = GRAVE_1
                    continue
            elif state == GRAVE_1:
                c = charstream.getchar()
                if c == '`':
                    state = GRAVE_2
                elif c == '\n':
                    state = NEWLINE
                else:
                    state = OTHER
                continue
            elif state == GRAVE_2:
                c = charstream.getchar()
                if c == '`':
                    state = INSIDE_CODEBLOCK
                elif c == '\n':
                    state = NEWLINE
                else:
                    state = OTHER
                continue
            elif state == INSIDE_CODEBLOCK:
                newblock = ''
                while True:
                    if charstream.peak(3) == '```':
                        charstream.skip(3)
                        codeblocks.append(newblock)
                        state = OTHER
                        break
                    c = charstream.getchar()
                    newblock += c
            elif state == OTHER:
                c = charstream.getchar()
                if c == '\n':
                    state = NEWLINE
                    continue
    except IndexError as e:
        # not an error, means we hit EOF
        return codeblocks


def parse_timeloc(row):
    nr = {k.lower().strip(): v for k, v in row.items()}
    timeloc = dict()
    possible_keys = {
        'lat': 'latitude',
        'latitude': 'latitude',
        'lon': 'longitude',
        'lng': 'longitude',
        'time': 'timestamp_utc',
        'timestamp_utc': 'timestamp_utc',
        'moment': 'timestamp_utc',
        'description': 'description'
    }
    for pk, pck in possible_keys.items():
        if pk in nr:
            timeloc[pck] = nr[pk]
    timeloc = parse_timestamp(timeloc)
    timeloc['latitude'] = float(timeloc['latitude'])
    timeloc['longitude'] = float(timeloc['longitude'])
    return timeloc


def parse_timestamp(timeloc):
    ts = timeloc['timestamp_utc']
    for fmt in ['%Y-%m-%d %H:%M %z']:
        try:
            dt = datetime.datetime.strptime(ts, fmt)
            # dt = dt.replace(tzinfo=datetime.timezone.utc)
            timeloc['timestamp_utc'] = dt.timestamp()
            return timeloc
        except:
            continue
    raise ValueError("couldn't parse timestamp")


def printrow_json(row):
    print(json.dumps(row, sort_keys=True))


def main():
    files = sys.argv[1:]
    codeblocks = list()
    for fn in files:
        with open(fn) as f:
            codeblocks += parse_md_find_codeblocks(Charstream(f.read()))
    timelocs = list()
    for cb in codeblocks:
        lines = [l for l in cb.split('\n') if l.strip()]
        try:
            rdr = csv.DictReader(lines)
            for row in rdr:
                # print(row)
                timeloc = parse_timeloc(row)
                timelocs.append(timeloc)
        except Exception as e:
            print(e)
            pass
    for timeloc in timelocs:
        printrow_json(timeloc)


if __name__ == '__main__': main()
