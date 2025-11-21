import requests
import pandas as pd
import joblib
from datetime import datetime
# from myapp.views import get_city_coords

def predict(city_lat, city_lon):
        


    # -------------------------------------------------------
    # Load trained models
    # -------------------------------------------------------

    TEMP_MODEL = joblib.load("myapp/real_model_testing_3/temp_model_xgb_regressor.pkl")
    CODE_MODEL = joblib.load("myapp/real_model_testing_3/weather_code_model_xgb_classifier.pkl")

    # -------------------------------------------------------
    # API URL
    # -------------------------------------------------------
    API_URL = "https://api.open-meteo.com/v1/forecast"

    # -------------------------------------------------------
    # Utility: Simplify WMO Weather Code
    # -------------------------------------------------------
    def simplify_weather_code(code):
        if code == 0:
            return 0
        elif code == 1:
            return 1
        elif code == 2:
            return 2
        elif code == 3:
            return 3
        elif code == 45:
            return 4
        elif code in [51, 53, 55]:
            return 5
        elif code in [61, 63, 65]:
            return 6
        elif code in [80, 81]:
            return 7
        elif code in [95, 96]:
            return 8
        else:
            return 9

    # -------------------------------------------------------
    # Compute Season
    # -------------------------------------------------------
    def get_season(month):
        if month in [12,1,2]:
            return 0
        elif month in [3,4,5]:
            return 1
        elif month in [6,7,8]:
            return 2
        else:
            return 3


    # -------------------------------------------------------
    # Fetch Live Weather and Predict
    # -------------------------------------------------------
    def predict_weather(lat=city_lat, lon=city_lon):

        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": [
                "uv_index_max",
                "uv_index_clear_sky_max",
                "precipitation_sum",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "wind_direction_10m_dominant",
                "shortwave_radiation_sum",
                "temperature_2m_mean",
                "cloud_cover_mean",
                "dew_point_2m_mean",
                "relative_humidity_2m_mean",
                "pressure_msl_mean",
                "surface_pressure_mean",
                "wind_gusts_10m_mean",
                "wind_speed_10m_mean",
                "apparent_temperature_mean",
                "et0_fao_evapotranspiration",
                "et0_fao_evapotranspiration_sum",
                "weather_code"
            ],
            "timezone": "auto"
        }

        response = requests.get(API_URL, params=params).json()
        d = response["daily"]

        # Use first entry of each list (today)
        df = pd.DataFrame({
            "uv_index_max ()": [d["uv_index_max"][0]],
            "uv_index_clear_sky_max ()": [d["uv_index_clear_sky_max"][0]],
            "precipitation_sum (mm)": [d["precipitation_sum"][0]],
            "wind_speed_10m_max (km/h)": [d["wind_speed_10m_max"][0]],
            "wind_gusts_10m_max (km/h)": [d["wind_gusts_10m_max"][0]],
            "wind_direction_10m_dominant (°)": [d["wind_direction_10m_dominant"][0]],
            "shortwave_radiation_sum (MJ/m²)": [d["shortwave_radiation_sum"][0]],
            "temperature_2m_mean (°C)": [d["temperature_2m_mean"][0]],
            "cloud_cover_mean (%)": [d["cloud_cover_mean"][0]],
            "dew_point_2m_mean (°C)": [d["dew_point_2m_mean"][0]],
            "relative_humidity_2m_mean (%)": [d["relative_humidity_2m_mean"][0]],
            "pressure_msl_mean (hPa)": [d["pressure_msl_mean"][0]],
            "surface_pressure_mean (hPa)": [d["surface_pressure_mean"][0]],
            "wind_gusts_10m_mean (km/h)": [d["wind_gusts_10m_mean"][0]],
            "wind_speed_10m_mean (km/h)": [d["wind_speed_10m_mean"][0]],
            "apparent_temperature_mean (°C)": [d["apparent_temperature_mean"][0]],
            "et0_fao_evapotranspiration_sum (mm)": [d["et0_fao_evapotranspiration_sum"][0]],
            "et0_fao_evapotranspiration (mm)": [d["et0_fao_evapotranspiration"][0]],
            "latitude": [lat],
            "longitude": [lon]
        })

        # ---- Date Features ----
        today = datetime.now()
        df["day"] = today.day
        df["month"] = today.month
        df["day_of_year"] = today.timetuple().tm_yday
        df["week"] = today.isocalendar().week

        # ---- Season ----
        df["season_num"] = get_season(today.month)

        # ---- weather code simplified ----
        code_raw = d["weather_code"][0]
        df["weather_code_simplified"] = simplify_weather_code(code_raw)

        # ---- Use exact same feature order as training ----
        FEATURES = [
            'uv_index_max ()', 'uv_index_clear_sky_max ()',
            'precipitation_sum (mm)', 'wind_speed_10m_max (km/h)',
            'wind_gusts_10m_max (km/h)', 'wind_direction_10m_dominant (°)',
            'shortwave_radiation_sum (MJ/m²)', 'temperature_2m_mean (°C)',
            'cloud_cover_mean (%)', 'dew_point_2m_mean (°C)',
            'relative_humidity_2m_mean (%)', 'pressure_msl_mean (hPa)',
            'surface_pressure_mean (hPa)', 'winddirection_10m_dominant (°)',
            'wind_gusts_10m_mean (km/h)', 'wind_speed_10m_mean (km/h)',
            'apparent_temperature_mean (°C)', 'et0_fao_evapotranspiration_sum (mm)',
            'et0_fao_evapotranspiration (mm)', 'latitude', 'longitude', 'day',
            'month', 'day_of_year', 'week', 'season_num','weather_code_simplified'
        ]

        # Fix missing column (winddirection_10m_dominant)
        df["winddirection_10m_dominant (°)"] = df["wind_direction_10m_dominant (°)"]

        df = df[FEATURES]

        # ---- Predict ----
        pred_temp = TEMP_MODEL.predict(df)[0]
        pred_code = CODE_MODEL.predict(df)[0]

        return pred_temp, pred_code

    WEATHER_LABELS = {
        0: "Clear",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        4: "Fog",
        5: "Drizzle",
        6: "Rain",
        7: "Rain showers",
        8: "Thunderstorm",
        9: "Unknown"
    }

    temp, code = predict_weather()
    weather_type = WEATHER_LABELS.get(int(code), "Unknown")


    return temp,weather_type
