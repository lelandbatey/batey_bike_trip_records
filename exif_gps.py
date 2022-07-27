#!/usr/bin/env python3
'''
References:
    https://exiftool.org/TagNames/EXIF.html
    https://exiftool.org/TagNames/GPS.html
'''
import datetime
import argparse
import json
import csv
import sys

from PIL import Image, ExifTags
from PIL.JpegImagePlugin import JpegImageFile


def parse_gps(rawgpsdict):
    gpsdict = dict()
    for rk, rv in rawgpsdict.items():
        if rk in ExifTags.GPSTAGS:
            k = ExifTags.GPSTAGS[rk]
            gpsdict[k] = rv
    return gpsdict


def convert_gps_dms_to_degreedecimal(gpsdict):
    def dms_to_dd(degrees, minutes, seconds, dir_reference):
        direction = 1
        if dir_reference in ['S', 'W']:
            direction = -1
        return (float(degrees) + (float(minutes) / 60.0) + (float(seconds) / (60 * 60))) * direction

    lat = dms_to_dd(*gpsdict['GPSLatitude'], gpsdict['GPSLatitudeRef'])
    lng = dms_to_dd(*gpsdict['GPSLongitude'], gpsdict['GPSLongitudeRef'])

    return lat, lng


def extract_gps_timestamp_utc(gpsdict):
    # GPSDateStamp 2016:07:07
    # GPSTimeStamp (12.0, 10.0, 5.0)
    year, month, day = gpsdict['GPSDateStamp'].split(':')
    hour, minute, second = gpsdict['GPSTimeStamp']
    return datetime.datetime(
        year=int(year),
        month=int(month),
        day=int(day),
        hour=int(hour),
        minute=int(minute),
        second=int(second),
        tzinfo=datetime.timezone.utc,
    )


def printrow_json(row):
    print(json.dumps(row, sort_keys=True))


def printrow_csv(dictwriter: csv.DictWriter, row):
    dictwriter.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('imagefiles', type=argparse.FileType('rb'), nargs='*')
    parser.add_argument(
        '--format',
        '-f',
        choices=['JSON', 'CSV'],
        default='JSON',
        help='Format of GPS data written to stdout'
    )
    args = parser.parse_args()

    printrow = None
    if args.format == 'JSON':
        printrow = printrow_json
    elif args.format == 'CSV':
        dictwriter = csv.DictWriter(
            sys.stdout,
            fieldnames=[
                'latitude', 'longitude', 'timestamp_utc', 'dilution_of_precision', 'filename',
                'error'
            ]
        )
        dictwriter.writeheader()
        printrow = lambda row: printrow_csv(dictwriter, row)

    GPSKEY = [k for k, v in ExifTags.TAGS.items() if v == 'GPSInfo'][0]

    for imgf in args.imagefiles:
        row = {
            'latitude': '',
            'longitude': '',
            'timestamp_utc': '',
            'dilution_of_precision': '',
            'filename': imgf.name,
            'error': 'GPS data is not present'
        }
        image: JpegImageFile = Image.open(imgf)
        # In order to get _all_ the EXIF data, we have to call the protected
        # `_get_merged_dict()` method, otherwise GPS EXIF isn't included
        rawexif = image.getexif()._get_merged_dict()
        if GPSKEY in rawexif:
            gpsdict = parse_gps(rawexif[GPSKEY])
            # print(f"{gpsdict=}")
            # print({ExifTags.TAGS[k]: v for k, v in rawexif.items()})
            lat, lng = convert_gps_dms_to_degreedecimal(gpsdict)
            timestamp = extract_gps_timestamp_utc(gpsdict)
            dopstr = '23000/1000'
            if 'GPSDOP' in gpsdict:
                dop = gpsdict['GPSDOP']
                dopstr = f"{dop.numerator}/{dop.denominator}"
            row = {
                'latitude': round(lat, 6),
                'longitude': round(lng, 6),
                'timestamp_utc': int(timestamp.timestamp()),
                'dilution_of_precision': dopstr,
                'filename': imgf.name,
                'error': ''
            }
        printrow(row)


if __name__ == '__main__':
    main()

    # with open('./images/2016-07-07 05.10.07.jpg', 'rb') as imgf:
    #     image: JpegImageFile = Image.open(imgf)
    #     # In order to get _all_ the EXIF data, we have to call the protected
    #     # `_get_merged_dict()` method, otherwise GPS EXIF isn't included
    #     rawexif = image.getexif()._get_merged_dict()
    #     for rk, rv in rawexif.items():
    #         k = None
    #         if rk in ExifTags.TAGS:
    #             k = ExifTags.TAGS[rk]
    #         if not k == 'GPSInfo': continue
    #         gpsdict = parse_gps(rv)
    #         lat, lng = convert_gps_dms_to_degreedecimal(gpsdict)
    #         timestamp = extract_gps_timestamp_utc(gpsdict)
    #         print(
    #             f"Latitude: {lat:.6f} Longitude: {lng:.6f} Timestamp: {timestamp} {timestamp.timestamp()}"
    #         )
