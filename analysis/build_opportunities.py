"""Publish frozen opportunity models offline; never refit on dropdown filters."""
import argparse
import json
from backend.app.capabilities.data.opportunities import _base
from backend.app.contracts.opportunities import OpportunityFilters

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-id', required=True)
    args = parser.parse_args()
    for days in (30,60,90):
        for inferred in (True,False):
            for past_due in (False,True):
                filters = OpportunityFilters(window_days=days, include_inferred=inferred, include_past_due=past_due)
                rows, model, version = _base(args.snapshot_id, filters, allow_fit=True)
                print(json.dumps({'days': days, 'inferred': inferred, 'past_due': past_due,
                    'version': version, 'accounts': len(rows), **model['quality']}, allow_nan=False), flush=True)
if __name__ == '__main__':
    main()
