import googlemaps
import staticmap

import binascii
import datetime
import json
import math
import sys

# Pirated google maps API key (from an example code sample published by Google)
GMAPS_APIKEY = "AIz" + "aSyA3gqF4a2G0bcRG7J" + "gzAwo40iVStrSv2OM"


def color_hash(obj):
    # https://stackoverflow.com/a/4382138
    kelly_colors_hex = [
        '#FFB300',  # Vivid Yellow
        '#803E75',  # Strong Purple
        '#FF6800',  # Vivid Orange
        '#A6BDD7',  # Very Light Blue
        '#C10020',  # Vivid Red
        '#CEA262',  # Grayish Yellow
        '#817066',  # Medium Gray

        # The following don't work well for people with defective color vision
        '#007D34',  # Vivid Green
        '#F6768E',  # Strong Purplish Pink
        '#00538A',  # Strong Blue
        '#FF7A5C',  # Strong Yellowish Pink
        '#53377A',  # Strong Violet
        '#FF8E00',  # Vivid Orange Yellow
        '#B32851',  # Strong Purplish Red
        '#F4C800',  # Vivid Greenish Yellow
        # '#7F180D',  # Strong Reddish Brown
        '#93AA00',  # Vivid Yellowish Green
        '#593315',  # Deep Yellowish Brown
        # '#F13A13',  # Vivid Reddish Orange
        '#232C16',  # Dark Olive Green
    ]
    return kelly_colors_hex[binascii.crc32(str(obj).encode('utf-8')) % len(kelly_colors_hex)]


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
        #print("Cos:", cos)
        #print(e)
        raise e

    return arc * 6378100


def decode_polyline(point_str):
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
    points = []
    prev_x = 0
    prev_y = 0
    for i in range(0, len(coords) - 1, 2):
        if coords[i] == 0 and coords[i + 1] == 0:
            continue

        prev_x += coords[i + 1]
        prev_y += coords[i]
        # a round to 6 digits ensures that the floats are the same as when
        # they were encoded
        points.append([round(prev_y, 6), round(prev_x, 6)])

    return points


def flatten_routes_points(directionsresponse):
    # print(directionsresponse)
    flatpoints = list()
    for route in directionsresponse:
        directionslegs = route['legs']
        for leg in directionslegs:
            directionssteps = leg['steps']
            for step in directionssteps:
                flatpoints += decode_polyline(step['polyline']['points'])
    return flatpoints


def bin_by_day(rows):
    days = {}
    for row in rows:
        ts = datetime.datetime.fromtimestamp(row['timestamp_utc'])
        ts_str = ts.strftime("%Y %m %d")
        if not ts_str in days:
            days[ts_str] = list()
        days[ts_str].append(row)
    return days


def draw_rows(m: staticmap.StaticMap, gmaps, rows, linecolor='red', markercolor='green'):
    points = [[cur['latitude'], cur['longitude']] for cur in rows]

    smoothpoints = list()
    for idx in range(len(points) - 1):
        cur = points[idx]
        nxt = points[idx + 1]
        if distance_on_unit_sphere(*cur, *nxt) > 500:
            directions = gmaps.directions(cur, nxt)
            print('Getting directions')
            flatpoints = flatten_routes_points(directions)
            smoothpoints += flatpoints
        else:
            smoothpoints += [cur, nxt]

    lpairs = list()

    for idx in range(len(smoothpoints) - 1):
        cur = smoothpoints[idx]
        nxt = smoothpoints[idx + 1]
        coordpair = [
            # I don't know why, but this komoot/staticmap library uses longitude-first coordinates :(
            [cur[1], cur[0]],
            [nxt[1], nxt[0]],
        ]
        lpairs.append(coordpair)

    def draw_lines(color, thickness):
        for pair in lpairs:
            coords = pair
            line = staticmap.Line(coords, color, thickness)
            m.add_line(line)

    draw_lines('white', 6)
    draw_lines(linecolor, 4)

    def draw_rawpoints(color, thickness):
        for point in points:
            pnt = [point[1], point[0]]
            marker = staticmap.CircleMarker(pnt, color, thickness)
            m.add_marker(marker)

    draw_rawpoints('white', 8)
    draw_rawpoints(markercolor, 5)


def main():
    gmaps = googlemaps.Client(key=GMAPS_APIKEY)
    rows = list()
    readfile = sys.stdin
    for line in readfile:
        if line.strip():
            rows.append(json.loads(line))
    m = staticmap.StaticMap(1500, 1500)
    rows = [r for r in rows if not 'error' in r or not r['error']]
    rows = sorted(rows, key=lambda x: x['timestamp_utc'])

    dayrows = bin_by_day(rows)

    for day, drows in dayrows.items():
        color = color_hash(day)
        draw_rows(m, gmaps, drows, linecolor=color, markercolor=color)

    image = m.render()
    output_name = 'map.png'
    if len(sys.argv) > 1:
        output_name = sys.argv[1]
    image.save(output_name)


if __name__ == '__main__': main()
