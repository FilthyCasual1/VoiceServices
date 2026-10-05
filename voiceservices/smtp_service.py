"""Core supervisor; worker implementation comes from an installed addon file."""
import argparse,json,time
from .core import Store
from .modules import Modules

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    with open(args.config) as source: config=json.load(source)
    modules=Modules(Store(config['database']),config=config)
    while True:
        if modules.installed('smtp-notifications'):
            modules.load('smtp-notifications').worker_main()
            return  # OpenRC restarts the supervisor with its original privileges.
        time.sleep(.5)

if __name__=='__main__': main()
