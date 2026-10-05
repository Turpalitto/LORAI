import logging, sys
def get_logger(name: str = "lorai"):
    l = logging.getLogger(name)
    if not l.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        l.addHandler(h); l.setLevel(logging.INFO)
    return l
log = get_logger()
