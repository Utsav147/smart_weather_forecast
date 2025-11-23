from django.shortcuts import render, redirect
from datetime import datetime, timedelta,date
from .models import MonthlyWeather,SmartSuggestion
import requests 
from myapp.real_model_testing_3.predict_live import predict
from django.core.files.uploadedfile import InMemoryUploadedFile
import google.generativeai as genai
import base64
import os


# OpenWeather API setup
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
CITY_COORDS = {
    "ahmedabad":  (23.0225, 72.5714),
    "surat":      (21.1702, 72.8311),
    "vadodara":   (22.3072, 73.1812),
    "rajkot":     (22.3039, 70.8022),
    "gandhinagar":(23.2237, 72.6500),
}


def today_view(request):
    # 1) If user selected a new city → update session
    if "city" in request.GET:
        request.session["selected_city"] = request.GET["city"]
    # 2) Read city from session (fallback = ahmedabad)
    city_key = request.session.get("selected_city", "ahmedabad")
    lat, lon = CITY_COORDS.get(city_key, CITY_COORDS["ahmedabad"])
    
    url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()
        sunrise = datetime.utcfromtimestamp(data['sys']['sunrise']) + timedelta(hours=5, minutes=30)
        sunset = datetime.utcfromtimestamp(data['sys']['sunset']) + timedelta(hours=5, minutes=30)

        today_data = {
            'city': data['name'],
            'temp': round(data['main']['temp']),
            'feels_like': round(data['main']['feels_like']),
            # 'condition': data['weather'][0]['main'],
            # 'description': data['weather'][0]['description'].title(),
            'humidity': f"{data['main']['humidity']}%",
            'wind_kmh': f"{round(data['wind']['speed'] * 3.6)} km/h",
            'min_temp': round(data['main']['temp_min']),
            'max_temp': round(data['main']['temp_max']),
            'icon': data['weather'][0]['icon'],
            'sunrise': sunrise.strftime('%I:%M %p'),
            'sunset': sunset.strftime('%I:%M %p'),
        }

    except Exception as e:
        print(f"Error fetching today's weather: {e}")
        today_data = None

    temp, weather_type = predict(lat, lon)
    month = datetime.now()
    
    def get_season(month):
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'summer'
        elif month in [6, 7, 8, 9]:
            return 'monsoon'
        else:
            return 'post-monsoon/winter'
        
    season = get_season(month.month)
    
    # Generate smart suggestions using Gemini API
    smart_suggestions = None
    if today_data:
        smart_suggestions = get_weather_suggestions(today_data, season, temp, weather_type)

    return render(request, 'myapp/today.html', {
        'today_data': today_data,
        "city_key": city_key,
        "pred_temp": temp,
        "pred_weather_type": weather_type,
        "season": season,
        "suggestions": smart_suggestions
    })


def get_weather_suggestions(weather_data, season, pred_temp, pred_weather):

    today = date.today()
    city = weather_data['city'].lower().strip()

    # Step 1 → Check if today’s suggestion exists for this city
    try:
        record = SmartSuggestion.objects.get(city=city, date=today)
        return {
            'clothing': record.clothing,
            'activities': record.activities,
            'health': record.health,
            'travel': record.travel
        }
    except SmartSuggestion.DoesNotExist:
        pass

    # Step 2 → Call Gemini API because no stored record
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    if not GEMINI_API_KEY:
        return {
            'clothing': 'Configure Gemini API key to get suggestions',
            'activities': '',
            'health': '',
            'travel': ''
        }

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""Based on the following weather conditions, provide brief, practical suggestions (max 2 lines each) suitable for Gujarat, India:

Current Weather:
- City: {weather_data['city']}
- Temperature: {weather_data['temp']}°C (Feels like: {weather_data['feels_like']}°C)
- Humidity: {weather_data['humidity']}
- Wind: {weather_data['wind_kmh']} km/h
- Range: {weather_data['min_temp']}°C to {weather_data['max_temp']}°C
- Season: {season}
- Predicted Temperature: {pred_temp}°C
- Predicted Weather: {pred_weather}

Provide EXACTLY 4 suggestions in this format:
CLOTHING: text
ACTIVITIES: text
HEALTH: text
TRAVEL: text
"""

        response = model.generate_content(prompt)
        text = response.text.strip()

        result = {'clothing': '', 'activities': '', 'health': '', 'travel': ''}
        category = None

        for line in text.split("\n"):
            line = line.strip()

            if line.startswith("CLOTHING:"):
                category = "clothing"
                result[category] = line.replace("CLOTHING:", "").strip()
            elif line.startswith("ACTIVITIES:"):
                category = "activities"
                result[category] = line.replace("ACTIVITIES:", "").strip()
            elif line.startswith("HEALTH:"):
                category = "health"
                result[category] = line.replace("HEALTH:", "").strip()
            elif line.startswith("TRAVEL:"):
                category = "travel"
                result[category] = line.replace("TRAVEL:", "").strip()
            elif category:
                result[category] += " " + line

        # Step 3 → Save new suggestions (minimal DB store)
        SmartSuggestion.objects.create(
            city=city,
            date=today,
            clothing=result['clothing'],
            activities=result['activities'],
            health=result['health'],
            travel=result['travel']
        )

        return result

    except Exception as e:
        print("Gemini Suggestion Error:", e)
        return {
            'clothing': 'Unable to generate suggestions',
            'activities': '',
            'health': '',
            'travel': ''
        }





def hourly_view(request):
    if "city" in request.GET:
        request.session["selected_city"] = request.GET["city"]
    city_key = request.session.get("selected_city", "ahmedabad")
    lat, lon = CITY_COORDS.get(city_key, CITY_COORDS["ahmedabad"])
    url = f'https://api.openweathermap.org/data/2.5/forecast/hourly?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()

        hourly_data = []
        for item in data.get('list', [])[:24]:
            dt_utc = datetime.utcfromtimestamp(item['dt'])
            ist_time = dt_utc + timedelta(hours=5)
            hourly_data.append({
                'time': ist_time.strftime('%I:%M %p'),
                'temp_c': round(item['main']['temp']),
                'condition': item['weather'][0]['main'],
                'humidity': f"{item['main']['humidity']}%",
                'wind_kmh': f"{round(item['wind']['speed'] * 3.6)} km/h"
            })

    except Exception as e:
        print(f"Error fetching hourly forecast: {e}")
        hourly_data = []

    return render(request, 'myapp/hourly.html', {'hourly_data': hourly_data,"city_key": city_key,})


def tenday_view(request):
    if "city" in request.GET:
        request.session["selected_city"] = request.GET["city"]
    city_key = request.session.get("selected_city", "ahmedabad")
    lat, lon = CITY_COORDS.get(city_key, CITY_COORDS["ahmedabad"])
    url = f'https://api.openweathermap.org/data/2.5/forecast/daily?lat={lat}&lon={lon}&cnt=10&appid={OPENWEATHER_API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()

        forecast_data = []
        for day in data.get('list', []):
            dt = datetime.utcfromtimestamp(day['dt']) + timedelta(hours=5, minutes=30)
            forecast_data.append({
                'date': dt.strftime('%B %d'),
                'high_low': f"{round(day['temp']['max'])}° / {round(day['temp']['min'])}°",
                'condition': day['weather'][0]['main'],
                'precip': f"{int(day.get('pop', 0) * 100)}%" if 'pop' in day else "0%",
                'wind': f"{round(day['speed'] * 3.6)} km/h"
            })

    except Exception as e:
        print(f"Error fetching 10-day forecast: {e}")
        forecast_data = []

    return render(request, 'myapp/10day.html', {'forecast_data': forecast_data,"city_key": city_key,})


def monthly_view(request):
    # keep selected city across pages
    if "city" in request.GET:
        request.session["selected_city"] = request.GET["city"]

    city_key = request.session.get("selected_city", "ahmedabad")
    lat, lon = CITY_COORDS.get(city_key, CITY_COORDS["ahmedabad"])

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=30)

    # EXISTING DATES ONLY FOR THIS lat/lon
    existing_dates = set(
        MonthlyWeather.objects.filter(
            lat=lat, lon=lon,
            date__gte=start_date
        ).values_list("date", flat=True)
    )

    # FIND MISSING DATES
    missing_dates = [
        start_date + timedelta(days=i)
        for i in range(30)
        if (start_date + timedelta(days=i)) not in existing_dates
    ]

    # FETCH MISSING DATES FROM API
    for date in missing_dates:
        start_unix = int(datetime.combine(date, datetime.min.time()).timestamp())
        end_unix = int(datetime.combine(date, datetime.max.time()).timestamp())

        url = (
            f"https://history.openweathermap.org/data/2.5/history/city"
            f"?lat={lat}&lon={lon}&type=hour"
            f"&start={start_unix}&end={end_unix}"
            f"&units=metric&appid={OPENWEATHER_API_KEY}"
        )

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            temps = [entry["main"]["temp"] for entry in data.get("list", [])]

            if temps:
                MonthlyWeather.objects.create(
                    lat=lat,
                    lon=lon,
                    date=date,
                    avg_temp=round(sum(temps) / len(temps), 1)
                )
        except:
            pass

    # GET FINAL 30-DAY DATA
    entries = MonthlyWeather.objects.filter(
        lat=lat, lon=lon,
        date__gte=start_date
    ).order_by("date")

    result = []
    for entry in entries:
        result.append({
            "label": entry.date.strftime("%d %b").lstrip("0"),
            "temp": f"{entry.avg_temp}°C"
        })

    return render(request, "myapp/monthly.html", {
        "result": result,
        "city_key": city_key,  # for dropdown display only
    })




# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Allowed image extensions and max file size
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 10 MB in bytes


def validate_image_file(file):
    # Check file extension
    file_name = file.name.lower()
    file_ext = os.path.splitext(file_name)[1]
    
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Only image files are allowed ({', '.join(ALLOWED_EXTENSIONS)})"
    
    # Check file size
    file_size = file.size
    if file_size > MAX_FILE_SIZE_BYTES:
        file_size_mb = file_size / (1024 * 1024)
        return False, f"File size ({file_size_mb:.2f} MB) exceeds the maximum limit of {MAX_FILE_SIZE_MB} MB"
    
    return True, None


def analyze_weather_from_image(image_data, content_type):

    try:
        # Initialize Gemini model with vision capabilities
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Create image part for Gemini API
        image_part = {
            'mime_type': content_type,
            'data': image_data
        }
        
        # Create a detailed prompt for comprehensive weather analysis
        prompt = """Analyze this image carefully and provide a detailed weather forecast.

STEP 1: Determine if this image contains a clear sky view (clouds, atmosphere, weather conditions visible).

STEP 2: If sky is detected, provide a comprehensive weather analysis with the following details:

Format your response EXACTLY as follows:

SKY_DETECTED: [YES/NO]

If YES, provide:
WEATHER_CONDITION: [Clear Sky/Partly Cloudy/Cloudy/Overcast/Rainy/Stormy/Foggy/Hazy]
CLOUD_COVERAGE: [0-100]% 
CLOUD_TYPE: [Cumulus/Stratus/Cirrus/Nimbus/Mixed/None]
CLOUD_DARKNESS: [Light/Medium/Dark/Very Dark]
CLOUD_INTENSITY: [Thin/Moderate/Thick/Dense]
RAIN_PROBABILITY: [0-100]%
APPROXIMATE_TEMP: [Temperature range in Celsius]
VISIBILITY: [Excellent/Good/Moderate/Poor]
ATMOSPHERIC_CONDITIONS: [Clear/Hazy/Dewy/Misty/Humid/Dry]
WIND_INDICATION: [Calm/Light Breeze/Moderate/Strong - based on cloud movement]
TIME_OF_DAY: [Dawn/Morning/Afternoon/Evening/Dusk/Night]
WEATHER_FORECAST: [Brief forecast description]
DETAILS: [Detailed explanation of observations]

If NO sky detected:
REASON: [Brief explanation]

Be specific and analytical in your observations."""

        # Generate content with both image and text prompt
        response = model.generate_content([prompt, image_part])
        
        # Parse the response
        response_text = response.text.strip()
        
        # Extract information from structured response
        result = {
            'is_sky': False,
            'weather_condition': None,
            'cloud_coverage': None,
            'cloud_type': None,
            'cloud_darkness': None,
            'cloud_intensity': None,
            'rain_probability': None,
            'approximate_temp': None,
            'visibility': None,
            'atmospheric_conditions': None,
            'wind_indication': None,
            'time_of_day': None,
            'weather_forecast': None,
            'details': None,
            'reason': None,
            'raw_response': response_text
        }
        
        # Parse structured response
        lines = response_text.split('\n')
        for line in lines:
            line_upper = line.upper()
            if 'SKY_DETECTED:' in line_upper:
                result['is_sky'] = 'YES' in line_upper
            elif 'WEATHER_CONDITION:' in line_upper and result['is_sky']:
                result['weather_condition'] = line.split(':', 1)[1].strip()
            elif 'CLOUD_COVERAGE:' in line_upper and result['is_sky']:
                result['cloud_coverage'] = line.split(':', 1)[1].strip()
            elif 'CLOUD_TYPE:' in line_upper and result['is_sky']:
                result['cloud_type'] = line.split(':', 1)[1].strip()
            elif 'CLOUD_DARKNESS:' in line_upper and result['is_sky']:
                result['cloud_darkness'] = line.split(':', 1)[1].strip()
            elif 'CLOUD_INTENSITY:' in line_upper and result['is_sky']:
                result['cloud_intensity'] = line.split(':', 1)[1].strip()
            elif 'RAIN_PROBABILITY:' in line_upper and result['is_sky']:
                result['rain_probability'] = line.split(':', 1)[1].strip()
            elif 'APPROXIMATE_TEMP:' in line_upper and result['is_sky']:
                result['approximate_temp'] = line.split(':', 1)[1].strip()
            elif 'VISIBILITY:' in line_upper and result['is_sky']:
                result['visibility'] = line.split(':', 1)[1].strip()
            elif 'ATMOSPHERIC_CONDITIONS:' in line_upper and result['is_sky']:
                result['atmospheric_conditions'] = line.split(':', 1)[1].strip()
            elif 'WIND_INDICATION:' in line_upper and result['is_sky']:
                result['wind_indication'] = line.split(':', 1)[1].strip()
            elif 'TIME_OF_DAY:' in line_upper and result['is_sky']:
                result['time_of_day'] = line.split(':', 1)[1].strip()
            elif 'WEATHER_FORECAST:' in line_upper and result['is_sky']:
                result['weather_forecast'] = line.split(':', 1)[1].strip()
            elif 'DETAILS:' in line_upper and result['is_sky']:
                result['details'] = line.split(':', 1)[1].strip()
            elif 'REASON:' in line_upper and not result['is_sky']:
                result['reason'] = line.split(':', 1)[1].strip()
        
        return result
        
    except Exception as e:
        return {
            'is_sky': False,
            'error': str(e),
            'reason': f'Error analyzing image: {str(e)}'
        }


def image_view(request):
   
    TEMP_IMAGES = {}
    caption = None
    image_base64 = None
    weather_info = None
    error_message = None
    user_key = str(request.session.session_key or request.META.get('REMOTE_ADDR'))

    # Clear memory if page is refreshed (GET request)
    if request.method == 'GET':
        TEMP_IMAGES.pop(user_key, None)

    if request.method == 'POST' and request.FILES.get('image'):
        image_file = request.FILES['image']

        # Validate the uploaded file
        is_valid, validation_error = validate_image_file(image_file)
        
        if not is_valid:
            error_message = validation_error
        elif isinstance(image_file, InMemoryUploadedFile):
            # Read image data
            image_data = image_file.read()
            
            # Convert to Base64 for HTML rendering
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_base64 = f"data:{image_file.content_type};base64,{image_base64}"

            # Save in dictionary with user-specific key
            TEMP_IMAGES[user_key] = {
                'filename': image_file.name,
                'content_type': image_file.content_type,
                'data': image_base64
            }

            # Analyze image using Gemini API
            weather_info = analyze_weather_from_image(image_data, image_file.content_type)
            
            # Generate caption based on analysis
            if weather_info.get('is_sky'):
                # Sky detected - show full weather forecast
                caption = "Weather Analysis Complete"
            else:
                # No sky detected - show only alert
                caption = None
                error_message = weather_info.get('reason', 'No sky detected in the image. Please upload an image with a clear view of the sky.')
                weather_info = None  # Don't show weather info

    # Retrieve if already uploaded
    if user_key in TEMP_IMAGES:
        image_base64 = TEMP_IMAGES[user_key]['data']

    return render(request, 'myapp/image.html', {
        'caption': caption,
        'image_base64': image_base64,
        'weather_info': weather_info,
        'error_message': error_message
    })
