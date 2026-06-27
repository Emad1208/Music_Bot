from Platform.Bale import bot_run
from utils.priority_artists import load_special_artists

if __name__ == "__main__":
    load_special_artists("singers.json")
    bot_run()