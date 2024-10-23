"Fetch and save gzipped tar files from an instance."

import os
import json
import sys
import requests

import utils


def fetch_and_save(url, apikey, dirpath):
    "Fetch the gzipped tar file and save to local disk."

    print(f"fetching mdbook.tgz from {url}")
    response = requests.get(url, headers=dict(apikey=apikey), stream=True)

    if response.status_code != 200:
        raise ValueError(f"invalid status code for response: {response.status_code}")
    try:
        content_disposition = response.headers["content-disposition"]
    except KeyError:
        raise ValueError("no content-disposition in response")
    parts = content_disposition.split('"')
    if len(parts) != 3:
        raise ValueError("no filename in content-disposition in response")

    filepath = os.path.join(dirpath, parts[1])
    with open(filepath, "wb") as outfile:
        outfile.write(response.raw.read())
    print(f"wrote mdbook.tgz to {filepath}")


if __name__ == "__main__":
    dirpath = sys.argv[1]
    print(dirpath)
    with open(os.path.join(dirpath, "config.json")) as infile:
        config = json.load(infile)
    fetch_and_save(config["site"].rstrip("/") + "/tgz", config["apikey"], dirpath)
