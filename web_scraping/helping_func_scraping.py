STOP_WORDS = {
    "اهنگ",
    "آهنگ",
    "موزیک",
    "ترانه",
    "دانلود",
    "song",
    "music",
    "download",
    "Download"
}


def remove_stop_words(text: str) -> str:
    words = text.split()
    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]
    return " ".join(cleaned_words)

STOP_PHRASES_DEL = (
    'ریمیکس',
    'از',
)
def remove_stop_words_del(text: str) -> str:
    for phrase in STOP_PHRASES_DEL:
        text = text.replace(phrase, "")

    words = text.split()
    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]
    return " ".join(cleaned_words)


STOP_PHRASES_BEH = (
    "جدید",
    "متن",
    "با نام",
    "شنیدنی",
    "به نام",
    "از",
)

def remove_stop_words_beh(text):
    for phrase in STOP_PHRASES_BEH:
        text = text.replace(phrase, "")

    return " ".join(
        word for word in text.split()
        if word not in STOP_WORDS
    )

    


