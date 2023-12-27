# ⚡️Power-Digger-3000⚡️

Streamlit dashboard to analyse the vinyl releases of recordlabels using the Discogs API.
Get the most relevant statistics concerning the releases of specific record labels. For example, the dashboard allows to extract which releases have the highest ratio of Discogs users who want the relase vs. Discogs users who have it. 

# Screenshots
![Alt text](/App_Initial.png)
![Alt text](/App_Statistics.png)

# Setup
Usage requires a personal access token that can be obtained here: https://www.discogs.com/settings/developers. Enter the token at the top of utils.py.

To run the app, download/clone the repo and run the streamlit app with 'streamlit run app.py'. You can now fill your database by entering discogs links to labels (e.g. 'https://www.discogs.com/label/640877-Love-On-The-Rocks'). Releases of a label are stored in the Data/ folder.
