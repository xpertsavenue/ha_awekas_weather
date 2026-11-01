"""Constants for the AWEKAS Weather integration."""

from datetime import timedelta

DOMAIN = "awekas_weather"

DEFAULT_TITLE = "AWEKAS Weather"

API_URL = "https://api.awekas.at/current.php"
STATION_API_URL = "https://api.awekas.at/station.php"
REQUEST_TIMEOUT = 10  # seconds

# The station uploads its data roughly once a minute. The API allows
# 240 requests per hour.
UPDATE_INTERVAL = timedelta(minutes=1)
# The station data (location, hardware, sensors) rarely changes
STATION_UPDATE_INTERVAL = timedelta(days=1)
# Pause polling for this long once the API reports an exceeded quota
QUOTA_RETRY_AFTER = timedelta(minutes=15)
# Measurements older than this are reported as unavailable
STALE_AFTER = timedelta(hours=1)
