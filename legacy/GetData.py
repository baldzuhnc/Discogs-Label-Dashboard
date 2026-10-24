import os
import sys
import discogs_client
from discogs_client.exceptions import HTTPError

consumer_key = os.environ.get('DISCOGS_CONSUMER', '')
consumer_secret = os.environ.get("DISCOGS_CONSUMER_SECRET", "")

user_agent = "CB_LabelSummary/0.1"

# A user-agent is required with Discogs API requests. Be sure to make your
# user-agent unique, or you may get a bad response.
user_agent = "discogs_api_example/2.0"

# instantiate our discogs_client object.
discogsclient = discogs_client.Client(user_agent)
discogsclient.set_consumer_key(consumer_key, consumer_secret)

# prepare the client with our API consumer data.
discogsclient.set_consumer_key(consumer_key, consumer_secret)
token, secret, url = discogsclient.get_authorize_url()
print(f'token: {token}')


# Request Token URL 	https://api.discogs.com/oauth/request_token
# Authorize URL 	https://www.discogs.com/oauth/authorize
# Access Token URL 	https://api.discogs.com/oauth/access_token


# 1. Get first page of releases from label
# https://www.discogs.com/label/1721-Universal-Egg
# Classification: Have/Want ratio, minprice, rating, no of versions, no of ocmments


# Long term: telegram app which returns links to releases which are worth listening
# /labels/{label_id}/releases{?page,per_page}
# GET https://api.discogs.com/artists/1?callback=callbackname
# 60 releases per minute (authenticated)
# e.g. GET https://api.discogs.com/artists/1/releases?page=2&per_page=75
