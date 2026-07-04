from db_Project.db import Database
from .word_db_scrape import WordDatabase



db = Database('db_music_Bot.db')
db.create_tables()

word_db = WordDatabase('music_words.db')
word_db.create_tables()