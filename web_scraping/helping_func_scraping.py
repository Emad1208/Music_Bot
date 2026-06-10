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


def remove_stop_words_del(text: str) -> str:
    if "ریمیکس" in text:
        text = text.replace("ریمیکس", "")
    words = text.split()
    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]
    return " ".join(cleaned_words)


def remove_stop_words_beh(text):
    if "با نام" in text:
        text = text.replace("با نام", "")
    if "شنیدنی" in text:
        text = text.replace("شنیدنی", "")
    if "به نام" in text:
        text = text.replace("به نام", "")

    words = text.split()

    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]

    return " ".join(cleaned_words)


    


