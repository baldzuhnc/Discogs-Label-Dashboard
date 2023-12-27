from utils import *
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
import os

current_directory = os.getcwd()
label_names = os.listdir(os.path.join(current_directory, "Data"))

# Config and title
st.set_page_config(
    page_title="⚡️Power digger 3000⚡️",
    page_icon="📀",
    layout="wide",
)
st.title("⚡️Power digger 3000⚡️")

# Sidebar: Data inflow
with st.sidebar:
    st.header("Data selector")
    # Fetching data flow
    # Flag to check if data fetching has occurred
    data_fetched = False

    st.write("Enter label link to fetch data. About 20 releases can be downloaded per minute.")
    discogs_link = st.sidebar.text_input("Enter Discogs label link")

    if discogs_link and not data_fetched:

        if extract_label_name(discogs_link) in label_names:
            st.write("Label already in database. Delete the folder and try again or select from dropdown.")
            data_fetched = True  # Set the flag to True after data fetching
        else:
            with st.spinner("Downloading releases..."):
                get_and_save_label(discogs_link, vinyl_only=True, other_format_exclude=True, output=False)
                st.success("Releases downloaded successfully!")
            data_fetched = True  # Set the flag to True after data fetching

    # Database Flow
    label_names = os.listdir(os.path.join(current_directory, "Data"))
    label_filter = st.sidebar.selectbox("Database", label_names)

    df = open_and_create_df(label_filter)

#Display labelname
st.header(label_filter)

# Key indicators
ki1, ki2, ki3, ki4, ki5 = st.columns(5)
ki1.metric(label = "Number of releases",value= len(df))
ki2.metric(label = "Median price for Mint", value= round(df["price_M"].median(), 2))
ki3.metric(label = "Avg. price for Mint", value= round(df["price_M"].mean(), 2))
ki4.metric(label = "Avg. Want/Have Ratio", value= round(df["wh_ratio"].mean(), 2))
ki5.metric(label = "Avg. Rating", value= round(df["rating_average"].mean(), 2))

first_style, second_style = most_common_styles(df["style"])
st.write(f'Most common styles: {first_style}, {second_style}')

#Plot dataframe
st.dataframe(df)

st.header("Statistics")
col1, col2, col3,col4,col5, col6 = st.columns([1, 1, 1, 1, 1, 1])

# Binsize
binsize = col1.slider("No. of bins", min_value=1, max_value = 60, value = 15)

# Create subcols for plots: Row 1
col1, col2 = st.columns([1, 1])

#Plot 1: Years
year_plot, ax = plt.subplots()
sns.histplot(df["year"], bins=binsize, kde=True, ax=ax, color='#FF4B4B')
ax.set_xlabel('Year')
ax.set_ylabel('Frequency')
ax.set_title('Smooth Distribution of records released')
col1.pyplot(year_plot)

#Plot 2: WH/Ratio
wh_plot, ax = plt.subplots()
sns.histplot(df["wh_ratio"], bins=binsize, kde=True, ax=ax, color='#FF4B4B')
ax.set_xlabel('Want/Have Ratio')
ax.set_ylabel('Frequency')
ax.set_title('Smooth Distribution of Want/Have Ratio')

col2.pyplot(wh_plot)

# Create subcols for plots: Row 2
col3, col4= st.columns([1, 1])

#Plot 3: Mint
mint_plot, ax = plt.subplots()
sns.histplot(df["price_M"], bins=binsize, kde=True, ax=ax, color='#FF4B4B')
ax.set_xlabel('Price for Mint Records')
ax.set_ylabel('Frequency')
ax.set_title('Smooth Distribution of price for Mint Records')

col3.pyplot(mint_plot)


#Plot 4: Year/median Mint
df_2 = df.dropna(subset=['year'])
year_med, ax = plt.subplots()
median_prices = df_2.groupby('year')['price_M'].median().reset_index()
ax.bar(median_prices['year'], median_prices['price_M'])
plt.xlim(min(df_2["year"] -1), max(df_2["year"] + 1))
plt.ylabel('Median Price for Mint')
plt.xlabel('Year')
plt.title('Median Price vs Year')
col4.pyplot(year_med)
