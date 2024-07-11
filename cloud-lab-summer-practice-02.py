import os
import json
import requests
import datetime


FUNC_RESPONSE = {
    'statusCode': 200,
    'body': ''
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# TELEGRAM_FILE_API_URL/<file_path>
TELEGRAM_FILE_API_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

OPEN_WEATHER_TOKEN = os.environ.get("OPEN_WEATHER_TOKEN")
OPEN_WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

OPEN_WEATHER_DEFAULT_PARAMS = {
    "appid": OPEN_WEATHER_TOKEN,
    "lang": "ru",
    "units": "metric"
}

BOT_COMMANDS = ['/start', '/help']

NORTH_MIN, NORTH_MAX = 0, 22.5
NORTH_WRAP_MIN, NORTH_WRAP_MAX = 337.5, 360
NORTH_EAST_MIN, NORTH_EAST_MAX = 22.5, 67.5
EAST_MIN, EAST_MAX = 67.5, 112.5
SOUTH_EAST_MIN, SOUTH_EAST_MAX = 112.5, 157.5
SOUTH_MIN, SOUTH_MAX = 157.5, 202.5
SOUTH_WEST_MIN, SOUTH_WEST_MAX = 202.5, 247.5
WEST_MIN, WEST_MAX = 247.5, 292.5
NORTH_WEST_MIN, NORTH_WEST_MAX = 292.5, 337.5

OTHER_TEXT_TYPE_SAMPLE = """Я не могу ответить на такой тип сообщения.
Но могу ответить на:
- Текстовое сообщение с названием населенного пункта.
- Голосовое сообщение с названием населенного пункта.
- Сообщение с геопозицией."""

START_TEXT_SAMPLE = '''Я расскажу о текущей погоде для населенного пункта.

Я могу ответить на:
- Текстовое сообщение с названием населенного пункта.
- Голосовое сообщение с названием населенного пункта.
- Сообщение с геопозицией.'''


def send_message(text, message):
    message_id = message['message_id']
    chat_id = message['chat']['id']
    reply_message = {'chat_id': chat_id,
                     'text': text,
                     'reply_to_message_id': message_id}

    requests.post(url=f'{TELEGRAM_API_URL}/sendMessage', json=reply_message)


def wind_direction(deg):
    directions = {
        "С": lambda d: (NORTH_MIN <= d <= NORTH_MAX) or (NORTH_WRAP_MIN < d <= NORTH_WRAP_MAX),
        "СВ": lambda d: NORTH_EAST_MIN < d <= NORTH_EAST_MAX,
        "В": lambda d: EAST_MIN < d <= EAST_MAX,
        "ЮВ": lambda d: SOUTH_EAST_MIN < d <= SOUTH_EAST_MAX,
        "Ю": lambda d: SOUTH_MIN < d <= SOUTH_MAX,
        "ЮЗ": lambda d: SOUTH_WEST_MIN < d <= SOUTH_WEST_MAX,
        "З": lambda d: WEST_MIN < d <= WEST_MAX,
        "СЗ": lambda d: NORTH_WEST_MIN < d <= NORTH_WEST_MAX
    }

    for direction, condition in directions.items():
        if condition(deg):
            return direction
    return None


def convert_unix_to_msk(unix_time):
    utc = datetime.datetime.utcfromtimestamp(unix_time)
    msk_offset = datetime.timedelta(hours=3)
    moscow_time = utc + msk_offset
    return moscow_time.strftime('%H:%M:%S')


def form_weather_answer(w_resp):
    return "\n".join([
        f"{w_resp['weather'][0]['description']}.",
        f"Температура {w_resp['main']['temp']} ℃, ощущается как {w_resp['main']['feels_like']} ℃.",
        f"Атмосферное давление {w_resp['main']['pressure']} мм рт. ст.",
        f"Влажность {w_resp['main']['humidity']} %.",
        f"Видимость {w_resp['visibility']} метров.",
        f"Ветер {w_resp['wind']['speed']} м/с {wind_direction(w_resp['wind']['deg'])}.",
        f"Восход солнца {convert_unix_to_msk(w_resp['sys']['sunrise'])} МСК. Закат {convert_unix_to_msk(w_resp['sys']['sunset'])} МСК."
    ])


def handle_location(message_in):
    params = {
        "lat": message_in["location"]["latitude"],
        "lon": message_in["location"]["longitude"]
    }
    params = OPEN_WEATHER_DEFAULT_PARAMS | params

    w_resp = requests.get(url=OPEN_WEATHER_API_URL, params=params).json()

    if (w_resp["cod"] == 200):
        text = form_weather_answer(w_resp)
        send_message(text, message_in)
    else:
        send_message("Я не знаю какая погода в этом месте.", message_in)



def handle_text_message(message):
    params = {
        "q": message['text']
    }
    params = OPEN_WEATHER_DEFAULT_PARAMS | params

    w_resp = requests.get(url=OPEN_WEATHER_API_URL, params=params).json()

    if (w_resp["cod"] == 200):
        text = form_weather_answer(w_resp)
        send_message(text, message)
    else:
        send_message(f"Я не нашел населенный пункт \"{message['text']}\"", message)


def handle_voice(message_in, context):
    voice = message_in["voice"]

    if voice['duration'] > 30:
        send_message("Я не могу обработать это голосовое сообщение.", message_in)
        return

    file_id = voice['file_id']
    file_response = requests.post(url=f"{TELEGRAM_API_URL}/getFile", params={"file_id": file_id}).json()

    if 'result' not in file_response:
        send_message("Не удалось получить голосовое сообщение", message_in)
        return

    voice_file = file_response["result"]
    file_path = voice_file["file_path"]

    voice_content = requests.get(f"{TELEGRAM_FILE_API_URL}/{file_path}").content
    token = context.token['access_token']

    yc_auth = {"Authorization": f"Bearer {token}"}
    yc_url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

    yc_resp = requests.post(url=yc_url, headers=yc_auth, data=voice_content).json()

    if "result" not in yc_resp:
        send_message("Не удалось распознать голосовое сообщение", message_in)
        return

    params = {
        "q": yc_resp["result"]
    }
    params = OPEN_WEATHER_DEFAULT_PARAMS | params

    w_resp = requests.get(url=OPEN_WEATHER_API_URL, params=params).json()

    if (w_resp["cod"] == 200):
        text = f"""Населенный пункт {yc_resp["result"]}.
{w_resp['weather'][0]['description']}.
Температура {round(w_resp['main']['temp'])} градусов цельсия.
Ощущается как {round(w_resp['main']['feels_like'])} градусов цельсия.
Давление {round(w_resp['main']['pressure'])} миллиметров ртутного столба.
Влажность {round(w_resp['main']['humidity'])} процентов."""
        send_message(text, message_in)
    else:
        send_message(f"Я не нашел населенный пункт \"{yc_resp["result"]}\"", message)



def handler(event, context):
    if TELEGRAM_BOT_TOKEN is None:
        return FUNC_RESPONSE

    update = json.loads(event['body'])

    if 'message' not in update:
        return FUNC_RESPONSE

    message_in = update['message']

    if 'text' in message_in:

        if 'entities' in message_in:
            entities = message_in['entities']
            for entity in entities:
                if "bot_command" in entity.get('type'):
                    if message_in['text'] in BOT_COMMANDS:
                        send_message(START_TEXT_SAMPLE, message_in)
                        return FUNC_RESPONSE


        handle_text_message(message_in)
    elif 'location' in message_in:
        handle_location(message_in)
    elif 'voice' in message_in:
        handle_voice(message_in, context)
    else:
        send_message(OTHER_TEXT_TYPE_SAMPLE, message_in)

    return FUNC_RESPONSE