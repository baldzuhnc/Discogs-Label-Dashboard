import math
import re
from collections import Counter
import time
import os
import requests
import json
import pandas as pd
from tqdm import tqdm
import discogs_client

user_token = ""
user_agent = ""

#Function to return label id
def extract_label_id(discogs_link):
    pattern = r'.*label/(\d+)-.*'
    match = re.match(pattern, discogs_link)
    if match:
        label_id = int(match.group(1))
        return label_id
    else:
        return None

def extract_label_name(discogs_link):
    user_token = 'yvnVEVRUIrhOoGoXPUKqWrFVEUydfUJLnOSENqkY'
    user_agent = "CB_LabelSummary/0.1"
    d = discogs_client.Client(user_agent, user_token)
    label = d.label(extract_label_id(discogs_link))
    label_name = label.name.replace(" ", "")

    return label_name

def get_release_ids(label_id):
    # Authentication/Instantiate discogs client
    user_token = 'yvnVEVRUIrhOoGoXPUKqWrFVEUydfUJLnOSENqkY'
    user_agent = "CB_LabelSummary/0.1"
    # consumer_key = "IUXDfzLvngOEfIomsahP"
    # consumer_secret = "EUIkNQNapcpFzUjmrZjKIBFxXyiXpqSC"
    d = discogs_client.Client(user_agent, user_token)

    label = d.label(label_id)
    label_name = label.name

    # Print no. of releases and calculate number of pages for forloop
    no_releases = len(label.releases)
    print(f'Getting catalogue ({no_releases} releases) of {label_name}...')
    num_pages = math.ceil(no_releases / 50)

    # Download releases implements discogs_client. No rate limit necessary? Have to see in the future.
    nested_releases = [label.releases.page(i) for i in tqdm(range(num_pages + 1))]
    # Flatten release list
    flattened_releases = [item for sublist in nested_releases for item in sublist]

    release_ids = [item.id for i, item in enumerate(flattened_releases)]
    unique_ids_set = set(release_ids)
    unique_ids_list = list(unique_ids_set)

    return unique_ids_list, label_name

def get_raw_data(ids, vinyl_only, other_format_exclude):
    excluded_formats = ["White Label", "Test Pressing", "Repress", "Mispress", "Promo", "Reissue"]

    # Initialize HTTP request
    parameters = {'token': user_token}
    header = {'user-agent': user_agent}

    # url_identity = "https://api.discogs.com/oauth/identity" #have to be included
    url_releases = "https://api.discogs.com/releases/"  # followed by item id
    url_marketplace_price = "https://api.discogs.com/marketplace/price_suggestions/"
    url_marketplace_stats = "https://api.discogs.com/marketplace/stats/"
    currency = "EUR"

    # Rate limiting
    sleep_duration = 60  # in seconds
    rate_limit_warning = f"Rate limit reached. Pausing for {sleep_duration} seconds."

    # Initialize container
    raw_releases = []  # For releases
    raw_prices = []
    raw_stats = []

    #Counters
    filecount = 0
    format_exclude_count = 0

    # Start GET

    print(f'Getting release data... ')

    for i, id in tqdm(enumerate(ids)):

        try:
            # GET release
            response_release = requests.get(f'{url_releases}{id}', params=parameters, headers=header)
            response_release.raise_for_status()  # Check if the request was successful (status code 200)

            # Remaining requests, Pause for 60 seconds if less than 1
            if int(response_release.headers.get("X-Discogs-Ratelimit-Remaining")) == 1:
                print(rate_limit_warning)
                time.sleep(sleep_duration)

            # Only get vinyl releases
            if vinyl_only and response_release.json()["formats"][0]["name"] != "Vinyl":
                filecount += 1
                # Skip to the next iteration if type of response is File
                continue
            elif other_format_exclude and any(format_desc in excluded_formats for format_desc in response_release.json()["formats"][0]["descriptions"]):
                # Skip to the next iteration if any excluded format is found in descriptions
                format_exclude_count += 1
                continue
            else:
                raw_releases.append(response_release.json())

            # GET price
            response_price = requests.get(f'{url_marketplace_price}{id}', params=parameters, headers=header)
            response_price.raise_for_status()  # Check if the request was successful (status code 200)
            raw_prices.append(response_price.json())  # Process the response content

            # Remaining requests, Pause for 60 seconds if less than 1
            if int(response_price.headers.get("X-Discogs-Ratelimit-Remaining")) == 1:
                print(rate_limit_warning)
                time.sleep(sleep_duration)

            # GET stats
            response_stats = requests.get(f'{url_marketplace_stats}{id}?{currency}', params=parameters, headers=header)
            response_stats.raise_for_status()  # Check if the request was successful (status code 200)
            raw_stats.append(response_stats.json())  # Process the response content

            # Remaining requests, Pause for 60 seconds if less than 1
            if int(response_stats.headers.get("X-Discogs-Ratelimit-Remaining")) == 1:
                print(rate_limit_warning)
                time.sleep(sleep_duration)

        except requests.exceptions.HTTPError as http_err:
            print(f'HTTP error occurred: {http_err}')
            break

        except requests.exceptions.RequestException as req_err:
            print(f'Request error occurred: {req_err}')
            break

    print(f'Done. Got {len(raw_releases)} of {len(ids)} total releases. {filecount} file(s) in catalogue.')

    return raw_releases, raw_prices, raw_stats

def test_get_raw(id):
    parameters = {'token': user_token}
    header = {'user-agent': user_agent}
    url_releases = "https://api.discogs.com/releases/"  # followed by item id

    response_release = requests.get(f'{url_releases}{id}', params=parameters, headers=header)
    response_release.raise_for_status()

    return response_release.json()

def save_raw_json(label_name, raw_releases, raw_prices, raw_stats):
    concatenated_label = label_name.replace(" ", "")

    # create folder with labelname in working directory
    current_directory = os.getcwd()
    folder_path = os.path.join(current_directory, "Data", concatenated_label)

    if not os.path.exists(folder_path):
        # If it doesn't exist, create the folder
        os.makedirs(folder_path)

        # Write files
        with open(f'{folder_path}/raw_releases.json', "w") as json_file:
            json.dump(raw_releases, json_file, indent=2)

        with open(f'{folder_path}/raw_prices.json', "w") as json_file:
            json.dump(raw_prices, json_file, indent=2)

        with open(f'{folder_path}/raw_stats.json', "w") as json_file:
            json.dump(raw_stats, json_file, indent=2)

        # print(f"Folder '{label_name}' created in the current working directory.")
    else:
        print(f"Folder '{concatenated_label}' already exists in the current working directory.")

def read_raw_json(label_name):
    concatenated_label = label_name.replace(" ", "")

    current_directory = os.getcwd()
    folder_path = os.path.join(current_directory, "Data", concatenated_label)

    if os.path.exists(folder_path):

        with open(f'{folder_path}/raw_releases.json', 'r') as json_file:
            raw_releases = json.load(json_file)

        with open(f'{folder_path}/raw_prices.json', 'r') as json_file:
            raw_prices = json.load(json_file)

        with open(f'{folder_path}/raw_stats.json', 'r') as json_file:
            raw_stats = json.load(json_file)

    else:
        print(f"Folder '{concatenated_label}' doesn't exist in the current working directory.")

    return raw_releases, raw_prices, raw_stats

def json_to_pandas(raw_releases, raw_prices, raw_stats):
    # Ids
    ids = [release["id"] for release in raw_releases]

    titles = [release["title"] for release in raw_releases]
    years = [release["year"] for release in raw_releases]
    url = [release["uri"] for release in raw_releases]
    formats = [release["formats"][0]["name"] for release in raw_releases]

    # Genre/Style
    genres = [', '.join(release["genres"]) if "genres" in release else None for release in raw_releases]
    styles = [', '.join(release["styles"]) if "styles" in release else None for release in raw_releases]

    # Community
    have = [release["community"]["have"] if "community" in release and "have" in release["community"] else None for
            release in raw_releases]
    want = [release["community"]["want"] if "community" in release and "want" in release["community"] else None for
            release in raw_releases]
    rating_count = [release["community"]["rating"]["count"] if "community" in release and "rating" in release[
        "community"] and "count" in release["community"]["rating"] else None for release in raw_releases]
    rating_average = [release["community"]["rating"]["average"] if "community" in release and "rating" in release[
        "community"] and "average" in release["community"]["rating"] else None for release in raw_releases]

    # Notes
    notes = [release["notes"] if "notes" in release else None for release in raw_releases]
    tokens = [len(note.split()) if note else 0 for note in notes]

    # Suggested prices
    price_M = [release["Mint (M)"]["value"] if "Mint (M)" in release and "value" in release["Mint (M)"] else None for
               release in raw_prices]
    price_NM = [release["Near Mint (NM or M-)"]["value"] if "Near Mint (NM or M-)" in release and "value" in release[
        "Near Mint (NM or M-)"] else None for release in raw_prices]
    price_VGp = [release["Very Good Plus (VG+)"]["value"] if "Very Good Plus (VG+)" in release and "value" in release[
        "Very Good Plus (VG+)"] else None for release in raw_prices]
    price_VG = [release["Very Good (VG)"]["value"] if "Very Good (VG)" in release and "value" in release[
        "Very Good (VG)"] else None for release in raw_prices]
    price_Gp = [release["Good Plus (G+)"]["value"] if "Good Plus (G+)" in release and "value" in release[
        "Good Plus (G+)"] else None for release in raw_prices]
    price_G = [release["Good (G)"]["value"] if "Good (G)" in release and "value" in release["Good (G)"] else None for
               release in raw_prices]
    price_F = [release["Fair (F)"]["value"] if "Fair (F)" in release and "value" in release["Fair (F)"] else None for
               release in raw_prices]
    price_P = [release["Poor (P)"]["value"] if "Poor (P)" in release and "value" in release["Poor (P)"] else None for
               release in raw_prices]

    # Stats
    lowest_price = [
        release["lowest_price"]["value"] if release and "lowest_price" in release and release["lowest_price"] else None
        for release in raw_stats]
    num_for_sale = [release["num_for_sale"] if release and "num_for_sale" in release else None for release in raw_stats]

    # C Create Pandas DF from variables
    data = {
        'title': titles,
        'year': years,
        'url': url,
        'style': styles,
        'want': want,
        'have': have,
        'rating_average': rating_average,
        'rating_count': rating_count,
        'price_M': price_M,
        'tokens': tokens,
        'notes': notes,
        'price_NM': price_NM,
        'price_VGp': price_VGp,
        'price_VG': price_VG,
        'price_Gp': price_Gp,
        'price_G': price_G,
        'price_F': price_F,
        'price_P': price_P,
        'genre': genres,
        'format': formats,
        'lowest_price': lowest_price,
        'num_for_sale': num_for_sale,
        'id': ids
    }

    # Create a Pandas DataFrame from the dictionary
    df = pd.DataFrame(data)
    df.replace([0, None], pd.NA, inplace=True)

    # Mutate columns
    want_index = df.columns.get_loc("want")
    wh_ratio = df["want"].fillna(0) / df["have"].fillna(1)
    df.insert(want_index , "wh_ratio", wh_ratio)


    return df

def most_common_styles(style_col):
    styles = []

    for i in range(len(style_col)):
        if pd.isna(style_col[i]):
            continue
        else:
            splitted = style_col[i].split(",")
        for j in range(len(splitted)):
            styles.append(splitted[j].strip())

    styles_count = Counter(styles)

    most_common_style = styles_count.most_common(1)[0][0]
    second_most_common = styles_count.most_common(2)[1][0]

    return most_common_style, second_most_common

#Master functions
def get_and_save_label(discogs_link, vinyl_only, other_format_exclude, output = False):
    label_id = extract_label_id(discogs_link)

    release_ids, label_name = get_release_ids(label_id)

    raw_releases, raw_prices, raw_stats = get_raw_data(release_ids, vinyl_only, other_format_exclude)

    save_raw_json(label_name, raw_releases, raw_prices, raw_stats)

    if output:
        print(f'Records from {label_name} successfully stored.')
        return json_to_pandas(raw_releases, raw_prices, raw_stats)

    else:
        print(f'Records from {label_name} successfully stored.')

def open_and_create_df(label_name):
    raw_releases, raw_prices, raw_stats = read_raw_json(label_name)
    df = json_to_pandas(raw_releases, raw_prices, raw_stats)

    return df
