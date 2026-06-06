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


STOP_WORDS_DEL = {
    "اهنگ",
    "آهنگ",
    "موزیک",
    "ترانه",
    "دانلود",
    "song",
    "music",
    "download",
    "Download",
    "ریمیکس"
}


def remove_stop_words(text: str) -> str:
    words = text.split()
    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]
    return " ".join(cleaned_words)


def remove_stop_words_del(text: str) -> str:
    words = text.split()
    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS_DEL
    ]
    return " ".join(cleaned_words)



    


