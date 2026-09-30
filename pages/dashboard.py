"""Legacy Streamlit entry: the maintained application is Flask."""
import os
import streamlit as st

st.title("HayatCare")
st.info("This feature is now maintained in the main HayatCare website. Start it with python run.py.")
st.link_button("Open dashboard", os.getenv("HAYATCARE_URL", "http://localhost:5000").rstrip("/") + "/dashboard")
