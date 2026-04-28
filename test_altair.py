import pandas as pd
import altair as alt

data = {
    "aircraft_id": ["A1", "A2", "A3", "A4", "A5"],
    "squadron": ["Sq1", "Sq1", "Sq2", "Sq2", "Sq2"],
    "Score": [65, 45, 30, 80, 50],
    "type": ["Fighter", "Fighter", "Bomber", "Bomber", "Bomber"]
}
chart_df = pd.DataFrame(data)
chart_df["Status"] = chart_df["Score"].apply(lambda s: "Operational" if s >= 60 else "Needs Attention" if s >= 40 else "Critical")
chart_df["Count"] = 1

color_scale = alt.Scale(
    domain=["Operational", "Needs Attention", "Critical"],
    range=["#00e676", "#ff9800", "#ff4b4b"]
)

chart = alt.Chart(chart_df).mark_bar().encode(
    x=alt.X("squadron:N", title="Squadron"),
    y=alt.Y("Count:Q", title="Number of Aircraft"),
    color=alt.Color("Status:N", scale=color_scale),
    detail="aircraft_id:N",
    tooltip=["aircraft_id", "type", "squadron", "Score", "Status"]
)
print(chart.to_json())
