from openai import OpenAI
from decouple import config
import json

api_token = config('API_TOKEN')


# creat client with api token
client = OpenAI(base_url='https://api.gapgpt.app/v1', api_key=api_token)

def dedicate_singer(text):
    prompt = f"""
    تو یک استخراج‌کننده اطلاعات موسیقی هستی.

    وظیفه:
    - از متن ورودی فقط نام خواننده و نام آهنگ را تشخیص بده
    - متن ورودی را تغییر نده
    - فقط و فقط یک JSON معتبر خروجی بده
    - هیچ توضیحی، هیچ متن اضافه‌ای، و هیچ markdownی ننویس

    فرمت خروجی دقیق:
    {{
    "artist": "نام خواننده",
    "song": "نام آهنگ"
    }}

    اگر نتوانستی تشخیص بدهی، مقدار مربوطه را null بگذار.

    متن ورودی:
    {text}
    """
    try:
        response = client.responses.create(
        model="gpt-5.3-chat-latest",
        input=prompt
        )
        raw_output = response.output_text
        data = json.loads(raw_output)   # تبدیل string به dict
        return data
    except Exception as e:
        return f"An error occurred: {e}"
    

# how to test
# output = dedicate_singer('علیرضا طلیسچی  بارون اومد و یادم داد')
# print(type(output))
      
# print(output)