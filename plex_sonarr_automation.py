#!/usr/bin/python

import os
import sys
from plexapi.server import PlexServer
from pyarr import SonarrAPI
import os
from dotenv import load_dotenv, set_key
from pathlib import Path

# Path to the .env file
env_path = Path('.env')

# Load existing environment variables from the .env file if it exists
if env_path.exists():
    load_dotenv(env_path)

# Function to prompt the user for input if the environment variable is not set
def get_env_variable(var_name, prompt):
    value = os.getenv(var_name)
    if not value:
        value = input(f"{prompt}: ")
        set_key(str(env_path), var_name, value)
    return value

# Check and prompt for necessary environment variables
plex_url = get_env_variable('PLEX_URL', 'Please enter your Plex URL')
plex_token = get_env_variable('PLEX_TOKEN', 'Please enter your Plex Token')
sonarr_url = get_env_variable('SONARR_URL', 'Please enter your Sonarr URL')
sonarr_key = get_env_variable('SONARR_KEY', 'Please enter your Sonarr API Key')
days_until_deletion = get_env_variable('DAYS_TO_DELETE', 'Please enter the number of days until deletion')

# Add 'd' to days_until_deletion
days_until_deletion = days_until_deletion + "d"

# Set up Plex and Sonarr instances
plex = PlexServer(plex_url, plex_token)
showLibrary = plex.library.section('TV Shows')
sonarr = SonarrAPI(sonarr_url, sonarr_key)
payload = {"monitored": False}

sys.exit()
#setting variable = "2d" will mean all completed episodes that have a last viewed date more than 2 days ago will be deleted
days_until_deletion = "2d"
episode_dict = {}

#Get All Unwatched Episodes over 2 days old and add to an nested dictionary in format {Show:[Episodes]}
for episode in showLibrary.search(unwatched=False,libtype='episode',filters={"lastViewedAt<<":days_until_deletion}):
    for guid in episode.season().show().guids:
        if 'tvdb' in str(guid):
            tvShowKey = str(guid)[13:-1]
    if tvShowKey not in episode_dict:
        episode_dict[tvShowKey] = []
    for guid in episode.guids:
        if 'tvdb' in str(guid):
            episode_dict[tvShowKey].append(int(str(guid)[13:-1]))

#Unmonitor and Delete all old watched episodes

for tvshow_id, episode_ids in episode_dict.items():
    sonarr_series_id = sonarr.get_series(id_=tvshow_id,tvdb=True)[0]['id']
    sonarr_episodes = sonarr.get_episode(id_=sonarr_series_id,series=True)
    for episode in sonarr_episodes:
        if episode["tvdbId"] in episode_ids and episode['hasFile'] == True:
            sonarr.upd_episode(episode['id'],payload)
            sonarr.del_episode_file(episode['episodeFileId'])

showLibrary.update()
showLibrary.emptyTrash()
print("Completed")
