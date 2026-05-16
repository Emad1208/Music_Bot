from openai import OpenAI
from decouple import config

api_token = config('API_TOKEN')


# creat client with api token
client = OpenAI(base_url='https://api.gapgpt.app/v1', api_key=api_token)

def dedicate_singer(text):
    prompt = f"""
           تو یک دستیار تشخیص نام آهنگ و نام خواننده هستی
           - متن داده شده بهت رو اصلا تغییر نده
           - نام خواننده و نام اهنگ رو از متن تشخیص بده و به فرمت JSON بنویس
           - خروجی کار به این شکل باشد  مثال (محسن چاوشی قطار)
            dedicated = (
                'artist': 'محسن چاوشی',
                'song': 'قطار'
            )

            
            {text}
            """
    try:
        response = client.responses.create(
            model="gpt-5.3-chat-latest",
            input=prompt
        )

        return response.output_text
    except Exception as e:
        return f"An error occurred: {e}"
    
print(dedicate_singer('علیرضا طلیسچی  بارون اومد و یادم داد'))