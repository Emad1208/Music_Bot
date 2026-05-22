from .musicsweb import process_search_query_musicsweb
from .upmusic import process_search_query_upmusics
from .gisomusic import process_search_query_gisomusic


async def process_search_query(song, 
        process_search_query_musicsweb = process_search_query_musicsweb,
        process_search_query_upmusics = process_search_query_upmusics,
        process_search_query_gisomusic = process_search_query_gisomusic
                  ):
    musics_web = await process_search_query_musicsweb(song)
    upmusics = await process_search_query_upmusics(song)
    gisomusic = await process_search_query_gisomusic(song)

    if upmusics:
        return upmusics
    
    elif musics_web:
        return  musics_web
    
    elif gisomusic:
        return  gisomusic




