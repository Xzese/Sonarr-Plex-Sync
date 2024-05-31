# Plex and Sonarr Episode Cleanup Script

This Python script automates the cleanup of watched episodes in your Plex library by removing them from your Sonarr library and unmonitoring them in Sonarr. It prompts the user for necessary environment variables and the number of days until deletion, and then performs the cleanup based on the specified criteria.

## Prerequisites

Before using this script, make sure you have the following prerequisites installed:

- Python 3
- `plexapi` library: You can install it via pip (`pip install plexapi`)
- `pyarr` library: You can install it via pip (`pip install pyarr`)
- `dotenv` library: You can install it via pip (`pip install python-dotenv`)

## Setup

1. Clone or download this repository to your local machine.
2. Ensure you have the necessary environment variables set:
   - `PLEX_URL`: Your Plex server URL
   - `PLEX_TOKEN`: Your Plex authentication token (Refer to [Plex Support](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) for help finding)
   - `SONARR_URL`: Your Sonarr server URL
   - `SONARR_KEY`: Your Sonarr API key (You can find it in Sonarr by navigating to Settings => General)
3. If any of these environment variables are not set, the script will prompt you to enter them when you run it.
4. Run the script.

## Usage

1. Run the script: `python episode_cleanup.py`
2. Follow the prompts to enter the required information:
   - Plex URL
   - Plex Token
   - Sonarr URL
   - Sonarr API Key
   - Number of days until deletion
3. The script will then proceed to unmonitor and delete watched episodes in Sonarr that are older than the specified number of days.

## Note

- This script assumes you have both Plex and Sonarr set up and running with your media library managed by Sonarr.
- Ensure that you have set the correct permissions and configurations in both Plex and Sonarr before running this script.