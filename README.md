# Batey Family Bike Trips

Every year, some amount of the Batey family goes on a multi-day bicycle trip
together. On the trip, each day we'll ride bicycles through scenic areas at a
relatively relaxed pace. None of us are "serious" bike riders, so our mileage
and routes may look pretty relaxed to seasoned cross-country riders.

This repository will be the data necessary to generate image-galleries of the
pictures from these bike trips. In order to preserve privacy, this repository
will _not_ house the collected pictures from the participants. Instead, this
repo will house the hard-data and metadata used to generate galleries of
images; it'll have everything necessary to generate the image galleries
*except* for the images themselves.

## Generate Data

```
# Generate the JSON lines GPS data:
cat <(python exif_gps.py 2018_batey_bike_trip/images/*) <(python markdown_gps.py 2018_batey_bike_trip/2018_batey_bike_trip.md) > 2018_batey_bike_trip/2018_pictures_gps_data.json
# Convert the GPS data into a nice map:
cat 2018_batey_bike_trip/2018_pictures_gps_data.json | python ./create_maps.py 2018_batey_bike_trip/map_2018_bike_trip.png
```
