from openai import OpenAI
from decouple import config

api_token = config('API_TOKEN')


# creat client with api token
client = OpenAI(base_url='https://api.gapgpt.app/v1', api_key=api_token)

def correct_grammar(text):
    prompt = f"""
            تو یک دستیار ویرایش متن هستی.
            وظیفه تو این است که متن ورودی را از نظر گرامر، روانی و تمیزی نهایی اصلاح کنی.
            قوانین:
            - معنای اصلی متن را تا حد ممکن حفظ کن.
            - غلط های املایی رو بگیر
            - اطلاعات جدید اضافه نکن.
            - کلمه اضافه یا کم نکن
            - علائم نگارشی اضافه نکن 
            - بیش از حد بازنویسی نکن مگر لازم باشد.
            - غلط‌های گرامری، فاصله‌ها و عبارت‌های نامأنوس را اصلاح کن.
            - اگر متن از قبل درست بود، فقط حداقل تغییر لازم را انجام بده.
            - فقط متن نهایی اصلاح‌شده را خروجی بده.
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



