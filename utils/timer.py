import time

from contextlib import contextmanager

@contextmanager
def timer(name : str):
    start_time = time.perf_counter()
    try:
        yield   
    finally:
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        print(f"[{name}] Elapsed time: {elapsed_time:.2f} seconds")