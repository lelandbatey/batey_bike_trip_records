#!/usr/bin/env python3
'''
create_maps.py makes pretty maps of GPS routes. Reads JSON-lines data on STDIN,
data formatted like so:

    {"latitude": 48.724511, "longitude": -119.446908, "timestamp_utc": 1467914535}
    {"latitude": 48.724283, "longitude": -119.4473, "timestamp_utc": 1467914547}

It then uses the Google maps API to find the probable road-based routes between
those coordinates (if those coordinates are further than .5 kilometers apart)
and the routes implied by the coordinates on a map.
'''
import googlemaps
import staticmap

import binascii
import datetime
import json
import math
import sys

from typing import List, Any, Dict, Tuple

# Pirated google maps API key (from an example code sample published by Google)
GMAPS_APIKEY = "AIz" + "aSyA3gqF4a2G0bcRG7J" + "gzAwo40iVStrSv2OM"

Coord = Tuple[float, float]


class TimeLocation:
    def __init__(self, lat=None, lng=None, moment=None):
        '''TimeLocation is both a time and place.'''
        # lat/lng are latitude longitude expressed in Decimal Degrees (DD)
        self.lat = lat
        self.lng = lng
        # moment is epoch timestamp in seconds
        self.moment: int = moment

    @staticmethod
    def fromrow(d):
        lat = d['latitude']
        lng = d['longitude']
        moment = d['timestamp_utc']
        return TimeLocation(lat, lng, moment)

    def latlngpoint(self):
        return [self.lat, self.lng]

    def dt(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.moment)


def color_hash(obj):
    # Leland colors (picked via Munsell color picker, found here: https://colorizer.org/)
    leland_colors_hex = [
        # Very bright colors
        '#FF00A6',  # Magenta
        '#FF0000',  # Red
        '#FFDD00',  # Yellow
        '#00FF00',  # Green
        '#00CFE0',  # Cyan
        '#FF9300',  # Orange
        # Darker colors
        '#004500',  # Dark green
        '#002492',  # Dark blue
        '#8b0000',  # Dark red
    ]
    return leland_colors_hex[binascii.crc32(str(obj).encode('utf-8')) % len(leland_colors_hex)]


# Below taken from here:
#     http://www.johndcook.com/blog/python_longitude_latitude/
def distance_on_unit_sphere(lat1, long1, lat2, long2):
    """Calculates the distance between two lat/long points. Returns distance in
    meters."""
    lat1, long1 = float(lat1), float(long1)
    lat2, long2 = float(lat2), float(long2)
    # Convert latitude and longitude to
    # spherical coordinates in radians.
    degrees_to_radians = math.pi / 180.0

    # phi = 90 - latitude
    phi1 = (90.0 - lat1) * degrees_to_radians
    phi2 = (90.0 - lat2) * degrees_to_radians

    # theta = longitude
    theta1 = long1 * degrees_to_radians
    theta2 = long2 * degrees_to_radians

    # Compute spherical distance from spherical coordinates.
    # For two locations in spherical coordinates
    # (1, theta, phi) and (1, theta, phi)
    # cosine( arc length ) =
    #    sin phi sin phi' cos(theta-theta') + cos phi cos phi'
    # distance = rho * arc length
    cos = (
        math.sin(phi1) * math.sin(phi2) * math.cos(theta1 - theta2) +
        math.cos(phi1) * math.cos(phi2)
    )
    cos = min(1, max(cos, -1))
    try:
        arc = math.acos(cos)
    except Exception as e:
        raise e
    return arc * 6378100


def decode_polyline(point_str) -> List[Coord]:
    '''Decodes a polyline that has been encoded using Google's algorithm
    http://code.google.com/apis/maps/documentation/polylinealgorithm.html
    https://gist.github.com/signed0/2031157

    This is a generic method that returns a list of (latitude, longitude)
    tuples.

    :param point_str: Encoded polyline string.
    :type point_str: string
    :returns: List of 2-tuples where each tuple is (latitude, longitude)
    :rtype: list
    '''
    # sone coordinate offset is represented by 4 to 5 binary chunks
    coord_chunks = [[]]
    for char in point_str:
        # convert each character to decimal from ascii
        value = ord(char) - 63
        # values that have a chunk following have an extra 1 on the left
        split_after = not (value & 0x20)
        value &= 0x1F

        coord_chunks[-1].append(value)
        if split_after:
            coord_chunks.append([])

    del coord_chunks[-1]
    coords = []

    for coord_chunk in coord_chunks:
        coord = 0
        for i, chunk in enumerate(coord_chunk):
            coord |= chunk << (i * 5)
        #there is a 1 on the right if the coord is negative
        if coord & 0x1:
            coord = ~coord  #invert
        coord >>= 1
        coord /= 100000.0
        coords.append(coord)
    # convert the 1 dimensional list to a 2 dimensional list and offsets to
    # actual values
    points: List[Coord] = []
    prev_x = 0
    prev_y = 0
    for i in range(0, len(coords) - 1, 2):
        if coords[i] == 0 and coords[i + 1] == 0:
            continue
        prev_x += coords[i + 1]
        prev_y += coords[i]
        # a round to 6 digits ensures that the floats are the same as when
        # they were encoded
        points.append((round(prev_y, 6), round(prev_x, 6)))
    return points


def flatten_routes_points(directionsresponse) -> List[Coord]:
    '''Accepts a `directionsresponse`, which is the response from calling the
    Google Maps `directions()` API. Returns a list of tuples, where each tuple
    is a lat-lng pair. '''
    flatpoints: List[Coord] = list()
    for route in directionsresponse:
        directionslegs = route['legs']
        for leg in directionslegs:
            directionssteps = leg['steps']
            for step in directionssteps:
                flatpoints += decode_polyline(step['polyline']['points'])
    return flatpoints


def bin_by_day(tlocs: List[TimeLocation]) -> Dict[str, List[TimeLocation]]:
    days = {}
    for tl in tlocs:
        ts = datetime.datetime.fromtimestamp(tl.moment)
        ts_str = ts.strftime("%Y_%m_%d")
        if not ts_str in days:
            days[ts_str] = list()
        days[ts_str].append(tl)
    return days


def draw_tlocs(
    m: staticmap.StaticMap,
    tlocs: List[TimeLocation],
    orig_tlocs: List[TimeLocation],
    linecolor='red',
    markercolor='green',
):
    def tlocs_to_lines(_tlocs: List[TimeLocation]):
        _lpairs = list()
        for idx in range(len(_tlocs) - 1):
            cur = _tlocs[idx].latlngpoint()
            nxt = _tlocs[idx + 1].latlngpoint()
            coordpair = [
                # I don't know why, but this komoot/staticmap library uses longitude-first coordinates :(
                [cur[1], cur[0]],
                [nxt[1], nxt[0]],
            ]
            _lpairs.append(coordpair)
        return _lpairs

    linepairs = list()
    linepairs = tlocs_to_lines(tlocs)
    # We use normal line formatting because the drawing function will flip the format
    orig_points = [tloc.latlngpoint() for tloc in orig_tlocs]

    def draw_lines(color, thickness):
        for pair in linepairs:
            coords = pair
            line = staticmap.Line(coords, color, thickness)
            m.add_line(line)

    draw_lines('white', 8)
    draw_lines(linecolor, 6)

    def draw_rawpoints(color, thickness):
        for point in orig_points:
            pnt = [point[1], point[0]]
            marker = staticmap.CircleMarker(pnt, color, thickness)
            m.add_marker(marker)

    draw_rawpoints('white', 9)
    draw_rawpoints(markercolor, 7)


def clamp_end_before_midnight(
    start_t: datetime.datetime, end_t: datetime.datetime
) -> Tuple[datetime.datetime, datetime.datetime]:
    '''
    If the time difference between start and end would span multiple days, we
    don't want to smoothly interpolate between then since that would imply
    continuous travel, even through the middle of the night, which doesn't
    match up with what we'd intuit. Instead, we clamp the end time to be 1
    second before midnight on the day of the start, and we assume that there's
    just missing data between then and the start of the later day.
    '''
    if start_t.day != end_t.day:
        end_t = datetime.datetime(
            year=start_t.year,
            day=start_t.day,
            month=start_t.month,
            hour=23,
            minute=59,
            second=59,
        )
    return start_t, end_t


def interpolate_timelocations(
    gmaps: googlemaps.Client,
    tlocs: List[TimeLocation],
) -> List[TimeLocation]:
    ''' Given a list of TimeLocations, interpolate between the two
    timelocations using the Googlemaps directions() API. '''
    interpolated_tlocs: List[TimeLocation] = list()
    for idx in range(len(tlocs) - 1):
        cur: TimeLocation = tlocs[idx]
        nxt: TimeLocation = tlocs[idx + 1]
        interpolated_tlocs.append(cur)
        if distance_on_unit_sphere(*(cur.latlngpoint()), *(nxt.latlngpoint())) > 500:
            print('Getting directions')
            directions = gmaps.directions(cur.latlngpoint(), nxt.latlngpoint(), mode='bicycling')
            flatpoints = flatten_routes_points(directions)
            # If the timediff would span a midnight boundary, the we assume
            # that there's a time-jump and clamp the duration interp
            start_t, end_t = clamp_end_before_midnight(cur.dt(), nxt.dt())
            per_point_timediff = (end_t - start_t) / (len(flatpoints) + 1)
            for pidx, point in enumerate(flatpoints):
                offset = (pidx + 1) * per_point_timediff
                newtime: datetime.datetime = start_t + offset
                newtloc = TimeLocation(lat=point[0], lng=point[1], moment=newtime.timestamp())
                interpolated_tlocs.append(newtloc)
    interpolated_tlocs.append(tlocs[-1])
    return interpolated_tlocs


def lon_to_x(lng, zoom):
    """
    transform longitude to tile number
    :type lng: float
    :type zoom: int
    :rtype: float
    """
    if not (-180 <= lng <= 180):
        lng = (lng + 180) % 360 - 180

    return ((lng + 180.) / 360) * pow(2, zoom)


def lat_to_y(lat, zoom):
    """
    transform latitude to tile number
    :type lat: float
    :type zoom: int
    :rtype: float
    """
    if not (-90 <= lat <= 90):
        lat = (lat + 90) % 180 - 90

    return (
        1 - math.log(math.tan(lat * math.pi / 180) + 1 / math.cos(lat * math.pi / 180)) / math.pi
    ) / 2 * pow(2, zoom)


def x_to_px(self, x):
    """
    transform tile number to pixel on image canvas
    :type x: float
    :rtype: float
    """
    # print(f"{x=}")
    # print(f"{self.x_center=}")
    # print(f"{self.tile_size=}")
    # print(f"{self.width=}")
    px = (x - self.x_center) * self.tile_size + self.width / 2
    return int(round(px))


def y_to_px(self, y):
    """
    transform tile number to pixel on image canvas
    :type y: float
    :rtype: float
    """
    # print(f"{y=}")
    # print(f"{self.y_center=}")
    # print(f"{self.tile_size=}")
    # print(f"{self.height=}")
    px = (y - self.y_center) * self.tile_size + self.height / 2
    return int(round(px))


def mincoords(coords):
    return (min(c[0] for c in coords), min(c[1] for c in coords))


def maxcoords(coords):
    return (max(c[0] for c in coords), max(c[1] for c in coords))


def calc_mapinfo(m):
    zoom = m._calculate_zoom()
    # print(f"{zoom=}")
    # extent has two coordinates which if rendered, are one in the top right
    # and one in the bottom left. bottom left coord comes first of the four
    # numbers.
    extent = m.determine_extent(zoom)
    # lng,lat fmt, in keeping with staticmap code we're copying
    topright_coords = (extent[2], extent[3])
    botmleft_coords = (extent[0], extent[1])

    # Have to set center on m to correctly calculate pix positions later
    lon_center, lat_center = (extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2
    m.x_center = lon_to_x(lon_center, zoom)
    m.y_center = lat_to_y(lat_center, zoom)

    topright_pix = (
        x_to_px(m, lon_to_x(topright_coords[0], zoom)),
        y_to_px(m, lat_to_y(topright_coords[1], zoom)),
    )
    botmleft_pix = (
        x_to_px(m, lon_to_x(botmleft_coords[0], zoom)),
        y_to_px(m, lat_to_y(botmleft_coords[1], zoom)),
    )

    # print(f"{topright_pix=}")
    # print(f"{botmleft_pix=}")

    mincorner = mincoords([topright_pix, botmleft_pix])
    maxcorner = maxcoords([topright_pix, botmleft_pix])

    height = maxcorner[1] - mincorner[1]
    width = maxcorner[0] - mincorner[0]

    # print(f"{height=}")
    # print(f"{width=}")
    return {
        'feature_height': height,
        'feature_width': width,
        'zoom': zoom,
    }


def calc_output_dimensions(wh_aspect_ratio, shortside_goal_length=1000):
    '''Returns width height'''
    if wh_aspect_ratio < 1:
        # taller than it is wide; width is 1000
        width = shortside_goal_length
        height = (1 / wh_aspect_ratio) * shortside_goal_length
        return int(width), int(height)
    width = wh_aspect_ratio * shortside_goal_length
    height = shortside_goal_length
    return int(width), int(height)


def main():
    gmaps = googlemaps.Client(key=GMAPS_APIKEY)
    rows = list()
    readfile = sys.stdin
    for line in readfile:
        if line.strip():
            rows.append(json.loads(line))
    # this 'm' is temporary only; the real 'm' is created with dynamic
    # dimensions for better fit later on.
    m = staticmap.StaticMap(1000, 1000)
    rows = [r for r in rows if not 'error' in r or not r['error']]
    rows = sorted(rows, key=lambda x: x['timestamp_utc'])

    tlocs = [TimeLocation.fromrow(row) for row in rows]
    # Draw to in-mem canvas so we can learn about aspect-ratioes in order to
    # have a nicely sized output image
    draw_tlocs(m, tlocs, tlocs)

    mapinfo = calc_mapinfo(m)
    aspect_ratio = mapinfo['feature_width'] / mapinfo['feature_height']
    m = staticmap.StaticMap(*calc_output_dimensions(aspect_ratio))

    interp_tlocs = interpolate_timelocations(gmaps, tlocs)

    orig_day_tlocs = bin_by_day(tlocs)
    day_tlocs = bin_by_day(interp_tlocs)

    output_name = 'map.png'
    if len(sys.argv) > 1:
        output_name = sys.argv[1]
    nameonly = '.'.join(output_name.split('.')[:-1])
    extnonly = output_name.split('.')[-1]

    for day, dtlocs in day_tlocs.items():
        color = color_hash(day)
        orig_dtlocs = orig_day_tlocs.get(day, list())

        tmp_daymap = staticmap.StaticMap(*calc_output_dimensions(aspect_ratio))
        draw_tlocs(tmp_daymap, dtlocs, dtlocs)
        mapinfo = calc_mapinfo(tmp_daymap)
        aspect_ratio = mapinfo['feature_width'] / mapinfo['feature_height']
        daymap = staticmap.StaticMap(*calc_output_dimensions(aspect_ratio))

        draw_tlocs(daymap, dtlocs, orig_dtlocs, linecolor=color, markercolor=color)
        draw_tlocs(m, dtlocs, orig_dtlocs, linecolor=color, markercolor=color)

        dayfname = f"{nameonly}_{day}.{extnonly}"
        print(f"Rendering {dayfname}")
        image = daymap.render()
        image.save(dayfname)

    print(f"Rendering {output_name}")
    image = m.render()
    image.save(output_name)


if __name__ == '__main__': main()
