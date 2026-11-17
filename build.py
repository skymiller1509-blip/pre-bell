#!/usr/bin/env python3
"""Build index.html from index.template.html + real_data.json.
Run after fetch_real.py:  python3 fetch_real.py && python3 build.py
"""
import json

data = json.load(open("/home/hatch/workspace/hackathons/base-prebell/real_data.json"))
tpl = open("/home/hatch/workspace/hackathons/base-prebell/index.template.html").read()
assert "__SNAPSHOT_JSON__" in tpl
html = tpl.replace("__SNAPSHOT_JSON__", json.dumps(data, separators=(",", ":")))
open("/home/hatch/workspace/hackathons/base-prebell/index.html", "w").write(html)
print("built index.html,", len(html), "bytes, snapshot", data["fetched_at_utc"])
