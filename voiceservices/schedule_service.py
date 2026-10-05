"""Unprivileged scheduler for the host's existing approved update provider."""
import argparse,json,logging,time
from .web import App
from . import update_schedule
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    with open(args.config) as f: app=App(json.load(f))
    while True:
        try: update_schedule.tick(app)
        except (ValueError,OSError) as exc: logging.warning('Update scheduler unavailable: %s',exc)
        time.sleep(10)
if __name__=='__main__': main()
